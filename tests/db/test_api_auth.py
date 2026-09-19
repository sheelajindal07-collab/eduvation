"""Integration tests for POST /auth/sign-up and POST /auth/sign-in
against the real Supabase Auth (same project as everything else).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app

client = TestClient(app)


@pytest.fixture
def registered_user(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed user with a known password, for testing
    sign-in without depending on the project's email-confirmation
    setting (sign-up itself is tested separately, tolerant of either
    setting)."""
    email = f"bcion-authtest-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple-1"
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)


class TestSignIn:
    def test_valid_credentials_return_access_token(
        self, registered_user: dict[str, str]
    ) -> None:
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == registered_user["user_id"]
        assert len(body["access_token"]) > 20  # a real JWT, not a placeholder

    def test_wrong_password_returns_401(self, registered_user: dict[str, str]) -> None:
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": "definitely-wrong"},
        )
        assert response.status_code == 401

    def test_nonexistent_email_also_returns_401_not_404(self) -> None:
        """No account-enumeration leak: a nonexistent email must look
        identical to a wrong password, not a distinguishable error."""
        response = client.post(
            "/auth/sign-in",
            json={"email": "definitely-not-registered@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401

    def test_returned_access_token_actually_works_for_rls(
        self, admin_client: Client, registered_user: dict[str, str]
    ) -> None:
        """The token isn't just well-formed — it genuinely authenticates
        against the live database, proven by successfully creating a
        student_profile row scoped to this exact user (RLS would reject
        a bad or mismatched token)."""
        response = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        token = response.json()["access_token"]

        from app.db import get_user_scoped_client

        scoped_client = get_user_scoped_client(token)
        try:
            result = (
                scoped_client.table("student_profiles")
                .insert(
                    {
                        "id": registered_user["user_id"],
                        "current_class": "Class 11",
                        "language": "en",
                    }
                )
                .execute()
            )
            assert result.data[0]["id"] == registered_user["user_id"]
        finally:
            admin_client.table("student_profiles").delete().eq(
                "id", registered_user["user_id"]
            ).execute()


class TestSignUp:
    def test_sign_up_new_email_succeeds_or_requires_confirmation(
        self, admin_client: Client
    ) -> None:
        """Tolerant of the project's email-confirmation setting (201 with
        a session, or 202 pending confirmation) — and of Supabase's own
        project-level email-sending rate limit, which this specific
        request genuinely can trigger since it exercises the real
        email-sending path.

        Checks the real HTTP status (429) Supabase Auth itself returns
        for a rate limit, not a guess at the message's wording
        (app/api/auth.py propagates exc.status from the underlying
        AuthApiError). The previous version of this test pattern-matched
        "rate limit" in the flattened-to-400 detail string, which flaked
        under the full suite's own combined sign-up load: Supabase has
        more than one rate-limit error code (`over_email_send_rate_limit`,
        `over_request_rate_limit`, confirmed live 2026-09-19) and not
        every variant's message necessarily contains that exact
        substring — the status code doesn't have that ambiguity."""
        email = f"bcion-signuptest-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up", json={"email": email, "password": "correct-horse-battery-staple-2"}
        )
        if response.status_code == 429:
            return

        assert response.status_code in (201, 202)
        if response.status_code == 201:
            user_id = response.json()["user_id"]
            admin_client.auth.admin.delete_user(user_id)
        else:
            # Pending confirmation: clean up via admin lookup by email
            # rather than leaving an orphaned unconfirmed account behind.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)

    def test_sign_up_with_already_registered_confirmed_email_does_not_error(
        self, registered_user: dict[str, str]
    ) -> None:
        """Supabase Auth's own anti-enumeration design: re-attempting
        sign-up with an email that's already registered and confirmed
        returns the SAME ambiguous "pending confirmation"-shaped response
        as a genuinely new email, never a distinguishing error — the
        same principle already applied to sign-in's error handling
        (never reveal whether an email exists). This is correct,
        intentional behaviour on Supabase's part, not a gap in this
        endpoint: it must not return 200/201 (that would mean a second
        real account got created), and must not return an error that
        leaks the email is taken."""
        response = client.post(
            "/auth/sign-up",
            json={"email": registered_user["email"], "password": "another-password-123"},
        )
        assert response.status_code != 201
        if response.status_code != 429:
            assert response.status_code == 202


@pytest.fixture
def seeded_pathway_for_migration(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": "Migration test career (SYNTHETIC)"})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "Migration test pathway (SYNTHETIC)",
                "description": "Seeded by tests/db/test_api_auth.py",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway}
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestGuestToAccountPlanMigration:
    """Tests app.api.auth._migrate_pending_plan directly against an
    already-confirmed, already-signed-in user (via POST /auth/sign-in,
    which sends no email) rather than through POST /auth/sign-up itself
    — sign-up's own email-sending path has a real, already-observed rate
    limit (see TestSignUp above), and re-triggering it here would make
    this test flaky for a reason that has nothing to do with the
    migration logic being tested. The one true end-to-end path (sign-up
    WITH a pending_plan, in a single request) is covered separately
    below, tolerant of the same rate limit as TestSignUp's tests."""

    def test_migrate_pending_plan_creates_a_real_row(
        self,
        admin_client: Client,
        registered_user: dict[str, str],
        seeded_pathway_for_migration: dict[str, Any],
    ) -> None:
        from app.api.auth import PendingPlan, _migrate_pending_plan
        from app.db import get_anon_client

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]

        fresh_client = get_anon_client()
        try:
            plan_id = _migrate_pending_plan(
                fresh_client,
                access_token,
                registered_user["user_id"],
                PendingPlan(
                    pathway_id=seeded_pathway_for_migration["pathway"]["id"],
                    estimated_additional_expenses=8000,
                    notes="Migrated from a guest session",
                ),
            )
        finally:
            fresh_client.postgrest.aclose()

        assert plan_id is not None
        row = admin_client.table("saved_plans").select("*").eq("id", plan_id).execute().data[0]
        assert row["student_id"] == registered_user["user_id"]
        assert row["pathway_id"] == seeded_pathway_for_migration["pathway"]["id"]
        assert row["notes"] == "Migrated from a guest session"
        admin_client.table("saved_plans").delete().eq("id", plan_id).execute()

    def test_migrate_pending_plan_for_nonexistent_pathway_returns_none_not_an_exception(
        self, registered_user: dict[str, str]
    ) -> None:
        """The core resilience property: a bad pending_plan must never
        raise up through sign-up and fail account creation."""
        import uuid as uuid_module

        from app.api.auth import PendingPlan, _migrate_pending_plan
        from app.db import get_anon_client

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": registered_user["email"], "password": registered_user["password"]},
        )
        access_token = sign_in.json()["access_token"]

        fresh_client = get_anon_client()
        try:
            plan_id = _migrate_pending_plan(
                fresh_client,
                access_token,
                registered_user["user_id"],
                PendingPlan(pathway_id=str(uuid_module.uuid4())),  # does not exist
            )
        finally:
            fresh_client.postgrest.aclose()
        assert plan_id is None


class TestSignUpWithPendingPlan:
    """The full end-to-end path: one real sign-up call that includes a
    pending_plan. Tolerant of the same email-sending rate limit as
    TestSignUp — this test's job is proving the wiring, and
    TestGuestToAccountPlanMigration above already proves the migration
    logic itself reliably without that dependency."""

    def test_sign_up_with_pending_plan_migrates_it_in_one_request(
        self, admin_client: Client, seeded_pathway_for_migration: dict[str, Any]
    ) -> None:
        email = f"bcion-migrationtest-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-3",
                "pending_plan": {
                    "pathway_id": seeded_pathway_for_migration["pathway"]["id"],
                    "notes": "From the sign-up flow itself",
                },
            },
        )
        if response.status_code == 429:
            return
        if response.status_code == 202:
            # Email confirmation required by this project's settings —
            # migration can't happen without a session; already covered
            # by the direct-function tests above.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            return

        assert response.status_code == 201
        body = response.json()
        assert body["migrated_plan_id"] is not None
        admin_client.table("saved_plans").delete().eq("id", body["migrated_plan_id"]).execute()
        admin_client.auth.admin.delete_user(body["user_id"])
