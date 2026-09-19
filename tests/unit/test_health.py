"""M0 smoke check: the application shell boots and reports its own
configuration honestly."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
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
    from CLAUDE.md, applied to the app's own self-report. Env vars are
    cleared explicitly so this doesn't depend on the developer machine's
    ambient state."""
    for var in (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

    response = client.get("/healthz")
    body = response.json()
    assert body["db_configured"] is False
    assert body["ai_configured"] is False

    get_settings.cache_clear()
