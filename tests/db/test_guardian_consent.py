"""Live regression tests for the guardian-consent gate — CLAUDE.md's
non-negotiable ("Real minor accounts stay disabled until the consent and
safeguarding workflow is reviewed by a person"), built this session per
the owner's decision recorded in STATUS.md. Backs
`db/migrations/0004_guardian_consent.sql` and `app/api/guardian_consent.py`.

Skips as a whole (see `tests/db/conftest.py`'s `_guardian_consent_
migration_applied` check) until that migration is applied to the live
project. `LoggingEmailSender` is used throughout (never a real provider —
none is configured, see `app/notifications/logging_sender.py`); these
tests prove the DATABASE bookkeeping and the EmailSender WIRING are
correct, not that a real inbox is reached — that needs the owner to
provision a real provider, see STATUS.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.api.guardian_consent import create_guardian_consent_request
from app.db import get_anon_client, get_user_scoped_client
from app.main import app
from app.notifications.logging_sender import LoggingEmailSender

client = TestClient(app)

# Comfortably 18+/under-18 as of any date this suite will realistically run.
_ADULT_DOB = "1990-01-01"


def _minor_dob(age_years: int) -> str:
    today = date.today()
    try:
        dob = today.replace(year=today.year - age_years)
    except ValueError:  # Feb 29 on a non-leap target year
        dob = today.replace(year=today.year - age_years, day=28)
    return dob.isoformat()


_MINOR_DOB = _minor_dob(15)


@pytest.fixture
def stub_email_sender(monkeypatch: pytest.MonkeyPatch) -> LoggingEmailSender:
    """Replaces app.api.auth's EmailSender factory with one whose `.sent`
    a test can assert against — never a real provider (none is
    configured; see app/notifications/logging_sender.py)."""
    sender = LoggingEmailSender()
    monkeypatch.setattr("app.api.auth.get_email_sender", lambda: sender)
    return sender


@pytest.fixture
def confirmed_adult(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed 18+ user — mirrors test_api_auth.py's own
    `registered_user`, kept separate here so this file has no import-time
    dependency on that one."""
    email = f"bcion-consent-adult-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple-adult-1"
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)


@pytest.fixture
def confirmed_minor(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed under-18 user WITH the sign-up-time metadata
    app.api.auth.sign_up() would have set, but created directly via the
    admin API (mirrors `registered_user`'s own reasoning: sidesteps
    Supabase's own email-confirmation setting, which is orthogonal to
    what these tests check) — this simulates exactly the "Case B" bundle
    (session unavailable at sign-up, metadata durably stored regardless)
    app/api/guardian_consent.py's own module docstring describes.
    `student_accounts`/`guardian_consents` cascade-delete with the user
    (on delete cascade, db/migrations/0004_guardian_consent.sql), same
    pattern the `reviewer` fixture already relies on for `reviewers`."""
    email = f"bcion-consent-minor-{uuid.uuid4().hex[:12]}@example.com"
    guardian_email = f"bcion-guardian-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery-staple-minor-1"
    created = admin_client.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"date_of_birth": _MINOR_DOB, "guardian_email": guardian_email},
        }
    )
    user_id = created.user.id
    yield {
        "email": email,
        "password": password,
        "user_id": user_id,
        "guardian_email": guardian_email,
    }
    admin_client.auth.admin.delete_user(user_id)


class TestAdultSignUpAndSignInUnchanged:
    """Task requirement: "an 18+ sign-up is immediately usable, unchanged
    from today's behavior (no regression for adults -- this is
    important, verify it explicitly)"."""

    def test_18_plus_sign_up_reports_active_and_immediately_usable(
        self, admin_client: Client
    ) -> None:
        email = f"bcion-consent-signup-adult-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-9",
                "date_of_birth": _ADULT_DOB,
            },
        )
        if response.status_code == 429:
            return  # Supabase's own email-sending rate limit -- unrelated to this gate
        assert response.status_code in (201, 202)
        if response.status_code == 202:
            # Supabase's OWN email-confirmation setting, orthogonal to
            # the guardian-consent gate -- already proven not-immediately-
            # usable-for-an-unrelated-reason is fine here; the reliable,
            # unambiguous proof is test_confirmed_adult_signs_in_and_
            # gets_an_active_token below.
            users = admin_client.auth.admin.list_users()
            match = next((u for u in users if u.email == email), None)
            if match:
                admin_client.auth.admin.delete_user(match.id)
            return
        body = response.json()
        assert body["account_status"] == "active"
        assert body["access_token"] is not None
        assert len(body["access_token"]) > 20
        admin_client.auth.admin.delete_user(body["user_id"])

    def test_confirmed_adult_signs_in_and_gets_an_active_token(
        self, confirmed_adult: dict[str, str]
    ) -> None:
        """The unambiguous version of the above, sidestepping Supabase's
        own email-confirmation setting entirely (same reasoning
        test_api_auth.py's TestSignIn already applies via
        `registered_user`) -- this is the one that must never regress."""
        response = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["account_status"] == "active"
        assert body["user_id"] == confirmed_adult["user_id"]
        assert len(body["access_token"]) > 20


