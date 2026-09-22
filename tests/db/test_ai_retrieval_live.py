"""Live tests for app/ai/retrieval.py (AI-5) against a real local
Supabase stack (`make test-db-up`) — the one property a fake client
cannot prove: that a REAL reviewer-scoped RLS client (which genuinely CAN
`SELECT` draft/in_review claims, db/migrations/0001_init.sql) still gets
them dropped by this module's own Python re-check, not merely by RLS.
`tests/unit/test_ai_retrieval.py` already covers the same shape of
behaviour with a fake client; this file is the live Postgres/PostgREST/
RLS round-trip proof, the same split `tests/db/test_web_timeline_page.py`
documents for its own case.

Read-only from `app.ai.retrieval`'s own point of view: every assertion
below calls only its `fetch_*`/`pathway_*` functions, which only ever
SELECT. Fixture setup/teardown (seeding and cleaning up the pathway/
claims/sources rows themselves) uses the service-role `admin_client`,
the same convention every other `tests/db` file already follows.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from supabase import Client

from app.ai import retrieval
from app.db import get_anon_client
from tests.db.conftest import run_name

_OFFICIAL_SOURCE_NAME = run_name("AI-5 RETRIEVAL LIVE SOURCE (fixture)")
_SYNTHETIC_SOURCE_NAME = run_name("AI-5 RETRIEVAL LIVE SYNTHETIC (fixture)")


@pytest.fixture
def retrieval_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A real pathway carrying one claim of each status this module must
    tell apart: a published, official-sourced `minimum_age`; a draft
    `maximum_age`; an in_review `required_subjects`; a `domicile_states`
    claim that IS `published` but is backed by a synthetic source (the
    state `forbid_publishing_synthetic_claims()` should prevent in
    practice — seeded directly here, the same defence-in-depth case
    `tests/unit/test_comparison.py` exercises in memory); and a published,
    correctly-currencied `verified_charges` claim for the cost-engine
    tests."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _OFFICIAL_SOURCE_NAME,
                "official_url": "https://example.invalid/ai-5-retrieval-official-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    synthetic_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _SYNTHETIC_SOURCE_NAME,
                "official_url": "https://example.invalid/ai-5-retrieval-synthetic-source",
                "source_type": "synthetic",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("AI-5 retrieval career")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("AI-5 retrieval pathway"),
                "description": "Seeded by tests/db/test_ai_retrieval_live.py",
            }
        )
        .execute()
        .data[0]
    )

    def _insert_claim(
        field: str, value: Any, status: str, source_id: str, **extra: Any
    ) -> dict[str, Any]:
        row: dict[str, Any] = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": field,
                    "value": value,
                    "source_id": source_id,
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": status,
                    "review_due_date": "2099-01-01",
                    **extra,
                }
            )
            .execute()
            .data[0]
        )
        return row

    claims = [
        _insert_claim("minimum_age", 18, "published", official_source["id"]),
        _insert_claim("maximum_age", 25, "draft", official_source["id"]),
        _insert_claim(
            "required_subjects", "Physics,Chemistry", "in_review", official_source["id"]
        ),
        _insert_claim("domicile_states", "Gujarat", "published", synthetic_source["id"]),
        _insert_claim(
            "verified_charges", 50000, "published", official_source["id"], currency="INR"
        ),
    ]

    yield {
        "career": career,
        "pathway": pathway,
        "official_source": official_source,
        "synthetic_source": synthetic_source,
        "claims": claims,
    }

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()
    admin_client.table("sources").delete().eq("id", synthetic_source["id"]).execute()


class TestFetchPathwayRecordsLive:
    def test_only_the_published_non_synthetic_claim_is_returned_as_guest(
        self, retrieval_pathway: dict[str, Any]
    ) -> None:
        guest = get_anon_client()
        records = retrieval.fetch_pathway_records(guest, retrieval_pathway["pathway"]["id"])
        fields = [r.field for r in records]
        assert "minimum_age" in fields
        assert "maximum_age" not in fields
        assert "required_subjects" not in fields
        assert "domicile_states" not in fields  # synthetic-backed, even though "published"
        by_field = {r.field: r for r in records}
        assert by_field["minimum_age"].value == 18
        assert by_field["minimum_age"].source_authority == _OFFICIAL_SOURCE_NAME

    def test_drafts_and_synthetic_backed_claims_stay_excluded_even_for_a_reviewer(
        self, retrieval_pathway: dict[str, Any], reviewer: tuple[str, Client]
    ) -> None:
        """The core live proof this file exists for: a REAL reviewer-
        scoped client (whose RLS genuinely lets it `SELECT` draft/
        in_review rows) still only gets the published, non-synthetic-
        backed record back — this module's own Python re-check, not RLS,
        is what is actually enforcing that, exactly as the module
        docstring claims."""
        _, reviewer_client = reviewer
        records = retrieval.fetch_pathway_records(
            reviewer_client, retrieval_pathway["pathway"]["id"]
        )
        fields = [r.field for r in records]
        assert "minimum_age" in fields
        assert "maximum_age" not in fields
        assert "required_subjects" not in fields
        assert "domicile_states" not in fields


class TestFetchClaimRecordLive:
    def test_a_published_claim_id_resolves_for_a_guest(
        self, retrieval_pathway: dict[str, Any]
    ) -> None:
        published_claim = next(
            c for c in retrieval_pathway["claims"] if c["field"] == "minimum_age"
        )
        guest = get_anon_client()
        record = retrieval.fetch_claim_record(guest, published_claim["id"])
        assert record is not None
        assert record.field == "minimum_age"
        assert record.value == 18

    def test_a_draft_claim_id_resolves_to_none_even_for_a_reviewer(
        self, retrieval_pathway: dict[str, Any], reviewer: tuple[str, Client]
    ) -> None:
        draft_claim = next(c for c in retrieval_pathway["claims"] if c["field"] == "maximum_age")
        _, reviewer_client = reviewer
        assert retrieval.fetch_claim_record(reviewer_client, draft_claim["id"]) is None


class TestPathwayCostSummaryLive:
    def test_delegates_to_the_real_cost_engine_against_live_data(
        self, retrieval_pathway: dict[str, Any]
    ) -> None:
        guest = get_anon_client()
        summary = retrieval.pathway_cost_summary(guest, retrieval_pathway["pathway"]["id"])
        assert summary.verified_charges.total is not None
        assert summary.verified_charges.total.amount == 50000
        assert summary.net_to_arrange is not None
        assert summary.net_to_arrange.amount == 50000


class TestPathwayEligibilityCriteriaLive:
    def test_only_the_published_criterion_is_built_even_for_a_reviewer(
        self, retrieval_pathway: dict[str, Any], reviewer: tuple[str, Client]
    ) -> None:
        _, reviewer_client = reviewer
        criteria = retrieval.pathway_eligibility_criteria(
            reviewer_client, retrieval_pathway["pathway"]["id"]
        )
        names = {c.name for c in criteria}
        assert names == {"minimum_age"}
