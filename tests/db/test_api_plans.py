"""Integration tests for POST/GET/PATCH/DELETE /plans against the real
database. Needs db/migrations/0002_saved_plans.sql applied — see
db/migrations/README.md.

The whole module skips cleanly (not a failure) until that migration is
applied to the connected project — see tests/db/conftest.py's
pytest_collection_modifyitems (a skip hook defined in a test_*.py file
itself is never picked up by pytest, only in conftest.py/plugins, so
that's where this lives, not here).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from tests.db.conftest import run_name

client = TestClient(app)


@pytest.fixture
def seeded_pathway_for_plans(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Plans test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Plans test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_plans.py",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway}
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


class TestSavePlan:
    def test_guest_cannot_save_a_plan(self, seeded_pathway_for_plans: dict[str, Any]) -> None:
        response = client.post(
            "/plans", json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]}
        )
        assert response.status_code == 401

    def test_signed_in_student_can_save_a_plan(
        self,
        student_a: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        response = client.post(
            "/plans",
            json={
                "pathway_id": seeded_pathway_for_plans["pathway"]["id"],
                "estimated_additional_expenses": 15000,
                "notes": "Considering this one",
            },
            headers=_auth_header(session.access_token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["pathway_id"] == seeded_pathway_for_plans["pathway"]["id"]
        assert body["estimated_additional_expenses"] == 15000
        assert body["notes"] == "Considering this one"

    def test_saving_the_same_pathway_twice_returns_409(
        self,
        student_a: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        headers = _auth_header(session.access_token)
        payload = {"pathway_id": seeded_pathway_for_plans["pathway"]["id"]}

        first = client.post("/plans", json=payload, headers=headers)
        assert first.status_code == 201

        second = client.post("/plans", json=payload, headers=headers)
        assert second.status_code == 409

    def test_saving_a_nonexistent_pathway_returns_404_not_409(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Security-review finding, 2026-09-19: this used to be
        mislabelled 409 ("already saved") — a foreign-key violation is a
        different problem from a genuine duplicate and must say so."""
        import uuid as uuid_module

        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        response = client.post(
            "/plans",
            json={"pathway_id": str(uuid_module.uuid4())},  # well-formed, doesn't exist
            headers=_auth_header(session.access_token),
        )
        assert response.status_code == 404

    def test_saving_a_malformed_pathway_id_returns_422_not_409(
        self, student_a: tuple[str, Client]
    ) -> None:
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        response = client.post(
            "/plans",
            json={"pathway_id": "not-a-uuid-at-all"},
            headers=_auth_header(session.access_token),
        )
        assert response.status_code == 422


class TestListAndIsolation:
    def test_student_b_does_not_see_student_a_plan(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        """The core safety property: RLS must isolate saved plans
        exactly like student_profiles — proven through the actual API,
        not just the migration's RLS policy in isolation."""
        _user_a_id, client_a = student_a
        _user_b_id, client_b = student_b
        session_a = client_a.auth.get_session()
        session_b = client_b.auth.get_session()
        assert session_a is not None
        assert session_b is not None

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=_auth_header(session_a.access_token),
        )
        assert create.status_code == 201

        b_list = client.get("/plans", headers=_auth_header(session_b.access_token))
        assert b_list.status_code == 200
        assert b_list.json() == []

        a_list = client.get("/plans", headers=_auth_header(session_a.access_token))
        assert a_list.status_code == 200
        assert len(a_list.json()) == 1


