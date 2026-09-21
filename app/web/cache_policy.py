"""`CachePolicyMiddleware` — fills the `cache_policy` slot `app/main.py`'s
registry reserved for a later task (A11Y-4, DEPLOY-18's pattern).

docs/CONTRACTS.md, "Difficult states and cache class" (**Settled — cache
class**): BCION Lite runs on shared/borrowed phones (docs/PRODUCT.md) --
a cached page from a previous user, especially the reviewer console, is
a real leak, not a performance nitpick. `no route sets Cache-Control
today`, so every response now gets one explicitly; nothing is left to a
browser's or intermediate cache's own default.

Three classes, checked in this order (first match wins):

1. **static** -- `public, max-age=<_STATIC_MAX_AGE_SECONDS>, immutable`,
   for `/static/*` only. docs/CONTRACTS.md's own text says this class is
   "cache-busted by filename hash, never by content" -- today's
   `app/static/css/app.css` and `app/static/js/explore-select.js` are
   referenced by their plain, UNhashed names
   (`app/web/templates/base.html`, `app/web/templates/explore.html`), so
   there is no cache-busting mechanism yet. A11Y-4's own task card is
   explicit that this stays a long max-age regardless -- flagged here,
   and in that task's completion report, as a known footgun for whoever
   next changes either file: a long cache with no busting mechanism
   means a deployed CSS/JS change may not reach an already-visiting
   browser until the max-age expires.
2. **public-anonymous** -- `public, max-age=<_PUBLIC_MAX_AGE_SECONDS>`,
   ONLY for an anonymous (no `Cookie`, no `Authorization` header) GET on
   the exact allow-list `_PUBLIC_ANONYMOUS_PATHS`. The POST on
   `/timeline/view` is deliberately not on that list -- it always falls
   through to no-store below, same as every other POST in this app.
   Either header present on an otherwise-allow-listed path falls back to
   no-store, checked directly here rather than only relied on via
   `SecurityHeadersMiddleware`'s own, later (more-outward) no-store
   override -- see this module's "ordering" note below -- so a returning
   or signed-in visitor never gets a cached response that might belong
   to someone else, even if this middleware is ever exercised on its
   own.
3. **no-store** -- everything else. Explicitly: every POST response
   regardless of path; `/reviewer/*`; `/auth/*`; `/plans*`;
   `/requirements/view` (see the module-level note below); and any
   request not covered by 1 or 2 above.

## Ordering against `SecurityHeadersMiddleware` (`app/main.py`)

`app/main.py`'s frozen slot order places `cache_policy` INWARD of
`security_headers` (`security_headers -> maintenance ->
request_id_logging -> cache_policy -> origin_check -> ...`). Starlette
executes a middleware's `send` wrapper for the OUTGOING response in the
reverse of the incoming order -- the innermost slot's wrapper runs
first, the outermost's runs last, and whichever runs last wins any
disagreement over the same header. `security_headers` already sets
`Cache-Control: no-store` (unconditionally) on any response to a request
carrying a cookie or a Bearer token (`app/main.py`'s
`_request_is_authenticated`) -- running AFTER this middleware, that is
the authoritative last word for a credentialed request no matter what
this middleware decided, including for `/static/*`, which this
middleware does not itself credential-check (docs/CONTRACTS.md: no-store
"is ... the only class for any cookie-bearing request", with no
carve-out for static assets). This is by design, not a race: the two
middlewares never need to agree with each other directly, because
`security_headers`'s unconditional rule is a strict superset of what
this module would otherwise allow through. This module still does its
own credential check for the public-anonymous class (rather than relying
on that ordering alone) so its own behaviour is correct even in a unit
test that exercises `CachePolicyMiddleware` in isolation.

## `/requirements/view` -- why it is not on the public-anonymous list

`app/web/requirements_pages.py`'s GET signature (SEC-5) accepts
`pathway_id` only -- every personal field (age, marks_percentage,
subjects_studied, domicile_state) is POST-only, per docs/CONTRACTS.md's
frozen "every personal input is POST-only" rule. So there is today no
GET on this path that could ever carry a personal query param. It is
still deliberately left off `_PUBLIC_ANONYMOUS_PATHS` (falling through to
no-store like every other unlisted path) rather than folded into
"anonymous GETs are fine here too": if a future change ever added a
personal field to that GET signature, this module must not have to be
touched to keep that response out of a shared cache.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# "Short" -- long enough to save a repeat fetch within one browsing
# session, short enough that a content edit (a newly-published claim
# changing what /compare/view or /requirements/view would show, a new
# career on /explore) is not stale for long on a shared device.
_PUBLIC_MAX_AGE_SECONDS = 300  # 5 minutes

# "Long" -- see this module's own docstring above: there is no
# cache-busting mechanism on these filenames today, so this value is a
# deliberate, flagged trade-off, not an oversight.
_STATIC_MAX_AGE_SECONDS = 31536000  # 1 year

_NO_STORE = "no-store"
_PUBLIC_CACHE_CONTROL = f"public, max-age={_PUBLIC_MAX_AGE_SECONDS}"
_STATIC_CACHE_CONTROL = f"public, max-age={_STATIC_MAX_AGE_SECONDS}, immutable"

# Exact-path, GET-only allow-list -- docs/CONTRACTS.md's "public-
# anonymous" class. The POST on /timeline/view is deliberately absent.
PUBLIC_ANONYMOUS_PATHS = frozenset({"/explore", "/compare/view", "/timeline/view"})

_STATIC_PATH_PREFIX = "/static/"


def _request_carries_credentials(request: Request) -> bool:
    """Same test as `app/main.py`'s `_request_is_authenticated`,
    duplicated rather than imported: that function lives in the
    application-factory module, which itself imports from `app/web/*`
    (e.g. `app.web.reviewer`) -- importing back from here would risk a
    cycle for no real gain, since the two checks are one line each. Any
    cookie at all counts, not just a recognised session name -- a
    stray/expired cookie still means an intermediate cache must not
    treat this response as anonymous, cacheable content."""
    if request.cookies:
        return True
    return request.headers.get("authorization", "").lower().startswith("bearer ")


def cache_control_for(request: Request) -> str:
    """The exact `Cache-Control` value for one request -- pure function
    of the request, no I/O, so it's trivially unit-testable on its own in
    addition to through the middleware/full app."""
    path = request.url.path
    if path.startswith(_STATIC_PATH_PREFIX):
        return _STATIC_CACHE_CONTROL
    if (
        request.method == "GET"
        and path in PUBLIC_ANONYMOUS_PATHS
        and not _request_carries_credentials(request)
    ):
        return _PUBLIC_CACHE_CONTROL
    return _NO_STORE


class CachePolicyMiddleware:
    """Fills the `cache_policy` slot DEPLOY-18 reserved (A11Y-4). See this
    module's own docstring for the three classes and the ordering note
    against `SecurityHeadersMiddleware`.

    Wraps `send` rather than Starlette's `BaseHTTPMiddleware` (which
    buffers the whole response body in memory to let its dispatch
    function inspect it) -- same reasoning as `app/main.py`'s
    `SecurityHeadersMiddleware`: this middleware never needs the body,
    only the response's start message.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        cache_control = cache_control_for(request)

        async def send_with_cache_control(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = cache_control
            await send(message)

        await self.app(scope, receive, send_with_cache_control)
