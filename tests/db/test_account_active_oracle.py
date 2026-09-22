"""Live regression tests for the `account_active()` cross-user identity-
oracle fix (`db/migrations/0014_account_active_grant_fix.sql`).

`account_active(uid uuid)` was introduced by `db/migrations/
0004_guardian_consent.sql`, already merged to `main` and already applied
to the real Mumbai staging project (STATUS.md's Infrastructure table).
This is NOT a CONSENT-4 regression — it is a pre-existing finding on
already-live code, surfaced by this branch's own migration-owner fix
round (adversarial re-review of CONSENT-4's own two migrations, which
lean on `account_active()` in their own re-scoped policies) and closed
here by an additive, CREATE-OR-REPLACE-based migration, never an edit to
0004 itself.

Skips as a whole (see `tests/db/conftest.py`'s
`_account_active_grant_fix_migration_applied` check) until
0014_account_active_grant_fix.sql is applied to the local stack this
suite targets.

The live reproduction this file's tests are built to catch, exactly as
found by adversarial review (see 0014's own migration header for the full
writeup): a session-less, anon-key-only call to
`POST /rest/v1/rpc/account_active` with `{"uid": "<any real
student_accounts.id>"}` returned HTTP 200 with a plain true/false BEFORE
this fix — a real cross-user information leak (whether an arbitrary
account is active/pending/frozen/deletion-due). After the fix: the same
call must be refused at the grant level (42501), and a signed-in caller
passing someone ELSE's uid must get the function's own safe default
(`true` — the same "no matching row" answer this function already gave
before this fix, for the unrelated case of a caller with no
`student_accounts` row at all), never that other account's real status.
"""

from __future__ import annotations

from typing import Any

import pytest
from postgrest.exceptions import APIError
from supabase import Client

_ADULT_DOB = "1990-01-01"


def _make_account(
    admin_client: Client,
    user_id: str,
    *,
    status: str = "active",
) -> None:
    """Seed a `student_accounts` row directly (service role, bypasses
    RLS) with an arbitrary `account_status` — mirrors
    `tests/db/test_admission.py`'s own `_make_account`, kept local here
    since this file needs 'pending_guardian_consent' specifically (a
    status whose REAL `account_active()` answer is `false`), which that
    helper's signature does not expose."""
    payload: dict[str, Any] = {
        "id": user_id,
        "date_of_birth": _ADULT_DOB,
        "account_status": status,
    }
    admin_client.table("student_accounts").insert(payload).execute()


