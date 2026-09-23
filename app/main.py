"""BCION Lite — FastAPI application factory.

M3: sign-in is wired in (tasks/BCI-004.md). M4: maker-checker + the
publishing console API (tasks/BCI-005.md). The first real UI
(`app/web/`) is wired in too -- see STATUS.md for the full list of
what's live.

## DEPLOY-18 — the middleware and router registry

Two ordered, named registries (`build_middleware_slots` /
`build_router_slots`) replace what used to be a flat sequence of
`app.add_middleware(...)` / `app.include_router(...)` calls. The point
isn't cleverness — it's that "every future task depends on getting this
registry right" (DEPLOY-18's own task card): a registry with names and a
frozen expected order is something a boot-time check can actually verify,
where a bare list of calls is not.

Slot order (frozen, do not reorder — docs/CONTRACTS.md / DEPLOY-18):
`trusted_host -> security_headers -> maintenance -> request_id_logging ->
cache_policy -> origin_check -> usage_events`. DEPLOY-18 wired real
behaviour for `trusted_host` (using the `ALLOWED_HOSTS` flag it also adds
to `app/core/config.py`); SEC-1 now fills `security_headers` and
`origin_check`; A11Y-4 now fills `cache_policy`; `maintenance` and
`request_id_logging` are reserved for later tasks (e.g. the pause/
kill-switch work); `usage_events` is explicitly optional and not built
yet. A reserved slot is a real, installed no-op middleware
(`_ReservedSlotMiddleware`) rather than a gap in the list, so the order
is enforced by Starlette's actual middleware stack from day one, not
just by a comment.

## A11Y-4 — Cache-Control middleware and shared-device hygiene

`CachePolicyMiddleware` (`app/web/cache_policy.py`) fills the
`cache_policy` slot: `Cache-Control` on every response, no-store by
default, with a short-max-age exception for an anonymous GET on an exact
allow-list (`/explore`, `/compare/view`, `/timeline/view` GET only) and a
long-max-age exception for `/static/*` — see that module's own docstring
for the three classes, the exact values, and why `cache_policy`'s inward
position relative to `security_headers` in the slot order above is
deliberate rather than incidental (`SecurityHeadersMiddleware`'s own
unconditional cookie/Bearer no-store, running later in the response
`send` chain, is a strict superset of anything `CachePolicyMiddleware`
would otherwise allow through). The reviewer console's sign-out route
(`app/web/reviewer/auth.py`) also sends `Clear-Site-Data: "cache"` on top
of this, the shared-device state's other mechanism
(docs/CONTRACTS.md).

Outside development, `create_app()` refuses to start (raises
`RuntimeError`) if the middleware or router registry doesn't exactly
match its expected, named shape — a required slot or router missing,
renamed, or reordered fails loudly at boot instead of silently shipping
without it. SEC-1 adds one more such check: `_verify_critical_settings`,
which fails the same way when a critical plain config value (not a
registry slot) is missing or still at its insecure development default.

## SEC-1 — security headers and the Origin check

`SecurityHeadersMiddleware` fills the `security_headers` slot: CSP,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a
restrictive `Permissions-Policy`, HSTS in production, and
`Cache-Control: no-store` on any response to a request that carried a
cookie or a `Bearer` token. The CSP's `script-src` currently allows
`'unsafe-inline'` — `app/web/templates/explore.html` has one inline
`<script>` (the selection-count progressive enhancement) and neither
that template nor `app/static/` is in this task's owned files, so
tightening `script-src` to match the "self only, no inline" goal is
left as an explicit follow-up for whichever task owns that template.

`OriginCheckMiddleware` fills the `origin_check` slot per
docs/CONTRACTS.md ("State-changing web posts need an Origin matching
ALLOWED_HOSTS; absent or mismatched is a 403"), scoped to requests
carrying the future `bcion_student_session` cookie — see that class's
own docstring for why it deliberately does not also gate on
`bcion_reviewer_session` (that is SEC-2's own, more specific job).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.account import router as account_router
from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.claims import router as claims_router
from app.api.compare import router as compare_router
from app.api.eligibility import router as eligibility_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.api.timeline import router as timeline_router
from app.core.config import Settings, get_settings
from app.core.logging import RequestIdLoggingMiddleware, configure_observability
from app.web.ask_pages import router as ask_pages_router
from app.web.cache_policy import CachePolicyMiddleware
from app.web.consent_pages import router as consent_pages_router
from app.web.errors import register_error_handlers
from app.web.pages import router as pages_router
from app.web.reviewer import router as reviewer_pages_router
from app.web.support_pages import router as support_pages_router


class _ReservedSlotMiddleware:
    """A structural placeholder for a middleware slot whose real
    behaviour is a separate, not-yet-built task. It changes nothing
    about the request/response -- it exists only so the ordered
    middleware registry has a real, inspectable, running entry at this
    position from day one. A later task swaps this class out for its
    own real middleware without moving or renaming the slot.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


