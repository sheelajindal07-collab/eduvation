"""DEPLOY-18 + SEC-1: the middleware/router registry in app/main.py.

Three things this task card calls "everything after it depends on
getting ... right": the middleware slot ORDER (frozen,
docs/CONTRACTS.md), the "refuse to start outside development" behaviour
when a slot is missing or misnamed (DEPLOY-18), and the same refusal for
a critical plain config value (SEC-1's env-var guard). All three are
asserted directly against `create_app()` with an injected registry/
settings, rather than only against the real module-level `app` --
constructing a deliberately-broken registry is how the refuse-to-start
path gets exercised at all, short of actually deleting code.
"""

from __future__ import annotations

from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings
from app.core.logging import RequestIdLoggingMiddleware
from app.main import (
    EXPECTED_MIDDLEWARE_ORDER,
    EXPECTED_ROUTERS,
    MiddlewareSlot,
    OriginCheckMiddleware,
    RouterSlot,
    SecurityHeadersMiddleware,
    _ReservedSlotMiddleware,
    app,
    build_middleware_slots,
    build_router_slots,
    create_app,
)

_VALID_PROD_OVERRIDES: dict[str, object] = {
    "app_env": "production",
    "supabase_url": "https://example.supabase.co",
    "supabase_publishable_key": "test-publishable-key",
    "app_secret_key": "a-real-generated-secret-key",
}


def _prod_settings(**overrides: object) -> Settings:
    # `_env_file=None` (same convention as tests/unit/test_health.py):
    # bypasses a real local .env so this test's "outside development"
    # path isn't at the mercy of whatever happens to be in it. Defaults
    # to settings that pass SEC-1's critical-settings guard too, so
    # tests about the *registry* aren't accidentally tripped up by it --
    # override individual fields to test the guard itself instead.
    merged = {**_VALID_PROD_OVERRIDES, **overrides}
    return Settings(_env_file=None, **merged)  # type: ignore[arg-type]


class TestMiddlewareOrder:
    def test_expected_order_constant_has_all_seven_named_slots(self) -> None:
        assert EXPECTED_MIDDLEWARE_ORDER == (
            "trusted_host",
            "security_headers",
            "maintenance",
            "request_id_logging",
            "cache_policy",
            "origin_check",
            "usage_events",
        )

    def test_build_middleware_slots_matches_expected_order(self) -> None:
        slots = build_middleware_slots(Settings(_env_file=None))
        assert tuple(slot.name for slot in slots) == EXPECTED_MIDDLEWARE_ORDER

    def test_each_slot_has_the_expected_middleware_class(self) -> None:
        """trusted_host (DEPLOY-18), security_headers and origin_check
        (SEC-1) and request_id_logging (OPS-2) are real, installed
        middleware; the remaining three stay reserved placeholders for
        later tasks."""
        slots = build_middleware_slots(Settings(_env_file=None))
        by_name = {slot.name: slot for slot in slots}
        assert by_name["trusted_host"].middleware_class is TrustedHostMiddleware
        assert by_name["security_headers"].middleware_class is SecurityHeadersMiddleware
        assert by_name["origin_check"].middleware_class is OriginCheckMiddleware
        assert by_name["request_id_logging"].middleware_class is RequestIdLoggingMiddleware
        for reserved_name in ("maintenance", "cache_policy", "usage_events"):
            assert by_name[reserved_name].middleware_class is _ReservedSlotMiddleware

    def test_the_real_app_installs_middleware_in_the_frozen_order(self) -> None:
        """`app.user_middleware[0]` is the OUTERMOST/first-executed layer
        (Starlette quirk: `add_middleware` prepends) -- so this list, read
        top to bottom, must equal EXPECTED_MIDDLEWARE_ORDER's own order."""
        expected_classes = [
            TrustedHostMiddleware,
            SecurityHeadersMiddleware,
            _ReservedSlotMiddleware,
            RequestIdLoggingMiddleware,
            _ReservedSlotMiddleware,
            OriginCheckMiddleware,
            _ReservedSlotMiddleware,
        ]
        actual_classes = [m.cls for m in app.user_middleware]
        assert actual_classes == expected_classes

    def test_trusted_host_uses_allowed_hosts_list_from_settings(self) -> None:
        settings = Settings(_env_file=None, allowed_hosts="example.com, api.example.com")
        slots = build_middleware_slots(settings)
        trusted_host_slot = next(s for s in slots if s.name == "trusted_host")
        assert trusted_host_slot.kwargs == {"allowed_hosts": ["example.com", "api.example.com"]}

    def test_security_headers_and_origin_check_receive_settings(self) -> None:
        settings = Settings(_env_file=None)
        slots = build_middleware_slots(settings)
        by_name = {slot.name: slot for slot in slots}
        assert by_name["security_headers"].kwargs == {"settings": settings}
        assert by_name["origin_check"].kwargs == {"settings": settings}


