"""Live tests for db/migrations/0009_guest_sessions.sql (AUTH-4).

The card's own risk line: "Definer functions are a deliberate RLS
bypass; an input bug leaks one guest's plans to another." So the centre
of this file is `TestCrossGuestIsolation` — guest X against guest Y,
through every RPC, including the IDOR shape where X knows Y's plan id.

Everything here runs through the anon client, because that is what a
guest actually is: no Supabase Auth user, no `auth.uid()`, nothing but a
token. `admin_client` (service_role) appears only to seed a pathway and
to inspect stored rows for the hashing test — never to make an assertion
about what a guest can reach.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import admit_student, run_name


@pytest.fixture
def pathway(admin_client: Client) -> Iterator[str]:
    """One real pathway — `guest_plans.pathway_id` is a foreign key, so
    every saved route needs a genuine one."""
    career_id = (
        admin_client.table("careers")
        .insert({"name": run_name("guest-session career")})
        .execute()
        .data[0]["id"]
    )
    pathway_id = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career_id,
                "name": run_name("guest-session pathway"),
                "description": "Seeded by tests/db/test_guest_session.py",
            }
        )
        .execute()
        .data[0]["id"]
    )
    yield pathway_id
    # pathways cascade from careers (0001_init.sql).
    admin_client.table("careers").delete().eq("id", career_id).execute()


@pytest.fixture
def second_pathway(admin_client: Client) -> Iterator[str]:
    career_id = (
        admin_client.table("careers")
        .insert({"name": run_name("guest-session career 2")})
        .execute()
        .data[0]["id"]
    )
    pathway_id = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career_id,
                "name": run_name("guest-session pathway 2"),
                "description": "Seeded by tests/db/test_guest_session.py",
            }
        )
        .execute()
        .data[0]["id"]
    )
    yield pathway_id
    admin_client.table("careers").delete().eq("id", career_id).execute()


def _new_session(client: Client) -> str:
    token = client.rpc("create_guest_session", {}).execute().data
    assert isinstance(token, str) and token
    return token


def _save(client: Client, token: str, pathway_id: str, expenses: float | None = None) -> bool:
    return (
        client.rpc(
            "save_guest_plan",
            {
                "p_token": token,
                "p_pathway_id": pathway_id,
                "p_estimated_additional_expenses": expenses,
            },
        )
        .execute()
        .data
        is True
    )


def _list(client: Client, token: str) -> list[dict]:
    return client.rpc("list_guest_plans", {"p_token": token}).execute().data or []


def _delete(client: Client, token: str, plan_id: str) -> bool:
    return (
        client.rpc("delete_guest_plan", {"p_token": token, "p_plan_id": plan_id})
        .execute()
        .data
        is True
    )


@pytest.fixture
def guest_x(guest_client: Client, admin_client: Client) -> Iterator[str]:
    token = _new_session(guest_client)
    yield token
    _purge(admin_client, token)


@pytest.fixture
def guest_y(guest_client: Client, admin_client: Client) -> Iterator[str]:
    token = _new_session(guest_client)
    yield token
    _purge(admin_client, token)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _purge(admin_client: Client, token: str) -> None:
    """Remove a session by its hash. guest_plans cascades."""
    admin_client.table("guest_sessions").delete().eq(
        "token_hash", _token_hash(token)
    ).execute()


# --------------------------------------------------------------------
# The tables are unreachable directly
# --------------------------------------------------------------------


class TestDirectTableAccessIsDenied:
    """AUTH-4 acceptance: "direct table access denied". Deny-all RLS plus
    revoked grants — either alone would deny; both are present because
    this is the only thing separating two anonymous strangers' data."""

    @pytest.mark.parametrize("table", ["guest_sessions", "guest_plans"])
    def test_a_guest_cannot_select(self, guest_client: Client, table: str) -> None:
        with pytest.raises(APIError):
            guest_client.table(table).select("*").execute()

    @pytest.mark.parametrize("table", ["guest_sessions", "guest_plans"])
    def test_a_guest_cannot_insert(self, guest_client: Client, table: str) -> None:
        with pytest.raises(APIError):
            guest_client.table(table).insert({"id": str(uuid.uuid4())}).execute()

    @pytest.mark.parametrize("table", ["guest_sessions", "guest_plans"])
    def test_a_signed_in_student_cannot_select_either(
        self, student_a: tuple[str, Client], table: str
    ) -> None:
        """Having an account does not grant a view of every anonymous
        visitor's routes."""
        _, client = student_a
        with pytest.raises(APIError):
            client.table(table).select("*").execute()

    @pytest.mark.parametrize("table", ["guest_sessions", "guest_plans"])
    def test_a_reviewer_cannot_select_either(
        self, reviewer: tuple[str, Client], table: str
    ) -> None:
        """A reviewer is trusted with the knowledge base, not with
        students' or visitors' own data — `is_reviewer()` appears nowhere
        in 0009, deliberately."""
        _, client = reviewer
        with pytest.raises(APIError):
            client.table(table).select("*").execute()

    def test_the_internal_helper_is_not_callable_by_a_guest(
        self, guest_client: Client, guest_x: str
    ) -> None:
        """`guest_session_id()` is revoked from anon/authenticated: it
        would be a token-probing oracle, letting a caller test guesses
        cheaply and learn when one is live."""
        with pytest.raises(APIError):
            guest_client.rpc("guest_session_id", {"p_token": guest_x}).execute()


