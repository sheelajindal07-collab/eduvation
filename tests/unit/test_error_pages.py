"""A11Y-3: the global HTML 404/403/500 error pages
(`app/web/errors.py`, `app/web/templates/error.html`).

Exercised against the real, module-level `app` (development settings)
for the "unknown URL" and JSON-contract-preservation cases -- proves the
handlers are actually wired into the live app via `create_app()`, not
just unit tested in isolation (same pattern
`tests/unit/test_security_middleware.py` uses for SEC-1's slots). The
genuine-403 and forced-500 cases build their own throwaway app via
`create_app()` plus one synthetic test-only route, rather than routing
through the real reviewer console's auth/session machinery (owned by a
different lane, and not available at the unit-test layer with no
Supabase configured) or the real JSON API's own error paths (which this
task's own risk statement says must never be touched by this change).
"""

from __future__ import annotations

import re

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.web.errors import _is_json_api_path, _wants_html

client = TestClient(app, raise_server_exceptions=False)


class TestJsonApiPathClassification:
    """`_is_json_api_path` — the closed, explicit deny-list this whole
    module's gate is built on (see app/web/errors.py's own docstring)."""

    def test_every_known_json_only_route_is_classified_as_json(self) -> None:
        for path in (
            "/ask",
            "/compare",
            "/eligibility",
            "/careers",
            "/timeline",
            "/healthz",
            "/readyz",
            "/auth/sign-in",
            "/auth/sign-up",
            "/claims",
            "/claims/some-id/approve",
            "/plans",
            "/plans/some-id",
            "/plans/some-id/actions",
        ):
            assert _is_json_api_path(path), path

    def test_html_page_paths_are_not_classified_as_json(self) -> None:
        for path in (
            "/",
            "/explore",
            "/compare/view",
            "/requirements/view",
            "/timeline/view",
            "/pathways/some-id/view",
            "/reviewer/queue",
            "/consent/confirm",
            "/ask/view",
            "/this-page-does-not-exist-at-all",
        ):
            assert not _is_json_api_path(path), path


class TestWantsHtmlGate:
    """The task's own named risk: gate on BOTH the route prefix list AND
    Accept, never Accept alone."""

    def test_a_json_api_path_is_never_html_even_with_an_html_accept_header(self) -> None:
        from starlette.requests import Request as StarletteRequest

        # A plain scope, mirroring what the handler actually receives --
        # simplest correct way to unit-test this pure function without a
        # full request/response round trip.
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/careers",
            "headers": [(b"accept", b"text/html")],
        }
        assert _wants_html(StarletteRequest(scope)) is False

    def test_an_html_page_path_without_an_html_accept_header_is_not_html(self) -> None:
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/explore",
            "headers": [(b"accept", b"application/json")],
        }
        assert _wants_html(StarletteRequest(scope)) is False

    def test_an_html_page_path_with_an_html_accept_header_is_html(self) -> None:
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/this-page-does-not-exist-at-all",
            "headers": [(b"accept", b"text/html")],
        }
        assert _wants_html(StarletteRequest(scope)) is True


class TestUnknownUrlIs404:
    def test_unknown_url_with_html_accept_renders_the_styled_page(self) -> None:
        response = client.get(
            "/this-page-does-not-exist-at-all", headers={"Accept": "text/html"}
        )
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "Page not found" in response.text
        assert 'href="/explore"' in response.text
        assert "Back to explore" in response.text
        assert response.headers["Cache-Control"] == "no-store"

    def test_unknown_url_never_leaks_the_requested_path_into_the_body(self) -> None:
        response = client.get(
            "/this-page-does-not-exist-at-all-ZzZ12345", headers={"Accept": "text/html"}
        )
        assert response.status_code == 404
        assert "this-page-does-not-exist-at-all-ZzZ12345" not in response.text

    def test_unknown_url_alert_has_role_alert(self) -> None:
        response = client.get(
            "/another-unknown-url-entirely", headers={"Accept": "text/html"}
        )
        assert response.status_code == 404
        assert 'role="alert"' in response.text

    def test_unknown_url_without_an_html_accept_header_stays_the_plain_json_404(
        self,
    ) -> None:
        """The task's own named risk, end to end: a non-browser caller
        (no `Accept: text/html`) must see FastAPI's ordinary 404 shape,
        completely unchanged."""
        response = client.get(
            "/this-page-does-not-exist-at-all", headers={"Accept": "application/json"}
        )
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"detail": "Not Found"}


class TestKnownJsonApiPathsAreNeverConvertedToHtml:
    """Even when a browser navigates straight to a JSON API URL (sending
    `Accept: text/html` the way a real browser tab-navigation would) --
    this task's own named risk, the reason the gate is a route-prefix
    list and not Accept alone."""

    def test_a_json_api_404_ish_path_stays_json_with_an_html_accept_header(self) -> None:
        response = client.get(
            "/plans/does-not-exist/actions", headers={"Accept": "text/html"}
        )
        assert "application/json" in response.headers["content-type"]
        assert "<html" not in response.text.lower()

    def test_a_validation_error_on_a_json_route_stays_the_pydantic_shape(self) -> None:
        """422 is handled by FastAPI's own `RequestValidationError`
        handler (more specific than this task's `Exception` handler, by
        MRO) -- unaffected either way, checked here for the same reason
        the two cases above are: an html Accept header must not change
        it."""
        response = client.post("/timeline", json={}, headers={"Accept": "text/html"})
        assert response.status_code == 422
        assert "application/json" in response.headers["content-type"]
        body = response.json()
        assert isinstance(body["detail"], list)
        assert body["detail"][0]["loc"] == ["body", "stages"]

    def test_an_uncaught_exception_on_a_json_route_stays_plain_text_not_html(self) -> None:
        """`/careers` fails today because no Supabase is configured in
        this unit-test process -- an ordinary uncaught exception, same as
        any other bug would produce. Proves the `Exception` handler's
        fallback for a non-HTML-gated request is byte-for-byte what
        Starlette's own `ServerErrorMiddleware.error_response` would have
        produced with no handler registered at all."""
        response = client.get("/careers", headers={"Accept": "text/html"})
        assert response.status_code == 500
        assert response.text == "Internal Server Error"
        assert "text/plain" in response.headers["content-type"]
        assert "<html" not in response.text.lower()


