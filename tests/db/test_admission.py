"""Live regression tests for CONSENT-4 — the admission axis + safeguarding
schema. Backs `db/migrations/0012_admission_axis.sql` and
`db/migrations/0013_safeguarding_schema.sql` (renumbered mid-review from
0011/0012 — a migration-owner fix round found `0011_ai_usage.sql`, AI-4,
had taken the 0011 slot on `main` while this branch was in review; see
both files' own headers for the full collision story); source of truth is
docs/CONSENT.md (frozen design).

Skips as a whole (see `tests/db/conftest.py`'s `_admission_axis_migration_
applied` / `_safeguarding_schema_migration_applied` checks) until both
migrations are applied to the live stack.

No app/api or app/web route exists yet for any of this (CONSENT-4 is
database-layer only) — every call here goes straight at the RPCs and
tables through an ordinary RLS-scoped `supabase-py` client, the same way
tests/db/test_guardian_consent.py exercises 0004-0006.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import _create_test_user, _release_test_client, run_name

_ADULT_DOB = "1990-01-01"


def _code_hash(code: str) -> str:
    """Mirrors 0012's `encode(extensions.digest(p_code, 'sha256'), 'hex')`
    exactly — sha-256, lowercase hex. Used only to SEED a row as the
    service role; no test ever sends a hash instead of a plaintext code
    to an RPC, matching the real contract (the caller always supplies the
    plaintext code; only the database ever computes the hash)."""
    return hashlib.sha256(code.encode()).hexdigest()


def _future(hours: int = 72) -> str:
    return (datetime.now(tz=UTC) + timedelta(hours=hours)).isoformat()


def _past(hours: int = 1) -> str:
    return (datetime.now(tz=UTC) - timedelta(hours=hours)).isoformat()


def _make_account(
    admin_client: Client,
    user_id: str,
    *,
    status: str = "active",
    admitted: bool = False,
) -> None:
    """Seed a `student_accounts` row directly (service role, bypasses
    RLS) — the same shape a real sign-up would eventually produce, once
    the follow-up app-layer work this migration's own header flags lands.
    """
    payload: dict[str, Any] = {
        "id": user_id,
        "date_of_birth": _ADULT_DOB,
        "account_status": status,
    }
    if admitted:
        payload["admitted_at"] = datetime.now(tz=UTC).isoformat()
    admin_client.table("student_accounts").insert(payload).execute()


def _seed_invite(
    admin_client: Client, *, code: str, expires_at: str, used_by: str | None = None
) -> str:
    row = (
        admin_client.table("pilot_invites")
        .insert(
            {
                "code_hash": _code_hash(code),
                "expires_at": expires_at,
                "used_by": used_by,
                "used_at": datetime.now(tz=UTC).isoformat() if used_by else None,
            }
        )
        .execute()
    )
    return str(row.data[0]["id"])


@pytest.fixture
def safeguarding_staff_member(admin_client: Client) -> Iterator[tuple[str, Client]]:
    """Mirrors `tests/db/conftest.py`'s own `reviewer` fixture exactly,
    for `safeguarding_staff` instead of `reviewers` — kept local to this
    file since nothing else in the suite needs a safeguarding-staff
    identity yet."""
    user_id, client = _create_test_user(admin_client)
    admin_client.table("safeguarding_staff").insert({"user_id": user_id}).execute()
    yield user_id, client
    _release_test_client(client)
    admin_client.auth.admin.delete_user(user_id)


# =====================================================================
# THE GAP CONSENT-4 MUST CLOSE (docs/CONSENT.md section 7) — is_admitted()
# ANDed into saved_plans'/student_profiles' write policies.
# =====================================================================
class TestIsAdmittedGateOnTheStudentVault:
    def test_admitted_student_can_still_write_saved_plans_and_profile(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """No regression for an admitted student — the task's own
        requirement: 'an admitted student A should still pass'."""
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=True)

        career = admin_client.table("careers").insert({"name": run_name("QA admission career")})
        career_id = career.execute().data[0]["id"]
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career_id,
                    "name": run_name("QA admission pathway"),
                    "description": "fixture",
                }
            )
            .execute()
        )
        pathway_id = pathway.data[0]["id"]
        try:
            plan = (
                own_client.table("saved_plans")
                .insert({"student_id": user_id, "pathway_id": pathway_id})
                .execute()
            )
            assert plan.data, "an ADMITTED student's own saved_plans insert must succeed"

            profile = (
                own_client.table("student_profiles")
                .insert({"id": user_id, "current_class": "Class 10"})
                .execute()
            )
            assert profile.data, "an ADMITTED student's own student_profiles insert must succeed"
        finally:
            admin_client.table("saved_plans").delete().eq("student_id", user_id).execute()
            admin_client.table("student_profiles").delete().eq("id", user_id).execute()
            admin_client.table("pathways").delete().eq("id", pathway_id).execute()
            admin_client.table("careers").delete().eq("id", career_id).execute()

    def test_not_yet_admitted_active_student_cannot_write_saved_plans_or_profile(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """THE single most important new test in this task
        (docs/CONSENT.md section 7 / this task's own card): an account
        that is consent-settled ('active') but has never redeemed an
        invite (`admitted_at is null`) must be refused, not silently
        let through — this is exactly the gap that existed before 0012."""
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=False)

        career = admin_client.table("careers").insert({"name": run_name("QA gate career")})
        career_id = career.execute().data[0]["id"]
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career_id,
                    "name": run_name("QA gate pathway"),
                    "description": "fixture",
                }
            )
            .execute()
        )
        pathway_id = pathway.data[0]["id"]
        try:
            with pytest.raises(APIError) as exc_info:
                own_client.table("saved_plans").insert(
                    {"student_id": user_id, "pathway_id": pathway_id}
                ).execute()
            assert exc_info.value.code == "42501"

            with pytest.raises(APIError) as exc_info:
                own_client.table("student_profiles").insert(
                    {"id": user_id, "current_class": "Class 10"}
                ).execute()
            assert exc_info.value.code == "42501"

            still_no_plan = (
                admin_client.table("saved_plans").select("id").eq("student_id", user_id).execute()
            )
            assert not still_no_plan.data, "the refused insert must not have actually written a row"
            still_no_profile = (
                admin_client.table("student_profiles").select("id").eq("id", user_id).execute()
            )
            assert not still_no_profile.data
        finally:
            admin_client.table("saved_plans").delete().eq("student_id", user_id).execute()
            admin_client.table("student_profiles").delete().eq("id", user_id).execute()
            admin_client.table("pathways").delete().eq("id", pathway_id).execute()
            admin_client.table("careers").delete().eq("id", career_id).execute()

    def test_student_with_no_student_accounts_row_at_all_cannot_write_either(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """The REAL, live shape of the gap today: an ordinary adult
        sign-up (app/api/auth.py) never creates a `student_accounts` row
        at all (0012's own header names this as a known follow-up gap).
        `is_admitted()` must fail CLOSED for that case too — the opposite
        default from `account_active()`, which fails open for exactly
        this same 'no row' shape."""
        user_id, own_client = student_a
        # Deliberately no _make_account() call — this student has no
        # student_accounts row whatsoever, exactly like every real 18+
        # sign-up today.
        career = admin_client.table("careers").insert({"name": run_name("QA no-row career")})
        career_id = career.execute().data[0]["id"]
        try:
            with pytest.raises(APIError) as exc_info:
                own_client.table("student_profiles").insert(
                    {"id": user_id, "current_class": "Class 10"}
                ).execute()
            assert exc_info.value.code == "42501"
        finally:
            admin_client.table("student_profiles").delete().eq("id", user_id).execute()
            admin_client.table("careers").delete().eq("id", career_id).execute()

    def test_admitted_at_is_not_client_writable(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """docs/CONSENT.md section 7: 'a client must never be able to set
        admitted_at ... directly via the REST API bypassing redeem_invite'.
        student_accounts has no UPDATE policy for anyone (0004), which
        0012 does not add one to — this proves that still holds for the
        NEW column specifically, not just the pre-existing ones."""
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=False)
        try:
            result = (
                own_client.table("student_accounts")
                .update({"admitted_at": datetime.now(tz=UTC).isoformat()})
                .eq("id", user_id)
                .execute()
            )
            assert not result.data, "no UPDATE policy exists — this must match zero rows"
            row = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert row["admitted_at"] is None, "admitted_at must still be unset"
        finally:
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_admitted_at_is_not_client_writable_via_insert(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """CRITICAL, adversarial-review finding (this session, post-merge
        review): the UPDATE path was already proven closed above, but
        the INSERT path was not — 0004's `student_accounts_insert_own`
        policy only checks `auth.uid() = id`, saying nothing about
        `admitted_at`/`deletion_due_at`. Live-reproduced before the fix:
        a signed-in caller's own-row INSERT with `admitted_at: now()` in
        the payload succeeded outright and made `is_admitted()` true —
        a complete bypass of `redeem_invite()`, no real invite code ever
        redeemed. `enforce_student_accounts_insert_not_admitted()`
        (0012) now unconditionally nulls both columns on every non-
        service-role INSERT — this proves the CLIENT'S OWN insert can no
        longer set either, and that `is_admitted()` stays false
        afterward, exactly the docs/CONSENT.md section 7 guarantee this
        migration exists to hold."""
        user_id, own_client = student_a
        try:
            result = (
                own_client.table("student_accounts")
                .insert(
                    {
                        "id": user_id,
                        "date_of_birth": _ADULT_DOB,
                        "account_status": "active",
                        "admitted_at": datetime.now(tz=UTC).isoformat(),
                    }
                )
                .execute()
            )
            assert result.data, "the own-row INSERT itself is still permitted (0004)"
            assert result.data[0]["admitted_at"] is None, (
                "a client-supplied admitted_at must be silently nulled by the trigger, "
                "never honoured"
            )

            row = (
                admin_client.table("student_accounts")
                .select("admitted_at, deletion_due_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert row["admitted_at"] is None
            assert row["deletion_due_at"] is None

            is_admitted_now = own_client.rpc("is_admitted", {}).execute()
            assert is_admitted_now.data is False, (
                "self-admission bypass: is_admitted() must still be False after a "
                "client-side INSERT that tried to set admitted_at directly"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_service_role_insert_with_admitted_at_still_works(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """The trigger's `service_role` carve-out (mirrors
        `enforce_claims_workflow()`, 0003) must not break this suite's
        own `_make_account(..., admitted=True)` seeding pattern, used
        throughout this file and `tests/db/conftest.py`'s
        `admit_student()` — a regression here would silently invalidate
        every OTHER test in this module that seeds an admitted account."""
        user_id, _own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=True)
        try:
            row = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert row["admitted_at"] is not None, (
                "service_role's own INSERT must still be able to set admitted_at "
                "directly — this is what every other test's seeding relies on"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()


# =====================================================================
# CRITICAL/HIGH, adversarial-review findings (this session, post-merge
# review): is_admitted()/is_safeguarding_staff() as an unauthenticated
# and/or cross-user identity oracle. Both functions take an explicit
# `p_uid` not bound to the caller's own identity, and originally had NO
# grant restriction at all — an anon-key-only caller (no session
# whatsoever) could learn any real user's admission/staff status one
# uid at a time, and any signed-in `authenticated` caller could do the
# same for an arbitrary OTHER user. Two independent fixes, both proven
# below: (1) `revoke ... from public, anon` (grant to `authenticated`
# only — mirrors redeem_invite()'s own block), and (2) the function body
# itself now refuses to answer for anyone but the caller
# (`p_uid = auth.uid()`), so even an `authenticated` cross-uid probe
# gets `false`, never the real answer.
# =====================================================================
class TestAdmissionOracleClosed:
    def test_anon_key_only_caller_cannot_call_is_admitted_at_all(
        self, admin_client: Client, guest_client: Client, student_a: tuple[str, Client]
    ) -> None:
        victim_id, _victim_client = student_a
        _make_account(admin_client, victim_id, status="active", admitted=True)
        try:
            with pytest.raises(APIError) as exc_info:
                guest_client.rpc("is_admitted", {"p_uid": victim_id}).execute()
            assert exc_info.value.code == "42501", (
                "anon must be refused at the GRANT level (42501), not merely answered "
                "'false' -- a grant-level refusal proves anon has no path to this "
                "function at all, not just that this one uid happened to say no"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", victim_id).execute()

    def test_anon_key_only_caller_cannot_call_is_safeguarding_staff_at_all(
        self, guest_client: Client, safeguarding_staff_member: tuple[str, Client]
    ) -> None:
        staff_id, _staff_client = safeguarding_staff_member
        with pytest.raises(APIError) as exc_info:
            guest_client.rpc("is_safeguarding_staff", {"p_uid": staff_id}).execute()
        assert exc_info.value.code == "42501"

    def test_authenticated_caller_cannot_probe_another_users_admission_status(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
    ) -> None:
        """Student A is genuinely admitted; student B is an ordinary
        signed-in caller with no special privilege. B passing A's uid
        explicitly must get `false` — the real answer for A is `true`,
        so a `true` here would mean the oracle survived the grant fix."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        _make_account(admin_client, a_id, status="active", admitted=True)
        try:
            probe = b_client.rpc("is_admitted", {"p_uid": a_id}).execute()
            assert probe.data is False, (
                "authenticated caller B must not learn A's real admission status by "
                "passing A's uid explicitly"
            )
            # Sanity: the SAME account, asked about ITSELF (own session, default
            # p_uid = auth.uid()), still tells the truth — proves the `false`
            # above is the oracle being closed, not is_admitted() being broken
            # outright. Deliberately not re-checked via admin_client/service_role:
            # `auth.uid()` is only ever populated from a real user JWT's `sub`
            # claim, which a service-role connection does not carry, so
            # `p_uid = auth.uid()` would spuriously fail for THAT caller too —
            # a fact about service-role calls, not a regression in this gate.
            self_check = a_client.rpc("is_admitted", {}).execute()
            assert self_check.data is True, (
                "sanity check: A's own session still correctly reports admitted=True"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", a_id).execute()

    def test_authenticated_caller_cannot_probe_another_users_staff_status(
        self,
        student_a: tuple[str, Client],
        safeguarding_staff_member: tuple[str, Client],
    ) -> None:
        _student_id, student_client = student_a
        staff_id, _staff_client = safeguarding_staff_member
        probe = student_client.rpc("is_safeguarding_staff", {"p_uid": staff_id}).execute()
        assert probe.data is False, (
            "authenticated caller must not learn a DIFFERENT user's staff status by "
            "passing that user's uid explicitly"
        )


# =====================================================================
# invite_is_valid() — advisory-only, anon-callable, leaks nothing
# =====================================================================
class TestInviteIsValid:
    def test_true_for_a_real_unused_unexpired_code(
        self, admin_client: Client, guest_client: Client
    ) -> None:
        code = f"qa-admission-valid-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            result = guest_client.rpc("invite_is_valid", {"p_code": code}).execute()
            assert result.data is True
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()

    def test_false_for_a_wrong_code(self, admin_client: Client, guest_client: Client) -> None:
        code = f"qa-admission-wrongtest-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            result = guest_client.rpc(
                "invite_is_valid", {"p_code": "definitely-not-the-real-code"}
            ).execute()
            assert result.data is False
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()

    def test_false_for_an_expired_code(self, admin_client: Client, guest_client: Client) -> None:
        code = f"qa-admission-expired-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_past())
        try:
            result = guest_client.rpc("invite_is_valid", {"p_code": code}).execute()
            assert result.data is False
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()

    def test_false_for_an_already_used_code(
        self, admin_client: Client, guest_client: Client, student_a: tuple[str, Client]
    ) -> None:
        used_by_id, _ = student_a  # a REAL user id — pilot_invites.used_by is a real FK
        code = f"qa-admission-used-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future(), used_by=used_by_id)
        try:
            result = guest_client.rpc("invite_is_valid", {"p_code": code}).execute()
            assert result.data is False
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()

    def test_response_shape_is_a_bare_boolean_never_a_row(
        self, admin_client: Client, guest_client: Client
    ) -> None:
        """docs/CONSENT.md section 4: 'MUST NOT leak which specific code
        was checked, MUST NOT return a row'. A valid and an invalid call
        must have the IDENTICAL response shape (a bare bool), so there is
        nothing for a caller to distinguish beyond the boolean itself."""
        code = f"qa-admission-shape-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            valid = guest_client.rpc("invite_is_valid", {"p_code": code}).execute()
            invalid = guest_client.rpc("invite_is_valid", {"p_code": "nope"}).execute()
            assert isinstance(valid.data, bool)
            assert isinstance(invalid.data, bool)
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()


# =====================================================================
# redeem_invite() — the ONLY way to become admitted
# =====================================================================
class TestRedeemInvite:
    def test_requires_an_authenticated_session(
        self, guest_client: Client
    ) -> None:
        """Granted to `authenticated` only, WITH an explicit `revoke ...
        from public` (0012) — an anon caller has no EXECUTE privilege on
        this function at all, so the refusal is a grant-level 42501, not
        merely the internal auth.uid() check (defense in depth; see
        0012's own comment for the live-verified finding this closes)."""
        with pytest.raises(APIError) as exc_info:
            guest_client.rpc("redeem_invite", {"p_code": "anything"}).execute()
        assert exc_info.value.code == "42501"

    def test_happy_path_admits_an_active_not_yet_admitted_account(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=False)
        code = f"qa-admission-redeem-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            result = own_client.rpc("redeem_invite", {"p_code": code}).execute()
            assert result.data is True

            account = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert account["admitted_at"] is not None

            invite = (
                admin_client.table("pilot_invites")
                .select("used_by, used_at")
                .eq("code_hash", _code_hash(code))
                .execute()
                .data[0]
            )
            assert invite["used_by"] == user_id
            assert invite["used_at"] is not None

            is_admitted_now = own_client.rpc("is_admitted", {}).execute()
            assert is_admitted_now.data is True
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_single_use_second_call_with_same_code_fails_and_does_not_re_stamp(
        self, admin_client: Client, student_a: tuple[str, Client], student_b: tuple[str, Client]
    ) -> None:
        """docs/CONSENT.md section 4: 'a second call for an already-used
        code must fail/return false, never silently re-stamp
        admitted_at'. Uses a SECOND student to prove the code is truly
        single-use system-wide, not just 'not reusable by the same
        caller'."""
        user_a_id, client_a = student_a
        user_b_id, client_b = student_b
        _make_account(admin_client, user_a_id, status="active", admitted=False)
        _make_account(admin_client, user_b_id, status="active", admitted=False)
        code = f"qa-admission-singleuse-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            first = client_a.rpc("redeem_invite", {"p_code": code}).execute()
            assert first.data is True
            first_stamp = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_a_id)
                .execute()
                .data[0]["admitted_at"]
            )

            second = client_b.rpc("redeem_invite", {"p_code": code}).execute()
            assert second.data is False, "a second caller must not be able to redeem a used code"

            b_account = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_b_id)
                .execute()
                .data[0]
            )
            assert b_account["admitted_at"] is None, "student B must not have been admitted"

            # Re-call as the SAME first caller too — must also fail, and
            # must not move the stamp.
            again = client_a.rpc("redeem_invite", {"p_code": code}).execute()
            assert again.data is False
            still_a_stamp = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_a_id)
                .execute()
                .data[0]["admitted_at"]
            )
            assert still_a_stamp == first_stamp, "admitted_at must never be re-stamped"
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()
            admin_client.table("student_accounts").delete().eq("id", user_a_id).execute()
            admin_client.table("student_accounts").delete().eq("id", user_b_id).execute()

    def test_fails_for_a_wrong_or_expired_code_without_consuming_a_real_one(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=False)
        expired_code = f"qa-admission-redeem-expired-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=expired_code, expires_at=_past())
        try:
            wrong = own_client.rpc("redeem_invite", {"p_code": "nope-not-a-code"}).execute()
            assert wrong.data is False

            expired = own_client.rpc("redeem_invite", {"p_code": expired_code}).execute()
            assert expired.data is False

            account = (
                admin_client.table("student_accounts")
                .select("admitted_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert account["admitted_at"] is None
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(expired_code)
            ).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_fails_and_does_not_burn_the_code_for_a_non_active_account(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """Ordering requirement from 0012's own docstring: the caller's
        own account must be checked 'active' BEFORE the invite code is
        touched at all, so a doomed attempt does not waste a real code."""
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="pending_guardian_consent", admitted=False)
        code = f"qa-admission-pending-{uuid.uuid4().hex[:12]}"
        _seed_invite(admin_client, code=code, expires_at=_future())
        try:
            result = own_client.rpc("redeem_invite", {"p_code": code}).execute()
            assert result.data is False

            invite = (
                admin_client.table("pilot_invites")
                .select("used_by")
                .eq("code_hash", _code_hash(code))
                .execute()
                .data[0]
            )
            assert invite["used_by"] is None, "the code must not have been consumed"
        finally:
            admin_client.table("pilot_invites").delete().eq(
                "code_hash", _code_hash(code)
            ).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()


# =====================================================================
# withdraw_account() — freeze now, AUTH-10 deletes later
# =====================================================================
class TestWithdrawAccount:
    def test_requires_an_authenticated_session(self, guest_client: Client) -> None:
        """Same `revoke ... from public` reasoning as
        TestRedeemInvite.test_requires_an_authenticated_session above."""
        with pytest.raises(APIError) as exc_info:
            guest_client.rpc("withdraw_account", {}).execute()
        assert exc_info.value.code == "42501"

    def test_freezes_stamps_deletion_due_and_records_a_consent_row(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=True)
        try:
            own_client.rpc("withdraw_account", {}).execute()

            account = (
                admin_client.table("student_accounts")
                .select("account_status, deletion_due_at")
                .eq("id", user_id)
                .execute()
                .data[0]
            )
            assert account["account_status"] == "frozen"
            assert account["deletion_due_at"] is not None
            due = datetime.fromisoformat(account["deletion_due_at"])
            expected = datetime.now(tz=UTC) + timedelta(days=30)
            assert abs((due - expected).total_seconds()) < 300  # 5-minute slack

            consent_rows = (
                admin_client.table("consents")
                .select("kind, action, wording_version")
                .eq("student_id", user_id)
                .execute()
                .data
            )
            assert len(consent_rows) == 1
            assert consent_rows[0]["kind"] == "account"
            assert consent_rows[0]["action"] == "withdrawn"
        finally:
            admin_client.table("consents").delete().eq("student_id", user_id).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_second_call_raises_and_does_not_extend_the_window_or_duplicate_consent(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=True)
        try:
            own_client.rpc("withdraw_account", {}).execute()
            first_due = (
                admin_client.table("student_accounts")
                .select("deletion_due_at")
                .eq("id", user_id)
                .execute()
                .data[0]["deletion_due_at"]
            )

            with pytest.raises(APIError):
                own_client.rpc("withdraw_account", {}).execute()

            second_due = (
                admin_client.table("student_accounts")
                .select("deletion_due_at")
                .eq("id", user_id)
                .execute()
                .data[0]["deletion_due_at"]
            )
            assert second_due == first_due, "a repeat call must not extend the 30-day window"

            consent_rows = (
                admin_client.table("consents")
                .select("id")
                .eq("student_id", user_id)
                .execute()
                .data
            )
            assert len(consent_rows) == 1, "a repeat call must not insert a second consent row"
        finally:
            admin_client.table("consents").delete().eq("student_id", user_id).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_withdrawal_immediately_revokes_write_access_via_is_admitted(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """Closes the loop between withdraw_account() and is_admitted():
        `admitted_at` is left untouched by a freeze, but `account_status`
        is no longer 'active', so is_admitted() (which requires BOTH)
        must now be false — a frozen account cannot write saved_plans/
        student_profiles even though it was admitted before."""
        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="active", admitted=True)
        try:
            own_client.rpc("withdraw_account", {}).execute()

            still_admitted = own_client.rpc("is_admitted", {}).execute()
            assert still_admitted.data is False

            career = admin_client.table("careers").insert(
                {"name": run_name("QA withdrawn career")}
            ).execute()
            career_id = career.data[0]["id"]
            pathway = (
                admin_client.table("pathways")
                .insert(
                    {
                        "career_id": career_id,
                        "name": run_name("QA withdrawn pathway"),
                        "description": "fixture",
                    }
                )
                .execute()
            )
            pathway_id = pathway.data[0]["id"]
            try:
                with pytest.raises(APIError) as exc_info:
                    own_client.table("saved_plans").insert(
                        {"student_id": user_id, "pathway_id": pathway_id}
                    ).execute()
                assert exc_info.value.code == "42501"
            finally:
                admin_client.table("pathways").delete().eq("id", pathway_id).execute()
                admin_client.table("careers").delete().eq("id", career_id).execute()
        finally:
            admin_client.table("consents").delete().eq("student_id", user_id).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()

    def test_raises_when_there_is_no_student_accounts_row_to_withdraw(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Same known gap as redeem_invite(): a caller with no
        student_accounts row (today's real adult sign-up shape) has
        nothing for this function to freeze, and it must say so rather
        than silently recording a 'withdrawn' event that never
        happened."""
        _user_id, own_client = student_a
        with pytest.raises(APIError):
            own_client.rpc("withdraw_account", {}).execute()


# =====================================================================
# is_safeguarding_staff() + safeguarding_flags — staff-only visibility
# =====================================================================
class TestSafeguardingVisibility:
    def test_is_safeguarding_staff_true_only_for_a_real_staff_member(
        self,
        student_a: tuple[str, Client],
        safeguarding_staff_member: tuple[str, Client],
    ) -> None:
        _student_id, student_client = student_a
        _staff_id, staff_client = safeguarding_staff_member

        assert student_client.rpc("is_safeguarding_staff", {}).execute().data is False
        assert staff_client.rpc("is_safeguarding_staff", {}).execute().data is True

    def test_safeguarding_flags_visible_to_staff_only(
        self,
        admin_client: Client,
        guest_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        reviewer: tuple[str, Client],
        safeguarding_staff_member: tuple[str, Client],
    ) -> None:
        """docs/CONSENT.md section 6: 'students AND content reviewers
        read ZERO rows of safeguarding_flags'. The flag concerns student
        A herself — even SHE cannot see it."""
        student_a_id, client_a = student_a
        _student_b_id, client_b = student_b
        _reviewer_id, reviewer_client = reviewer
        _staff_id, staff_client = safeguarding_staff_member

        flag = (
            admin_client.table("safeguarding_flags")
            .insert({"student_id": student_a_id, "category": "qa-admission-probe"})
            .execute()
        )
        flag_id = flag.data[0]["id"]
        try:
            # guest (anon-key, no session) is refused at the GRANT level
            # now (adversarial review fix, this session: `anon` lost
            # EXECUTE on `is_safeguarding_staff()` entirely — see
            # db/migrations/0013_safeguarding_schema.sql's own comment),
            # a flat 42501 rather than an empty result set — a STRONGER
            # "zero rows visible" than before, not a weaker one:
            # `authenticated` callers (client_a/b, reviewer_client below)
            # keep their EXECUTE grant, so their own RLS check still just
            # filters to zero rows as before.
            with pytest.raises(APIError) as exc_info:
                guest_client.table("safeguarding_flags").select("*").eq(
                    "id", flag_id
                ).execute()
            assert exc_info.value.code == "42501"
            assert not client_a.table("safeguarding_flags").select("*").eq(
                "id", flag_id
            ).execute().data
            assert not client_b.table("safeguarding_flags").select("*").eq(
                "id", flag_id
            ).execute().data
            assert not reviewer_client.table("safeguarding_flags").select("*").eq(
                "id", flag_id
            ).execute().data

            staff_rows = (
                staff_client.table("safeguarding_flags")
                .select("*")
                .eq("id", flag_id)
                .execute()
                .data
            )
            assert len(staff_rows) == 1, "a real safeguarding-staff member must see the flag"
            assert staff_rows[0]["category"] == "qa-admission-probe"
        finally:
            admin_client.table("safeguarding_flags").delete().eq("id", flag_id).execute()