class TestUpdateAndDelete:
    def test_update_with_malformed_plan_id_returns_422_not_500(
        self, student_a: tuple[str, Client]
    ) -> None:
        """Security-review finding, 2026-09-19: this used to crash to an
        unhandled 500 — plan_id had no format validation at all."""
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        response = client.patch(
            "/plans/definitely-not-a-uuid",
            json={"notes": "x"},
            headers=_auth_header(session.access_token),
        )
        assert response.status_code == 422

    def test_delete_with_malformed_plan_id_returns_422_not_500(
        self, student_a: tuple[str, Client]
    ) -> None:
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        response = client.delete(
            "/plans/definitely-not-a-uuid", headers=_auth_header(session.access_token)
        )
        assert response.status_code == 422

    def test_update_own_plan(
        self,
        student_a: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        headers = _auth_header(session.access_token)

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=headers,
        )
        plan_id = create.json()["id"]

        update = client.patch(
            f"/plans/{plan_id}", json={"notes": "Changed my mind"}, headers=headers
        )
        assert update.status_code == 200
        assert update.json()["notes"] == "Changed my mind"

    def test_student_b_cannot_update_student_a_plan(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        _user_a_id, client_a = student_a
        _user_b_id, client_b = student_b
        session_a = client_a.auth.get_session()
        session_b = client_b.auth.get_session()
        assert session_a is not None
        assert session_b is not None

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=_auth_header(session_a.access_token),
        )
        plan_id = create.json()["id"]

        attempt = client.patch(
            f"/plans/{plan_id}",
            json={"notes": "student B trying to edit"},
            headers=_auth_header(session_b.access_token),
        )
        assert attempt.status_code == 404  # RLS hides it; never a 403 that confirms it exists

    def test_student_b_cannot_delete_student_a_plan(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        """Coverage gap flagged in the security review, 2026-09-19: only
        the update side of cross-user isolation had a committed test —
        the reviewer confirmed delete was correct live, but nothing
        pinned it down as a permanent regression test."""
        _user_a_id, client_a = student_a
        _user_b_id, client_b = student_b
        session_a = client_a.auth.get_session()
        session_b = client_b.auth.get_session()
        assert session_a is not None
        assert session_b is not None

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=_auth_header(session_a.access_token),
        )
        plan_id = create.json()["id"]

        attempt = client.delete(f"/plans/{plan_id}", headers=_auth_header(session_b.access_token))
        assert attempt.status_code == 404  # RLS hides it; never a 403 that confirms it exists

        # the plan must still exist, untouched, for its real owner:
        still_there = admin_client.table("saved_plans").select("*").eq("id", plan_id).execute()
        assert len(still_there.data) == 1

        admin_client.table("saved_plans").delete().eq("id", plan_id).execute()

    def test_reviewer_has_no_special_access_to_saved_plans(
        self,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        """Coverage gap flagged in the security review, 2026-09-19: the
        reviewer role governs the public knowledge base (db/migrations/
        0001_init.sql), not the student vault -- confirmed correct live
        but not pinned down as a permanent test until now. Mirrors
        test_rls.py's identical check on student_profiles."""
        _user_a_id, client_a = student_a
        _reviewer_id, reviewer_client = reviewer
        session_a = client_a.auth.get_session()
        reviewer_session = reviewer_client.auth.get_session()
        assert session_a is not None
        assert reviewer_session is not None

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=_auth_header(session_a.access_token),
        )
        plan_id = create.json()["id"]

        reviewer_list = client.get("/plans", headers=_auth_header(reviewer_session.access_token))
        assert reviewer_list.status_code == 200
        assert reviewer_list.json() == []

        reviewer_read = client.patch(
            f"/plans/{plan_id}",
            json={"notes": "reviewer trying to edit"},
            headers=_auth_header(reviewer_session.access_token),
        )
        assert reviewer_read.status_code == 404

    def test_delete_own_plan(
        self,
        student_a: tuple[str, Client],
        seeded_pathway_for_plans: dict[str, Any],
    ) -> None:
        _user_id, scoped_client = student_a
        session = scoped_client.auth.get_session()
        assert session is not None
        headers = _auth_header(session.access_token)

        create = client.post(
            "/plans",
            json={"pathway_id": seeded_pathway_for_plans["pathway"]["id"]},
            headers=headers,
        )
        plan_id = create.json()["id"]

        delete = client.delete(f"/plans/{plan_id}", headers=headers)
        assert delete.status_code == 204

        listing = client.get("/plans", headers=headers)
        assert listing.json() == []
