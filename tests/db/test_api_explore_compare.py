"""Integration tests for GET /careers and GET /compare against the real
database — seeds via the service-role admin client, reads through the
actual FastAPI app as a guest would (no Authorization header, so
app.api.deps.get_db_client falls back to the anon/RLS-restricted client).
This is the real M1 exit proof for the vertical slice: a published
career record really does flow through explore -> compare with correct
trust labels, and a draft claim really is invisible to a guest.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app

client = TestClient(app)


@pytest.fixture
def seeded_pathway(
    admin_client: Client, synthetic_source: str
) -> Iterator[dict[str, Any]]:
    """A career + one pathway with a published 'entry_requirements' claim
    and a published 'verified_charges' cost claim, all cleaned up after.
    Uses the synthetic_source fixture (tests/db/conftest.py) — note the DB
    trigger forbids ever publishing a claim on a synthetic source, so
    these claims are deliberately left in 'draft' where that matters and
    the test asserts on draft-invisibility rather than needing a real
    official source just to prove the plumbing works end to end.
    """
    career = (
        admin_client.table("careers")
        .insert({"name": "API test career (SYNTHETIC)"})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "API test pathway (SYNTHETIC)",
                "description": "Seeded by tests/db/test_api_explore_compare.py",
            }
        )
        .execute()
        .data[0]
    )
    draft_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "entry_requirements",
                "value": "should never be visible to a guest",
                "source_id": synthetic_source,
                "verification_date": "2026-01-01",
                "verifier": "test-fixture",
                "status": "draft",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )

    yield {"career": career, "pathway": pathway, "draft_claim": draft_claim}

    admin_client.table("claims").delete().eq("id", draft_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestExploreCareers:
    def test_guest_sees_seeded_career_and_pathway(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get("/careers")
        assert response.status_code == 200
        body = response.json()

        career_ids = {c["id"] for c in body["careers"]}
        pathway_ids = {p["id"] for p in body["pathways"]}
        assert seeded_pathway["career"]["id"] in career_ids
        assert seeded_pathway["pathway"]["id"] in pathway_ids


class TestComparePathways:
    def test_rejects_fewer_than_two_pathways(self, seeded_pathway: dict[str, Any]) -> None:
        response = client.get("/compare", params={"pathway_id": seeded_pathway["pathway"]["id"]})
        assert response.status_code == 400

    def test_guest_never_sees_a_draft_claim_value(
        self, admin_client: Client, seeded_pathway: dict[str, Any]
    ) -> None:
        """The core safety property of this whole slice: a draft claim's
        VALUE must never reach a guest response, even though the claim
        row technically exists and is tied to a pathway they can see."""
        other_pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": seeded_pathway["career"]["id"],
                    "name": "second API test pathway (SYNTHETIC)",
                    "description": "Seeded by tests/db/test_api_explore_compare.py",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare",
                params={
                    "pathway_id": [
                        seeded_pathway["pathway"]["id"],
                        other_pathway["id"],
                    ]
                },
            )
            assert response.status_code == 200
            body = response.json()
            target = next(
                p for p in body["pathways"] if p["pathway_id"] == seeded_pathway["pathway"]["id"]
            )
            entry_req = target["fields"]["entry_requirements"]
            assert entry_req["label"] == "not_available"
            assert entry_req["value"] is None
        finally:
            admin_client.table("pathways").delete().eq("id", other_pathway["id"]).execute()

    def test_published_official_claim_shows_correct_trust_label(
        self, admin_client: Client, seeded_pathway: dict[str, Any]
    ) -> None:
        """End-to-end: seed a claim against a real official Source,
        publish it, and confirm the API returns it with the right label —
        not just the pure-function unit test, the whole stack."""
        official_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": "API TEST OFFICIAL SOURCE (fixture)",
                    "official_url": "https://example.invalid/official-test-source",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        other_pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": seeded_pathway["career"]["id"],
                    "name": "third API test pathway (SYNTHETIC)",
                    "description": "Seeded by tests/db/test_api_explore_compare.py",
                }
            )
            .execute()
            .data[0]
        )
        published_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": other_pathway["id"],
                    "field": "verified_charges",
                    "value": 75000,
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": "test-fixture-reviewer",
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare",
                params={
                    "pathway_id": [
                        seeded_pathway["pathway"]["id"],
                        other_pathway["id"],
                    ]
                },
            )
            assert response.status_code == 200
            body = response.json()
            target = next(p for p in body["pathways"] if p["pathway_id"] == other_pathway["id"])
            cost = target["cost"]["verified_charges"]
            assert cost["value"] == 75000
            assert cost["label"] == "checked_against_official_source"
            assert cost["source_url"] == "https://example.invalid/official-test-source"
        finally:
            admin_client.table("claims").delete().eq("id", published_claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", other_pathway["id"]).execute()
            admin_client.table("sources").delete().eq("id", official_source["id"]).execute()

    def test_net_to_arrange_is_computed_live_and_assumption_is_editable(
        self, admin_client: Client, seeded_pathway: dict[str, Any]
    ) -> None:
        """End-to-end proof that GET /compare returns app/rules/cost.py's
        real net_to_arrange, not just the raw verified_charges figure --
        and that the ?estimated_additional_expenses override (Lite Build
        Pack §6 "assumption editing") changes it for this request only,
        without writing anything to the database."""
        official_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": "API TEST OFFICIAL SOURCE (net_to_arrange)",
                    "official_url": "https://example.invalid/official-test-source-2",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        other_pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": seeded_pathway["career"]["id"],
                    "name": "fourth API test pathway (SYNTHETIC)",
                    "description": "Seeded by tests/db/test_api_explore_compare.py",
                }
            )
            .execute()
            .data[0]
        )
        published_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": other_pathway["id"],
                    "field": "verified_charges",
                    "value": 100000,
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": "test-fixture-reviewer",
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            params = {
                "pathway_id": [seeded_pathway["pathway"]["id"], other_pathway["id"]],
            }

            no_override = client.get("/compare", params=params)
            assert no_override.status_code == 200
            target = next(
                p for p in no_override.json()["pathways"] if p["pathway_id"] == other_pathway["id"]
            )
            # No hint, no override -> assume zero extra, not unknown.
            assert target["cost"]["net_to_arrange"] == 100000

            with_override = client.get(
                "/compare", params={**params, "estimated_additional_expenses": 25000}
            )
            assert with_override.status_code == 200
            target = next(
                p
                for p in with_override.json()["pathways"]
                if p["pathway_id"] == other_pathway["id"]
            )
            assert target["cost"]["net_to_arrange"] == 125000

            # The other pathway in the same request has no published
            # verified_charges claim at all -- its net must stay unknown,
            # proving the override doesn't paper over a missing figure.
            unpublished = next(
                p
                for p in with_override.json()["pathways"]
                if p["pathway_id"] == seeded_pathway["pathway"]["id"]
            )
            assert unpublished["cost"]["net_to_arrange"] is None
        finally:
            admin_client.table("claims").delete().eq("id", published_claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", other_pathway["id"]).execute()
            admin_client.table("sources").delete().eq("id", official_source["id"]).execute()