# CSP `script-src` note (SEC-1): 'unsafe-inline' stays here until
# app/web/templates/explore.html's one inline <script> (the selection-
# count progressive enhancement) moves to a static file — neither that
# template nor app/static/ is owned by this task. Everything else is
# 'self'-only, no inline.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self'; "
    "frame-ancestors 'none'"
)
_PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), payment=()"
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


def _request_is_authenticated(request: Request) -> bool:
    """True if the request carries a session cookie or a Bearer token --
    docs/CONTRACTS.md's "Cache-Control no-store on responses to cookie/
    bearer requests" (SEC-1). Any cookie at all counts, not just a
    recognised session name: a stray/expired cookie still means an
    intermediate cache must not treat this response as anonymous,
    cacheable content."""
    if request.cookies:
        return True
    return request.headers.get("authorization", "").lower().startswith("bearer ")


class SecurityHeadersMiddleware:
    """Fills the `security_headers` slot DEPLOY-18 reserved (SEC-1).

    Adds CSP, `X-Content-Type-Options`, `Referrer-Policy`,
    `Permissions-Policy`, HSTS (production only) and, for a request that
    carried a cookie or Bearer token, `Cache-Control: no-store` — see
    `_request_is_authenticated`. Wraps `send` rather than using
    Starlette's `BaseHTTPMiddleware` (which buffers the whole response
    body in memory to let its dispatch function inspect it) since this
    middleware never needs the body, only the response's start message.
    """

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        no_store = _request_is_authenticated(request)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = _PERMISSIONS_POLICY
                headers["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
                if self._settings.app_env == "production":
                    headers["Strict-Transport-Security"] = _HSTS_VALUE
                if no_store:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


# docs/CONTRACTS.md: the only session cookie this check protects today.
# Deliberately NOT `bcion_reviewer_session` (app/web/reviewer_pages.py) —
# see OriginCheckMiddleware's own docstring for why that is SEC-2's job,
# not this slot's.
_GUARDED_SESSION_COOKIE = "bcion_student_session"
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheckMiddleware:
    """Fills the `origin_check` slot DEPLOY-18 reserved (SEC-1).

    docs/CONTRACTS.md: "State-changing web posts need an Origin matching
    ALLOWED_HOSTS; absent or mismatched is a 403." Scoped to requests
    that carry `_GUARDED_SESSION_COOKIE` — the student web-session
    cookie CONTRACTS.md states this rule alongside — rather than to
    every state-changing request in the app: the JSON API is
    Bearer-only and never reads a cookie (CONTRACTS.md "the JSON API is
    Bearer-only; cookies belong to the web layer alone"), so it has
    nothing here to protect.

    Deliberately does NOT also gate on `bcion_reviewer_session`
    (app/web/reviewer_pages.py): the plan's own SEC-2 task gives
    /reviewer's CSRF handling its own dependency and, in the same
    change, updates tests/db/test_reviewer_console.py to send a matching
    Origin header. That test suite posts with the reviewer cookie today
    without one; enforcing this check against that cookie now — ahead of
    SEC-2 — would break it. No route in this codebase sets
    `bcion_student_session` yet, so this middleware is real, tested
    logic that is a true no-op against every route that exists today.
    """

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        guarded = (
            request.method in _STATE_CHANGING_METHODS
            and _GUARDED_SESSION_COOKIE in request.cookies
        )
        if guarded and not self._origin_is_allowed(request):
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "origin_not_allowed",
                        "message": "This request's origin could not be verified.",
                    }
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _origin_is_allowed(self, request: Request) -> bool:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if not origin:
            return False
        host = urlsplit(origin).hostname
        if not host:
            return False
        allowed = self._settings.allowed_hosts_list
        return "*" in allowed or host in allowed