# --------------------------------------------------------------------
# The token
# --------------------------------------------------------------------


class TestTheToken:
    def test_is_256_bits_of_randomness(self, guest_x: str) -> None:
        """32 bytes hex-encoded = 64 hex characters (AUTH-4: "256-bit")."""
        assert len(guest_x) == 64
        assert all(c in "0123456789abcdef" for c in guest_x)

    def test_two_sessions_get_different_tokens(
        self, guest_x: str, guest_y: str
    ) -> None:
        assert guest_x != guest_y

    def test_is_stored_only_as_a_sha256_hash(
        self, admin_client: Client, guest_x: str
    ) -> None:
        """AUTH-4 acceptance: "token stored as SHA-256". Checked by
        computing the hash independently in Python and finding THAT in
        the table — and by confirming the raw token appears in no row."""
        rows = admin_client.table("guest_sessions").select("token_hash").execute().data
        hashes = {row["token_hash"] for row in rows}
        assert _token_hash(guest_x) in hashes
        assert guest_x not in hashes

    def test_an_unknown_token_lists_nothing(self, guest_client: Client) -> None:
        assert _list(guest_client, "0" * 64) == []

    def test_a_garbage_token_is_not_an_error(self, guest_client: Client) -> None:
        """A stale or mangled cookie is an ordinary state, not a crash."""
        assert _list(guest_client, "not-a-token") == []
        assert _save(guest_client, "not-a-token", str(uuid.uuid4())) is False

    def test_an_empty_token_resolves_to_nothing(self, guest_client: Client) -> None:
        """Guards the `coalesce(p_token, '')` in `guest_session_id`: an
        empty string must hash to something that matches no row, never
        to a NULL comparison that could behave surprisingly."""
        assert _list(guest_client, "") == []

    def test_a_null_token_resolves_to_nothing(self, guest_client: Client) -> None:
        assert guest_client.rpc("list_guest_plans", {"p_token": None}).execute().data in (
            [],
            None,
        )


# --------------------------------------------------------------------
# Saving and listing
# --------------------------------------------------------------------


