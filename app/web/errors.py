"""A11Y-3 — global HTML error pages: 404 / 403 / 500.

`register_error_handlers(app)` is called once from `create_app()`, the
same way `app/core/logging.py`'s `configure_observability(app)` already
is (`app/main.py`'s "smallest possible additive change" comment there
names the precedent). Neither an exception handler nor
`configure_observability` is a `MiddlewareSlot`/`RouterSlot` — DEPLOY-18's
two registries (`app/main.py`) are frozen specifically for middleware and
routers, and an exception handler is neither, so this does not touch
either registry.

## The risk this module is built around

This task's own named risk: "The handler could alter API JSON contracts.
Guard it by route prefix list, not by Accept alone." A browser navigating
directly to a JSON API URL (not via `fetch`/XHR) sends
`Accept: text/html` too — gating on Accept alone would silently turn a
JSON API's error response into an HTML page for that one case, which is
exactly the kind of contract change `tests/unit`/`tests/db`'s existing
API test files must never see. So every new handler below checks BOTH a
route prefix list AND the Accept header before ever rendering HTML, and
falls through to FastAPI's/Starlette's own untouched default behaviour —
verbatim, not just "close enough" — for anything that fails either check.

`_JSON_API_EXACT_PATHS`/`_JSON_API_PATH_PREFIXES` is the closed, explicit
list of every JSON-only route this app serves today (one entry per
`app/api/*` router — cross-checked against `app/main.py`'s
`EXPECTED_ROUTERS` and each module's own `@router.get/post/...`
decorators). The HTML side is deliberately the COMPLEMENT of this list,
not a positive enumeration of known HTML paths: an "unknown URL" 404 (a
student following a stale/garbled link) is by definition not a route
this app has ever registered, so a positive allow-list keyed on
registered HTML page paths could never match it — that would defeat the
one acceptance case ("An unknown URL (404) ... returns the correctly-
styled HTML page") this whole task exists to cover. Knowing the small,
closed JSON side precisely is what "guard by route prefix list" actually
buys here: a new JSON-only route silently falls on the SAFE side (still
JSON, not accidentally re-rendered as HTML) only if it is added to this
list — flagged here for whoever next adds an `app/api/*` router.

## 403 copy — never per-request detail

The 403 page's copy is the SAME fixed catalogue string
`app/web/templates/_states.html`'s own `permission_denied()` macro
already uses (`global.difficult_state.permission_denied`,
`app/i18n/en.json`/`hi.json`) — resolved directly here via `translate()`
rather than through that macro (this module is plain Python, not a
template), so there is exactly one place that copy is authored. This is
a real cross-user-access-adjacent guarantee, not just a style choice:
echoing back any id, path or detail from the failed request (e.g. "you
can't access pathway abc-123") would leak that `abc-123` exists at all
to someone probing ids — the 500/404 pages below carry the same
guarantee for the same reason, via plain, fixed, hardcoded English (not
one of `app/i18n`'s eight frozen catalogue keys, same "plain text, same
state every other template's text is in before I18N-3 extracts it"
convention `_states.html`'s own `session_expired()` macro already uses).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse, Response

from app.i18n import translate
from app.web.templating import locale_for_request, templates

# Every JSON-only route this app serves today — one entry per
# app/api/* router, cross-checked against app/main.py's EXPECTED_ROUTERS
# and each module's own route decorators. See this module's own
# docstring for why the HTML side is this list's complement, not a
# second, positive list of its own.
_JSON_API_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/ask",  # app/api/ask.py
        "/compare",  # app/api/compare.py (HTML page is the distinct /compare/view)
        "/eligibility",  # app/api/eligibility.py
        "/careers",  # app/api/explore.py
        "/timeline",  # app/api/timeline.py (HTML page is the distinct /timeline/view)
        "/healthz",  # app/api/health.py
        "/readyz",  # app/api/health.py
    }
)
_JSON_API_PATH_PREFIXES: tuple[str, ...] = (
    "/auth",  # app/api/auth.py
    "/claims",  # app/api/claims.py
    "/plans",  # app/api/plans.py
)


def _is_json_api_path(path: str) -> bool:
    if path in _JSON_API_EXACT_PATHS:
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in _JSON_API_PATH_PREFIXES
    )


def _wants_html(request: Request) -> bool:
    """BOTH conditions, never Accept alone — this task's own named risk
    (see this module's docstring)."""
    if _is_json_api_path(request.url.path):
        return False
    return "text/html" in request.headers.get("accept", "")


def _status_class(status_code: int) -> int:
    """Collapses an arbitrary status code onto the one this app actually
    has a styled page for: 404, 403, or (everything else, including any
    other 4xx this app doesn't otherwise raise from an HTML route today,
    and every 5xx) 500."""
    if status_code in (404, 403):
        return status_code
    return 500


def _copy_for_status(request: Request, status_code: int) -> tuple[str, str, str]:
    """`(heading, message, alert_variant)` for one status class — see
    this module's own docstring for why the 403 message is resolved via
    `translate()` (the same fixed, catalogued copy
    `_states.html.permission_denied()` uses) while 404/500 are plain,
    hardcoded English."""
    resolved = _status_class(status_code)
    if resolved == 404:
        return (
            "Page not found",
            "We couldn't find that page. It may have moved, or the link might be out of date.",
            "caution",
        )
    if resolved == 403:
        message = translate(
            "global.difficult_state.permission_denied", locale_for_request(request)
        )
        return ("You don't have access to this", message, "error")
    return (
        "Something went wrong",
        "Something on our side went wrong. Please try again in a moment.",
        "error",
    )


def _render_error_page(request: Request, status_code: int) -> Response:
    heading, message, alert_variant = _copy_for_status(request, status_code)
    response = templates.TemplateResponse(
        request,
        "error.html",
        {"heading": heading, "message": message, "alert_variant": alert_variant},
        status_code=status_code,
    )
    # Set directly, not left to app/web/cache_policy.py's
    # CachePolicyMiddleware: verified live (see this task's completion
    # report) that a handler registered for the bare `Exception` class
    # (the 500 case below) is pulled OUT of Starlette's normal
    # ExceptionMiddleware and run from the outermost `ServerErrorMiddleware`
    # instead (`starlette.applications.Starlette.build_middleware_stack`:
    # `if key in (500, Exception): error_handler = value` — special-cased,
    # not left in the `exception_handlers` dict `ExceptionMiddleware`
    # gets), which sends its response on the RAW incoming ASGI `send`,
    # bypassing every one of this app's own middleware entirely — so
    # CachePolicyMiddleware never runs at all for that response, and would
    # not add a `Cache-Control` header of any kind, not even the wrong
    # one. The 404/403 branch (a plain `StarletteHTTPException` handler,
    # not pulled out this way) DOES still flow through the ordinary
    # middleware stack and would get `no-store` from CachePolicyMiddleware
    # regardless — this explicit header is set unconditionally on every
    # status class anyway, so this module's own guarantee ("error pages
    # are never cached") does not depend on that routing detail either way.
    response.headers["Cache-Control"] = "no-store"
    return response


async def _handle_http_exception(request: Request, exc: Exception) -> Response:
    # Starlette's own `ExceptionHandler` type is `Callable[[Request,
    # Exception], ...]` regardless of which exc_class a handler is
    # registered for (contravariant in the exception parameter) -- the
    # narrower `StarletteHTTPException` parameter mypy needs below is only
    # ever actually true at runtime because `register_error_handlers`
    # registers this exact function for that exact class.
    assert isinstance(exc, StarletteHTTPException)
    if _wants_html(request):
        return _render_error_page(request, exc.status_code)
    # Byte-for-byte FastAPI's own default (fastapi.exception_handlers.
    # http_exception_handler) — every existing JSON API error shape is
    # completely unchanged for any request that fails either gate above.
    return await http_exception_handler(request, exc)


async def _handle_uncaught_exception(request: Request, exc: Exception) -> Response:
    if _wants_html(request):
        return _render_error_page(request, 500)
    # Byte-for-byte the SAME fallback Starlette's own
    # `ServerErrorMiddleware.error_response` produces when no handler is
    # registered at all -- registering a handler for the bare `Exception`
    # class does not change where that fallback runs (Starlette's own
    # `build_middleware_stack` special-cases `key in (500, Exception)`:
    # it is pulled OUT of the normal `exception_handlers` dict and run
    # from `ServerErrorMiddleware` itself, the app's OUTERMOST layer,
    # exactly as it always was -- see `_render_error_page`'s own comment
    # above for why that means this app's own middleware never sees this
    # particular response at all, for either branch of this function).
    return PlainTextResponse("Internal Server Error", status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    """Wires the two handlers above into `app` — called once from
    `create_app()` (see this module's docstring for why this is not a
    `MiddlewareSlot`/`RouterSlot`)."""
    # `Starlette.add_exception_handler`'s own stub wants a handler typed
    # for the general `Exception`, not the specific subclass it is being
    # registered against — Starlette only ever calls this handler for a
    # `StarletteHTTPException` instance (matching the class it's keyed on
    # below), so this is safe at runtime; mypy just can't express "this
    # handler's second argument type is bound to the registered class"
    # without the cast. Same pattern already used elsewhere in this
    # codebase for a narrower-than-declared handler/callback type.
    app.add_exception_handler(
        StarletteHTTPException,
        cast(
            "Callable[[Request, Exception], Coroutine[Any, Any, Response]]",
            _handle_http_exception,
        ),
    )
    app.add_exception_handler(Exception, _handle_uncaught_exception)
