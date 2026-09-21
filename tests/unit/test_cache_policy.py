"""A11Y-4: `CachePolicyMiddleware` (app/web/cache_policy.py) -- the
`cache_policy` slot app/main.py's registry reserved (DEPLOY-18).

BCION Lite runs on shared/borrowed phones (docs/PRODUCT.md): a cached
page from a previous user, especially the reviewer console, is a real
leak, not a performance nitpick. Every route family docs/CONTRACTS.md
names is exercised here twice -- once as a guest (no cookie), once
carrying an arbitrary cookie (standing in for "a reviewer", or simply
"any returning/signed-in visitor" -- the credential check is "any cookie
at all", never a specific session name, so one stand-in cookie proves
the general rule) -- to prove the allow-listed public paths degrade to
no-store the moment a cookie is present, not just that a guest gets the
short-cache response.

Uses the real, module-level `app` (development settings, no Supabase
configured) via `fastapi.testclient.TestClient`, same pattern as
tests/unit/test_security_middleware.py and tests/unit/test_smoke.py --
`/explore` needs a working `get_db_client` dependency to render at all,
so it gets the same fake-DB override tests/unit/test_smoke.py already
established; every other route here either has no DB dependency
(`/timeline/view`) or already degrades gracefully to a friendly template
without one (`/compare/view`, `/requirements/view`,
`app/web/common.py`'s `_db_client_or_none`).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

from app.api.deps import get_db_client
from app.main import app
from app.web.cache_policy import (
    PUBLIC_ANONYMOUS_PATHS,
    CachePolicyMiddleware,
    cache_control_for,
)
from app.web.reviewer import COOKIE_NAME as REVIEWER_COOKIE_NAME

# Any cookie at all is the trigger (cache_policy.py's own docstring) --
# this name is not privileged in any way; it stands in for "a returning
# or signed-in visitor" generally, not specifically a reviewer.
_SOME_COOKIE = {"some_cookie": "some-value"}

_PUBLIC_CACHE_CONTROL = "public, max-age=300"
_STATIC_CACHE_CONTROL = "public, max-age=31536000, immutable"
_NO_STORE = "no-store"


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    def select(self, *args: Any, **kwargs: Any) -> _FakeTable:
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult([])


class _FakeDbClient:
    def table(self, name: str) -> _FakeTable:
        return _FakeTable()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client_with_fake_db() -> TestClient:
    """Same fixture as tests/unit/test_smoke.py's -- /explore's route
    function depends on `get_db_client` directly (not the "_or_none"
    variant every other screen uses), so it needs a working fake rather
    than degrading gracefully on its own."""

    def fake_db() -> Any:
        yield _FakeDbClient()

    app.dependency_overrides[get_db_client] = fake_db
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db_client, None)


class TestPureCacheControlForFunction:
    """`cache_control_for` is a pure function of the request -- covered
    directly, in addition to through the full app below, since it is the
    one place all three classes' decision logic actually lives."""

    def test_allow_listed_anonymous_get_is_public(self) -> None:
        for path in PUBLIC_ANONYMOUS_PATHS:
            scope = {"type": "http", "method": "GET", "path": path, "headers": []}
            assert cache_control_for(StarletteRequest(scope)) == _PUBLIC_CACHE_CONTROL

    def test_allow_listed_path_with_a_cookie_falls_back_to_no_store(self) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/explore",
            "headers": [(b"cookie", b"some_cookie=value")],
        }
        assert cache_control_for(StarletteRequest(scope)) == _NO_STORE

    def test_allow_listed_path_with_a_bearer_header_falls_back_to_no_store(self) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/compare/view",
            "headers": [(b"authorization", b"Bearer sometoken")],
        }
        assert cache_control_for(StarletteRequest(scope)) == _NO_STORE

    def test_post_to_an_allow_listed_path_is_no_store(self) -> None:
        """The POST on /timeline/view is deliberately NOT on the
        allow-list -- only its GET is."""
        scope = {"type": "http", "method": "POST", "path": "/timeline/view", "headers": []}
        assert cache_control_for(StarletteRequest(scope)) == _NO_STORE

    def test_static_path_is_long_max_age_regardless_of_credentials(self) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/static/css/app.css",
            "headers": [(b"cookie", b"some_cookie=value")],
        }
        assert cache_control_for(StarletteRequest(scope)) == _STATIC_CACHE_CONTROL

    def test_unlisted_path_is_no_store(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/reviewer/queue", "headers": []}
        assert cache_control_for(StarletteRequest(scope)) == _NO_STORE

    def test_non_http_scope_is_passed_through_untouched(self) -> None:
        """Lifespan/websocket scopes must never be touched -- same
        `scope["type"] != "http"` guard app/main.py's own
        SecurityHeadersMiddleware/OriginCheckMiddleware and
        app/core/logging.py's RequestIdLoggingMiddleware all use (see
        tests/unit/test_logging_redaction.py's test of the same name for
        the identical pattern this mirrors)."""
        import asyncio

        calls: list[str] = []

        async def _inner_app(scope: object, receive: object, send: object) -> None:
            calls.append("called")

        middleware = CachePolicyMiddleware(_inner_app)

        async def _run() -> None:
            await middleware({"type": "lifespan"}, None, None)

        asyncio.run(_run())
        assert calls == ["called"]


class TestExplorePage:
    """docs/CONTRACTS.md's public-anonymous allow-list, entry 1 of 3."""

    def test_guest_get_is_public_short_cache(self, client_with_fake_db: TestClient) -> None:
        response = client_with_fake_db.get("/explore")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _PUBLIC_CACHE_CONTROL

    def test_get_with_a_cookie_falls_back_to_no_store(
        self, client_with_fake_db: TestClient
    ) -> None:
        response = client_with_fake_db.get("/explore", cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE


class TestCompareViewPage:
    """docs/CONTRACTS.md's public-anonymous allow-list, entry 2 of 3."""

    def test_guest_get_is_public_short_cache(self, client: TestClient) -> None:
        response = client.get("/compare/view")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _PUBLIC_CACHE_CONTROL

    def test_get_with_a_cookie_falls_back_to_no_store(self, client: TestClient) -> None:
        response = client.get("/compare/view", cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE


class TestTimelineViewPage:
    """docs/CONTRACTS.md's public-anonymous allow-list, entry 3 of 3 --
    GET only. The POST on this exact path is explicitly NOT allow-listed
    (its own class test below)."""

    def test_guest_get_is_public_short_cache(self, client: TestClient) -> None:
        response = client.get("/timeline/view")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _PUBLIC_CACHE_CONTROL

    def test_get_with_a_cookie_falls_back_to_no_store(self, client: TestClient) -> None:
        response = client.get("/timeline/view", cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_post_is_no_store_even_as_a_guest(self, client: TestClient) -> None:
        response = client.post("/timeline/view", data={})
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_post_is_no_store_with_a_cookie_too(self, client: TestClient) -> None:
        response = client.post("/timeline/view", data={}, cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE


class TestRequirementsViewPage:
    """Not on the public-anonymous allow-list at all -- SEC-5 already
    makes every personal field POST-only, so its GET signature
    (app/web/requirements_pages.py) only ever accepts `pathway_id`, never
    a personal value. Always no-store, guest or not, with or without a
    (non-personal) query param."""

    def test_guest_get_with_no_pathway_id_is_no_store(self, client: TestClient) -> None:
        response = client.get("/requirements/view")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_guest_get_with_a_pathway_id_is_still_no_store(self, client: TestClient) -> None:
        response = client.get(
            "/requirements/view", params={"pathway_id": "00000000-0000-0000-0000-000000000000"}
        )
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_post_is_no_store(self, client: TestClient) -> None:
        response = client.post("/requirements/view", data={})
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE


class TestReviewerConsole:
    """/reviewer/* -- no-store for the whole console, guest or not."""

    def test_sign_in_form_is_no_store_as_a_guest(self, client: TestClient) -> None:
        response = client.get("/reviewer/sign-in")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_sign_in_form_is_no_store_with_a_stale_cookie(self, client: TestClient) -> None:
        response = client.get("/reviewer/sign-in", cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_queue_redirects_to_sign_in_and_is_no_store_as_a_guest(
        self, client: TestClient
    ) -> None:
        response = client.get("/reviewer/queue")
        assert response.status_code == 303
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_queue_is_no_store_with_the_reviewer_cookie(self, client: TestClient) -> None:
        # An invalid/unrecognised token still degrades to a redirect
        # (get_reviewer_session's own contract -- "never raises") --
        # what matters here is only the Cache-Control header, not the
        # sign-in state itself.
        response = client.get(
            "/reviewer/queue", cookies={REVIEWER_COOKIE_NAME: "not-a-real-token"}
        )
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_sign_out_is_no_store(self, client: TestClient) -> None:
        response = client.post(
            "/reviewer/sign-out", cookies={REVIEWER_COOKIE_NAME: "some-token"}
        )
        assert response.status_code == 303
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_sign_out_also_sends_clear_site_data_cache(self, client: TestClient) -> None:
        """docs/CONTRACTS.md: "Reviewer sign-out also sends
        Clear-Site-Data: 'cache', the shared-device state's mechanism" --
        a second, browser-enforced instruction on top of the no-store
        header above (app/web/reviewer/auth.py's reviewer_sign_out
        docstring explains why "cache" only, not "cookies" too). The full
        real-browser back-button journey is tests/e2e/
        test_shared_device.py's job; this is the fast, no-DB-needed check
        that the header itself is actually on the wire."""
        response = client.post(
            "/reviewer/sign-out", cookies={REVIEWER_COOKIE_NAME: "some-token"}
        )
        assert response.headers["Clear-Site-Data"] == '"cache"'


class TestAuthRoutes:
    """/auth/* -- no-store, and every POST is no-store regardless of
    path in any case."""

    def test_sign_up_with_a_malformed_body_is_still_no_store(self, client: TestClient) -> None:
        response = client.post("/auth/sign-up", json={})
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_sign_in_with_a_malformed_body_is_still_no_store(self, client: TestClient) -> None:
        response = client.post("/auth/sign-in", json={})
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == _NO_STORE


class TestPlansRoutes:
    """/plans* -- no-store, guest or not."""

    def test_get_plans_without_auth_is_no_store(self, client: TestClient) -> None:
        response = client.get("/plans")
        assert response.status_code == 401
        assert response.headers["Cache-Control"] == _NO_STORE

    def test_get_plans_with_a_cookie_is_still_no_store(self, client: TestClient) -> None:
        response = client.get("/plans", cookies=_SOME_COOKIE)
        assert response.status_code == 401
        assert response.headers["Cache-Control"] == _NO_STORE


class TestStaticAssets:
    """/static/* -- long max-age, cache-busted by filename hash today in
    theory only (docs/CONTRACTS.md) -- see app/web/cache_policy.py's own
    docstring for the flagged gap."""

    def test_guest_get_of_the_compiled_css_is_long_max_age(self, client: TestClient) -> None:
        response = client.get("/static/css/app.css")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _STATIC_CACHE_CONTROL

    def test_a_cookie_forces_no_store_even_on_a_static_asset(self, client: TestClient) -> None:
        """docs/CONTRACTS.md's literal text: no-store "is ... the only
        class for any cookie-bearing request" -- no static carve-out.
        `CachePolicyMiddleware` itself does not special-case credentials
        for /static/*, but `SecurityHeadersMiddleware` (app/main.py,
        outward of cache_policy in the frozen slot order) unconditionally
        forces no-store on any cookie-bearing request, so the full stack
        still gets this right end to end."""
        response = client.get("/static/css/app.css", cookies=_SOME_COOKIE)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE


class TestEverythingElseDefaultsToNoStore:
    def test_healthz_is_no_store_by_default(self, client: TestClient) -> None:
        """Not on any allow-list and not /static/* -- the plain default,
        proven against a route with no auth/db baggage at all."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == _NO_STORE