class TestUnder18SignUpValidation:
    def test_under_18_sign_up_without_guardian_email_is_rejected(self) -> None:
        email = f"bcion-consent-nogte-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-8",
                "date_of_birth": _MINOR_DOB,
                # guardian_email deliberately omitted
            },
        )
        assert response.status_code == 400
        assert "guardian_email" in response.json()["detail"]

    def test_under_18_sign_up_with_guardian_email_reports_pending_not_active(
        self, admin_client: Client, stub_email_sender: LoggingEmailSender
    ) -> None:
        """Task requirement: "the response should clearly indicate the
        account is pending guardian confirmation, not immediately usable
        -- do not silently let the student in". Tolerant of Supabase's
        own email-confirmation setting (both branches of app.api.auth.
        sign_up's `minor` handling return this same shape) -- the
        EmailSender-was-actually-called assertion is covered separately
        below (TestCreateGuardianConsentRequest), where it isn't
        ambiguous which branch ran."""
        email = f"bcion-consent-pending-{uuid.uuid4().hex[:12]}@example.com"
        guardian_email = f"bcion-guardian-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-7",
                "date_of_birth": _MINOR_DOB,
                "guardian_email": guardian_email,
            },
        )
        if response.status_code == 429:
            return
        assert response.status_code == 201
        body = response.json()
        assert body["account_status"] == "pending_guardian_consent"
        assert body["access_token"] is None
        assert body["message"]

        users = admin_client.auth.admin.list_users()
        match = next((u for u in users if u.email == email), None)
        if match:
            admin_client.auth.admin.delete_user(match.id)


class TestCreateGuardianConsentRequest:
    """Exercises app.api.guardian_consent.create_guardian_consent_request
    directly against a real, already-signed-in student — same technique
    test_api_auth.py's TestGuestToAccountPlanMigration already uses to
    sidestep the sign-up email-confirmation ambiguity for testing the
    underlying logic reliably."""

    def test_creates_pending_account_generates_token_and_calls_email_sender(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        # Reuse the confirmed_adult fixture purely as "a real user with a
        # real session" -- the age/minor decision is the caller's job
        # (app.api.auth.sign_up already tests that), not this function's.
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]
        guardian_email = f"bcion-guardian-{uuid.uuid4().hex[:12]}@example.com"

        scoped_client = get_user_scoped_client(access_token)
        sender = LoggingEmailSender()
        try:
            create_guardian_consent_request(
                scoped_client,
                student_id=user_id,
                date_of_birth=date(2015, 1, 1),
                guardian_email=guardian_email,
                sender=sender,
            )
        finally:
            scoped_client.postgrest.aclose()

        account = (
            admin_client.table("student_accounts").select("*").eq("id", user_id).execute().data
        )
        assert len(account) == 1
        assert account[0]["account_status"] == "pending_guardian_consent"
        assert account[0]["date_of_birth"] == "2015-01-01"

        consents = (
            admin_client.table("guardian_consents")
            .select("*")
            .eq("student_id", user_id)
            .execute()
            .data
        )
        assert len(consents) == 1
        assert consents[0]["status"] == "pending"
        assert consents[0]["guardian_email"] == guardian_email
        assert consents[0]["token"]
        assert consents[0]["confirmed_at"] is None

        assert len(sender.sent) == 1
        sent = sender.sent[0]
        assert sent["to"] == guardian_email
        assert consents[0]["token"] in sent["body"]
        assert "/consent/confirm?token=" in sent["body"]


