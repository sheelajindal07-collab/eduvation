"""Live regression tests for CONSENT-10 — POST /account/withdraw.

This is the HTTP surface CONSENT-4 explicitly left out of its own scope;
`app/api/account.py`'s own module docstring explains why it exists and
what it does and does not own. `tests/db/test_admission.py::
TestWithdrawAccount` already proves `withdraw_account()` itself (the RPC)
freezes/stamps/idempotency-guards correctly at the database layer — this
file does not repeat that proof. It proves the ROUTE's own, additional
contract instead: called through the real, wired-in app (not the RPC
directly), a signed-in student can withdraw only their own account, a
second call is idempotent from an HTTP caller's perspective (200, not an
error), a withdrawn account's further writes are refused (RLS, already
built by CONSENT-4), and — the one claim this task named that nothing else
in this codebase yet checks — a withdrawn account can still READ its own
existing data, because freezing is not deletion.

Needs `db/migrations/0013_safeguarding_schema.sql` applied (same as
`test_admission.py`) — this file does not add its own skip gate for that
(tests/db/conftest.py's `pytest_collection_modifyitems` is not owned by
this task), so an unapplied migration surfaces as a real, informative
failure here rather than a silent skip, which is the correct
"no run in flight" outcome CLAUDE.md/docs/TESTING.md ask for anyway.

**A real, live-verified finding, not an assumption — see
`TestFreezeDoesNotDeleteButDoesBlockReads` below.** This task's own
acceptance criteria say a frozen account "CAN still read its own existing
data (freezing is not the same as deleting)". Live-verified against the
real stack (a probe script, not a guess): that distinction holds for the
account's own `student_accounts` row (`student_accounts_select_own`,
0004, has no `account_active()`/`is_admitted()` gate), but does NOT hold
for `saved_plans` — `saved_plans_select_own` (0012_admission_axis.sql)
requires `account_active(auth.uid())`, which becomes `false` the instant
`account_status` leaves `'active'`, so a frozen account's own SELECT on
its own saved plans silently returns zero rows (RLS-filtered, not an
error — the same shape as "this plan belongs to someone else"). The
identical gate is on `student_profiles_select_own`. This is a pre-existing
RLS design decision from CONSENT-4 (0012_admission_axis.sql), not
something this task's route causes or can fix from the application layer
— "RLS is the actual enforcement, not application code" is this
codebase's own settled principle (app/api/plans.py's docstring), and this
task is not a migration owner. Flagged in the completion report as an
open question rather than silently accepted or worked around.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from tests.db.conftest import admit_student, run_name

client = TestClient(app)


# CONSENT-4 (0012): POST/PATCH/DELETE /plans (and withdraw_account() itself)
# need is_admitted() -- see tests/db/test_api_plans.py's own identical
# override for the full reasoning. Overriding conftest.py's student_a/
# student_b fixtures here (pytest's documented same-name-override pattern)
# admits both once, centrally, for every test in this module.
@pytest.fixture
def student_a(student_a: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, scoped_client = student_a
    admit_student(admin_client, user_id)
    return user_id, scoped_client


@pytest.fixture
def student_b(student_b: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, scoped_client = student_b
    admit_student(admin_client, user_id)
    return user_id, scoped_client


@pytest.fixture
def seeded_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Withdrawal test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Withdrawal test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_withdrawal.py",
            }
        )
        .execute()
        .data[0]
    )
    yield pathway
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


def _access_token(scoped_client: Client) -> str:
    session = scoped_client.auth.get_session()
    assert session is not None
    return str(session.access_token)


def _auth_header(scoped_client: Client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token(scoped_client)}"}


class TestWithdrawRoute:
    def test_guest_cannot_call_withdraw(self) -> None:
        response = client.post("/account/withdraw")
        assert response.status_code == 401

    def test_signed_in_student_can_withdraw_own_account(
        self, student_a: tuple[str, Client], admin_client: Client
    ) -> None:
        user_id, scoped_client = student_a

        response = client.post("/account/withdraw", headers=_auth_header(scoped_client))

        assert response.status_code == 200
        body = response.json()
        assert body["account_status"] == "frozen"
        assert body["deletion_due_at"] is not None

        row = (
            admin_client.table("student_accounts")
            .select("account_status, deletion_due_at")
            .eq("id", user_id)
            .execute()
            .data[0]
        )
        assert row["account_status"] == "frozen"
        assert row["deletion_due_at"] is not None

        consent_rows = (
            admin_client.table("consents")
            .select("kind, action")
            .eq("student_id", user_id)
            .execute()
            .data
        )
        assert len(consent_rows) == 1
        assert consent_rows[0] == {"kind": "account", "action": "withdrawn"}

    def test_second_call_is_idempotent_not_an_error_and_does_not_extend_the_window(
        self, student_a: tuple[str, Client], admin_client: Client
    ) -> None:
        """The RPC itself raises on a second call (0013's own idempotency
        guard, already proven at that layer by test_admission.py) — this
        route's own job is to turn that into a non-error, unchanged-state
        response for an HTTP caller, not relay a raw trigger error for
        "you already did this"."""
        user_id, scoped_client = student_a
        headers = _auth_header(scoped_client)

        first = client.post("/account/withdraw", headers=headers)
        assert first.status_code == 200
        first_due = first.json()["deletion_due_at"]

        second = client.post("/account/withdraw", headers=headers)
        assert second.status_code == 200, second.text
        second_body = second.json()
        assert second_body["account_status"] == "frozen"
        assert second_body["deletion_due_at"] == first_due, (
            "a repeat call must not extend the 30-day window"
        )

        consent_rows = (
            admin_client.table("consents")
            .select("id")
            .eq("student_id", user_id)
            .execute()
            .data
        )
        assert len(consent_rows) == 1, "a repeat call must not insert a second consent row"

    def test_withdrawal_blocks_further_plan_writes(
        self,
        student_a: tuple[str, Client],
        seeded_pathway: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        headers = _auth_header(scoped_client)

        save = client.post("/plans", json={"pathway_id": seeded_pathway["id"]}, headers=headers)
        assert save.status_code == 201
        plan_id = save.json()["id"]

        withdraw = client.post("/account/withdraw", headers=headers)
        assert withdraw.status_code == 200

        # Same 404 shape app/api/plans.py already gives for "not yours" /
        # "doesn't exist" -- an RLS denial on a frozen account's own plan
        # must look identical, not leak a distinguishable error
        # (docs/UI.md "explain the boundary without exposing another
        # user's data", the same reasoning plans.py already applies).
        patch = client.patch(
            f"/plans/{plan_id}", json={"notes": "trying after withdrawal"}, headers=headers
        )
        assert patch.status_code == 404

        delete = client.delete(f"/plans/{plan_id}", headers=headers)
        assert delete.status_code == 404

    def test_a_different_account_is_completely_unaffected(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        seeded_pathway: dict[str, Any],
        admin_client: Client,
    ) -> None:
        _a_id, a_client = student_a
        b_id, b_client = student_b
        a_headers = _auth_header(a_client)
        b_headers = _auth_header(b_client)

        withdraw = client.post("/account/withdraw", headers=a_headers)
        assert withdraw.status_code == 200

        # B's own account row: untouched.
        b_row = (
            admin_client.table("student_accounts")
            .select("account_status, deletion_due_at")
            .eq("id", b_id)
            .execute()
            .data[0]
        )
        assert b_row["account_status"] == "active"
        assert b_row["deletion_due_at"] is None

        # B can still write a plan of their own.
        save = client.post("/plans", json={"pathway_id": seeded_pathway["id"]}, headers=b_headers)
        assert save.status_code == 201

        # A's withdrawal call never touched B's consents trail either.
        b_consents = (
            admin_client.table("consents").select("id").eq("student_id", b_id).execute().data
        )
        assert b_consents == []

    def test_withdrawing_someone_elses_account_is_not_possible(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        """withdraw_account() takes no id parameter at all -- it resolves
        auth.uid() from the caller's own token server-side -- so there is
        no request shape that could name a victim. This test exists to
        make that structural guarantee an explicit, checked fact rather
        than an assumption: B's own withdraw call, however it is
        constructed, can only ever freeze B, never A."""
        a_id, _a_client = student_a
        b_id, b_client = student_b

        response = client.post("/account/withdraw", headers=_auth_header(b_client))
        assert response.status_code == 200
        assert response.json()["account_status"] == "frozen"

        a_row = (
            admin_client.table("student_accounts")
            .select("account_status")
            .eq("id", a_id)
            .execute()
            .data[0]
        )
        assert a_row["account_status"] == "active"

        b_row = (
            admin_client.table("student_accounts")
            .select("account_status")
            .eq("id", b_id)
            .execute()
            .data[0]
        )
        assert b_row["account_status"] == "frozen"


class TestFreezeDoesNotDeleteButDoesBlockReads:
    """This task's own acceptance criteria: confirm, don't assume, that
    "freezing is not deleting" — a withdrawn account can still read its
    own existing data. Live-verified finding, reported in this session's
    completion notes as an open question: this holds for the account's
    OWN status/metadata, but not for `saved_plans` (or, by the identical
    policy shape, `student_profiles`) — see this module's own docstring
    for the exact RLS clause responsible and why fixing it is outside
    this task's scope (not a migration owner)."""

    def test_the_accounts_own_status_and_deletion_due_date_stay_readable(
        self, student_a: tuple[str, Client]
    ) -> None:
        """The one piece of "freezing is not deleting" that DOES hold
        today, and the one this route's own success response relies on
        (see app/api/account.py's `_own_account_row`)."""
        _user_id, scoped_client = student_a
        headers = _auth_header(scoped_client)

        withdraw = client.post("/account/withdraw", headers=headers)
        assert withdraw.status_code == 200

        own_row = scoped_client.table("student_accounts").select("*").execute().data
        assert len(own_row) == 1
        assert own_row[0]["account_status"] == "frozen"
        assert own_row[0]["deletion_due_at"] is not None

    def test_a_frozen_accounts_own_saved_plan_becomes_unreadable_too(
        self,
        student_a: tuple[str, Client],
        seeded_pathway: dict[str, Any],
    ) -> None:
        """NOT the acceptance criteria's expectation — documenting the
        real, live-verified behavior rather than the assumption, per this
        module's own docstring. `saved_plans_select_own`
        (0012_admission_axis.sql) requires `account_active(auth.uid())`,
        which is false the instant `account_status` leaves 'active', so
        this is RLS silently filtering the row (empty list), the exact
        same shape as "not yours" — not a 403, not a crash, just gone
        from this student's own view of their own data."""
        _user_id, scoped_client = student_a
        headers = _auth_header(scoped_client)

        save = client.post("/plans", json={"pathway_id": seeded_pathway["id"]}, headers=headers)
        assert save.status_code == 201

        withdraw = client.post("/account/withdraw", headers=headers)
        assert withdraw.status_code == 200

        own_plans = scoped_client.table("saved_plans").select("*").execute().data
        assert own_plans == [], (
            "if this ever starts returning the plan, the RLS gap this test "
            "documents has been fixed -- update this test (and tell the "
            "acceptance criteria it now genuinely holds) rather than "
            "leaving this assertion stale"
        )

        via_api = client.get("/plans", headers=headers)
        assert via_api.status_code == 200
        assert via_api.json() == []
