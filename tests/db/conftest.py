"""Shared fixtures for RLS/policy tests (`make test-db`).

These tests run against a REAL Supabase/Postgres project with
db/migrations/0001_init.sql applied — never against the owner/service
role for the assertions themselves (that would bypass RLS and hide a real
bug; docs/SECURITY.md). The whole module skips, with a clear reason, when
that project isn't configured — never silently "passes" a check that
didn't run.

The service-role key is used ONLY here, to create and tear down throwaway
test users for the guest / student A / student B / reviewer access
matrix. It is intentionally kept out of `app/core/config.py` — the
running application must never read it (docs/SECURITY.md).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import Client, create_client

from app.core.config import get_settings


class _TestOnlySettings(BaseSettings):
    """Test-only: reads the service-role key that the app itself never
    touches. Kept separate from app.core.config.Settings on purpose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_service_role_key: str | None = None


def _service_role_configured() -> bool:
    return bool(_TestOnlySettings().supabase_service_role_key)


_SKIP_REASON = (
    "SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY / SUPABASE_SERVICE_ROLE_KEY "
    "not fully set. RLS tests need a real project with "
    "db/migrations/0001_init.sql applied, plus a service-role key to "
    "create throwaway test users — see db/migrations/README.md and "
    ".env.example. Expected until the owner provisions their own "
    "Supabase project (docs/DECISIONS.md)."
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip every test collected under tests/db/ when unconfigured.

    A bare module-level `pytestmark` in this conftest.py does NOT apply to
    sibling test modules (that only works inside a test file itself) — so
    without this hook, tests/db/test_rls.py would try to run for real and
    fail with connection errors instead of skipping cleanly. Verified by
    running `pytest tests/db` before and after adding this hook.
    """
    if get_settings().db_configured and _service_role_configured():
        return
    skip_marker = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture(scope="module")
def admin_client() -> Client:
    """Service-role client. TEST SETUP/TEARDOWN ONLY — never used to make
    an assertion about what a real user can or can't do; that would defeat
    the point of testing RLS."""
    settings = get_settings()
    key = _TestOnlySettings().supabase_service_role_key
    assert settings.supabase_url is not None
    assert key is not None
    return create_client(settings.supabase_url, key)


def _create_test_user(admin: Client) -> tuple[str, Client]:
    """Creates a throwaway confirmed user, returns (user_id, a client
    authenticated as that user via a fresh password sign-in)."""
    settings = get_settings()
    email = f"bcion-test-{uuid.uuid4().hex[:12]}@example.invalid"
    password = uuid.uuid4().hex
    created = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id

    assert settings.supabase_url is not None
    assert settings.supabase_publishable_key is not None
    user_client = create_client(settings.supabase_url, settings.supabase_publishable_key)
    session = user_client.auth.sign_in_with_password({"email": email, "password": password})
    user_client.postgrest.auth(session.session.access_token)
    return user_id, user_client


@pytest.fixture
def guest_client() -> Client:
    """Anon-key client, no user session — the 'guest' row of the access
    matrix (docs/SECURITY.md)."""
    from app.db import get_anon_client

    return get_anon_client()


@pytest.fixture
def student_a(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def student_b(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def reviewer(admin_client: Client) -> Iterator[tuple[str, Client]]:
    user_id, client = _create_test_user(admin_client)
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield user_id, client
    admin_client.auth.admin.delete_user(user_id)  # cascades to reviewers row


@pytest.fixture
def synthetic_source(admin_client: Client) -> Iterator[str]:
    """A source row tagged synthetic, for tests that must never risk
    touching anything that looks like a real, verified fact."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": "TEST FIXTURE — not a real authority",
                "official_url": "https://example.invalid/not-a-real-source",
                "source_type": "synthetic",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()
