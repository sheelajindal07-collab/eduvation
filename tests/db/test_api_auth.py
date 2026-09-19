"""Integration tests for POST /auth/sign-up and POST /auth/sign-in
against the real Supabase Auth (same project as everything else).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

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
        email-sending path. A rate-limit response is an infrastructure
        constraint of the shared test project, not an endpoint bug —
        confirmed by inspecting the literal error message rather than
        assumed, so this test can't accidentally mask a real 400."""
        email = f"bcion-signuptest-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up", json={"email": email, "password": "correct-horse-battery-staple-2"}
        )
        if response.status_code == 400:
            assert "rate limit" in response.json()["detail"].lower(), (
                f"Got a 400 that isn't the known rate-limit case: {response.json()}"
            )
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
        if response.status_code == 400:
            assert "rate limit" in response.json()["detail"].lower()
        else:
            assert response.status_code == 202