class TestSaveAndList:
    def test_a_guest_saves_and_lists_by_token(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        assert _save(guest_client, guest_x, pathway, 5000) is True
        plans = _list(guest_client, guest_x)
        assert len(plans) == 1
        assert plans[0]["pathway_id"] == pathway
        assert float(plans[0]["estimated_additional_expenses"]) == 5000

    def test_saving_the_same_route_twice_is_idempotent(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        _save(guest_client, guest_x, pathway, 1000)
        _save(guest_client, guest_x, pathway, 2000)
        plans = _list(guest_client, guest_x)
        assert len(plans) == 1
        assert float(plans[0]["estimated_additional_expenses"]) == 2000

    def test_expenses_may_be_omitted(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        assert _save(guest_client, guest_x, pathway) is True
        assert _list(guest_client, guest_x)[0]["estimated_additional_expenses"] is None

    def test_only_an_existing_pathway_id_is_accepted(
        self, guest_client: Client, guest_x: str
    ) -> None:
        """AUTH-4 acceptance, verbatim. Enforced by the foreign key, so
        it holds for any write path, not just this RPC."""
        with pytest.raises(APIError):
            _save(guest_client, guest_x, str(uuid.uuid4()))

    def test_a_negative_expense_is_refused(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        with pytest.raises(APIError):
            _save(guest_client, guest_x, pathway, -1)

    def test_an_absurd_expense_is_refused(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        with pytest.raises(APIError):
            _save(guest_client, guest_x, pathway, 10_000_000_000)

    def test_at_most_ten_plans_per_session(
        self, guest_client: Client, admin_client: Client, guest_x: str
    ) -> None:
        """AUTH-4 acceptance: "max 10 plans per session"."""
        career_id = (
            admin_client.table("careers")
            .insert({"name": run_name("guest-limit career")})
            .execute()
            .data[0]["id"]
        )
        try:
            pathway_ids = [
                admin_client.table("pathways")
                .insert(
                    {
                        "career_id": career_id,
                        "name": run_name(f"guest-limit pathway {i}"),
                        "description": "fixture",
                    }
                )
                .execute()
                .data[0]["id"]
                for i in range(11)
            ]
            for pathway_id in pathway_ids[:10]:
                assert _save(guest_client, guest_x, pathway_id) is True
            assert len(_list(guest_client, guest_x)) == 10
            with pytest.raises(APIError):
                _save(guest_client, guest_x, pathway_ids[10])
            assert len(_list(guest_client, guest_x)) == 10
        finally:
            admin_client.table("careers").delete().eq("id", career_id).execute()

    def test_the_cap_does_not_block_updating_an_existing_plan(
        self, guest_client: Client, admin_client: Client, guest_x: str
    ) -> None:
        """The limit trigger fires on INSERT only. If it fired on UPDATE
        too, a session holding exactly ten routes could never revise any
        of their estimates — the upsert's update branch would trip a cap
        it does not actually exceed."""
        career_id = (
            admin_client.table("careers")
            .insert({"name": run_name("guest-cap career")})
            .execute()
            .data[0]["id"]
        )
        try:
            pathway_ids = [
                admin_client.table("pathways")
                .insert(
                    {
                        "career_id": career_id,
                        "name": run_name(f"guest-cap pathway {i}"),
                        "description": "fixture",
                    }
                )
                .execute()
                .data[0]["id"]
                for i in range(10)
            ]
            for pathway_id in pathway_ids:
                _save(guest_client, guest_x, pathway_id, 100)
            assert _save(guest_client, guest_x, pathway_ids[0], 999) is True
            plans = {p["pathway_id"]: p for p in _list(guest_client, guest_x)}
            assert float(plans[pathway_ids[0]]["estimated_additional_expenses"]) == 999
            assert len(plans) == 10
        finally:
            admin_client.table("careers").delete().eq("id", career_id).execute()


# --------------------------------------------------------------------
# THE POINT OF THIS FILE
# --------------------------------------------------------------------


class TestCrossGuestIsolation:
    """Guest X must never see, change or delete guest Y's plans through
    any path. These functions are SECURITY DEFINER, so RLS is NOT a
    backstop here — if one of them keys a statement on a caller-supplied
    id instead of the resolved session, the leak is total."""

    def test_y_cannot_see_x_s_plans(
        self, guest_client: Client, guest_x: str, guest_y: str, pathway: str
    ) -> None:
        _save(guest_client, guest_x, pathway, 5000)
        assert _list(guest_client, guest_y) == []

    def test_each_session_sees_only_its_own(
        self,
        guest_client: Client,
        guest_x: str,
        guest_y: str,
        pathway: str,
        second_pathway: str,
    ) -> None:
        _save(guest_client, guest_x, pathway)
        _save(guest_client, guest_y, second_pathway)
        assert [p["pathway_id"] for p in _list(guest_client, guest_x)] == [pathway]
        assert [p["pathway_id"] for p in _list(guest_client, guest_y)] == [second_pathway]

    def test_y_cannot_delete_x_s_plan_even_knowing_its_id(
        self, guest_client: Client, guest_x: str, guest_y: str, pathway: str
    ) -> None:
        """The IDOR. `delete_guest_plan` is keyed on the plan id AND the
        session resolved from the token; keying it on the id alone would
        make this pass for guest Y, with RLS switched off by SECURITY
        DEFINER and nothing else to stop it."""
        _save(guest_client, guest_x, pathway)
        plan_id = _list(guest_client, guest_x)[0]["id"]

        assert _delete(guest_client, guest_y, plan_id) is False
        # ... and X's plan is still there.
        assert len(_list(guest_client, guest_x)) == 1

    def test_x_can_delete_its_own_plan(
        self, guest_client: Client, guest_x: str, pathway: str
    ) -> None:
        _save(guest_client, guest_x, pathway)
        plan_id = _list(guest_client, guest_x)[0]["id"]
        assert _delete(guest_client, guest_x, plan_id) is True
        assert _list(guest_client, guest_x) == []

    def test_deleting_a_nonexistent_plan_looks_the_same_as_someone_elses(
        self, guest_client: Client, guest_x: str, guest_y: str, pathway: str
    ) -> None:
        """Both return false. A caller must not be able to tell "no such
        plan" from "that plan is not yours" — the difference would
        confirm the existence of another session's row."""
        _save(guest_client, guest_x, pathway)
        someone_elses = _list(guest_client, guest_x)[0]["id"]
        assert _delete(guest_client, guest_y, someone_elses) is False
        assert _delete(guest_client, guest_y, str(uuid.uuid4())) is False

    def test_y_saving_does_not_touch_x_s_row(
        self, guest_client: Client, guest_x: str, guest_y: str, pathway: str
    ) -> None:
        """Both sessions saving the SAME pathway must produce two
        independent rows — the unique constraint is (session_id,
        pathway_id), not (pathway_id)."""
        _save(guest_client, guest_x, pathway, 111)
        _save(guest_client, guest_y, pathway, 222)
        assert float(_list(guest_client, guest_x)[0]["estimated_additional_expenses"]) == 111
        assert float(_list(guest_client, guest_y)[0]["estimated_additional_expenses"]) == 222

    def test_a_student_token_is_not_a_guest_token(
        self, guest_client: Client, student_a: tuple[str, Client], guest_x: str, pathway: str
    ) -> None:
        """A signed-in student calling the guest RPCs with their own
        session gets nothing: these functions key on the guest token
        only, and a student has no guest session."""
        _save(guest_client, guest_x, pathway)
        _, client = student_a
        assert _list(client, guest_x) == _list(guest_client, guest_x)  # token is the key
        assert _list(client, "0" * 64) == []

    def test_a_guest_cannot_reach_a_students_saved_plans(
        self,
        admin_client: Client,
        guest_client: Client,
        student_a: tuple[str, Client],
        pathway: str,
    ) -> None:
        """The two stores are separate: `saved_plans` is own-row by
        `auth.uid()` (0002/0004), `guest_plans` is token-scoped. A guest
        has no `auth.uid()`, so it sees no saved_plans row at all.

        Admitted first (CONSENT-4, 0012: saved_plans' own-row INSERT now
        also requires is_admitted()) so student A's own insert succeeds
        and this test still exercises what it is actually about.

        Migration-owner fix round, 0014_account_active_grant_fix.sql: a
        guest's SELECT on `saved_plans` is now refused at the GRANT level
        (42501 'permission denied for function account_active'), not
        merely filtered to an empty result — `saved_plans_select_own`'s
        USING clause references `account_active(auth.uid())`, and `anon`
        lost EXECUTE on that function entirely (see that migration's own
        header for the live-verified cross-user-oracle finding this
        closes; tests/db/access_matrix.py's `saved_plans`/SELECT/`guest`
        cell documents the same shape). A stronger 'zero rows visible'
        than before, not a weaker one."""
        student_id, student_client = student_a
        admit_student(admin_client, student_id)
        student_client.table("saved_plans").insert(
            {"student_id": student_id, "pathway_id": pathway}
        ).execute()
        with pytest.raises(APIError) as exc_info:
            guest_client.table("saved_plans").select("*").execute()
        assert exc_info.value.code == "42501"


# --------------------------------------------------------------------
# Expiry
# --------------------------------------------------------------------


class TestExpiry:
    def test_a_new_session_expires_in_seven_days(
        self, admin_client: Client, guest_x: str
    ) -> None:
        row = (
            admin_client.table("guest_sessions")
            .select("created_at, expires_at")
            .eq("token_hash", _token_hash(guest_x))
            .single()
            .execute()
        )
        from datetime import datetime

        created = datetime.fromisoformat(row.data["created_at"])
        expires = datetime.fromisoformat(row.data["expires_at"])
        assert 6.9 < (expires - created).total_seconds() / 86400 < 7.1

    def test_an_expired_session_lists_nothing(
        self, guest_client: Client, admin_client: Client, guest_x: str, pathway: str
    ) -> None:
        """AUTH-4 acceptance: "expired returns empty". Expiry is applied
        on READ (`guest_session_id` filters on `expires_at`), so this
        holds the instant the row ages out — it does not wait for a purge
        to run."""
        _save(guest_client, guest_x, pathway)
        assert len(_list(guest_client, guest_x)) == 1

        admin_client.table("guest_sessions").update(
            {"expires_at": "2020-01-01T00:00:00+00:00"}
        ).eq("token_hash", _token_hash(guest_x)).execute()

        assert _list(guest_client, guest_x) == []

    def test_an_expired_session_cannot_save(
        self, guest_client: Client, admin_client: Client, guest_x: str, pathway: str
    ) -> None:
        admin_client.table("guest_sessions").update(
            {"expires_at": "2020-01-01T00:00:00+00:00"}
        ).eq("token_hash", _token_hash(guest_x)).execute()
        assert _save(guest_client, guest_x, pathway) is False

    def test_an_expired_session_cannot_delete(
        self, guest_client: Client, admin_client: Client, guest_x: str, pathway: str
    ) -> None:
        _save(guest_client, guest_x, pathway)
        plan_id = _list(guest_client, guest_x)[0]["id"]
        admin_client.table("guest_sessions").update(
            {"expires_at": "2020-01-01T00:00:00+00:00"}
        ).eq("token_hash", _token_hash(guest_x)).execute()
        assert _delete(guest_client, guest_x, plan_id) is False

    def test_the_python_layer_agrees_with_the_database_on_seven_days(self) -> None:
        """`COOKIE_MAX_AGE_SECONDS` and `guest_sessions.expires_at`'s
        default must not drift apart: a cookie that outlived the row
        would make a returning guest present a token that silently
        resolves to nothing."""
        from app.web.guest_session import COOKIE_MAX_AGE_SECONDS

        assert COOKIE_MAX_AGE_SECONDS == 7 * 24 * 60 * 60

    def test_creating_a_session_purges_expired_ones(
        self, guest_client: Client, admin_client: Client, pathway: str
    ) -> None:
        """AUTH-4: "purged opportunistically on create". The expired
        session's plans go with it, by cascade."""
        doomed = _new_session(guest_client)
        _save(guest_client, doomed, pathway)
        admin_client.table("guest_sessions").update(
            {"expires_at": "2020-01-01T00:00:00+00:00"}
        ).eq("token_hash", _token_hash(doomed)).execute()

        survivor = _new_session(guest_client)
        try:
            remaining = (
                admin_client.table("guest_sessions")
                .select("token_hash")
                .eq("token_hash", _token_hash(doomed))
                .execute()
                .data
            )
            assert remaining == []
        finally:
            _purge(admin_client, survivor)


class TestThePythonLayer:
    """app/web/guest_session.py drives the same RPCs. Exercised here
    rather than as a unit test with a mocked client: a mock would agree
    with whatever the module does, including a wrong parameter name,
    which is precisely the bug class worth catching in a module whose
    only job is to pass arguments correctly."""

    def test_create_then_save_then_list_then_delete(
        self, guest_client: Client, admin_client: Client, pathway: str
    ) -> None:
        from app.web import guest_session as gs

        token = gs.create_session(guest_client)
        try:
            assert len(token) == 64
            assert gs.list_plans(guest_client, token) == []

            assert gs.save_plan(guest_client, token, pathway, 7500) is True
            plans = gs.list_plans(guest_client, token)
            assert len(plans) == 1
            assert plans[0].pathway_id == pathway
            assert plans[0].estimated_additional_expenses == 7500

            assert gs.delete_plan(guest_client, token, plans[0].id) is True
            assert gs.list_plans(guest_client, token) == []
        finally:
            _purge(admin_client, token)

    def test_a_stale_token_is_an_empty_list_not_an_error(
        self, guest_client: Client
    ) -> None:
        from app.web import guest_session as gs

        assert gs.list_plans(guest_client, "0" * 64) == []
        assert gs.save_plan(guest_client, "0" * 64, str(uuid.uuid4())) is False

    def test_the_guest_plan_shape_carries_no_free_text(self) -> None:
        """A guest is anonymous and un-consented, so there must be
        nowhere for a child to type their name or their situation. The
        table has no such column; this checks the Python shape has not
        grown one either."""
        from dataclasses import fields

        from app.web.guest_session import GuestPlan

        assert {f.name for f in fields(GuestPlan)} == {
            "id",
            "pathway_id",
            "estimated_additional_expenses",
            "created_at",
        }

    def test_an_empty_cookie_is_treated_as_no_cookie(self) -> None:
        from starlette.datastructures import Headers
        from starlette.requests import Request

        from app.web.guest_session import COOKIE_NAME, token_from_request

        def _request(cookie_value: str) -> Request:
            headers = Headers({"cookie": f"{COOKIE_NAME}={cookie_value}"})
            return Request({"type": "http", "headers": headers.raw})

        assert token_from_request(_request("")) is None
        assert token_from_request(_request("   ")) is None
        assert token_from_request(_request("abc")) == "abc"

    def test_the_cookie_is_httponly_and_samesite_lax(self) -> None:
        """This token is the ONLY thing separating one guest's saved
        routes from another's, so it must never be readable by script
        and must not ride along on a cross-site POST."""
        from fastapi import Response

        from app.web.guest_session import set_session_cookie

        response = Response()
        set_session_cookie(response, "a" * 64)
        header = response.headers["set-cookie"]
        assert "HttpOnly" in header
        assert "samesite=lax" in header.lower()
        assert "Max-Age=604800" in header
