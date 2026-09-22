"""Integration tests for GET /ask and GET /ask/view against the real
database (UI-11 / BCI-014) — seeds via the service-role admin client,
reads through a guest's real, RLS-restricted anon client (no Authorization
header), the same convention `tests/db/test_api_explore_compare.py` and
`tests/db/test_web_pages.py` already use.

Neither route is registered on `app.main.app` yet — `app/main.py` is a
frozen, lead-only registry (see `app/api/ask.py`'s own module docstring
for the exact `RouterSlot` lines the lead needs to add) — so, like
`tests/unit/test_web_ask.py`, this module builds its own small
`FastAPI()` app wrapping both routers directly. Unlike that unit-test
module, NOTHING here fakes the database: `get_db_client`/
`_db_client_or_none` are left exactly as `app/api/ask.py`/
`app/web/ask_pages.py` wire them, so every request in this file really
hits the local Supabase stack (`tests/db/conftest.py`'s loopback-only
target guard) and is really subject to RLS — this file's whole point is
proving a DRAFT claim is genuinely invisible to a guest here, not merely
absent from a hand-built fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from supabase import Client

from app.api.ask import router as ask_json_router
from app.web.ask_pages import router as ask_html_router
from tests.db.conftest import run_name

_FALLBACK_COPY = "You can still compare routes and use the calculators."


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ask_json_router)
    app.include_router(ask_html_router)
    return app


client = TestClient(_make_app())


@pytest.fixture
def seeded_pathway(admin_client: Client, synthetic_source: str) -> Iterator[dict[str, Any]]:
    """A career + one pathway with:
    - a PUBLISHED `entry_requirements` claim (pathway_overview should show it)
    - a PUBLISHED `verified_charges` claim with a currency (cost_breakdown)
    - a PUBLISHED `minimum_age` claim (eligibility_gap)
    - a DRAFT `main_stages` claim on a SYNTHETIC source (must stay
      invisible to a guest -- both because it's a draft and because a
      synthetic source can never back a published claim at all)
    all cleaned up after.
    """
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Ask BCION test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Ask BCION test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_ask_view.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("ASK VIEW TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/ask-view-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    published_claims = (
        admin_client.table("claims")
        .insert(
            [
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "entry_requirements",
                    "value": "Class 12 pass with Physics, Chemistry, Biology",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "verified_charges",
                    "value": 85000,
                    "currency": "INR",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "minimum_age",
                    "value": 16,
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
    draft_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "main_stages",
                "value": "should never be visible to a guest",
                "source_id": synthetic_source,
                "verification_date": "2026-01-01",
                "verifier": run_name("test-fixture"),
                "status": "draft",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )

    yield {
        "career": career,
        "pathway": pathway,
        "official_source": official_source,
        "published_claims": published_claims,
        "draft_claim": draft_claim,
    }

    claim_ids = [c["id"] for c in published_claims] + [draft_claim["id"]]
    admin_client.table("claims").delete().in_("id", claim_ids).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestAskJsonRouteAgainstTheRealStack:
    def test_guest_sees_the_published_pathway_overview_fact(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["entry_requirements"]["value"]["value"] == (
            "Class 12 pass with Physics, Chemistry, Biology"
        )
        assert fields_by_name["entry_requirements"]["value"]["source_url"] == (
            "https://example.invalid/ask-view-test-source"
        )

    def test_guest_never_sees_the_draft_synthetic_claim(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """RLS-level proof, not just this module's own defensive
        re-filter: a real guest anon client cannot even SELECT the draft
        row, so it can never reach `field_value_for` in the first place."""
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert "main_stages" not in fields_by_name
        assert "Main stages" in body["missing_information"]

    def test_cost_breakdown_shows_the_currency_safe_verified_charges(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "cost_breakdown", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["verified_charges"]["value"]["value"] == 85000
        assert fields_by_name["verified_charges"]["value"]["currency"] == "INR"
        assert fields_by_name["verified_charges"]["value"]["label"] == (
            "checked_against_official_source"
        )

    def test_eligibility_gap_shows_minimum_age_and_lists_the_rest_as_missing(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "eligibility_gap", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["minimum_age"]["value"]["value"] == 16
        assert "Domicile" in body["missing_information"]

    def test_unknown_template_is_a_404_that_never_reflects_the_raw_id(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={
                "template": "not-a-real-template-abc123",
                "pathway_id": seeded_pathway["pathway"]["id"],
            },
        )
        assert response.status_code == 404
        assert "not-a-real-template-abc123" not in response.text

    def test_malformed_pathway_id_is_a_clean_422_not_a_500(self) -> None:
        response = client.get(
            "/ask", params={"template": "cost_breakdown", "pathway_id": "not-a-uuid"}
        )
        assert response.status_code == 422

    def test_ai_disabled_by_default_shows_the_fallback_message(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        body = response.json()
        assert body["ai_enabled"] is False
        assert body["show_fallback"] is True
        assert body["fallback_message"] == _FALLBACK_COPY


class TestAskViewPageAgainstTheRealStack:
    def test_every_entry_point_returns_200_with_fallback_copy_and_cited_records(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """The three real `_ask.html` call sites -- cost_breakdown/
        pathway_overview (compare.html), eligibility_gap
        (requirements.html) -- each with pathway_id."""
        for template_id in ("cost_breakdown", "pathway_overview", "eligibility_gap"):
            response = client.get(
                "/ask/view",
                params={"template": template_id, "pathway_id": seeded_pathway["pathway"]["id"]},
            )
            assert response.status_code == 200, template_id
            assert _FALLBACK_COPY in response.text, template_id
            assert "https://example.invalid/ask-view-test-source" in response.text, template_id

    def test_guest_never_sees_the_draft_claim_on_the_rendered_page(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask/view",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert "should never be visible to a guest" not in response.text

    def test_unknown_template_is_a_friendly_404_page_not_a_500(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask/view",
            params={
                "template": "not-a-real-template-abc123",
                "pathway_id": seeded_pathway["pathway"]["id"],
            },
        )
        assert response.status_code == 404
        assert "not-a-real-template-abc123" not in response.text
        assert "Back to explore" in response.text

    def test_pathway_name_is_shown_for_context(self, seeded_pathway: dict[str, Any]) -> None:
        response = client.get(
            "/ask/view",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert seeded_pathway["pathway"]["name"] in response.text
