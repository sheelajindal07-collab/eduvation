"""M0 smoke check: the application shell boots and reports its own
configuration honestly."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.health as health_module
from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_healthz_reports_unconfigured_dependencies_honestly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no Supabase/AI credentials set, nothing should claim to be
    configured that isn't — the "never fabricate passing results" rule
    from CLAUDE.md, applied to the app's own self-report.

    A real .env may exist on the developer's machine (it does on this
    one, since the Supabase project got wired up) — pydantic-settings
    reads that file directly, so deleting OS env vars alone does NOT
    isolate this test from it (caught for real: this test failed with
    `db_configured` True once .env held real values, exactly the bug it
    exists to catch, just aimed at itself first). `_env_file=None`
    bypasses the file entirely for this one construction.
    """
    monkeypatch.setattr(health_module, "get_settings", lambda: Settings(_env_file=None))

    response = client.get("/healthz")
    body = response.json()
    assert body["db_configured"] is False
    assert body["ai_configured"] is False


# ---------------------------------------------------------------------
# GET /readyz (DEPLOY-5) — a distinct, more thorough check than
# /healthz: actually queries the database via the guest client, and
# reports AI_ENABLED per docs/CONTRACTS.md. `_anon_client_or_none` is
# monkeypatched directly (rather than the real `get_anon_client`) so
# these tests never depend on whether this machine's real .env happens
# to have Supabase configured -- same isolation concern
# test_healthz_reports_unconfigured_dependencies_honestly's own
# docstring already explains for /healthz.
# ---------------------------------------------------------------------


class _FakeTable:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises

    def select(self, *args: Any, **kwargs: Any) -> _FakeTable:
        return self

    def limit(self, *args: Any, **kwargs: Any) -> _FakeTable:
        return self

    def execute(self) -> Any:
        if self._raises is not None:
            raise self._raises
        return type("Result", (), {"data": []})()


class _FakePostgrest:
    def aclose(self) -> None:
        pass


class _FakeClient:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.postgrest = _FakePostgrest()

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(raises=self._raises)


def test_readyz_returns_503_when_db_is_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(health_module, "_anon_client_or_none", lambda: None)

    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database_reachable"] is False


def test_readyz_returns_200_when_the_query_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(health_module, "_anon_client_or_none", lambda: _FakeClient())

    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database_reachable"] is True


def test_readyz_returns_503_when_the_query_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(
        health_module,
        "_anon_client_or_none",
        lambda: _FakeClient(raises=RuntimeError("connection refused: db.internal:5432")),
    )

    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database_reachable"] is False
    # The underlying exception text (which could embed a host/port) must
    # never reach the response body -- only the boolean.
    assert "db.internal" not in response.text
    assert "5432" not in response.text


def test_readyz_reports_ai_enabled_and_app_env_per_contracts_md(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: Settings(_env_file=None, ai_enabled="true", app_env="staging"),
    )
    monkeypatch.setattr(health_module, "_anon_client_or_none", lambda: _FakeClient())

    response = client.get("/readyz")
    body = response.json()
    assert body["ai_enabled"] is True
    assert body["app_env"] == "staging"


def test_readyz_never_leaks_a_credential_shaped_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            supabase_url="https://sekret-project.supabase.co",
            gemini_api_key="AIzaSuperSecretValue",
        ),
    )
    monkeypatch.setattr(health_module, "_anon_client_or_none", lambda: _FakeClient())

    response = client.get("/readyz")
    assert "sekret-project" not in response.text
    assert "AIzaSuperSecretValue" not in response.text
