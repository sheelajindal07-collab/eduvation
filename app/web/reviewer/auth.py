"""GET/POST /reviewer/sign-in, POST /reviewer/sign-out — the cookie-based
session authentication for the reviewer console.

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

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.api.auth import authenticate
from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.core.csrf import require_same_origin
from app.db import get_anon_client, get_user_scoped_client
from app.web.templating import templates

router = APIRouter(prefix="/reviewer", tags=["reviewer-console"], include_in_schema=False)
# I18N-1: this module used to construct its own `Jinja2Templates`, a
# second Jinja environment independent of the student screens' one. Any
# global or filter registered on one was silently absent on the other.
# There is now exactly one environment, in app/web/templating.py, and
# this router shares it — this module's deliberate separation from
# app/web/pages.py (see the docstring above) is about ROUTES and the
# session mechanism, never about having a private template environment.

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

require_reviewer_origin = require_same_origin(COOKIE_NAME)
"""SEC-2's CSRF dependency, bound to this console's session cookie.

Built once here and applied by every state-changing reviewer route --
this module's own sign-in POST below and all three action routes in
queue.py -- so there is exactly one object to point at when asking "what
protects the console's forms". `app/core/csrf.py` owns the rule itself
(Origin, falling back to Referer, matched against
`Settings.allowed_hosts_list`; a cookie-bearing POST with neither header
is refused); a future student-session cookie builds its own instance from
the same factory rather than copying any of it.

It is a no-op for a request that carries no session cookie, which is
exactly what makes it safe on the sign-in POST -- see that route's
docstring.
"""


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


@router.get("/sign-in")
def reviewer_sign_in_form(request: Request) -> Any:
    return templates.TemplateResponse(request, "reviewer_sign_in.html", {"error": None})


@router.post("/sign-in", dependencies=[Depends(require_reviewer_origin)])
def reviewer_sign_in_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> Any:
    """SEC-2 note before anything else: the CSRF dependency above is
    attached here but is a deliberate NO-OP for an ordinary sign-in. The
    browser posting this form has not been issued `COOKIE_NAME` yet --
    this request is what creates it -- and `require_same_origin` only
    guards requests that ALREADY carry the cookie. Gating the login form
    on an `Origin` header would lock a reviewer out of signing in from a
    client that omits one, which is a far worse failure than the "login
    CSRF" it would prevent (docs/SECURITY.md records that residual risk
    as accepted). What the dependency DOES cover here: an already-signed-
    in session re-posting this form, which is a cookie-bearing state
    change like any other.

    Reuses `app/api/auth.py`'s `authenticate()` — the one place this
    app calls Supabase's own `sign_in_with_password` — rather than
    reimplementing the call here. On success, sets the session cookie
    and redirects (303, so the browser re-requests /reviewer/queue with
    GET, not a resubmitted POST) to /reviewer/queue. On failure,
    re-renders this same form with the identical anti-enumeration
    wording `authenticate()` already uses ("never reveal whether the
    email exists") — never a distinguishable error for a bad email vs. a
    bad password.
    """
    # UI-review finding, 2026-09-21 (HIGH, FIX 3): DB unavailable handling
    try:
        client = get_anon_client()
    except Exception:
        return templates.TemplateResponse(
            request,
            "reviewer_sign_in.html",
            {"error": "The review system isn't available right now -- please try again shortly."},
            status_code=503,
        )
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
            # the FIRST CSRF defense for the zero-JS approve/reject/
            # submit forms (no separate CSRF-token mechanism is
            # practical with no client-side script to carry one).
            # SEC-2 added the second: `require_reviewer_origin` above, a
            # server-side Origin/Referer check on every cookie-bearing
            # state change, for the cases SameSite alone does not cover
            # (a client that ignores the attribute, a same-site but
            # different-host subdomain). These flags are unchanged by
            # SEC-2 -- the check was added alongside them, not instead
            # of them.
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
    """Deliberately NOT carrying SEC-2's `require_reviewer_origin` (the
    task card names the three action routes plus sign-in, and this is
    neither). A forced sign-out is the one cookie-bearing state change
    here that alters no verified data and is fully undone by signing in
    again, while gating it would strand a reviewer whose client sends
    neither header on a session they can no longer end. Flagged for the
    lead rather than decided silently -- if the console later gains any
    route whose sign-out has a side effect, this needs the guard."""
    return _redirect_to_sign_in()
