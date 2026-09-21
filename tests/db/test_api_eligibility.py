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
from tests.db.conftest import run_name

client = TestClient(app)

# QA-3: these two literals are asserted verbatim further down (not read
# back off the fixture's own returned dict, unlike every career/pathway
# name in this file), so each is tagged exactly once, here, and reused —
# never re-typed — everywhere it must match.
_ELIGIBILITY_SOURCE_NAME = run_name("API TEST ELIGIBILITY SOURCE (fixture)")
_MALICIOUS_SOURCE_NAME = run_name("MALICIOUS SOURCE (test)")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
                "authority_name": _ELIGIBILITY_SOURCE_NAME,
                "official_url": "https://example.invalid/eligibility-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Eligibility test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Eligibility test pathway (SYNTHETIC)"),
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
                    "verifier": run_name("test-fixture-reviewer"),
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
        # ux-qa-reviewer finding, 2026-09-19: a bare claim UUID has
        # nowhere to get "source authority ... official link,
        # verification date" from (docs/UI.md) -- now resolved.
        assert all(c["source_authority"] == _ELIGIBILITY_SOURCE_NAME for c in body["criteria"])
        assert all(
            c["source_url"] == "https://example.invalid/eligibility-source"
            for c in body["criteria"]
        )
        assert all(c["verification_date"] == "2026-09-01" for c in body["criteria"])

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
            .insert({"name": run_name("No-criteria test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("No-criteria test pathway (SYNTHETIC)"),
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


class TestDangerousSourceUrlSchemeIsNeverRendered:
    """Security-review finding, 2026-09-20: nothing validated the URL
    scheme on Source.official_url before it reached a template's
    href="{{ ... }}" -- a javascript:/data: URI would render as a fully
    clickable, script-executing link on the evidence badge. Confirmed
    live and fixed with the same "degrade to unavailable" pattern
    app/planning/comparison.py's field_value_for() also uses -- this
    route builds source_url independently, so that fix doesn't cover it."""

    def test_javascript_scheme_source_url_is_never_returned(
        self, admin_client: Client
    ) -> None:
        dangerous_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": _MALICIOUS_SOURCE_NAME,
                    "official_url": "javascript:alert(document.cookie)",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("Dangerous-URL test career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("Dangerous-URL test pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_api_eligibility.py",
                }
            )
            .execute()
            .data[0]
        )
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "minimum_age",
                    "value": "17",
                    "source_id": dangerous_source["id"],
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
                "/eligibility", params={"pathway_id": pathway["id"], "age": 18}
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["criteria"]) == 1
            # The authority name (plain text, safe) still shows; the
            # dangerous URL itself must never reach the response.
            assert body["criteria"][0]["source_authority"] == _MALICIOUS_SOURCE_NAME
            assert body["criteria"][0]["source_url"] is None
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()
            admin_client.table("sources").delete().eq("id", dangerous_source["id"]).execute()


@pytest.fixture
def pathway_with_a_draft_criterion(
    admin_client: Client,
) -> Iterator[dict[str, Any]]:
    """One PUBLISHED minimum_age=17 claim, plus a DRAFT
    minimum_marks_percentage=90 claim never approved by anyone.
    db/migrations/0001_init.sql's `claims_select_published` policy lets
    a reviewer's own RLS-scoped client SELECT the draft row too (so they
    can review it) — that must not mean a reviewer calling /eligibility
    gets an outcome computed from it."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("API TEST DRAFT-CRITERION SOURCE (fixture)"),
                "official_url": "https://example.invalid/draft-criterion-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Draft-criterion test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Draft-criterion test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_api_eligibility.py",
            }
        )
        .execute()
        .data[0]
    )
    claims = [
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_age",
                "value": "17",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0],
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_marks_percentage",
                "value": "90",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "draft",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0],
    ]

    yield {"pathway": pathway}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestDraftClaimsNeverAffectEligibilityOutcome:
    """Regression test for a maker-checker bypass: _criteria_from_claims
    used to build a criterion from ANY row the caller's client could
    SELECT, trusting RLS alone to mean "this is a published fact" --
    true for a guest/student, false for a reviewer, who can also SELECT
    drafts. A student scoring 72% would fail a published-only check here
    (only minimum_age=17 exists) but would wrongly fail an unpublished
    minimum_marks_percentage=90 check if the draft leaked through."""

    def test_reviewer_gets_the_same_outcome_as_a_guest_draft_ignored(
        self,
        reviewer: tuple[str, Client],
        pathway_with_a_draft_criterion: dict[str, Any],
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.get(
            "/eligibility",
            params={
                "pathway_id": pathway_with_a_draft_criterion["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
            },
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "meets"
        assert len(body["criteria"]) == 1
        assert body["criteria"][0]["name"] == "minimum_age"
