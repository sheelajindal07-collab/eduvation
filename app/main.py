"""BCION Lite — FastAPI application factory.

M3: sign-in is wired in (tasks/BCI-004.md). M4: maker-checker + the
publishing console API (tasks/BCI-005.md). The first real UI
(`app/web/`) is wired in too -- see STATUS.md for the full list of
what's live.

## DEPLOY-18 — the middleware and router registry

Two ordered, named registries (`_build_middleware_slots` /
`_build_router_slots`) replace what used to be a flat sequence of
`app.add_middleware(...)` / `app.include_router(...)` calls. The point
isn't cleverness — it's that "every future task depends on getting this
registry right" (DEPLOY-18's own task card): a registry with names and a
frozen expected order is something a boot-time check can actually verify,
where a bare list of calls is not.

Slot order (frozen, do not reorder — docs/CONTRACTS.md / DEPLOY-18):
`trusted_host -> security_headers -> maintenance -> request_id_logging ->
cache_policy -> origin_check -> usage_events`. DEPLOY-18 itself only wires
real behaviour for `trusted_host` (using the `ALLOWED_HOSTS` flag it also
adds to `app/core/config.py`); `security_headers` and `origin_check` are
reserved slots SEC-1 fills next; `maintenance`, `request_id_logging` and
`cache_policy` are reserved for later tasks (e.g. the pause/kill-switch
work); `usage_events` is explicitly optional and not built yet. A
reserved slot is a real, installed no-op middleware (`_ReservedSlotMiddleware`)
rather than a gap in the list, so the order is enforced by Starlette's
actual middleware stack from day one, not just by a comment.

Outside development, `create_app()` refuses to start (raises
`RuntimeError`) if the middleware or router registry doesn't exactly
match its expected, named shape — a required slot or router missing,
renamed, or reordered fails loudly at boot instead of silently shipping
without it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.auth import router as auth_router
from app.api.claims import router as claims_router
from app.api.compare import router as compare_router
from app.api.eligibility import router as eligibility_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.api.timeline import router as timeline_router
from app.core.config import Settings, get_settings
from app.web.consent_pages import router as consent_pages_router
from app.web.pages import router as pages_router
from app.web.reviewer_pages import router as reviewer_pages_router


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
        MiddlewareSlot("security_headers", _ReservedSlotMiddleware),  # SEC-1 fills this in
        MiddlewareSlot("maintenance", _ReservedSlotMiddleware),  # reserved, not built yet
        MiddlewareSlot("request_id_logging", _ReservedSlotMiddleware),  # reserved
        MiddlewareSlot("cache_policy", _ReservedSlotMiddleware),  # reserved
        MiddlewareSlot("origin_check", _ReservedSlotMiddleware),  # SEC-1 fills this in
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

    app = FastAPI(
        title="BCION Lite",
        description="A 10-100 user career-decision pilot. See docs/PRODUCT.md.",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

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
