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
from tests.db.conftest import run_name

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
        .insert({"name": run_name("API test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("API test pathway (SYNTHETIC)"),
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
                "verifier": run_name("test-fixture"),
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

    def test_malformed_pathway_id_gives_a_clean_422_not_a_500(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """Security-review finding, 2026-09-20 (MEDIUM): the JSON route
        had zero UUID-shape validation on pathway_id before calling
        assemble_comparisons(), which passed it straight into a Postgres
        query -- a malformed id raised an uncaught postgrest APIError
        (Postgres code 22P02) that propagated as an unhandled 500.
        app/web/pages.py's HTML route already had this exact fix; this
        pins the same protection onto the JSON route."""
        response = client.get(
            "/compare",
            params={"pathway_id": ["not-a-uuid", seeded_pathway["pathway"]["id"]]},
        )
        assert response.status_code == 422

    def test_duplicate_pathway_id_gives_a_clean_400_not_a_fake_comparison(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """Security-review finding, 2026-09-20 (LOW): requesting the same
        pathway_id twice passed the count check and silently rendered
        the same pathway twice as if it were a real two-way comparison."""
        pid = seeded_pathway["pathway"]["id"]
        response = client.get("/compare", params={"pathway_id": [pid, pid]})
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
                    "name": run_name("second API test pathway (SYNTHETIC)"),
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
                    "authority_name": run_name("API TEST OFFICIAL SOURCE (fixture)"),
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
                    "name": run_name("third API test pathway (SYNTHETIC)"),
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
                    "verifier": run_name("test-fixture-reviewer"),
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
                    "authority_name": run_name("API TEST OFFICIAL SOURCE (net_to_arrange)"),
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
                    "name": run_name("fourth API test pathway (SYNTHETIC)"),
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
                    "verifier": run_name("test-fixture-reviewer"),
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


class TestReviewerNeverSeesADraftClaimEitherAppLayerNotJustRLS:
    """Security-review finding, 2026-09-20 (MEDIUM, test coverage): every
    existing test for /compare used only the guest role. RLS
    (db/migrations/0001_init.sql's `claims_select_published` policy)
    already blocks a guest/student from ever fetching a draft row at
    all, which means those tests only prove RLS works -- not that
    field_value_for()'s own independent status/synthetic re-check does
    anything. A REVIEWER's RLS-scoped client CAN select a draft row
    (`status=published or is_reviewer()`), so a reviewer-authenticated
    request is the only one that actually exercises the app-layer check
    end to end over a live DB round-trip, rather than relying on RLS
    having already filtered the row out before app code ever saw it.
    Mirrors tests/db/test_api_eligibility.py's
    TestDraftClaimsNeverAffectEligibilityOutcome for a sibling route."""

    def test_reviewer_still_never_sees_a_draft_claim_value_on_compare(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        seeded_pathway: dict[str, Any],
    ) -> None:
        """seeded_pathway already carries a draft entry_requirements
        claim on a synthetic source -- both reasons it must never show
        as a fact. Authenticate as the reviewer fixture (whose RLS-scoped
        client CAN see this row) and prove the API response still hides
        it, proving the app layer, not RLS, is what protects this field
        for the one role RLS lets the row through for."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token

        other_pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": seeded_pathway["career"]["id"],
                    "name": run_name("reviewer-visibility test pathway (SYNTHETIC)"),
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
                headers=_auth(token),
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
