"""Live end-to-end tests for GET /pathways/{id}/view (UI-5) -- the
pathway/career detail page. Same seeding pattern as
tests/db/test_web_pages.py; the difference here is this file's own
publication-integrity focus: every fact on this page is built through
`app.planning.comparison.field_value_for`, and this suite exists to
prove that a draft or synthetic-sourced claim never reaches the
response, not just that a published one renders correctly.
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

_DETAIL_SOURCE_NAME = run_name("DETAIL PAGE TEST OFFICIAL SOURCE (fixture)")
_DETAIL_PATHWAY_DESCRIPTION = (
    "Seeded by tests/db/test_web_detail.py -- what a student in this pathway would do."
)


@pytest.fixture
def detail_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A real career + pathway with four published, cycle-scoped
    "programme fact" claims plus a published, cycle-scoped
    verified_charges claim -- enough real content to prove every fact,
    its trust badge, its source, its verification date AND its
    academic_cycle all render, not just that the page doesn't crash."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Detail page test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Detail page test pathway (SYNTHETIC)"),
                "description": _DETAIL_PATHWAY_DESCRIPTION,
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _DETAIL_SOURCE_NAME,
                "official_url": "https://example.invalid/detail-web-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    claim_specs = [
        ("entry_requirements", "Class 12 with Physics, Chemistry, Biology"),
        ("main_stages", "Entrance exam, counselling, admission"),
        ("time_range", "5.5 years"),
        ("location", "Ahmedabad"),
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
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                    "academic_cycle": "2026-27",
                }
            )
            .execute()
            .data[0]
        )
    claims.append(
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "verified_charges",
                "value": 125000,
                "currency": "INR",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
                "academic_cycle": "2026-27",
            }
        )
        .execute()
        .data[0]
    )

    yield {"career": career, "pathway": pathway, "source": official_source}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestPathwayDetailPage:
    def test_malformed_pathway_id_shows_a_friendly_message_not_a_500(self) -> None:
        response = client.get("/pathways/not-a-uuid-at-all/view")
        assert response.status_code == 200
        assert "doesn&#39;t point to a valid pathway" in response.text
        assert "Back to explore" in response.text

    def test_malformed_pathway_id_error_alert_has_role_alert(self) -> None:
        response = client.get("/pathways/also-not-a-uuid/view")
        assert response.status_code == 200
        assert 'role="alert"' in response.text

    def test_nonexistent_pathway_id_shows_a_friendly_message_not_a_500(self) -> None:
        response = client.get(
            "/pathways/00000000-0000-0000-0000-000000000000/view"
        )
        assert response.status_code == 200
        assert "couldn&#39;t find that pathway" in response.text
        assert "00000000-0000-0000-0000-000000000000" not in response.text

    def test_db_unavailable_shows_a_friendly_message_not_a_500(self) -> None:
        from app.web.pages import _db_client_or_none

        def _unavailable() -> Iterator[Client | None]:
            yield None

        app.dependency_overrides[_db_client_or_none] = _unavailable
        try:
            response = client.get(
                "/pathways/00000000-0000-0000-0000-000000000001/view"
            )
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert "trouble reaching our data" in response.text
        assert "try again shortly" in response.text

    def test_shows_pathway_and_career_names_and_description(
        self, detail_pathway: dict[str, Any]
    ) -> None:
        response = client.get(f"/pathways/{detail_pathway['pathway']['id']}/view")
        assert response.status_code == 200
        assert detail_pathway["pathway"]["name"] in response.text
        assert detail_pathway["career"]["name"] in response.text
        assert _DETAIL_PATHWAY_DESCRIPTION in response.text

    def test_published_facts_show_trust_badge_source_date_and_cycle(
        self, detail_pathway: dict[str, Any]
    ) -> None:
        response = client.get(f"/pathways/{detail_pathway['pathway']['id']}/view")
        assert response.status_code == 200
        assert "Class 12 with Physics, Chemistry, Biology" in response.text
        assert "Checked against official source" in response.text
        assert _DETAIL_SOURCE_NAME in response.text
        assert "verified 2026-09-01" in response.text
        assert "2026-27 cycle" in response.text

    def test_verified_charges_shows_money_currency_and_cycle(
        self, detail_pathway: dict[str, Any]
    ) -> None:
        response = client.get(f"/pathways/{detail_pathway['pathway']['id']}/view")
        assert response.status_code == 200
        assert "₹1,25,000" in response.text or "₹125,000" in response.text
        assert "What you'd need to arrange" in response.text

    def test_links_forward_to_requirements_timeline_and_compare(
        self, detail_pathway: dict[str, Any]
    ) -> None:
        pathway_id = detail_pathway["pathway"]["id"]
        response = client.get(f"/pathways/{pathway_id}/view")
        assert response.status_code == 200
        assert f"/requirements/view?pathway_id={pathway_id}" in response.text
        assert f"/timeline/view?pathway_id={pathway_id}" in response.text
        assert f"/compare/view?pathway_id={pathway_id}" in response.text

    def test_draft_claim_value_never_appears_in_the_response_body(
        self,
        admin_client: Client,
        detail_pathway: dict[str, Any],
    ) -> None:
        """Seeds a DRAFT claim with a distinctive, greppable value on a
        field this page renders (`location`, already published by the
        fixture above) and asserts it does not appear anywhere in the
        response text -- not the JSON API, the actual rendered HTML a
        browser would show. `field_value_for` reads the LATEST match by
        claims_by_field keying on field name, so this draft (inserted
        after the fixture's published claims) must never win the slot or
        leak into it."""
        distinctive_value = "DRAFT-VALUE-MUST-NEVER-RENDER-detail-a1b2c3"
        draft_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": run_name("Detail page draft test source"),
                    "official_url": "https://example.invalid/detail-draft-test-source",
                    "source_type": "official",
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
                    "entity_id": detail_pathway["pathway"]["id"],
                    "field": "main_stages",
                    "value": distinctive_value,
                    "source_id": draft_source["id"],
                    "verification_date": "2026-01-01",
                    "verifier": run_name("test-fixture"),
                    "status": "draft",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(f"/pathways/{detail_pathway['pathway']['id']}/view")
            assert response.status_code == 200
            assert distinctive_value not in response.text
        finally:
            admin_client.table("claims").delete().eq("id", draft_claim["id"]).execute()
            admin_client.table("sources").delete().eq("id", draft_source["id"]).execute()

    def test_synthetic_sourced_approved_looking_claim_never_appears(
        self,
        admin_client: Client,
        synthetic_source: str,
    ) -> None:
        """A claim that is `in_review` (the state demo-mode "sample"
        claims sit in -- the closest a claim can get to looking
        "approved" without being genuinely published) AND backed by a
        `synthetic` source must still degrade to `not_available` on this
        page: `trust_label_for_claim` returns `not_available` for
        anything that is not `status == published`, before it even looks
        at the source, so this is never rendered -- not as a labelled
        sample, not as a blank slot, not at all. Uses its own pathway
        (rather than `detail_pathway`'s) with zero other claims, so a
        distinctive value is not needed: if ANY value for this field
        appeared, the page would be showing a fact that was never
        published."""
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("Detail page synthetic test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("Detail page synthetic test pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_web_detail.py.",
                }
            )
            .execute()
            .data[0]
        )
        distinctive_value = "SYNTHETIC-APPROVED-LOOKING-MUST-NEVER-RENDER-x9y8z7"
        in_review_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "entry_requirements",
                    "value": distinctive_value,
                    "source_id": synthetic_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("test-fixture"),
                    "status": "in_review",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(f"/pathways/{pathway['id']}/view")
            assert response.status_code == 200
            assert distinctive_value not in response.text
            assert "Not available" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", in_review_claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()

    def test_no_published_claims_degrades_to_not_available_not_a_crash(
        self, admin_client: Client
    ) -> None:
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("Detail page empty test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("Detail page empty test pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_web_detail.py, zero claims.",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(f"/pathways/{pathway['id']}/view")
            assert response.status_code == 200
            assert pathway["name"] in response.text
            assert "Not available" in response.text
        finally:
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestPathwayDetailLinkWiredFromExploreAndCompare:
    """UI-5 item 4: `_components.html`'s `pathway_detail_link` macro
    finally has a route to point at -- Explore's and Compare's existing
    (unchanged) calls to it must now render a real, working link instead
    of nothing."""

    def test_explore_links_to_the_pathway_detail_page(
        self, detail_pathway: dict[str, Any]
    ) -> None:
        pathway_id = detail_pathway["pathway"]["id"]
        response = client.get("/explore")
        assert response.status_code == 200
        assert f'/pathways/{pathway_id}/view' in response.text

        follow = client.get(f"/pathways/{pathway_id}/view")
        assert follow.status_code == 200
        assert detail_pathway["pathway"]["name"] in follow.text

    def test_compare_links_to_the_pathway_detail_page(
        self, detail_pathway: dict[str, Any], admin_client: Client
    ) -> None:
        # Compare needs a second pathway to satisfy MIN_PATHWAYS.
        career_b = (
            admin_client.table("careers")
            .insert({"name": run_name("Detail page compare-partner career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway_b = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career_b["id"],
                    "name": run_name("Detail page compare-partner pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_web_detail.py.",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare/view",
                params={
                    "pathway_id": [detail_pathway["pathway"]["id"], pathway_b["id"]]
                },
            )
            assert response.status_code == 200
            assert f'/pathways/{detail_pathway["pathway"]["id"]}/view' in response.text
            assert f'/pathways/{pathway_b["id"]}/view' in response.text
        finally:
            admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
            admin_client.table("careers").delete().eq("id", career_b["id"]).execute()
