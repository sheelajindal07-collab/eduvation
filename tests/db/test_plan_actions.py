"""Live tests for db/migrations/0010_plan_actions.sql and the AUTH-5
additions to app/api/plans.py.

Acceptance lines covered here:
  * "One is_current per student enforced in DB"
  * "B cannot read or tick A's actions"
  * "PATCH can null a field"
  * "Negative or absurd expenses and over-long notes return 422"

`plan_actions` has no `student_id` of its own — ownership comes from the
parent plan — so `TestCrossStudentIsolation` is the test that the
via-the-parent policy is actually scoped, and not merely present.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from supabase import Client

from app.api.plans import MAX_EXPENSES, MAX_NOTES_LENGTH
from app.main import app
from tests.db.conftest import run_name

http = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pathways(admin_client: Client) -> Iterator[list[str]]:
    career_id = (
        admin_client.table("careers")
        .insert({"name": run_name("plan-actions career")})
        .execute()
        .data[0]["id"]
    )
    ids = [
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career_id,
                "name": run_name(f"plan-actions pathway {i}"),
                "description": "Seeded by tests/db/test_plan_actions.py",
            }
        )
        .execute()
        .data[0]["id"]
        for i in range(3)
    ]
    yield ids
    # pathways cascade from careers (0001_init.sql).
    admin_client.table("careers").delete().eq("id", career_id).execute()


def _save(client: Client, student_id: str, pathway_id: str) -> str:
    return (
        client.table("saved_plans")
        .insert({"student_id": student_id, "pathway_id": pathway_id})
        .execute()
        .data[0]["id"]
    )


# --------------------------------------------------------------------
# is_current
# --------------------------------------------------------------------


class TestOneCurrentPlanPerStudent:
    def test_a_new_plan_is_not_current(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        """Nobody's decision is invented for them."""
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        row = (
            client.table("saved_plans")
            .select("is_current")
            .eq("id", plan_id)
            .single()
            .execute()
        )
        assert row.data["is_current"] is False

    def test_a_student_may_have_one_current_plan(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        client.table("saved_plans").update({"is_current": True}).eq("id", plan_id).execute()
        rows = client.table("saved_plans").select("id").eq("is_current", True).execute()
        assert [row["id"] for row in rows.data] == [plan_id]

    def test_a_second_current_plan_is_refused_by_the_database(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        """Acceptance, verbatim: "One is_current per student enforced in
        DB" — not by the route that happens to clear the old one first."""
        student_id, client = student_a
        first = _save(client, student_id, pathways[0])
        second = _save(client, student_id, pathways[1])
        client.table("saved_plans").update({"is_current": True}).eq("id", first).execute()
        with pytest.raises(APIError):
            client.table("saved_plans").update({"is_current": True}).eq(
                "id", second
            ).execute()

    def test_many_non_current_plans_are_fine(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        """The index is PARTIAL. A plain unique (student_id, is_current)
        would also have capped a student at one non-current plan, i.e.
        no saved alternatives at all — which is most of what the My Plan
        screen is for."""
        student_id, client = student_a
        for pathway_id in pathways:
            _save(client, student_id, pathway_id)
        rows = client.table("saved_plans").select("id").execute()
        assert len(rows.data) == 3

    def test_two_students_may_each_have_their_own_current_plan(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        """The index is per student. If it were global, the second
        student to choose a decision would be refused because of a
        stranger's row."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        a_plan = _save(a_client, a_id, pathways[0])
        b_plan = _save(b_client, b_id, pathways[0])
        a_client.table("saved_plans").update({"is_current": True}).eq("id", a_plan).execute()
        b_client.table("saved_plans").update({"is_current": True}).eq("id", b_plan).execute()
        assert (
            a_client.table("saved_plans")
            .select("id")
            .eq("is_current", True)
            .execute()
            .data[0]["id"]
            == a_plan
        )

    def test_the_api_switches_the_current_plan(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """The common case: "make this one current instead", without the
        caller having to un-set the old one themselves."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        first = _save(client, student_id, pathways[0])
        second = _save(client, student_id, pathways[1])

        assert (
            http.patch(f"/plans/{first}", json={"is_current": True}, headers=_auth(token))
        ).status_code == 200
        response = http.patch(
            f"/plans/{second}", json={"is_current": True}, headers=_auth(token)
        )
        assert response.status_code == 200
        assert response.json()["is_current"] is True

        current = client.table("saved_plans").select("id").eq("is_current", True).execute()
        assert [row["id"] for row in current.data] == [second]


def _access_token(admin_client: Client, user_client: Client, user_id: str) -> str:
    """The signed-in student's own access token, for the HTTP layer.

    `_create_test_user` (tests/db/conftest.py) already signed this client
    in; this reads the token back off that session rather than signing in
    a second time, which would leave two live sessions for one user.
    """
    session = user_client.auth.get_session()
    assert session is not None
    return session.access_token


# --------------------------------------------------------------------
# plan_actions — ownership comes from the parent plan
# --------------------------------------------------------------------


class TestCrossStudentIsolation:
    """`plan_actions` has no student_id of its own, so if the
    via-the-parent policy is wrong, every student's checklist is
    readable by every other."""

    def test_b_cannot_read_a_s_actions(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        a_id, a_client = student_a
        _, b_client = student_b
        plan_id = _save(a_client, a_id, pathways[0])
        a_client.table("plan_actions").insert(
            {"plan_id": plan_id, "action_key": "check_entry_requirements", "done": True}
        ).execute()

        assert a_client.table("plan_actions").select("*").execute().data != []
        assert b_client.table("plan_actions").select("*").execute().data == []

    def test_b_cannot_tick_a_s_action(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        """Acceptance, verbatim: "B cannot read or tick A's actions"."""
        a_id, a_client = student_a
        _, b_client = student_b
        plan_id = _save(a_client, a_id, pathways[0])
        with pytest.raises(APIError):
            b_client.table("plan_actions").insert(
                {"plan_id": plan_id, "action_key": "gather_documents", "done": True}
            ).execute()

    def test_b_cannot_update_a_s_action_row(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        a_id, a_client = student_a
        _, b_client = student_b
        plan_id = _save(a_client, a_id, pathways[0])
        action_id = (
            a_client.table("plan_actions")
            .insert({"plan_id": plan_id, "action_key": "review_main_stages"})
            .execute()
            .data[0]["id"]
        )
        assert (
            b_client.table("plan_actions")
            .update({"done": True})
            .eq("id", action_id)
            .execute()
            .data
            == []
        )

    def test_b_cannot_delete_a_s_action_row(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        a_id, a_client = student_a
        _, b_client = student_b
        plan_id = _save(a_client, a_id, pathways[0])
        action_id = (
            a_client.table("plan_actions")
            .insert({"plan_id": plan_id, "action_key": "plan_for_duration"})
            .execute()
            .data[0]["id"]
        )
        assert (
            b_client.table("plan_actions").delete().eq("id", action_id).execute().data == []
        )
        assert a_client.table("plan_actions").select("id").execute().data != []

    def test_a_guest_sees_no_actions_at_all(
        self, student_a: tuple[str, Client], guest_client: Client, pathways: list[str]
    ) -> None:
        a_id, a_client = student_a
        plan_id = _save(a_client, a_id, pathways[0])
        a_client.table("plan_actions").insert(
            {"plan_id": plan_id, "action_key": "check_entry_requirements"}
        ).execute()
        assert guest_client.table("plan_actions").select("*").execute().data == []

    def test_a_reviewer_sees_no_actions_either(
        self,
        student_a: tuple[str, Client],
        reviewer: tuple[str, Client],
        pathways: list[str],
    ) -> None:
        """A reviewer is trusted with the knowledge base, not with a
        student's own checklist — `is_reviewer()` appears nowhere in
        0010."""
        a_id, a_client = student_a
        _, reviewer_client = reviewer
        plan_id = _save(a_client, a_id, pathways[0])
        a_client.table("plan_actions").insert(
            {"plan_id": plan_id, "action_key": "check_entry_requirements"}
        ).execute()
        assert reviewer_client.table("plan_actions").select("*").execute().data == []


class TestDoneAtIsServerOwned:
    def test_ticking_sets_done_at(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        row = (
            client.table("plan_actions")
            .insert(
                {"plan_id": plan_id, "action_key": "gather_documents", "done": True}
            )
            .execute()
            .data[0]
        )
        assert row["done_at"] is not None

    def test_an_unticked_action_has_no_done_at(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        row = (
            client.table("plan_actions")
            .insert({"plan_id": plan_id, "action_key": "gather_documents"})
            .execute()
            .data[0]
        )
        assert row["done_at"] is None

    def test_a_client_supplied_done_at_is_overwritten(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        """A student must not be able to claim they did something last
        week — the trigger owns this column."""
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        row = (
            client.table("plan_actions")
            .insert(
                {
                    "plan_id": plan_id,
                    "action_key": "gather_documents",
                    "done": True,
                    "done_at": "2020-01-01T00:00:00+00:00",
                }
            )
            .execute()
            .data[0]
        )
        assert not row["done_at"].startswith("2020")

    def test_un_ticking_clears_done_at(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        action_id = (
            client.table("plan_actions")
            .insert(
                {"plan_id": plan_id, "action_key": "gather_documents", "done": True}
            )
            .execute()
            .data[0]["id"]
        )
        row = (
            client.table("plan_actions")
            .update({"done": False})
            .eq("id", action_id)
            .execute()
            .data[0]
        )
        assert row["done_at"] is None

    def test_re_ticking_keeps_the_original_time(
        self, student_a: tuple[str, Client], pathways: list[str]
    ) -> None:
        """Saving the same tick twice must not silently reset when it
        happened."""
        student_id, client = student_a
        plan_id = _save(client, student_id, pathways[0])
        first = (
            client.table("plan_actions")
            .insert(
                {"plan_id": plan_id, "action_key": "gather_documents", "done": True}
            )
            .execute()
            .data[0]
        )
        again = (
            client.table("plan_actions")
            .update({"done": True})
            .eq("id", first["id"])
            .execute()
            .data[0]
        )
        assert again["done_at"] == first["done_at"]


# --------------------------------------------------------------------
# The API layer
# --------------------------------------------------------------------


class TestPatchCanClearAField:
    def test_patch_can_null_notes(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """Acceptance, verbatim: "PATCH can null a field". Before AUTH-5
        the route dropped every null before building the update, so a
        student who wanted to remove a note they had written simply could
        not."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        client.table("saved_plans").update({"notes": "something"}).eq(
            "id", plan_id
        ).execute()

        response = http.patch(
            f"/plans/{plan_id}", json={"notes": None}, headers=_auth(token)
        )
        assert response.status_code == 200
        assert response.json()["notes"] is None

    def test_patch_can_null_expenses(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        client.table("saved_plans").update({"estimated_additional_expenses": 500}).eq(
            "id", plan_id
        ).execute()

        response = http.patch(
            f"/plans/{plan_id}",
            json={"estimated_additional_expenses": None},
            headers=_auth(token),
        )
        assert response.status_code == 200
        assert response.json()["estimated_additional_expenses"] is None

    def test_an_absent_key_is_still_left_alone(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """The other half of what PATCH means: not mentioning a field
        must not clear it. `exclude_unset` is what distinguishes the two
        cases; a plain `model_dump()` would have nulled this."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        client.table("saved_plans").update({"notes": "keep me"}).eq(
            "id", plan_id
        ).execute()

        response = http.patch(
            f"/plans/{plan_id}",
            json={"estimated_additional_expenses": 100},
            headers=_auth(token),
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "keep me"


class TestInputBounds:
    """Acceptance, verbatim: "Negative or absurd expenses and over-long
    notes return 422"."""

    def test_negative_expenses_are_refused(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        response = http.post(
            "/plans",
            json={"pathway_id": pathways[0], "estimated_additional_expenses": -1},
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_absurd_expenses_are_refused(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        response = http.post(
            "/plans",
            json={
                "pathway_id": pathways[0],
                "estimated_additional_expenses": MAX_EXPENSES + 1,
            },
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_over_long_notes_are_refused(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        response = http.post(
            "/plans",
            json={"pathway_id": pathways[0], "notes": "x" * (MAX_NOTES_LENGTH + 1)},
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_the_same_bounds_apply_on_patch(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """A bound enforced only on create is not a bound."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        assert (
            http.patch(
                f"/plans/{plan_id}",
                json={"estimated_additional_expenses": -5},
                headers=_auth(token),
            ).status_code
            == 422
        )
        assert (
            http.patch(
                f"/plans/{plan_id}",
                json={"notes": "x" * (MAX_NOTES_LENGTH + 1)},
                headers=_auth(token),
            ).status_code
            == 422
        )

    def test_a_value_at_the_boundary_is_accepted(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """Off-by-one guard: the limits are inclusive."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        response = http.post(
            "/plans",
            json={
                "pathway_id": pathways[0],
                "estimated_additional_expenses": MAX_EXPENSES,
                "notes": "x" * MAX_NOTES_LENGTH,
            },
            headers=_auth(token),
        )
        assert response.status_code == 201


class TestTickActionRoute:
    def test_a_student_ticks_their_own_action(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        response = http.put(
            f"/plans/{plan_id}/actions/check_entry_requirements",
            json={"done": True},
            headers=_auth(token),
        )
        assert response.status_code == 200
        assert response.json()["done"] is True
        assert response.json()["done_at"] is not None

    def test_ticking_twice_is_one_row(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        for _ in range(2):
            http.put(
                f"/plans/{plan_id}/actions/gather_documents",
                json={"done": True},
                headers=_auth(token),
            )
        listed = http.get(f"/plans/{plan_id}/actions", headers=_auth(token))
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_an_unknown_action_key_is_refused(
        self, student_a: tuple[str, Client], pathways: list[str], admin_client: Client
    ) -> None:
        """`plan_actions.action_key` is plain text with no enum behind
        it, so this check is the only thing stopping free text being
        stored on a table that deliberately holds none."""
        student_id, client = student_a
        token = _access_token(admin_client, client, student_id)
        plan_id = _save(client, student_id, pathways[0])
        response = http.put(
            f"/plans/{plan_id}/actions/whatever_i_like",
            json={"done": True},
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_b_ticking_a_s_plan_gets_404_not_a_row(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
        admin_client: Client,
    ) -> None:
        """Through the HTTP layer as well as the database: 404, and
        indistinguishable from "no such plan"."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        a_plan = _save(a_client, a_id, pathways[0])
        b_token = _access_token(admin_client, b_client, b_id)
        response = http.put(
            f"/plans/{a_plan}/actions/check_entry_requirements",
            json={"done": True},
            headers=_auth(b_token),
        )
        assert response.status_code == 404
        assert a_client.table("plan_actions").select("*").execute().data == []

    def test_b_listing_a_s_actions_sees_nothing(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        pathways: list[str],
        admin_client: Client,
    ) -> None:
        a_id, a_client = student_a
        b_id, b_client = student_b
        a_plan = _save(a_client, a_id, pathways[0])
        a_client.table("plan_actions").insert(
            {"plan_id": a_plan, "action_key": "check_entry_requirements", "done": True}
        ).execute()
        b_token = _access_token(admin_client, b_client, b_id)
        assert http.get(f"/plans/{a_plan}/actions", headers=_auth(b_token)).json() == []

    def test_an_anonymous_caller_is_refused(self, pathways: list[str]) -> None:
        import uuid

        assert (
            http.put(
                f"/plans/{uuid.uuid4()}/actions/check_entry_requirements",
                json={"done": True},
            ).status_code
            == 401
        )
