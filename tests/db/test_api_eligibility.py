"""Integration tests for GET /eligibility against the real database.

Seeds eligibility-shaped claims on a real pathway via the service-role
admin client, then checks the actual FastAPI route builds the right
criteria from them and returns the right outcome — end to end, not
mocked.
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
def eligibility_pathway(
    admin_client: Client,
) -> Iterator[dict[str, Any]]:
    """A career + pathway with a real official source and four
    eligibility claims published: minimum_age=17, maximum_age=25,
    minimum_marks_percentage=50, required_subjects=Physics,Chemistry,Biology.
    """
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": "API TEST ELIGIBILITY SOURCE (fixture)",
                "official_url": "https://example.invalid/eligibility-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": "Eligibility test career (SYNTHETIC)"})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "Eligibility test pathway (SYNTHETIC)",
                "description": "Seeded by tests/db/test_api_eligibility.py",
            }
        )
        .execute()
        .data[0]
    )

    claim_specs = [
        ("minimum_age", "17"),
        ("maximum_age", "25"),
        ("minimum_marks_percentage", "50"),
        ("required_subjects", "Physics,Chemistry,Biology"),
    ]
    claims = []
    for field, value in claim_specs:
        claims.append(
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": field,
                    "value": value,
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

    yield {"career": career, "pathway": pathway, "source": official_source, "claims": claims}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestEligibilityEndpoint:
    def test_eligible_student_meets(self, eligibility_pathway: dict[str, Any]) -> None:
        response = client.get(
            "/eligibility",
            params={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology,English",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert len(body["criteria"]) == 4
        assert all(c["source_claim_id"] is not None for c in body["criteria"])

    def test_missing_subject_gives_does_not_meet(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/eligibility",
            params={
                "pathway_id": eligibility_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry",  # no Biology
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "does_not_meet"

    def test_no_student_facts_gives_insufficient_information(
        self, eligibility_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/eligibility", params={"pathway_id": eligibility_pathway["pathway"]["id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "insufficient_information"

    def test_pathway_with_no_eligibility_claims_vacuously_meets(
        self, admin_client: Client
    ) -> None:
        """A pathway that has never had eligibility rules published has
        no criteria to fail or be unknown about — must not fabricate an
        'insufficient_information' about rules nobody ever stated."""
        career = (
            admin_client.table("careers")
            .insert({"name": "No-criteria test career (SYNTHETIC)"})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": "No-criteria test pathway (SYNTHETIC)",
                    "description": "No eligibility claims at all",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get("/eligibility", params={"pathway_id": pathway["id"]})
            assert response.status_code == 200
            body = response.json()
            assert body["outcome"] == "meets"
            assert body["criteria"] == []
        finally:
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()
