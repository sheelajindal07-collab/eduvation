"""GET/POST /reviewer/sign-in, POST /reviewer/sign-out, GET /reviewer/queue,
POST /reviewer/claims/{id}/{submit,approve,reject} — the first browser-
usable UI on top of `app/api/claims.py`'s publishing-console API
(BCI-005, fully live and tested but reachable only via curl/Postman
until now).

Kept as its own router/module, deliberately NOT merged into
`app/web/pages.py` — this is a distinct, newly-authenticated surface
with its own security-sensitive session mechanism, not another
read-only page in the guest/student journey.

## Why a new cookie-based session, scoped here only
Every route before this task read auth exactly one way: a client-
supplied `Authorization: Bearer <token>` header
(`app/api/deps.py`'s `get_db_client`/`require_auth`). That works for
curl/Postman/a JS `fetch` call, but a plain browser GET or an HTML
`<form method="post">` has no mechanism to attach a custom header — so
there was, and until this module, still is, NO way for a signed-in
browser session to exist anywhere in this app. This module adds exactly
one: a session cookie, read by `get_reviewer_session` below, which lives
ONLY in this file. `app/api/deps.py` is untouched — the JSON API and
`app/web/pages.py` still only ever look at the Authorization header,
exactly as before this task.

## How the cookie reaches app/api/claims.py's routes
Rather than a second real HTTP round-trip (the existing routes'
`Authorization: Bearer` header has no way to ride along on a plain HTML
form POST either — attaching it would need JS, defeating the zero-JS
requirement), each action route below calls straight into claims.py's
own route FUNCTIONS (`submit_claim`/`approve_claim`/`reject_claim`),
passing an `AuthedSession` built from the cookie's token — the exact
same `AuthedSession` shape `require_auth` would have built from a
literal `Authorization: Bearer <token>` header, carrying that same
token as `access_token`. Same pattern `app/web/pages.py` already
established for `assemble_comparisons()`: one code path, reused, never
duplicated or indirected through a second network hop. Any failure
(403 not-a-reviewer, 400 bad transition, 404 not found) is whatever
`HTTPException` that shared function already raises — this module adds
no separate access-control decision of its own, same "RLS is the real
enforcement" principle as every other route in this codebase.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.auth import authenticate
from app.api.claims import approve_claim, list_claims, reject_claim, submit_claim
from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.db import get_anon_client, get_user_scoped_client

router = APIRouter(prefix="/reviewer", tags=["reviewer-console"], include_in_schema=False)
templates = Jinja2Templates(directory="app/web/templates")

COOKIE_NAME = "bcion_reviewer_session"
# Scoped to this router's own paths only (belt-and-suspenders alongside
# httponly/samesite below) — a cookie set here is never sent to
# /explore, /compare/view, or any JSON API route, and none of those
# routes would read it even if it were.
COOKIE_PATH = "/reviewer"
# Supabase's own Session.expires_in (seconds) is what actually sizes the
# cookie below — this is only a fallback for the type checker's benefit,
# since expires_in is a required, non-Optional field on that model and a
# real Supabase response always sets it. A cookie must never be handed
# an unbounded lifetime as a fallback, so this stays conservative (one
# hour) rather than long-lived.
_FALLBACK_MAX_AGE_SECONDS = 3600


def get_reviewer_session(request: Request) -> Iterator[AuthedSession | None]:
    """Cookie -> `AuthedSession`, mirroring `app/api/deps.py`'s
    `require_auth` contract (same dataclass shape, same fresh-client-
    per-request, same yield+finally close so the connection pool isn't
    leaked — see that module's docstring) but reading this router's own
    session cookie instead of an Authorization header.

    Never raises: an absent OR no-longer-valid token both yield `None`,
    so every route below can turn that into a friendly redirect to
    `/reviewer/sign-in` (a human clicked a link, not an API call — same
    "explain, don't just error" reasoning `app/web/pages.py`'s
    `compare_page` already uses for a malformed link) rather than
    `require_auth`'s bare 401.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        yield None
        return
    try:
        client = get_user_scoped_client(token)
    except Exception:
        # UI-review finding, 2026-09-21 (LOW, robustness): this used to
        # construct the client BEFORE this try block, so e.g.
        # app/db/client.py's SupabaseNotConfiguredError (whose own
        # docstring says callers should catch it and degrade gracefully)
        # propagated as an unhandled 500 instead of the graceful
        # sign-in-redirect this function exists to produce everywhere
        # else. Any failure here now yields None too, same as the
        # invalid-token path below.
        yield None
        return
    try:
        try:
            user_response = client.auth.get_user(jwt=token)
        except Exception:
            user_response = None
        if user_response is None or user_response.user is None:
            yield None
        else:
            yield AuthedSession(client=client, access_token=token)
    finally:
        client.postgrest.aclose()


def _redirect_to_sign_in() -> RedirectResponse:
    response = RedirectResponse(url="/reviewer/sign-in", status_code=303)
    # Clears a stale/invalid cookie too (harmless no-op if there wasn't
    # one) so a reviewer whose token has expired isn't stuck bouncing
    # between /reviewer/queue and /reviewer/sign-in with a dead cookie.
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return response


def _redirect_to_queue_with_error(detail: object) -> RedirectResponse:
    """UI-review finding, 2026-09-21 (HIGH): the three action routes below
    used to call straight into claims.py's submit_claim/approve_claim/
    reject_claim with no error handling, so any HTTPException it raised
    (self-approval, an invalid workflow transition, or the 404 two
    reviewers racing on the same claim produces -- the normal case
    maker-checker exists for) surfaced as FastAPI's raw default JSON
    error body, with no way back to the queue. Same "explain, don't just
    error" reasoning as `app/web/pages.py`'s `compare_page` (a human
    clicked a button, they didn't send a malformed request on purpose)
    adapted to this router's POST-then-redirect shape: 303 back to the
    queue, with the failure's own detail message carried as a query
    param so `reviewer_queue_page` can show it as a visible alert instead
    of silently dropping it."""
    return RedirectResponse(url=f"/reviewer/queue?error={quote(str(detail))}", status_code=303)


@router.get("/sign-in")
def reviewer_sign_in_form(request: Request) -> Any:
    return templates.TemplateResponse(request, "reviewer_sign_in.html", {"error": None})


@router.post("/sign-in")
def reviewer_sign_in_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> Any:
    """Reuses `app/api/auth.py`'s `authenticate()` — the one place this
    app calls Supabase's own `sign_in_with_password` — rather than
    reimplementing the call here. On success, sets the session cookie
    and redirects (303, so the browser re-requests /reviewer/queue with
    GET, not a resubmitted POST) to /reviewer/queue. On failure,
    re-renders this same form with the identical anti-enumeration
    wording `authenticate()` already uses ("never reveal whether the
    email exists") — never a distinguishable error for a bad email vs. a
    bad password.
    """
    client = get_anon_client()
    try:
        try:
            session = authenticate(client, email, password)
        except HTTPException as exc:
            return templates.TemplateResponse(
                request,
                "reviewer_sign_in.html",
                {"error": exc.detail},
                status_code=exc.status_code,
            )

        settings = get_settings()
        response = RedirectResponse(url="/reviewer/queue", status_code=303)
        response.set_cookie(
            key=COOKIE_NAME,
            value=session.access_token,
            httponly=True,  # no JS access to the token, ever
            samesite="lax",  # blocks the cookie on a cross-site POST --
            # the actual CSRF defense for the zero-JS approve/reject/
            # submit forms below (no separate CSRF-token mechanism is
            # practical with no client-side script to carry one).
            secure=(settings.app_env == "production"),  # mirrors
            # app/main.py's own docs_url conditional: plain http still
            # works for local dev, only production requires https.
            max_age=session.expires_in or _FALLBACK_MAX_AGE_SECONDS,
            path=COOKIE_PATH,
        )
        return response
    finally:
        client.postgrest.aclose()


@router.post("/sign-out")
def reviewer_sign_out() -> Any:
    return _redirect_to_sign_in()


@router.get("/queue")
def reviewer_queue_page(
    request: Request,
    error: str | None = Query(default=None),
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    """Lists what needs a reviewer's attention, via the exact same
    `list_claims` function `GET /claims` (the JSON API) already calls —
    same default `["draft", "in_review"]` status filter, same RLS: a
    signed-in non-reviewer gets an empty queue here too, not an error
    (existing, intentional behaviour — see claims.py's own docstring).

    `error`, when present, is the detail message from an action route
    below that failed (see `_redirect_to_queue_with_error`) — rendered by
    the template as a visible alert, not silently dropped.
    """
    if session is None:
        return _redirect_to_sign_in()
    claims = list_claims(status=["draft", "in_review"], session=session)
    return templates.TemplateResponse(
        request, "reviewer_queue.html", {"claims": claims, "error": error}
    )


@router.post("/claims/{claim_id}/submit")
def reviewer_submit_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    try:
        submit_claim(claim_id, session=session)
    except HTTPException as exc:
        return _redirect_to_queue_with_error(exc.detail)
    return RedirectResponse(url="/reviewer/queue", status_code=303)


@router.post("/claims/{claim_id}/approve")
def reviewer_approve_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    try:
        approve_claim(claim_id, session=session)
    except HTTPException as exc:
        return _redirect_to_queue_with_error(exc.detail)
    return RedirectResponse(url="/reviewer/queue", status_code=303)


@router.post("/claims/{claim_id}/reject")
def reviewer_reject_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    try:
        reject_claim(claim_id, session=session)
    except HTTPException as exc:
        return _redirect_to_queue_with_error(exc.detail)
    return RedirectResponse(url="/reviewer/queue", status_code=303)
