"""DEPLOY-5: scripts/smoke.py's individual checks, exercised in-process
against the real app via FastAPI's TestClient (an httpx.Client subclass,
so it's a drop-in for every `check_*` function's `client` parameter --
no real socket, no separate server process needed).

/explore and /careers need a database; the real module-level `app` has
none configured on this machine, so those two checks use a dependency
override with an in-memory fake, the same pattern
tests/unit/test_web_timeline_page.py's neighbours already use elsewhere
in this suite. Every other check runs against the real app as-is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db_client
from app.main import app

# scripts/ is never installed as a package (pyproject.toml's own
# comment: "run in place ... never imported as an installed package") --
# loaded here by path instead of a normal import.
_SMOKE_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "smoke.py"
_spec = importlib.util.spec_from_file_location("smoke", _SMOKE_PATH)
assert _spec is not None and _spec.loader is not None
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke"] = smoke
_spec.loader.exec_module(smoke)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


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
def client_with_fake_db() -> TestClient:
    def fake_db() -> Any:
        yield _FakeDbClient()

    app.dependency_overrides[get_db_client] = fake_db
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db_client, None)


class TestIndividualChecks:
    def test_healthz_ok(self, client: TestClient) -> None:
        result = smoke.check_healthz(client)
        assert result.ok is True

    def test_readyz_answers_even_when_not_ready(self, client: TestClient) -> None:
        # No DB configured on this machine -- /readyz correctly reports
        # 503, and check_readyz treats that as a *valid answer*, not a
        # check failure (see its own docstring: "what matters here is
        # that it answers at all, with the expected shape").
        result = smoke.check_readyz(client)
        assert result.ok is True

    def test_explore_renders_with_a_working_db(self, client_with_fake_db: TestClient) -> None:
        result = smoke.check_explore_renders(client_with_fake_db)
        assert result.ok is True

    def test_careers_json_with_a_working_db(self, client_with_fake_db: TestClient) -> None:
        result = smoke.check_careers_json(client_with_fake_db)
        assert result.ok is True

    def test_plans_requires_auth(self, client: TestClient) -> None:
        result = smoke.check_plans_requires_auth(client)
        assert result.ok is True

    def test_plans_check_fails_if_it_ever_returns_200(self, client: TestClient) -> None:
        """Guards the check itself, not just the route: a check that
        can't fail is worthless."""

        class _AlwaysOkClient:
            def get(self, path: str) -> Any:
                class _Resp:
                    status_code = 200

                return _Resp()

        result = smoke.check_plans_requires_auth(_AlwaysOkClient())  # type: ignore[arg-type]
        assert result.ok is False

    def test_reviewer_queue_redirects_to_sign_in(self, client: TestClient) -> None:
        result = smoke.check_reviewer_queue_redirects(client)
        assert result.ok is True
        assert "sign-in" in result.detail

    def test_docs_state_matches_development(self, client: TestClient) -> None:
        result = smoke.check_docs_state(client, "development")
        assert result.ok is True

    def test_docs_state_fails_if_docs_are_open_and_env_claims_production(
        self, client: TestClient
    ) -> None:
        # The real app runs with development settings, so /docs is 200 --
        # asserting "production" expectations against it must fail, or
        # this check could never catch docs left open in a real prod env.
        result = smoke.check_docs_state(client, "production")
        assert result.ok is False

    def test_app_env_matches(self, client: TestClient) -> None:
        result = smoke.check_app_env(client, "development")
        assert result.ok is True

    def test_app_env_mismatch_fails(self, client: TestClient) -> None:
        result = smoke.check_app_env(client, "production")
        assert result.ok is False


class TestRunChecksAndMain:
    def test_run_checks_without_expected_env_skips_the_two_env_gated_checks(
        self, client_with_fake_db: TestClient
    ) -> None:
        results = smoke.run_checks(
            "http://testserver", expected_env=None, timeout=5.0, client=client_with_fake_db
        )
        names = {r.name for r in results}
        assert "docs_state" not in names
        assert "app_env" not in names

    def test_run_checks_with_expected_env_includes_them(
        self, client_with_fake_db: TestClient
    ) -> None:
        results = smoke.run_checks(
            "http://testserver",
            expected_env="development",
            timeout=5.0,
            client=client_with_fake_db,
        )
        names = {r.name for r in results}
        assert "docs_state" in names
        assert "app_env" in names

    def test_never_issues_anything_but_get(self) -> None:
        # Static guard against a future edit accidentally adding a
        # write: DEPLOY-5's own acceptance criterion is "issues only GET
        # requests".
        source = _SMOKE_PATH.read_text(encoding="utf-8")
        for verb in (".post(", ".put(", ".patch(", ".delete("):
            assert verb not in source, f"scripts/smoke.py must never call client{verb}"