@dataclass(frozen=True)
class MiddlewareSlot:
    """One named entry in the ordered `MIDDLEWARE` registry.

    `name` is the stable identifier the boot-time check and the
    middleware-order test key off -- it must never be renamed once
    frozen, only have its `middleware_class`/`kwargs` swapped out when a
    real implementation lands.
    """

    name: str
    middleware_class: Callable[..., ASGIApp]
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterSlot:
    """One named entry in the router registry. `router` is `None` only
    ever transiently in a test constructing a deliberately-broken
    registry -- a real boot always has every slot filled."""

    name: str
    router: APIRouter | None


# Frozen slot order — docs/CONTRACTS.md, DEPLOY-18. Do not reorder;
# see this module's docstring for why each slot is where it is.
EXPECTED_MIDDLEWARE_ORDER: tuple[str, ...] = (
    "trusted_host",
    "security_headers",
    "maintenance",
    "request_id_logging",
    "cache_policy",
    "origin_check",
    "usage_events",
)

EXPECTED_ROUTERS: tuple[str, ...] = (
    "health",
    "explore",
    "compare",
    "eligibility",
    "timeline",
    "auth",
    "plans",
    "claims",
    "pages",
    "reviewer_pages",
    "consent_pages",
    "ask",
    "ask_pages",
    "support_pages",
    "account",
)


def build_middleware_slots(settings: Settings) -> list[MiddlewareSlot]:
    """The ordered `MIDDLEWARE` list. Executed outermost-first in the
    order returned here -- see `create_app` for why `add_middleware` is
    called in *reverse* of this list to achieve that."""
    return [
        MiddlewareSlot(
            "trusted_host",
            TrustedHostMiddleware,
            {"allowed_hosts": settings.allowed_hosts_list},
        ),
        MiddlewareSlot("security_headers", SecurityHeadersMiddleware, {"settings": settings}),
        MiddlewareSlot("maintenance", _ReservedSlotMiddleware),  # reserved, not built yet
        MiddlewareSlot("request_id_logging", RequestIdLoggingMiddleware),  # OPS-2
        MiddlewareSlot("cache_policy", CachePolicyMiddleware),  # A11Y-4
        MiddlewareSlot("origin_check", OriginCheckMiddleware, {"settings": settings}),
        MiddlewareSlot("usage_events", _ReservedSlotMiddleware),  # optional, not built yet
    ]


def build_router_slots() -> list[RouterSlot]:
    """The router registry, in the order routes were historically
    included (preserved exactly -- FastAPI route resolution doesn't
    depend on include order for these disjoint-prefix routers, but there
    is no reason to reshuffle it)."""
    return [
        RouterSlot("health", health_router),
        RouterSlot("explore", explore_router),
        RouterSlot("compare", compare_router),
        RouterSlot("eligibility", eligibility_router),
        RouterSlot("timeline", timeline_router),
        RouterSlot("auth", auth_router),
        RouterSlot("plans", plans_router),
        RouterSlot("claims", claims_router),
        RouterSlot("pages", pages_router),
        RouterSlot("reviewer_pages", reviewer_pages_router),
        RouterSlot("consent_pages", consent_pages_router),
        RouterSlot("ask", ask_router),
        RouterSlot("ask_pages", ask_pages_router),
        RouterSlot("support_pages", support_pages_router),
        RouterSlot("account", account_router),
    ]


