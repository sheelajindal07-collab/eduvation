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
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
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

    def test_under_18_sign_up_with_guardian_email_same_as_own_email_is_rejected(self) -> None:
        """Adversarial review, 2026-09-21 (HIGH): nothing previously
        stopped a self-declared minor from entering their OWN email as
        guardian_email -- once a real email provider is configured
        (none is today, app/notifications/logging_sender.py), that minor
        could receive their own 'guardian confirmation' email and
        self-confirm instantly. Checked case-insensitively (mixed-case
        variant) since Supabase Auth itself treats email case-
        insensitively."""
        email = f"bcion-consent-selfguardian-{uuid.uuid4().hex[:12]}@example.com"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-6",
                "date_of_birth": _MINOR_DOB,
                "guardian_email": email.upper(),
            },
        )
        assert response.status_code == 400
        assert "guardian_email" in response.json()["detail"]

    def test_under_18_sign_up_with_plus_tagged_own_email_as_guardian_is_rejected(self) -> None:
        """Adversarial re-check, 2026-09-21 (MEDIUM), of the fix above:
        the exact-match (post-casefold) comparison it introduced was
        live-reproduced as bypassable via '+tag' sub-addressing —
        `local+anything@domain` is delivered to the same inbox as
        `local@domain` on Gmail, Outlook/M365, ProtonMail, FastMail, etc.
        (RFC 5233 "Sieve Subaddress"), so a minor could type
        `name+guardian@gmail.com` as guardian_email, receive the
        "guardian confirmation" email in their own inbox, and
        self-confirm -- the exact defeat the check above exists to
        prevent, just via a different-looking string. See
        `app.api.auth._normalize_email_for_self_check`."""
        email = f"bcion-consent-plustag-{uuid.uuid4().hex[:12]}@example.com"
        local, _, domain = email.partition("@")
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-6",
                "date_of_birth": _MINOR_DOB,
                "guardian_email": f"{local}+guardian@{domain}",
            },
        )
        assert response.status_code == 400
        assert "guardian_email" in response.json()["detail"]

    def test_under_18_sign_up_with_genuinely_different_guardian_dotted_email_is_accepted(
        self, admin_client: Client, stub_email_sender: LoggingEmailSender
    ) -> None:
        """Guards the other direction of the same fix: dot-stripping was
        deliberately NOT added to `_normalize_email_for_self_check`
        (Gmail treats dots as insignificant, but Outlook/M365 and many
        Indian ISPs/school email systems do not -- two different real
        people can differ only by a dot on those providers), so a
        genuinely different guardian address that merely happens to
        contain a dot must still be accepted, not wrongly rejected as
        'the same email'."""
        email = f"bcion-consent-dotguardian-{uuid.uuid4().hex[:12]}@example.com"
        local, _, domain = email.partition("@")
        guardian_email = f"{local}.guardian@{domain}"
        response = client.post(
            "/auth/sign-up",
            json={
                "email": email,
                "password": "correct-horse-battery-staple-6",
                "date_of_birth": _MINOR_DOB,
                "guardian_email": guardian_email,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending_guardian_consent"
        users = admin_client.auth.admin.list_users()
        match = next((u for u in users if u.email == email.casefold()), None)
        if match is not None:
            admin_client.auth.admin.delete_user(match.id)

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
    underlying logic reliably.

    This is, precisely, the path that used to be silently broken by the
    RETURNING/RLS conflict db/migrations/0005_guardian_consent_request_rpc.sql
    fixes (see that migration's own module comment and
    app.api.guardian_consent.create_guardian_consent_request's docstring):
    `scoped_client` below is a REAL signed-in student's own session, not
    the service-role `admin_client` — exactly the caller that used to get
    an unhandled `APIError` ("new row violates row-level security policy
    for table guardian_consents") out of the old two-plain-insert
    implementation. `admin_client` is used only to verify what actually
    landed in the database afterward, never to perform the write being
    tested."""

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


class TestCreateGuardianConsentRequestRpcDirectly:
    """Regression test for the exact bug
    db/migrations/0005_guardian_consent_request_rpc.sql fixes, isolated
    from app.api.guardian_consent.create_guardian_consent_request's own
    Python wrapper: calls the `create_guardian_consent_request` SQL
    function directly, as a real signed-in student, and proves it
    succeeds and returns a real token. Before the fix, the equivalent
    plain `client.table("guardian_consents").insert(...).execute()` (what
    the Python wrapper used to do) failed outright with "new row violates
    row-level security policy for table guardian_consents" — supabase-py
    defaults to `Prefer: return=representation`, and Postgres applies
    `guardian_consents`' SELECT policies (there are none, by design — see
    0004_guardian_consent.sql) to the RETURNING re-select, not just the
    INSERT policy's WITH CHECK to the write. This test would have failed
    with exactly that error against the pre-fix implementation."""

    def test_rpc_succeeds_as_a_real_signed_in_student_and_returns_a_real_token(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]
        guardian_email = f"bcion-guardian-rpc-{uuid.uuid4().hex[:12]}@example.com"

        scoped = get_user_scoped_client(access_token)
        try:
            result = scoped.rpc(
                "create_guardian_consent_request",
                {"p_date_of_birth": "2015-06-01", "p_guardian_email": guardian_email},
            ).execute()
        finally:
            scoped.postgrest.aclose()

        token = result.data
        assert token is not None, (
            "the RPC must return a real token for a fresh request from a real "
            "signed-in student -- a None here means the insert was silently "
            "blocked (the exact RETURNING/RLS bug this migration fixes) or "
            "treated as an idempotent duplicate when it should not have been"
        )
        assert isinstance(token, str)
        # 32 random bytes, hex-encoded (0004_guardian_consent.sql's
        # enforce_guardian_consent_server_token) -- 64 hex characters.
        assert len(token) == 64

        account = (
            admin_client.table("student_accounts").select("*").eq("id", user_id).execute().data
        )
        assert len(account) == 1
        assert account[0]["account_status"] == "pending_guardian_consent"

        consents = (
            admin_client.table("guardian_consents")
            .select("*")
            .eq("student_id", user_id)
            .execute()
            .data
        )
        assert len(consents) == 1
        assert consents[0]["token"] == token
        assert consents[0]["guardian_email"] == guardian_email
        assert consents[0]["status"] == "pending"

        admin_client.table("guardian_consents").delete().eq("student_id", user_id).execute()

    def test_rpc_returns_none_and_sends_no_second_row_for_an_already_pending_student(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        """Idempotency, now enforced at the SQL layer via `ON CONFLICT
        (student_id) WHERE status = 'pending' DO NOTHING` rather than by
        the Python layer catching a unique-violation exception."""
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]

        scoped = get_user_scoped_client(access_token)
        try:
            first = scoped.rpc(
                "create_guardian_consent_request",
                {
                    "p_date_of_birth": "2015-06-01",
                    "p_guardian_email": "guardian-first@example.com",
                },
            ).execute()
            assert first.data is not None

            second = scoped.rpc(
                "create_guardian_consent_request",
                {
                    "p_date_of_birth": "2015-06-01",
                    "p_guardian_email": "guardian-second@example.com",
                },
            ).execute()
        finally:
            scoped.postgrest.aclose()

        assert second.data is None

        consents = (
            admin_client.table("guardian_consents")
            .select("*")
            .eq("student_id", user_id)
            .execute()
            .data
        )
        assert len(consents) == 1, "the second call must not have created a second row"
        assert consents[0]["guardian_email"] == "guardian-first@example.com"

        admin_client.table("guardian_consents").delete().eq("student_id", user_id).execute()


class TestCreateGuardianConsentRequestRpcCannotActOnAnotherStudent:
    """Task requirement: prove spoofing another student's id is
    structurally impossible, not just policy-checked — the RPC takes no
    student_id parameter at all (contra the old RLS-policy-checked
    design: `guardian_consents_insert_own`'s `with check (auth.uid() =
    student_id)` compared a CLIENT-SUPPLIED value to auth.uid(); this RPC
    never accepts one to compare in the first place). Uses two distinct,
    real, signed-in students in the same test (CLAUDE.md: "Cross-user
    access (guest, student A, student B, reviewer) is tested every time
    auth, RLS or publication changes")."""

    def test_rpc_always_attributes_the_new_row_to_the_callers_own_auth_uid(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
    ) -> None:
        student_a_id, client_a = student_a
        student_b_id, client_b = student_b

        result_a = client_a.rpc(
            "create_guardian_consent_request",
            {
                "p_date_of_birth": "2015-01-01",
                "p_guardian_email": f"guardian-a-{uuid.uuid4().hex[:8]}@example.com",
            },
        ).execute()
        result_b = client_b.rpc(
            "create_guardian_consent_request",
            {
                "p_date_of_birth": "2016-01-01",
                "p_guardian_email": f"guardian-b-{uuid.uuid4().hex[:8]}@example.com",
            },
        ).execute()

        assert result_a.data is not None
        assert result_b.data is not None
        assert result_a.data != result_b.data, "each student must get their own, distinct token"

        consent_a = (
            admin_client.table("guardian_consents")
            .select("student_id, token")
            .eq("token", result_a.data)
            .execute()
            .data
        )
        consent_b = (
            admin_client.table("guardian_consents")
            .select("student_id, token")
            .eq("token", result_b.data)
            .execute()
            .data
        )
        assert len(consent_a) == 1
        assert len(consent_b) == 1
        assert consent_a[0]["student_id"] == student_a_id, (
            "student A's own call must create a row for student A, never anyone else"
        )
        assert consent_b[0]["student_id"] == student_b_id, (
            "student B's own call must create a row for student B, never anyone else"
        )
        assert consent_a[0]["student_id"] != consent_b[0]["student_id"]

        admin_client.table("guardian_consents").delete().eq("student_id", student_a_id).execute()
        admin_client.table("guardian_consents").delete().eq("student_id", student_b_id).execute()


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


@pytest.fixture
def seeded_pathway_for_guardian_tests(admin_client: Client) -> Iterator[dict[str, Any]]:
    """Same seed-a-pathway pattern as tests/db/test_api_plans.py's own
    `seeded_pathway_for_plans` — kept local to this file rather than
    imported/shared, since a fixture defined inside one test_*.py file is
    invisible to every other one (see tests/db/conftest.py's
    `second_reviewer` docstring for the exact prior incident that
    established this pattern)."""
    career = (
        admin_client.table("careers")
        .insert({"name": "Guardian-consent test career (SYNTHETIC)"})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "Guardian-consent test pathway (SYNTHETIC)",
                "description": "Seeded by tests/db/test_guardian_consent.py",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway}
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestTokenAndExpiryAreServerGenerated:
    """CRITICAL finding, adversarial review 2026-09-21: the INSERT RLS
    policy on `guardian_consents` constrains only `student_id` — nothing
    stopped a caller from choosing their own `token` (and `expires_at`),
    then calling the anon-grantable `confirm_guardian_consent(p_token)`
    RPC with that self-chosen token to activate their own account with
    zero real guardian involvement. Proves the fix
    (`enforce_guardian_consent_server_token`, db/migrations/
    0004_guardian_consent.sql): a client-supplied `token`/`expires_at` is
    silently OVERWRITTEN, not rejected — the row is still created (that's
    fine, useful even), just never with the attacker's chosen values."""

    def test_client_supplied_token_is_overwritten_and_never_confirms(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]
        attacker_chosen_token = "attacker-chosen-not-random-" + uuid.uuid4().hex

        scoped = get_user_scoped_client(access_token)
        try:
            result = (
                scoped.table("guardian_consents")
                .insert(
                    {
                        "student_id": user_id,
                        "guardian_email": "not-a-real-guardian@example.com",
                        "token": attacker_chosen_token,
                    }
                )
                .execute()
            )
        finally:
            scoped.postgrest.aclose()

        # The row IS created (a client-supplied token is overwritten,
        # not rejected outright) but never with the attacker's value.
        assert len(result.data) == 1
        assert result.data[0]["token"] != attacker_chosen_token

        real_token = (
            admin_client.table("guardian_consents")
            .select("token")
            .eq("student_id", user_id)
            .execute()
            .data[0]["token"]
        )
        assert real_token != attacker_chosen_token
        assert real_token == result.data[0]["token"]

        # The core proof: the attacker's own chosen value can never
        # activate anything via the public confirmation endpoint.
        attacker_confirm = client.get(f"/consent/confirm?token={attacker_chosen_token}")
        assert attacker_confirm.status_code == 200
        assert "no longer valid" in attacker_confirm.text.lower()

        admin_client.table("guardian_consents").delete().eq("student_id", user_id).execute()

    def test_client_supplied_expires_at_is_also_overwritten(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        """Same trigger, same reasoning, for `expires_at` — an attacker
        setting a far-future expiry would otherwise (if not for this fix)
        make their own request never age out."""
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]

        scoped = get_user_scoped_client(access_token)
        try:
            result = (
                scoped.table("guardian_consents")
                .insert(
                    {
                        "student_id": user_id,
                        "guardian_email": "not-a-real-guardian-2@example.com",
                        "expires_at": "2099-01-01T00:00:00+00:00",
                    }
                )
                .execute()
            )
        finally:
            scoped.postgrest.aclose()

        expires_at = datetime.fromisoformat(result.data[0]["expires_at"])
        assert expires_at.year < 2099
        # Roughly 72 hours out (the named assumption) — generous
        # tolerance for however long the test itself takes to run.
        assert expires_at < datetime.now(UTC) + timedelta(hours=73)

        admin_client.table("guardian_consents").delete().eq("student_id", user_id).execute()


class TestOnlyOnePendingConsentPerStudent:
    """MEDIUM finding, adversarial review 2026-09-21: idempotency was
    previously enforced only in Python (create_guardian_consent_request
    catching a unique-violation on the *student_accounts* insert, before
    ever reaching this table) — a direct API caller could otherwise
    insert unlimited guardian_consents rows with arbitrary guardian_email
    values (a spam vector once a real provider is configured). Proves the
    DB-level partial unique index (`guardian_consents_one_pending_per_
    student`) stops a second pending row for the same student regardless
    of caller."""

    def test_second_pending_insert_for_same_student_is_rejected(
        self, admin_client: Client, confirmed_adult: dict[str, str]
    ) -> None:
        sign_in = client.post(
            "/auth/sign-in",
            json={"email": confirmed_adult["email"], "password": confirmed_adult["password"]},
        )
        assert sign_in.status_code == 200
        access_token = sign_in.json()["access_token"]
        user_id = confirmed_adult["user_id"]

        scoped = get_user_scoped_client(access_token)
        try:
            first = (
                scoped.table("guardian_consents")
                .insert({"student_id": user_id, "guardian_email": "guardian-one@example.com"})
                .execute()
            )
            assert len(first.data) == 1

            with pytest.raises(APIError) as exc_info:
                scoped.table("guardian_consents").insert(
                    {"student_id": user_id, "guardian_email": "guardian-two@example.com"}
                ).execute()
            assert exc_info.value.code == "23505"
        finally:
            scoped.postgrest.aclose()

        admin_client.table("guardian_consents").delete().eq("student_id", user_id).execute()


class TestAccountActiveGatesOtherOwnRowTables:
    """HIGH finding, adversarial review 2026-09-21: the guardian-consent
    gate was previously enforced ONLY inside app.api.auth.authenticate()
    — never backed by RLS on saved_plans/student_profiles, the tables
    that actually hold a student's data. Proves `account_active(auth.
    uid())` (ANDed into both own-row policies, db/migrations/
    0004_guardian_consent.sql) denies a pending account's own-row access
    at the database layer even with a real, valid access token obtained
    by bypassing this app's own gate entirely — the same raw
    `sign_in_with_password` technique `TestTokenNeverReadableThroughNormalRls`
    above uses to prove the same thing for the token itself."""

    def _raw_session_bypassing_the_app_gate(self, email: str, password: str) -> str:
        raw = get_anon_client()
        try:
            session = raw.auth.sign_in_with_password({"email": email, "password": password})
        finally:
            raw.postgrest.aclose()
        assert session.session is not None
        return session.session.access_token

    def test_pending_students_own_token_cannot_read_their_saved_plans_row(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
        seeded_pathway_for_guardian_tests: dict[str, Any],
    ) -> None:
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403  # lazy-creates the pending student_accounts row

        # Service role writes a saved_plans row directly for this
        # student — simulates data that exists regardless of how it got
        # there; the point is what a PENDING account's own token can
        # read now, not how the row came to exist.
        admin_client.table("saved_plans").insert(
            {
                "student_id": confirmed_minor["user_id"],
                "pathway_id": seeded_pathway_for_guardian_tests["pathway"]["id"],
            }
        ).execute()

        access_token = self._raw_session_bypassing_the_app_gate(
            confirmed_minor["email"], confirmed_minor["password"]
        )
        scoped = get_user_scoped_client(access_token)
        try:
            seen = (
                scoped.table("saved_plans")
                .select("*")
                .eq("student_id", confirmed_minor["user_id"])
                .execute()
            )
            assert seen.data == [], (
                "account_active(auth.uid()) must deny a pending account's own "
                "saved_plans row, even with a real, valid access token obtained "
                "outside app.api.auth.authenticate()"
            )
        finally:
            scoped.postgrest.aclose()

        admin_client.table("saved_plans").delete().eq(
            "student_id", confirmed_minor["user_id"]
        ).execute()

    def test_pending_students_own_token_cannot_read_their_student_profile_row(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403

        admin_client.table("student_profiles").insert(
            {"id": confirmed_minor["user_id"], "current_class": "10"}
        ).execute()

        access_token = self._raw_session_bypassing_the_app_gate(
            confirmed_minor["email"], confirmed_minor["password"]
        )
        scoped = get_user_scoped_client(access_token)
        try:
            seen = (
                scoped.table("student_profiles")
                .select("*")
                .eq("id", confirmed_minor["user_id"])
                .execute()
            )
            assert seen.data == [], (
                "account_active(auth.uid()) must deny a pending account's own "
                "student_profiles row too"
            )
        finally:
            scoped.postgrest.aclose()

        admin_client.table("student_profiles").delete().eq(
            "id", confirmed_minor["user_id"]
        ).execute()


class TestCrossUserAccessMatrix:
    """LOW finding, adversarial review 2026-09-21: CLAUDE.md requires
    "Cross-user access (guest, student A, student B, reviewer) is tested
    every time auth, RLS or publication changes" — this file didn't yet
    exercise the student_b/guest_client/reviewer fixtures at all before
    this. Mirrors tests/db/test_api_plans.py's own cross-user tests."""

    def test_student_b_cannot_read_student_as_student_accounts_row(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        student_b: tuple[str, Client],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403  # lazy-creates the row this test needs to exist

        _user_b_id, client_b = student_b
        seen = (
            client_b.table("student_accounts")
            .select("*")
            .eq("id", confirmed_minor["user_id"])
            .execute()
        )
        assert seen.data == [], "student B must never see student A's student_accounts row"

    def test_student_b_cannot_insert_a_guardian_consents_row_for_student_a(
        self,
        confirmed_minor: dict[str, str],
        student_b: tuple[str, Client],
    ) -> None:
        _user_b_id, client_b = student_b
        raised = False
        try:
            client_b.table("guardian_consents").insert(
                {
                    "student_id": confirmed_minor["user_id"],
                    "guardian_email": "student-b-attacker@example.com",
                }
            ).execute()
        except Exception:  # noqa: BLE001 — any rejection is the point
            raised = True
        assert raised, "student B must not be able to insert a row for student A's student_id"

    def test_guest_cannot_read_student_accounts(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        guest_client: Client,
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403

        seen = (
            guest_client.table("student_accounts")
            .select("*")
            .eq("id", confirmed_minor["user_id"])
            .execute()
        )
        assert seen.data == [], "a guest (anon) client must never read student_accounts"

    def test_guest_cannot_read_guardian_consents(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        guest_client: Client,
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403

        seen = (
            guest_client.table("guardian_consents")
            .select("*")
            .eq("student_id", confirmed_minor["user_id"])
            .execute()
        )
        assert seen.data == [], "a guest (anon) client must never read guardian_consents"

    def test_guest_cannot_insert_guardian_consents(self, guest_client: Client) -> None:
        raised = False
        try:
            guest_client.table("guardian_consents").insert(
                {
                    "student_id": str(uuid.uuid4()),
                    "guardian_email": "guest-attacker@example.com",
                }
            ).execute()
        except Exception:  # noqa: BLE001
            raised = True
        assert raised, "an anon (guest) client must not be able to insert a guardian_consents row"

    def test_reviewer_has_no_special_access_to_student_accounts_or_guardian_consents(
        self,
        admin_client: Client,
        confirmed_minor: dict[str, str],
        reviewer: tuple[str, Client],
        stub_email_sender: LoggingEmailSender,
    ) -> None:
        """The reviewer role governs the public knowledge base (db/
        migrations/0001_init.sql), not the student vault — mirrors
        tests/db/test_api_plans.py's identical check on saved_plans."""
        blocked = client.post(
            "/auth/sign-in",
            json={"email": confirmed_minor["email"], "password": confirmed_minor["password"]},
        )
        assert blocked.status_code == 403

        _reviewer_id, reviewer_client = reviewer
        accounts_seen = (
            reviewer_client.table("student_accounts")
            .select("*")
            .eq("id", confirmed_minor["user_id"])
            .execute()
        )
        assert accounts_seen.data == []

        consents_seen = (
            reviewer_client.table("guardian_consents")
            .select("*")
            .eq("student_id", confirmed_minor["user_id"])
            .execute()
        )
        assert consents_seen.data == []
