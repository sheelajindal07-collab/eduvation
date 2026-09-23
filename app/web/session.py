"""`bcion_student_session` — the student-facing HTML session cookie.

Generalises `app/web/reviewer/auth.py`'s own cookie pattern (see that
module's docstring for the full "why a cookie at all" rationale, which
applies here unchanged) into a second, SEPARATE mechanism, this time for
student-facing HTML pages rather than the reviewer console.
`docs/CONTRACTS.md`'s "Error shape, sessions, guest state, flags" section
already settles this cookie's exact shape: `bcion_student_session`
(httponly, samesite=lax, secure in production, `path=/`, max-age = token
expiry) — the constants and helpers below are that settled shape, built
for real, not a new design.

## Deliberately NOT `app/api/deps.py`

`app/api/deps.py`'s `get_db_client`/`require_auth` read ONLY an
`Authorization: Bearer <token>` header — that module is untouched by
this task and stays untouched: the JSON API is Bearer-only
(`docs/CONTRACTS.md`, "The JSON API is Bearer-only; cookies belong to
the web layer alone"). A plain browser GET or a zero-JS `<form>` POST
has no way to attach a custom header, which is exactly why
`app/web/reviewer/auth.py` had to invent a cookie in the first place —
this module is the same fix, generalised for student-facing pages
instead of the reviewer console. Nothing here is wired into any route
yet (no student-facing HTML sign-in page exists yet) — this card's own
scope is the mechanism itself, not that page.

## Cross-user isolation

Exactly the same story as `get_reviewer_session`: the cookie carries a
real Supabase access token, so `client.auth.get_user(jwt=token)` and
every RLS-scoped query issued through the returned client are the real
enforcement — this module makes no ownership decision of its own, and
grants no more than the token itself already would via
`Authorization: Bearer`. Two different students' cookies (or a guest's
missing one) can never resolve to the same, or to each other's,
identity.

## Known, accepted, inherited residual risk — no revocation before expiry

The access token carried inside this cookie cannot be revoked before its
own natural expiry; this module does not attempt that, and building
revocation is out of this card's scope. The existing mitigation (a
short-lived Supabase JWT, already the default everywhere else in this
codebase, e.g. `app/web/reviewer/auth.py`'s own cookie) is what keeps
that window small — inherited here, not re-invented.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from supabase_auth.types import Session

from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.db import get_user_scoped_client

COOKIE_NAME = "bcion_student_session"
# Unlike app/web/reviewer/auth.py's COOKIE_PATH ("/reviewer" only, since
# that console is a distinct, separately-authenticated surface), this
# cookie is scoped to the whole app: student-facing pages live all over
# (/explore, /compare/view, /plans/view once it exists, ...), not under
# one path prefix.
COOKIE_PATH = "/"

# Same conservative fallback as app/web/reviewer/auth.py's own
# _FALLBACK_MAX_AGE_SECONDS, for the same reason: Session.expires_in is a
# required, non-Optional field on a real Supabase response, so this only
# ever matters to the type checker, never in practice. A cookie must
# never be handed an unbounded lifetime as a fallback.
FALLBACK_MAX_AGE_SECONDS = 3600

SESSION_ENDED_NOTICE = "session_ended"
"""A stable, non-free-text code carried by `session_ended_redirect`
below — same convention as `app/web/reviewer/queue.py`'s
`QUEUE_ERROR_MESSAGES` dict (a code in the query string, never reflected
prose), so whichever future sign-in page reads `?notice=` can render
its own "your session ended" copy without this module needing to know
that page's template or i18n key. No Phase 1 refresh token exists
(`docs/CONTRACTS.md`: "No refresh token in Phase 1: expiry means
re-sign-in behind a 'your session ended' notice") — this is that notice,
generalised out of the cookie mechanism itself so any caller (an expired
cookie, a garbage one, or an explicit sign-out this card doesn't build
yet) can raise it identically."""


def get_student_session(request: Request) -> Iterator[AuthedSession | None]:
    """Cookie -> `AuthedSession`, mirroring `app/web/reviewer/auth.py`'s
    `get_reviewer_session` contract exactly (same dataclass shape, same
    fresh-client-per-request, same yield+finally close so the connection
    pool isn't leaked — see that module's docstring) but reading this
    module's own `bcion_student_session` cookie instead.

    Never raises: an absent, garbage or (once Supabase itself rejects an
    expired token, exactly as it does an invalid one) expired cookie all
    yield `None` — a caller turns that into `session_ended_redirect`
    below, the same way every `app/web/reviewer/auth.py` route turns a
    `None` from `get_reviewer_session` into `_redirect_to_sign_in`.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        yield None
        return
    try:
        client = get_user_scoped_client(token)
    except Exception:
        # Same reasoning as get_reviewer_session's own try/except: a
        # construction-time failure (e.g. SupabaseNotConfiguredError,
        # whose own docstring asks callers to catch it and degrade
        # gracefully) must degrade the same way an invalid token does,
        # never propagate as an unhandled 500.
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


def session_ended_redirect(url: str = "/") -> Response:
    """A 303 redirect to `url` (default: the landing page — no
    student-facing sign-in page exists yet for this card to point at
    instead) carrying `SESSION_ENDED_NOTICE`, and clearing a stale/
    invalid cookie — same "harmless no-op if there wasn't one" reasoning
    as `app/web/reviewer/auth.py`'s `_redirect_to_sign_in`.

    Runs the result through `no_store` below: a redirect telling a
    browser its session just ended must never itself be cached and
    replayed to somebody else on a shared device (docs/PRODUCT.md).
    """
    response = RedirectResponse(url=f"{url}?notice={SESSION_ENDED_NOTICE}", status_code=303)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return no_store(response)


def no_store(response: Response) -> Response:
    """Explicitly mark `response` `Cache-Control: no-store`.

    Belt-and-suspenders, not a substitute: `app/web/cache_policy.py`'s
    `CachePolicyMiddleware` already forces `no-store` on every response
    to a cookie-bearing request in the real, fully-assembled app,
    regardless of what any individual route sets. This helper exists for
    the caller that wants the guarantee to hold even outside that full
    middleware stack (e.g. a route exercised in isolation, or this
    module's own `session_ended_redirect`, whose whole purpose is a
    stale-session bounce that must never be served from a shared cache)
    — not because the middleware needs help in the real, running app.
    """
    response.headers["Cache-Control"] = "no-store"
    return response


def set_student_session_cookie(response: Response, session: Session) -> Response:
    """Set `bcion_student_session` with `docs/CONTRACTS.md`'s exact
    settled flags, generalising `app/web/reviewer/auth.py`'s own
    `reviewer_sign_in_submit` cookie-setting code (see that route for the
    line-by-line reasoning behind each flag — httponly, samesite=lax,
    secure only in production, sized to the token's own real lifetime —
    all unchanged here) so that whichever future student sign-in route
    is built sets this cookie the exact same well-reviewed way, rather
    than duplicating that logic. Not called by any route yet — no
    student-facing HTML sign-in page exists; this card's own scope is
    the mechanism, not that page.
    """
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=session.access_token,
        httponly=True,  # no JS access to the token, ever
        samesite="lax",  # first CSRF defense for a future zero-JS form,
        # same reasoning as app/web/reviewer/auth.py's own cookie
        secure=(settings.app_env == "production"),  # plain http still
        # works for local dev, only production requires https — mirrors
        # app/web/reviewer/auth.py's identical conditional
        max_age=session.expires_in or FALLBACK_MAX_AGE_SECONDS,
        path=COOKIE_PATH,
    )
    return response