class TestPendingAccountCannotSignIn:
    def test_pending_account_is_blocked_at_sign_in_with_a_clear_error(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        """`confirmed_minor` has NO student_accounts row yet (created
        directly via the admin API, bypassing app.api.auth.sign_up) --
        this specifically exercises the lazy-bootstrap-at-sign-in path
        (app.api.guardian_consent.enforce_guardian_consent_gate) and
        proves the account is blocked either way: whether the pending
        row already existed or is created on this very call."""
        response = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert response.status_code == 403
        assert "guardian" in response.json()["detail"].lower()

        # The lazy-create path must have generated a real request.
        account = (
            admin_client.table("student_accounts")
            .select("*")
            .eq("id", confirmed_minor["user_id"])
            .execute()
            .data
        )
        assert len(account) == 1
        assert account[0]["account_status"] == "pending_guardian_consent"
        assert len(stub_email_sender.sent) == 1
        assert stub_email_sender.sent[0]["to"] == confirmed_minor["guardian_email"]

        # A second attempt hits the "already pending" branch, not
        # lazy-create again -- must still block, and must NOT re-send.
        second = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert second.status_code == 403
        assert len(stub_email_sender.sent) == 1


class TestConfirmationFlow:
    def test_confirming_a_valid_token_activates_the_account_and_sign_in_then_works(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        # Trigger lazy-creation of the pending request (see class above).
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403

        token = (
            admin_client.table("guardian_consents")
            .select("token")
            .eq("student_id", confirmed_minor["user_id"])
            .execute()
            .data[0]["token"]
        )

        confirm = client.get(f"/consent/confirm?token={token}")
        assert confirm.status_code == 200
        assert "no longer valid" not in confirm.text.lower()

        account = (
            admin_client.table("student_accounts")
            .select("account_status")
            .eq("id", confirmed_minor["user_id"])
            .execute()
            .data
        )
        assert account[0]["account_status"] == "active"

        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert sign_in.status_code == 200
        assert sign_in.json()["account_status"] == "active"

    def test_already_confirmed_token_is_rejected_with_the_generic_error(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        token = (
            admin_client.table("guardian_consents")
            .select("token")
            .eq("student_id", confirmed_minor["user_id"])
            .execute()
            .data[0]["token"]
        )
        first = client.get(f"/consent/confirm?token={token}")
        assert "no longer valid" not in first.text.lower()

        second = client.get(f"/consent/confirm?token={token}")
        assert second.status_code == 200
        assert "no longer valid" in second.text.lower()

    def test_expired_token_is_rejected_with_the_generic_error(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        row = (
            admin_client.table("guardian_consents")
            .select("id, token")
            .eq("student_id", confirmed_minor["user_id"])
            .execute()
            .data[0]
        )
        # Service-role only -- backdates the row to simulate having aged
        # past the 72-hour window, without waiting 72 real hours.
        admin_client.table("guardian_consents").update({"expires_at": "2000-01-01T00:00:00Z"}).eq(
            "id", row["id"]
        ).execute()

        response = client.get(f"/consent/confirm?token={row['token']}")
        assert response.status_code == 200
        assert "no longer valid" in response.text.lower()

        account = (
            admin_client.table("student_accounts")
            .select("account_status")
            .eq("id", confirmed_minor["user_id"])
            .execute()
            .data
        )
        assert account[0]["account_status"] == "pending_guardian_consent"

    def test_malformed_or_nonexistent_token_degrades_gracefully_never_a_500(self) -> None:
        response = client.get("/consent/confirm?token=not-a-real-token-at-all")
        assert response.status_code == 200
        assert "no longer valid" in response.text.lower()

    def test_missing_token_degrades_gracefully_never_a_500(self) -> None:
        response = client.get("/consent/confirm")
        assert response.status_code == 200
        assert "no longer valid" in response.text.lower()


class TestTokenNeverReadableThroughNormalRls:
    """Task requirement: "the TOKEN itself must never be readable via any
    RLS-scoped client, only matchable via the confirmation endpoint's own
    server-side lookup." Proves that property directly, not just by
    absence of a route that would expose it."""

    def test_students_own_rls_scoped_client_cannot_select_guardian_consents_at_all(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        # Sign in again now that lazy-creation ran -- still blocked
        # (account is still pending), but we only need a valid access
        # token here, which authenticate() never returns for a pending
        # account. So sign the student in at the Supabase layer directly
        # (bypassing this app's own gate) purely to get a real token to
        # probe RLS with, same as any other RLS test in this suite would
        # obtain one.
        raw = get_anon_client()
        try:
            session = raw.auth.sign_in_with_password(
                {"email": confirmed_minor["email"], "password": confirmed_minor["password"]}
            )
        finally:
            raw.postgrest.aclose()
        scoped = get_user_scoped_client(session.session.access_token)
        try:
            seen = (
                scoped.table("guardian_consents")
                .select("*")
                .eq("student_id", confirmed_minor["user_id"])
                .execute()
            )
            assert seen.data == [], (
                "a student's own RLS-scoped client must never be able to read "
                "their own guardian_consents row (the token) directly"
            )
        finally:
            scoped.postgrest.aclose()

    def test_students_own_rls_scoped_client_cannot_self_activate_via_update(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        """The core bypass this whole feature exists to prevent: a
        student with the right password must not be able to flip their
        own account_status to 'active' directly."""
        client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        raw = get_anon_client()
        try:
            session = raw.auth.sign_in_with_password(
                {"email": confirmed_minor["email"], "password": confirmed_minor["password"]}
            )
        finally:
            raw.postgrest.aclose()
        scoped = get_user_scoped_client(session.session.access_token)
        try:
            result = (
                scoped.table("student_accounts")
                .update({"account_status": "active"})
                .eq("id", confirmed_minor["user_id"])
                .execute()
            )
            assert result.data == [], "a student must not be able to self-activate via UPDATE"
        finally:
            scoped.postgrest.aclose()

        account = (
            admin_client.table("student_accounts")
            .select("account_status")
            .eq("id", confirmed_minor["user_id"])
            .execute()
            .data
        )
        assert account[0]["account_status"] == "pending_guardian_consent"


class TestUnder18RawInsertCannotClaimActive:
    """Task requirement (defense in depth, db/migrations/0004_guardian_
    consent.sql's `enforce_account_status_matches_age` trigger): even a
    caller with a genuinely valid access token for their own under-18
    account cannot bypass app/api/guardian_consent.py by inserting
    `student_accounts` directly with account_status='active'."""

    def test_direct_insert_of_active_for_an_under_18_dob_is_rejected(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        scoped = get_user_scoped_client(sign_in.json()["access_token"])
        try:
            raised = False
            try:
                scoped.table("student_accounts").insert(
                    {
                        "id": confirmed_adult["user_id"],
                        "date_of_birth": _MINOR_DOB,
                        "account_status": "active",
                    }
                ).execute()
            except Exception:  # noqa: BLE001 — any rejection is the point
                raised = True
            assert raised, "the database trigger must reject an under-18 row inserted as active"
        finally:
            scoped.postgrest.aclose()