class TestAccountActiveOracleClosed:
    def test_anon_key_only_caller_cannot_call_account_active_at_all(
        self, admin_client: Client, guest_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """The exact live reproduction the adversarial reviewer used: a
        session-less anon-key-only RPC call with an arbitrary real uid.
        Must now be refused at the GRANT level (42501) — a stronger
        refusal than merely answering 'false', proving anon has no path
        to this function at all, not just that this one uid happened to
        say no."""
        victim_id, _victim_client = student_a
        _make_account(admin_client, victim_id, status="active")
        try:
            with pytest.raises(APIError) as exc_info:
                guest_client.rpc("account_active", {"uid": victim_id}).execute()
            assert exc_info.value.code == "42501"
        finally:
            admin_client.table("student_accounts").delete().eq("id", victim_id).execute()

    def test_authenticated_caller_probing_another_user_never_gets_the_real_answer(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
    ) -> None:
        """THE core proof the oracle is closed. Student A's REAL
        account_active() answer is `false` ('pending_guardian_consent',
        not 'active') — chosen deliberately, not 'active', so that a
        leaked real answer and the function's own safe default (`true`)
        are DISTINGUISHABLE: if B ever saw `false` here, that would be
        A's genuine status leaking through; before this fix, that is
        exactly what happened (live-reproduced by the adversarial
        reviewer). After the fix, B must see `true` — the safe default,
        never A's real, worse-case-sensitive status."""
        a_id, _a_client = student_a
        b_id, b_client = student_b
        _make_account(admin_client, a_id, status="pending_guardian_consent")
        try:
            probe = b_client.rpc("account_active", {"uid": a_id}).execute()
            assert probe.data is True, (
                "authenticated caller B must NOT learn A's real (false) "
                "account_active() status by passing A's uid explicitly -- "
                "must get the safe default (true), never the real answer"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", a_id).execute()

    def test_self_probe_still_returns_the_real_answer(
        self, admin_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """Sanity check, proving the fix closes the CROSS-user path
        without breaking the function for a caller asking about
        THEMSELVES (`uid = auth.uid()`, the only shape every real RLS
        policy in this schema ever uses) -- otherwise the `true` in the
        test above could just mean account_active() was broken outright,
        not that the oracle was specifically closed."""
        a_id, a_client = student_a
        _make_account(admin_client, a_id, status="pending_guardian_consent")
        try:
            self_check = a_client.rpc("account_active", {"uid": a_id}).execute()
            assert self_check.data is False, (
                "a caller asking about their OWN uid must still get the real "
                "answer -- account_active() itself must not be broken by this fix"
            )
        finally:
            admin_client.table("student_accounts").delete().eq("id", a_id).execute()

    def test_no_student_accounts_row_default_is_unchanged_for_the_caller_s_own_uid(
        self, student_a: tuple[str, Client]
    ) -> None:
        """0004's own design note (lines ~68-91/383-391): an 18+/legacy
        account with NO `student_accounts` row at all must default OPEN
        (`true`), never be gated by a table that was never populated for
        them. This must still hold for the caller's own uid after the
        fix -- deliberately no `_make_account()` call here, exactly like
        every real adult sign-up today."""
        a_id, a_client = student_a
        result = a_client.rpc("account_active", {"uid": a_id}).execute()
        assert result.data is True

    def test_active_account_s_own_row_policies_are_unaffected(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
    ) -> None:
        """No regression on the ONLY way this function is really used in
        this schema: every RLS policy calls it as
        `account_active(auth.uid())`, always the caller's own id. Proves
        an ACTIVE student's own saved_plans write still succeeds after
        the fix -- `uid = auth.uid()` is a no-op for this call shape."""
        from tests.db.conftest import admit_student, run_name

        user_id, own_client = student_a
        admit_student(admin_client, user_id, status="active")
        career = admin_client.table("careers").insert(
            {"name": run_name("QA account-active-fix career")}
        )
        career_id = career.execute().data[0]["id"]
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career_id,
                    "name": run_name("QA account-active-fix pathway"),
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
            assert plan.data, (
                "an ACTIVE, ADMITTED student's own saved_plans insert must still succeed"
            )
        finally:
            admin_client.table("saved_plans").delete().eq("student_id", user_id).execute()
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()
            admin_client.table("pathways").delete().eq("id", pathway_id).execute()
            admin_client.table("careers").delete().eq("id", career_id).execute()

    def test_pending_account_s_own_row_write_still_denied(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
    ) -> None:
        """The other half of the same no-regression proof: a PENDING
        account's own-row write must still be denied after the fix --
        `account_active(auth.uid())` must still correctly return `false`
        for the caller's own pending row, exactly as it did before 0014."""
        from tests.db.conftest import run_name

        user_id, own_client = student_a
        _make_account(admin_client, user_id, status="pending_guardian_consent")
        career = admin_client.table("careers").insert(
            {"name": run_name("QA account-active-fix pending career")}
        )
        career_id = career.execute().data[0]["id"]
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career_id,
                    "name": run_name("QA account-active-fix pending pathway"),
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
            admin_client.table("student_accounts").delete().eq("id", user_id).execute()
            admin_client.table("pathways").delete().eq("id", pathway_id).execute()
            admin_client.table("careers").delete().eq("id", career_id).execute()