_MARKER_DETAIL = "reviewer-only-detail-must-never-render-9f2c1a"
_MARKER_PATH_SEGMENT = "secret-pathway-id-83af"


def _app_with_synthetic_error_routes() -> TestClient:
    """A throwaway `create_app()` instance plus two test-only routes that
    raise a genuine 403 (with a detail carrying a marker that must never
    reach the rendered page) and an uncaught exception (ditto) -- see
    this module's own docstring for why a synthetic route is used instead
    of routing through the real reviewer console or JSON API."""
    test_app = create_app()

    @test_app.get("/explore/synthetic-403-test/{pathway_id}")
    def _raise_403(pathway_id: str) -> None:
        raise HTTPException(status_code=403, detail=f"cannot access {_MARKER_DETAIL}")

    @test_app.get("/explore/synthetic-500-test")
    def _raise_500() -> None:
        raise RuntimeError(_MARKER_DETAIL)

    return TestClient(test_app, raise_server_exceptions=False)


class TestGenuine403:
    def test_a_real_403_renders_the_styled_page(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            f"/explore/synthetic-403-test/{_MARKER_PATH_SEGMENT}",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == 403
        assert "text/html" in response.headers["content-type"]
        # Jinja autoescapes the apostrophe to &#39; -- matches what a
        # browser actually receives, same convention every other test in
        # this codebase already follows for this exact sentence
        # (tests/db/test_web_pages.py's own requirements-page assertions).
        assert "You don&#39;t have access to this" in response.text
        assert 'href="/explore"' in response.text
        assert response.headers["Cache-Control"] == "no-store"

    def test_a_real_403_never_echoes_the_requests_own_id_path_or_detail(self) -> None:
        """The task's own cross-user-access-adjacent concern: echoing
        back any id/path/detail from the failed request would leak that
        it exists at all to someone probing ids."""
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            f"/explore/synthetic-403-test/{_MARKER_PATH_SEGMENT}",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == 403
        assert _MARKER_PATH_SEGMENT not in response.text
        assert _MARKER_DETAIL not in response.text
        assert "cannot access" not in response.text
        # Fixed catalogue copy only (app/i18n/en.json
        # global.difficult_state.permission_denied) -- the same generic
        # sentence _states.html's own permission_denied() macro renders.
        # Jinja autoescapes the apostrophe to &#39;.
        assert (
            "You don&#39;t have access to this. If that seems wrong, contact your reviewer."
            in response.text
        )

    def test_a_real_403_alert_has_role_alert(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            f"/explore/synthetic-403-test/{_MARKER_PATH_SEGMENT}",
            headers={"Accept": "text/html"},
        )
        assert 'role="alert"' in response.text


class TestForced500:
    def test_a_forced_500_renders_the_styled_page(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            "/explore/synthetic-500-test", headers={"Accept": "text/html"}
        )
        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]
        assert "Something went wrong" in response.text
        assert 'href="/explore"' in response.text
        assert response.headers["Cache-Control"] == "no-store"

    def test_a_forced_500_never_leaks_the_exception_message_or_a_traceback(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            "/explore/synthetic-500-test", headers={"Accept": "text/html"}
        )
        assert response.status_code == 500
        assert _MARKER_DETAIL not in response.text
        assert "RuntimeError" not in response.text
        assert "Traceback" not in response.text
        assert "File \"" not in response.text

    def test_a_forced_500_alert_has_role_alert(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        response = synthetic_client.get(
            "/explore/synthetic-500-test", headers={"Accept": "text/html"}
        )
        assert 'role="alert"' in response.text


class TestNoStackTraceOrDetailAnywhereAcrossAllThree:
    """Belt-and-braces sweep across all three status classes, grepping
    the actual response text (not just reading the template) -- this
    task's own acceptance wording."""

    def test_no_python_traceback_markers_in_any_of_the_three_pages(self) -> None:
        synthetic_client = _app_with_synthetic_error_routes()
        responses = [
            client.get("/this-page-does-not-exist-at-all", headers={"Accept": "text/html"}),
            synthetic_client.get(
                f"/explore/synthetic-403-test/{_MARKER_PATH_SEGMENT}",
                headers={"Accept": "text/html"},
            ),
            synthetic_client.get(
                "/explore/synthetic-500-test", headers={"Accept": "text/html"}
            ),
        ]
        for response in responses:
            for marker in ("Traceback", "site-packages", "app\\web", "app/web", '  File "'):
                assert marker not in response.text
            assert not re.search(r"\b[A-Za-z]:\\\\", response.text)
