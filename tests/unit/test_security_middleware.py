"""SEC-1: SecurityHeadersMiddleware and OriginCheckMiddleware — the two
slots app/main.py's registry reserved for this task (see that module's
own "SEC-1" docstring section).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from app.core.config import Settings
from app.main import (
    _GUARDED_SESSION_COOKIE,
    OriginCheckMiddleware,
    SecurityHeadersMiddleware,
    app,
    create_app,
)

client = TestClient(app)


class TestSecurityHeadersOnTheRealApp:
    """The real, module-level `app` (development settings) — proves the
    slot is actually wired into the live middleware stack, not just unit
    tested in isolation."""

    def test_every_response_gets_the_baseline_headers(self) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "geolocation=()" in response.headers["Permissions-Policy"]
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_no_hsts_outside_production(self) -> None:
        response = client.get("/healthz")
        assert "Strict-Transport-Security" not in response.headers

    def test_anonymous_request_is_not_forced_no_store_by_security_headers_itself(self) -> None:
        """A11Y-4 update: `cache_policy` (app/web/cache_policy.py) is now
        a real, filled slot (see app/main.py's own docstring) whose own
        default is `Cache-Control: no-store` on almost every path -- so
        the FULL app's response to an anonymous `/healthz` GET is
        genuinely `no-store` today (a route not on cache_policy's
        public-anonymous allow-list), and that is correct, not a
        regression (see tests/unit/test_cache_policy.py's
        `TestEverythingElseDefaultsToNoStore`). What this test always
        actually meant to prove is narrower and is unchanged by that:
        `SecurityHeadersMiddleware` itself only forces `Cache-Control:
        no-store` for a request carrying a cookie or Bearer token, and
        adds no such header at all for a plain anonymous one -- checked
        here by calling the middleware directly, with cache_policy's slot
        out of the picture entirely, rather than through the full
        app/registry it used to be (mis)read through."""
        import asyncio

        sent: list[dict[str, object]] = []

        async def _inner_app(scope: object, receive: object, send: object) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})

        async def _capture_send(message: dict[str, object]) -> None:
            sent.append(message)

        async def _noop_receive() -> dict[str, object]:
            return {"type": "http.request"}

        middleware = SecurityHeadersMiddleware(_inner_app, settings=Settings(_env_file=None))  # type: ignore[arg-type]

        async def _run() -> None:
            scope = {"type": "http", "method": "GET", "headers": []}
            await middleware(scope, _noop_receive, _capture_send)  # type: ignore[arg-type]

        asyncio.run(_run())

        raw_headers = sent[0]["headers"]
        header_names = {name.decode().lower() for name, _ in raw_headers}  # type: ignore[misc]
        assert "cache-control" not in header_names

    def test_a_request_carrying_a_cookie_gets_no_store(self) -> None:
        response = client.get("/healthz", cookies={"some_cookie": "value"})
        assert response.headers["Cache-Control"] == "no-store"

    def test_a_bearer_request_gets_no_store(self) -> None:
        response = client.get("/healthz", headers={"Authorization": "Bearer test-token"})
        assert response.headers["Cache-Control"] == "no-store"


class TestHstsInProduction:
    def _prod_client(self) -> TestClient:
        settings = Settings(
            _env_file=None,
            app_env="production",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            app_secret_key="a-real-generated-secret-key",
            # TrustedHostMiddleware (outermost) would otherwise 400 every
            # request in production, since ALLOWED_HOSTS is fail-closed
            # (empty) by default outside development.
            allowed_hosts="testserver",
        )
        return TestClient(create_app(settings=settings))

    def test_hsts_present_in_production(self) -> None:
        response = self._prod_client().get("/healthz")
        hsts = response.headers["Strict-Transport-Security"]
        assert hsts == "max-age=63072000; includeSubDomains"


class TestOriginCheckMiddleware:
    """Exercised against the real /timeline/view POST route (stateless,
    always 200 regardless of form content) -- see app/main.py's
    OriginCheckMiddleware docstring for why this is scoped to
    `_GUARDED_SESSION_COOKIE` (`bcion_student_session`) only, a cookie no
    route in this codebase sets yet."""

    def test_state_changing_request_without_the_guarded_cookie_is_unaffected(self) -> None:
        response = client.post("/timeline/view", data={})
        assert response.status_code == 200

    def test_guarded_cookie_with_no_origin_or_referer_is_rejected(self) -> None:
        response = client.post(
            "/timeline/view",
            data={},
            cookies={_GUARDED_SESSION_COOKIE: "some-token"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "origin_not_allowed"

    def test_guarded_cookie_with_a_mismatched_origin_is_rejected_under_a_strict_allowlist(
        self,
    ) -> None:
        # The real `app` runs with development settings (ALLOWED_HOSTS
        # wildcard), so this needs a strict, production-like allowlist
        # to actually exercise a mismatch -- see TestHstsInProduction's
        # helper for the same pattern.
        settings = Settings(
            _env_file=None,
            app_env="production",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            app_secret_key="a-real-generated-secret-key",
            # "testserver" (TestClient's own default Host) so
            # TrustedHostMiddleware -- outermost, running before this
            # request ever reaches OriginCheckMiddleware -- lets the
            # request through; the mismatch this test cares about is the
            # Origin header below, not the Host header.
            allowed_hosts="testserver",
        )
        strict_client = TestClient(create_app(settings=settings))
        response = strict_client.post(
            "/timeline/view",
            data={},
            cookies={_GUARDED_SESSION_COOKIE: "some-token"},
            headers={"Origin": "https://evil.example.com"},
        )
        assert response.status_code == 403

    def test_guarded_cookie_with_a_matching_origin_is_allowed(self) -> None:
        # The real `app` runs with development settings, so
        # allowed_hosts_list is ["*"] and any Origin is accepted.
        response = client.post(
            "/timeline/view",
            data={},
            cookies={_GUARDED_SESSION_COOKIE: "some-token"},
            headers={"Origin": "http://testserver"},
        )
        assert response.status_code == 200

    def test_guarded_cookie_falls_back_to_referer_when_origin_is_absent(self) -> None:
        response = client.post(
            "/timeline/view",
            data={},
            cookies={_GUARDED_SESSION_COOKIE: "some-token"},
            headers={"Referer": "http://testserver/timeline/view"},
        )
        assert response.status_code == 200

    def test_a_non_state_changing_request_with_the_guarded_cookie_is_unaffected(self) -> None:
        response = client.get(
            "/timeline/view",
            cookies={_GUARDED_SESSION_COOKIE: "some-token"},
        )
        assert response.status_code == 200

    def test_origin_check_rejects_with_a_strict_allowed_hosts_list(self) -> None:
        settings = Settings(
            _env_file=None,
            app_env="production",
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="test-publishable-key",
            app_secret_key="a-real-generated-secret-key",
            allowed_hosts="bcion.example.com",
        )
        # TrustedHostMiddleware would reject a bare TestClient request
        # (Host: testserver) outright, so exercise OriginCheckMiddleware
        # directly instead of through the full app for this one case.
        async def _unreachable(scope: object, receive: object, send: object) -> None:
            raise AssertionError("should be rejected before reaching the wrapped app")

        origin_check = OriginCheckMiddleware(app=_unreachable, settings=settings)  # type: ignore[arg-type]
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{_GUARDED_SESSION_COOKIE}=tok".encode()),
                (b"origin", b"https://not-allowed.example.com"),
            ],
        }
        request = StarletteRequest(scope)
        assert origin_check._origin_is_allowed(request) is False

        scope_allowed = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{_GUARDED_SESSION_COOKIE}=tok".encode()),
                (b"origin", b"https://bcion.example.com"),
            ],
        }
        assert origin_check._origin_is_allowed(StarletteRequest(scope_allowed)) is True