def _verify_middleware_registry(slots: list[MiddlewareSlot]) -> None:
    names = tuple(slot.name for slot in slots)
    if names != EXPECTED_MIDDLEWARE_ORDER:
        raise RuntimeError(
            "Refusing to start: the middleware registry does not match the "
            f"frozen slot order (DEPLOY-18 / docs/CONTRACTS.md). Expected "
            f"{EXPECTED_MIDDLEWARE_ORDER!r}, got {names!r}."
        )


def _verify_router_registry(slots: list[RouterSlot]) -> None:
    names = tuple(slot.name for slot in slots)
    if names != EXPECTED_ROUTERS:
        raise RuntimeError(
            "Refusing to start: the router registry does not match the "
            f"expected set of routers (DEPLOY-18). Expected {EXPECTED_ROUTERS!r}, "
            f"got {names!r}."
        )
    missing = [slot.name for slot in slots if slot.router is None]
    if missing:
        raise RuntimeError(
            f"Refusing to start: router slot(s) {missing!r} have no router "
            "attached (DEPLOY-18: a required router slot must never be absent)."
        )


_VALID_APP_ENVS: tuple[str, ...] = ("development", "staging", "production")
# Must match Settings.app_secret_key's own default (app/core/config.py).
_INSECURE_DEV_SECRET_KEY = "dev-insecure-key-change-me"


def _verify_critical_settings(settings: Settings) -> None:
    """SEC-1's env-var guard: outside development, a missing or still-
    default critical setting fails the boot, the same "refuse to start"
    contract DEPLOY-18's registry checks use, applied to plain config
    values that have no registry slot of their own.

    Only called when `settings.app_env != "development"` (see
    `create_app`), so this never blocks a developer's own machine.
    """
    if settings.app_env not in _VALID_APP_ENVS:
        raise RuntimeError(
            f"Refusing to start: APP_ENV={settings.app_env!r} is not one of "
            f"{_VALID_APP_ENVS!r}."
        )
    if not settings.db_configured:
        raise RuntimeError(
            "Refusing to start: SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY must be "
            f"set outside development (APP_ENV={settings.app_env!r})."
        )
    if settings.app_secret_key == _INSECURE_DEV_SECRET_KEY:
        raise RuntimeError(
            "Refusing to start: APP_SECRET_KEY is still the insecure development "
            f"default outside development (APP_ENV={settings.app_env!r})."
        )


def create_app(
    *,
    settings: Settings | None = None,
    middleware_slots: list[MiddlewareSlot] | None = None,
    router_slots: list[RouterSlot] | None = None,
) -> FastAPI:
    """Build the FastAPI app from the middleware and router registries.

    The three keyword overrides exist for tests only (DEPLOY-18's own
    "refuse to start" unit test constructs a deliberately-broken
    registry and asserts this raises) -- ordinary callers, including the
    module-level `app` below, call this with no arguments.
    """
    settings = settings if settings is not None else get_settings()
    middleware_slots = (
        middleware_slots if middleware_slots is not None else build_middleware_slots(settings)
    )
    router_slots = router_slots if router_slots is not None else build_router_slots()

    if settings.app_env != "development":
        _verify_middleware_registry(middleware_slots)
        _verify_router_registry(router_slots)
        _verify_critical_settings(settings)

    app = FastAPI(
        title="BCION Lite",
        description="A 10-100 user career-decision pilot. See docs/PRODUCT.md.",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    configure_observability(app)  # OPS-2: JSON formatter + redaction filter, root logger
    register_error_handlers(app)  # A11Y-3: global HTML 404/403/500 pages

    # Reversed: Starlette's `add_middleware` prepends to its own internal
    # list, so the last one added ends up outermost (first to see a
    # request). Calling it in reverse here means `middleware_slots[0]`
    # (trusted_host) really is outermost/first, matching the order the
    # registry -- and the docstring -- describe.
    for slot in reversed(middleware_slots):
        app.add_middleware(slot.middleware_class, **slot.kwargs)

    for router_slot in router_slots:
        if router_slot.router is not None:
            app.include_router(router_slot.router)

    return app


app = create_app()