class TestRouterRegistry:
    def test_build_router_slots_matches_expected_names(self) -> None:
        slots = build_router_slots()
        assert tuple(slot.name for slot in slots) == EXPECTED_ROUTERS

    def test_every_router_slot_is_filled(self) -> None:
        slots = build_router_slots()
        assert all(slot.router is not None for slot in slots)


class TestRefuseToStartOutsideDevelopment:
    def test_production_boots_with_an_intact_registry_and_valid_settings(self) -> None:
        # Must not raise.
        built = create_app(settings=_prod_settings())
        assert len(built.routes) > 0

    def test_production_refuses_to_start_with_a_missing_middleware_slot(self) -> None:
        settings = _prod_settings()
        slots = [s for s in build_middleware_slots(settings) if s.name != "security_headers"]
        try:
            create_app(settings=settings, middleware_slots=slots)
        except RuntimeError as exc:
            assert "middleware registry" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for a missing middleware slot")

    def test_production_refuses_to_start_with_a_reordered_middleware_registry(self) -> None:
        settings = _prod_settings()
        slots = build_middleware_slots(settings)
        reordered = [slots[1], slots[0], *slots[2:]]
        try:
            create_app(settings=settings, middleware_slots=reordered)
        except RuntimeError as exc:
            assert "middleware registry" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for a reordered middleware registry")

    def test_production_refuses_to_start_with_a_misnamed_router_slot(self) -> None:
        settings = _prod_settings()
        routers = build_router_slots()
        renamed = [RouterSlot("healthzzz", routers[0].router), *routers[1:]]
        try:
            create_app(settings=settings, router_slots=renamed)
        except RuntimeError as exc:
            assert "router registry" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for a misnamed router slot")

    def test_production_refuses_to_start_with_a_missing_router(self) -> None:
        settings = _prod_settings()
        routers = build_router_slots()
        blanked = [RouterSlot(routers[0].name, None), *routers[1:]]
        try:
            create_app(settings=settings, router_slots=blanked)
        except RuntimeError as exc:
            assert "no router attached" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for a missing router")

    def test_development_stays_lenient_about_a_broken_registry(self) -> None:
        """A half-built registry on a developer's own machine must never
        block `make dev` -- only staging/production enforce completeness."""
        dev_settings = Settings(_env_file=None, app_env="development")
        broken_middleware = [
            s for s in build_middleware_slots(dev_settings) if s.name != "maintenance"
        ]
        broken_routers = [
            RouterSlot(s.name, None) for s in build_router_slots()[:1]
        ] + build_router_slots()[1:]
        built = create_app(
            settings=dev_settings,
            middleware_slots=broken_middleware,
            router_slots=broken_routers,
        )
        assert built is not None


class TestCriticalSettingsGuard:
    """SEC-1's env-var guard: outside development, a missing or
    still-default critical setting fails the boot the same way a broken
    registry does."""

    def test_production_refuses_to_start_without_supabase_configured(self) -> None:
        settings = _prod_settings(supabase_url=None, supabase_publishable_key=None)
        try:
            create_app(settings=settings)
        except RuntimeError as exc:
            assert "SUPABASE_URL" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when Supabase is unconfigured")

    def test_production_refuses_to_start_with_the_default_secret_key(self) -> None:
        settings = _prod_settings(app_secret_key="dev-insecure-key-change-me")
        try:
            create_app(settings=settings)
        except RuntimeError as exc:
            assert "APP_SECRET_KEY" in str(exc)
        else:
            raise AssertionError("expected RuntimeError with the default secret key")

    def test_refuses_to_start_with_an_invalid_app_env(self) -> None:
        settings = _prod_settings(app_env="quality-assurance")
        try:
            create_app(settings=settings)
        except RuntimeError as exc:
            assert "APP_ENV" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for an invalid APP_ENV")

    def test_development_is_never_checked(self) -> None:
        """A developer's own machine never has Supabase configured by
        default (app/core/config.py's docstring) -- this must not block
        `make dev`."""
        dev_settings = Settings(_env_file=None, app_env="development")
        built = create_app(settings=dev_settings)
        assert built is not None


class TestMiddlewareSlotDataclass:
    def test_kwargs_defaults_to_an_empty_dict_not_a_shared_mutable(self) -> None:
        a = MiddlewareSlot("a", _ReservedSlotMiddleware)
        b = MiddlewareSlot("b", _ReservedSlotMiddleware)
        assert a.kwargs == {}
        assert a.kwargs is not b.kwargs
