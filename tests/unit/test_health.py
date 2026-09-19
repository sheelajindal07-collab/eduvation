"""M0 smoke check: the application shell boots and reports its own
configuration honestly."""

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
