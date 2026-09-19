"""Live end-to-end tests for the actual clickable UI (app/web/) — the
first real user-facing screens this whole project has had. Same seeding
pattern as tests/db/test_api_explore_compare.py; the difference here is
asserting on rendered HTML content instead of a JSON body.
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
def two_pathways(
    admin_client: Client, synthetic_source: str
) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers").insert({"name": "Web UI test career"}).execute().data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "Web UI test pathway A",
                "description": "Seeded by tests/db/test_web_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    pathway_b = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "Web UI test pathway B",
                "description": "Seeded by tests/db/test_web_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": "WEB UI TEST OFFICIAL SOURCE",
                "official_url": "https://example.invalid/web-ui-test-source",
                "source_type": "official",
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
                "entity_id": pathway_a["id"],
                "field": "verified_charges",
                "value": 85000,
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

    yield {"career": career, "pathway_a": pathway_a, "pathway_b": pathway_b}

    admin_client.table("claims").delete().eq("id", published_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestExplorePage:
    def test_home_redirects_to_explore(self) -> None:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/explore"

    def test_static_css_is_served(self) -> None:
        response = client.get("/static/css/app.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_explore_lists_seeded_career_and_pathways(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get("/explore")
        assert response.status_code == 200
        assert two_pathways["career"]["name"] in response.text
        assert two_pathways["pathway_a"]["name"] in response.text
        assert two_pathways["pathway_b"]["name"] in response.text


class TestComparePage:
    def test_wrong_pathway_count_shows_a_friendly_message_not_a_bare_error(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view", params={"pathway_id": [two_pathways["pathway_a"]["id"]]}
        )
        assert response.status_code == 200
        assert "Pick 2 or 3 pathways" in response.text
        assert "Back to explore" in response.text

    def test_compare_shows_both_pathway_names_and_trust_labels(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert response.status_code == 200
        assert two_pathways["pathway_a"]["name"] in response.text
        assert two_pathways["pathway_b"]["name"] in response.text
        # Pathway A's published official claim:
        assert "Checked against official source" in response.text
        assert "85,000" in response.text
        # Pathway B has no claims at all -- every field must degrade to
        # "not available", never a blank or a crash (docs/UI.md: "name
        # the missing requirement/information, never guess").
        assert "Not available" in response.text

    def test_closing_prompt_is_present(self, two_pathways: dict[str, Any]) -> None:
        """docs/UI.md's exact required closing prompt for this screen."""
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert "Which option would you like to investigate further?" in response.text
