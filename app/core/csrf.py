"""SEC-2 — CSRF protection for cookie-authenticated, state-changing
requests: an `Origin` check with a `Referer` fallback, expressed as a
reusable FastAPI dependency.

## Why an Origin check and not a CSRF token

`app/web/reviewer/auth.py`'s cookie-setting comment already states the
constraint: the reviewer console's approve / reject / submit forms are
plain, zero-JS `<form method="post">` elements. There is no client-side
script to carry a per-session CSRF token into a hidden field, and adding
one would defeat the zero-JS requirement the whole console is built to.
`SameSite=Lax` on the cookie is the first line of defence (a genuinely
cross-*site* POST does not carry the cookie at all in any browser that
honours it), and this check is the second: the server itself refuses any
cookie-bearing state-changing request whose declared origin it cannot
verify. That covers the cases SameSite alone does not — a browser that
ignores or has not yet applied the attribute, a same-site-but-different-
host subdomain, and any future relaxation of the cookie's own flags.

## The rule, exactly

A request is guarded when BOTH hold:

* its method is state-changing (`POST`/`PUT`/`PATCH`/`DELETE`), and
* it carries one of the session cookies named when the dependency was
  built.

A guarded request is rejected with `403` unless every origin-declaring
header it *does* send names a host in `Settings.allowed_hosts_list` (the
same list `TrustedHostMiddleware` uses — SEC-1/DEPLOY-18), and it sends
at least one of them:

* `Origin` present -> its host must be allowed.
* `Referer` present -> its host must be allowed too. It is the documented
  *fallback* for browsers that omit `Origin` on a same-site navigation,
  but when both headers are present both are checked rather than the
  first one winning. Two disagreeing values are not something a browser
  produces for an honest same-origin form post, so the safe reading of a
  disagreement is "reject", not "take whichever one passes".
* Neither present -> **rejected**. Fail closed, never fail open: "no
  Origin" is precisely the shape an old or stripped-down client uses,
  and treating it as trustworthy would leave the forms this exists to
  protect unprotected.
* `Origin: null` (a sandboxed iframe, some redirect chains) has no host
  and is therefore rejected by the same rule.

An UNguarded request — no cookie, or a safe method — is never inspected
and never rejected. Two consequences worth stating plainly:

* **The JSON API is untouched.** `app/api/*` routes authenticate with
  `Authorization: Bearer` only (docs/CONTRACTS.md: "the JSON API is
  Bearer-only; cookies belong to the web layer alone"), have no session
  cookie to carry, and do not attach this dependency at all. A bearer
  client is never asked for an `Origin`.
* **A sign-in POST still works from anywhere.** The request that
  *creates* a session does not yet carry the cookie, so it is not
  guarded. That is deliberate (see `app/web/reviewer/auth.py`): gating it
  would lock every reviewer out of signing in. The dependency is still
  attached there, so a request that ALREADY has a session and re-posts
  the sign-in form is checked like any other cookie-bearing POST. The
  residual exposure is "login CSRF" (an attacker silently signing a
  victim's browser in as the attacker) — documented as accepted in
  docs/SECURITY.md, not overlooked.

## Relationship to `app/main.py`'s `OriginCheckMiddleware` (SEC-1)

SEC-1 installed the same rule as ASGI middleware for the *future*
`bcion_student_session` cookie, and deliberately did not extend it to
`bcion_reviewer_session` because doing so before this task would have
broken the console's own test suite (see that class's docstring). This
module is the per-route form of the same contract, which is what a route
that must also read the session needs.

`origin_is_allowed` here is deliberately AT LEAST AS STRICT as that
middleware's `_origin_is_allowed` — never more permissive (the "both
headers must pass" rule above is the one difference, and it only ever
rejects more). `tests/unit/test_csrf.py` pins that relationship so the
two cannot silently drift apart. Folding the middleware onto this
function is a one-line follow-up for whichever task next owns
`app/main.py`; SEC-2 does not own that file.

## Adding a second cookie session later

    from app.core.csrf import require_same_origin

    require_student_origin = require_same_origin("bcion_student_session")

    @router.post("/plan/save", dependencies=[Depends(require_student_origin)])
    def save_plan(...) -> Any: ...

Build the dependency once at module level and reuse the instance; the
factory takes any number of cookie names, so one guard can cover a route
that accepts either session.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings

# docs/CONTRACTS.md's error shape: `detail` is an object, the code is the
# contract and the message is not. Same code string SEC-1's
# OriginCheckMiddleware already returns, so a client sees one stable code
# for this failure regardless of which of the two implementations
# rejected the request.
CSRF_ERROR_CODE = "origin_not_allowed"
CSRF_ERROR_MESSAGE = "This request's origin could not be verified."

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
"""Mirrors app/main.py's `_STATE_CHANGING_METHODS`. `GET`/`HEAD`/
`OPTIONS` are excluded because they are supposed to be safe; a route that
changes state on a GET is the bug, and no route in this codebase does."""

_ORIGIN_HEADERS = ("origin", "referer")
"""Checked in this order, but ALL present values must pass — see the
module docstring. `Referer` is the fallback for an absent `Origin`, not a
weaker alternative to a present one."""


def _declared_host(header_value: str) -> str | None:
    """The hostname a browser-supplied `Origin`/`Referer` declares.

    `urlsplit().hostname` is already lower-cased and strips any port and
    userinfo, so `https://Example.COM:8443/x` and `https://example.com`
    compare equal — which is right, hostnames are case-insensitive and
    `ALLOWED_HOSTS` is a host list, not an origin list. Anything without
    a parseable host (notably the literal `null` origin) returns None and
    is rejected by the caller.
    """
    return urlsplit(header_value).hostname


def _host_is_allowed(host: str, settings: Settings) -> bool:
    """Exact-match against `allowed_hosts_list`, plus the `*` wildcard
    that property returns in development.

    Deliberately identical to SEC-1's middleware, including what it does
    NOT do: `TrustedHostMiddleware` additionally understands a
    `*.example.com` prefix pattern, and this does not. A wildcard
    ALLOWED_HOSTS entry therefore passes the Host check and fails this
    one — a closed failure, not an open one. docs/SECURITY.md states the
    requirement: list exact hostnames.

    An empty `allowed_hosts_list` (unset `ALLOWED_HOSTS` outside
    development — `app/core/config.py`'s fail-closed default) matches
    nothing at all, so a misconfigured deployment rejects every guarded
    POST rather than accepting every one of them.
    """
    allowed = settings.allowed_hosts_list
    if "*" in allowed:
        return True
    return host in {h.lower() for h in allowed}


def origin_is_allowed(request: Request, settings: Settings) -> bool:
    """Whether this request's declared origin(s) may perform a
    state-changing action against this app. See the module docstring for
    the exact rule; this function does not itself look at the method or
    at any cookie.
    """
    declared = [value for header in _ORIGIN_HEADERS if (value := request.headers.get(header))]
    if not declared:
        # Fail closed. A cookie-bearing POST that declares no origin at
        # all is exactly the request this check exists to refuse.
        return False
    for value in declared:
        host = _declared_host(value)
        if host is None or not _host_is_allowed(host, settings):
            return False
    return True


def request_is_guarded(request: Request, cookie_names: frozenset[str]) -> bool:
    """A state-changing request that actually carries one of the named
    session cookies. Everything else — a safe method, or a request with
    no session cookie (a signed-out visitor, a Bearer API client, the
    sign-in POST that has not been issued a cookie yet) — is not this
    check's business.

    "Carries" means a NON-EMPTY value, not merely the name being
    present. An empty session cookie authenticates nobody (every reader
    of it, `get_reviewer_session` included, treats it as absent), so
    guarding it would buy no security and would cost something real:
    signing out sets `<name>=""` with `Max-Age=0`, and a client that
    keeps the emptied cookie rather than dropping it would then be
    unable to sign in again without an `Origin` header. Same fail-safe
    reasoning as leaving the sign-in POST itself ungated.
    """
    if request.method.upper() not in STATE_CHANGING_METHODS:
        return False
    return any(request.cookies.get(name) for name in cookie_names)


def require_same_origin(*cookie_names: str) -> Callable[..., None]:
    """Build the FastAPI dependency that enforces the rule above for the
    given session cookie name(s).

    Usage (build once at module level, apply to as many routes as you
    like — route-level `dependencies=[...]` are solved BEFORE the
    endpoint's own parameters, so a rejected request never reaches the
    session lookup, the database, or the route body):

        require_reviewer_origin = require_same_origin(COOKIE_NAME)

        @router.post("/claims/{claim_id}/approve",
                     dependencies=[Depends(require_reviewer_origin)])
        def reviewer_approve_claim(...) -> Any: ...

    Settings arrive through `Depends(get_settings)` rather than a direct
    `get_settings()` call so a test can narrow `ALLOWED_HOSTS` for one
    client via `app.dependency_overrides[get_settings]` without touching
    the process-wide cached singleton.
    """
    if not cookie_names:
        raise ValueError(
            "require_same_origin() needs at least one cookie name: a guard that "
            "matches no cookie would silently never run."
        )
    guarded_cookies = frozenset(cookie_names)

    def _guard(request: Request, settings: Settings = Depends(get_settings)) -> None:
        if not request_is_guarded(request, guarded_cookies):
            return
        if origin_is_allowed(request, settings):
            return
        raise HTTPException(
            status_code=403,
            detail={"code": CSRF_ERROR_CODE, "message": CSRF_ERROR_MESSAGE},
        )

    return _guard
