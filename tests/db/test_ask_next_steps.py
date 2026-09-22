"""Integration tests for GET /ask?template=next_steps against the real
database (AI-18, `tasks/BCI-021.md`).

`app.main.app` already registers both the `ask` and `plans` router slots
(`app/main.py`'s `build_router_slots()`), so — unlike
`tests/db/test_ask_view.py`, written before that registration existed —
this file uses `app.main.app` directly, the same simpler pattern
`tests/db/test_api_plans.py`/`tests/db/test_plan_actions.py` already use.

AI is left at its pilot default (disabled) throughout this file: the
plan-id ownership check this card's own text asks for
("never trust a bare plan_id... since a request could name another
identity's plan id") happens entirely BEFORE `_pipeline_answer()` is ever
called (`app/api/ask.py`'s `ask()`), so every 404/resolution assertion
here is real against the live stack without needing a live/mocked AI
provider. `tests/unit/test_ai_next_steps.py` is where the actual
claim-to-action-text catalogue is proven, against plain fixtures, without
a database at all.
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


# CONSENT-4 (0012): every test below that saves a plan exercises a real,
# RLS-scoped write to saved_plans, which now also requires
# is_admitted(auth.uid()). Same fixture-override pattern already used in
# tests/db/test_plan_actions.py — see that file's own comment for why.
@pytest.fixture
def student_a(student_a: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_a
    admit_student(admin_client, user_id)
    return user_id, client_


@pytest.fixture
def student_b(student_b: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_b
    admit_student(admin_client, user_id)
    return user_id, client_


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _access_token(admin_client: Client, user_client: Client, user_id: str) -> str:
    """Mirrors `tests/db/test_plan_actions.py`'s own file-local helper of
    the same name (same unused-parameter shape, kept for call-site parity
    with that precedent) — `_create_test_user` (`tests/db/conftest.py`)
    already signed this client in; this just reads the token back off
    that session rather than signing in a second time."""
    session = user_client.auth.get_session()
    assert session is not None
    return session.access_token


@pytest.fixture
def seeded_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A career + one pathway with a PUBLISHED `application_window`
    claim and a PUBLISHED `documents_required` claim, both on a real
    (non-synthetic) source — the two action-catalogue fields this card's
    own text worked through (`app/ai/actions.py`)."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("next-steps test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("next-steps test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_ask_next_steps.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("NEXT STEPS TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/next-steps-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    claims = (
        admin_client.table("claims")
        .insert(
            [
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "application_window",
                    "value": "1 March 2027 to 30 April 2027",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "documents_required",
                    "value": "Class 10 marksheet, Passport-size photo",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
            ]
        )
        .execute()
        .data
    )

    yield {"career": career, "pathway": pathway, "official_source": official_source}

    claim_ids = [c["id"] for c in claims]
    admin_client.table("claims").delete().in_("id", claim_ids).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


def _save_plan(client_: Client, student_id: str, pathway_id: str) -> str:
    """Mirrors `tests/db/test_plan_actions.py`'s own file-local `_save`
    helper — a direct, RLS-scoped insert, not a round trip through
    `POST /plans` (this file already exercises `GET /ask` over HTTP;
    seeding via the SDK keeps that the one HTTP call under test)."""
    return (
        client_.table("saved_plans")
        .insert({"student_id": student_id, "pathway_id": pathway_id})
        .execute()
        .data[0]["id"]
    )


class TestNextStepsByPathwayId:
    def test_works_end_to_end_with_pathway_id_directly(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "next_steps", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["template_id"] == "next_steps"
        assert body["entity_kind"] == "pathway"
        assert body["entity_id"] == seeded_pathway["pathway"]["id"]
        # AI disabled by default (pilot default, unset in this test
        # environment) -- deterministic fact_cards are deliberately empty
        # for this template (app/api/ask.py's ASK_TEMPLATES["next_steps"]
        # .fields == ()), and next_step_actions needs the AI layer, which
        # is off.
        assert body["fact_cards"] == []
        assert body["ai_enabled"] is False
        assert body["show_fallback"] is True
        assert body["next_step_actions"] == []


class TestNextStepsByPlanId:
    def test_the_owning_student_s_plan_id_resolves_to_their_pathway(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        a_id, a_client = student_a
        token = _access_token(admin_client, a_client, a_id)
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])

        response = client.get(
            "/ask",
            params={"template": "next_steps", "plan_id": plan_id},
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["entity_kind"] == "pathway"
        assert body["entity_id"] == seeded_pathway["pathway"]["id"]

    def test_a_guest_cannot_resolve_another_identity_s_plan_id(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
    ) -> None:
        """Proof: a plan id belonging to a different identity (a guest,
        here) returns 404, never that identity's actions."""
        a_id, a_client = student_a
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])

        response = client.get("/ask", params={"template": "next_steps", "plan_id": plan_id})
        assert response.status_code == 404
        assert seeded_pathway["pathway"]["id"] not in response.text

    def test_student_b_cannot_resolve_student_a_s_plan_id(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        """Proof: a plan id belonging to a different identity (student A,
        here) returns 404 for student B, never student A's actions."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])
        b_token = _access_token(admin_client, b_client, b_id)

        response = client.get(
            "/ask",
            params={"template": "next_steps", "plan_id": plan_id},
            headers=_auth(b_token),
        )
        assert response.status_code == 404
        assert seeded_pathway["pathway"]["id"] not in response.text

    def test_a_nonexistent_plan_id_is_a_404(self) -> None:
        response = client.get(
            "/ask",
            params={
                "template": "next_steps",
                "plan_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == 404

    def test_a_malformed_plan_id_is_a_404_not_a_500(self) -> None:
        response = client.get(
            "/ask", params={"template": "next_steps", "plan_id": "not-a-uuid"}
        )
        assert response.status_code == 404

    def test_plan_id_is_ignored_by_the_other_three_templates(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        """`plan_id` is only ever consulted for `next_steps`
        (`app/api/ask.py`'s own docstring) -- for every other template it
        is simply unused, and the existing pathway_id/career_id
        422 still applies when neither is given."""
        a_id, a_client = student_a
        token = _access_token(admin_client, a_client, a_id)
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])

        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "plan_id": plan_id},
            headers=_auth(token),
        )
        assert response.status_code == 422


class TestNextStepsFactCardsAreDeliberatelyEmpty:
    def test_missing_information_is_also_empty(self, seeded_pathway: dict[str, Any]) -> None:
        """`ASK_TEMPLATES["next_steps"].fields == ()` -- nothing to be
        missing either, since nothing was ever looked up as a fact."""
        response = client.get(
            "/ask",
            params={"template": "next_steps", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert response.json()["missing_information"] == []
