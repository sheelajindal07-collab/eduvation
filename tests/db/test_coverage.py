"""Live tests for app/planning/coverage.py's `covered_jurisdictions` —
SCOPE-6.

`covered_jurisdictions` is the one place "does this jurisdiction have any
published, non-synthetic fact yet" is answered — these tests exercise it
against the REAL claims/sources/pathways tables and RLS policies on the
local Supabase stack, not just its own in-process logic, matching this
card's own instruction to verify the publication-integrity properties
live rather than only at the unit level.
"""

from __future__ import annotations

import random
import string
from collections.abc import Iterator
from typing import Any

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from app.planning.coverage import covered_jurisdictions
from tests.db.conftest import run_name


def _fake_jurisdiction() -> str:
    """A syntactically valid (docs/CONTRACTS.md "Entity vocabulary"
    shape -- db/migrations/0008_jurisdiction_currency.sql's
    `^[A-Z]{2}(-[A-Z0-9]{1,3})?$`) but deliberately FAKE jurisdiction code
    -- not a real ISO 3166 country, not one of app/data/jurisdictions.py's
    47 real state/UT/pilot-country codes -- so this file's own "is NOT
    covered yet" assertions can never be made flaky by:

    (1) some other, concurrently-running LANE on this same shared local
        stack publishing a real claim under a real code like "GB" or "IN"
        at the same wall-clock moment (docs/TESTING.md's parallel-lane
        contract: many worktrees share one local stack), and
    (2) this FILE's own tests running as separate `pytest-xdist` WORKERS
        (`make test-db-parallel`) -- a fixed shared fake code (e.g. a
        bare "ZZ" for every test) would let one worker's published claim
        make another, concurrently-running worker's "not covered yet"
        assertion spuriously fail, since `covered_jurisdictions` answers
        at jurisdiction granularity, not per-pathway.

    "ZZ" itself is reserved (never assigned) in real ISO 3166-1, so the
    "ZZ-XXX" shape here can never collide with a real subdivision code
    either.
    """
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"ZZ-{suffix}"


@pytest.fixture
def coverage_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A dedicated career + pathway in a fresh, per-test-call FAKE
    jurisdiction (see `_fake_jurisdiction`), plus one official
    (non-synthetic) source — no claim yet. Each test below inserts/
    deletes its own claim(s) directly, since what status a claim is in
    (and whether it ever reaches `published`) is exactly what each test
    is about."""
    jurisdiction = _fake_jurisdiction()
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Coverage test career")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Coverage test pathway"),
                "description": "Seeded by tests/db/test_coverage.py",
                "jurisdiction": jurisdiction,
            }
        )
        .execute()
        .data[0]
    )
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("COVERAGE TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/coverage-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway, "source": source, "jurisdiction": jurisdiction}
    # Belt-and-braces: every test below already deletes its own claim in
    # its own try/finally, but this covers a test that fails before that
    # finally runs too -- `entity_id` is a plain uuid column with no FK
    # to `pathways` (db/migrations/0001_init.sql's polymorphic
    # entity_type/entity_id pair), so deleting the pathway first would
    # not cascade and would leave an orphaned claim behind.
    admin_client.table("claims").delete().eq("entity_id", pathway["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", source["id"]).execute()


def _insert_claim(
    admin_client: Client,
    pathway_id: str,
    source_id: str,
    *,
    status: str,
    jurisdiction: str,
) -> str:
    row = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_id,
                "field": "verified_charges",
                "value": 1000,
                "currency": "INR",
                "source_id": source_id,
                "verification_date": "2026-09-01",
                "verifier": run_name("coverage-test-fixture"),
                "status": status,
                "review_due_date": "2099-01-01",
                "jurisdiction": jurisdiction,
            }
        )
        .execute()
        .data[0]
    )
    return row["id"]


class TestCoveredJurisdictions:
    def test_no_claim_at_all_is_not_covered(
        self, admin_client: Client, coverage_pathway: dict[str, Any]
    ) -> None:
        assert coverage_pathway["jurisdiction"] not in covered_jurisdictions(admin_client)

    def test_draft_claim_does_not_cover_the_jurisdiction(
        self, admin_client: Client, guest_client: Client, coverage_pathway: dict[str, Any]
    ) -> None:
        jurisdiction = coverage_pathway["jurisdiction"]
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            coverage_pathway["source"]["id"],
            status="draft",
            jurisdiction=jurisdiction,
        )
        try:
            assert jurisdiction not in covered_jurisdictions(guest_client)
            assert jurisdiction not in covered_jurisdictions(admin_client)
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_in_review_claim_does_not_cover_the_jurisdiction(
        self, admin_client: Client, guest_client: Client, coverage_pathway: dict[str, Any]
    ) -> None:
        jurisdiction = coverage_pathway["jurisdiction"]
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            coverage_pathway["source"]["id"],
            status="in_review",
            jurisdiction=jurisdiction,
        )
        try:
            assert jurisdiction not in covered_jurisdictions(guest_client)
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_publishing_the_only_claim_makes_the_jurisdiction_covered(
        self, admin_client: Client, guest_client: Client, coverage_pathway: dict[str, Any]
    ) -> None:
        """The acceptance scenario, verbatim and live: a jurisdiction is
        uncovered while its only claim is draft, and becomes covered the
        moment -- ONLY the moment -- that claim is actually published,
        not merely submitted to in_review."""
        jurisdiction = coverage_pathway["jurisdiction"]
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            coverage_pathway["source"]["id"],
            status="draft",
            jurisdiction=jurisdiction,
        )
        try:
            assert jurisdiction not in covered_jurisdictions(guest_client)

            admin_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            assert jurisdiction not in covered_jurisdictions(guest_client)

            admin_client.table("claims").update({"status": "published"}).eq(
                "id", claim_id
            ).execute()
            assert jurisdiction in covered_jurisdictions(guest_client)
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_covered_regardless_of_which_clients_own_view_is_wider(
        self,
        admin_client: Client,
        guest_client: Client,
        reviewer: tuple[str, Client],
        coverage_pathway: dict[str, Any],
    ) -> None:
        """A signed-in reviewer's own RLS-scoped client legally sees a
        DRAFT claim directly (`claims_select_published`,
        db/migrations/0001_init.sql: "status = 'published' or
        is_reviewer()") -- proved below by a raw select -- but
        `covered_jurisdictions` must still say "not covered" through that
        SAME client, exactly like it does through a guest's. This is the
        acceptance criterion, live: "the coverage/publication gate must
        apply regardless of the viewer's own role, same 'RLS is not the
        only check' lesson this codebase has learned before"."""
        jurisdiction = coverage_pathway["jurisdiction"]
        _reviewer_id, reviewer_client = reviewer
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            coverage_pathway["source"]["id"],
            status="draft",
            jurisdiction=jurisdiction,
        )
        try:
            raw = (
                reviewer_client.table("claims").select("id, status").eq("id", claim_id).execute()
            )
            assert raw.data and raw.data[0]["status"] == "draft", (
                "premise of this test: a reviewer's own client really does see the draft row"
            )
            assert jurisdiction not in covered_jurisdictions(reviewer_client)
            assert jurisdiction not in covered_jurisdictions(guest_client)
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_keyed_on_the_pathways_own_jurisdiction_not_the_claims(
        self, admin_client: Client, guest_client: Client, coverage_pathway: dict[str, Any]
    ) -> None:
        """SCOPE-6's own wording: "a jurisdiction counts as 'covered'
        only if at least one PUBLISHED, NON-SYNTHETIC claim exists for a
        pathway IN IT" -- the PATHWAY's own `jurisdiction` column, not
        whatever a claim's own (independent, SCOPE-3) `jurisdiction`
        column happens to say. A claim's `jurisdiction` states which
        jurisdiction the fact itself is true for and can legitimately
        differ from its pathway's own (docs/CONTRACTS.md "Entity
        vocabulary") -- this derivation must not conflate the two."""
        pathway_jurisdiction = coverage_pathway["jurisdiction"]
        claim_jurisdiction = _fake_jurisdiction()
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            coverage_pathway["source"]["id"],
            status="published",
            jurisdiction=claim_jurisdiction,
        )
        try:
            covered = covered_jurisdictions(guest_client)
            assert pathway_jurisdiction in covered, (
                "the pathway's own jurisdiction must be covered by its published claim"
            )
            assert claim_jurisdiction not in covered, (
                "the claim's own (different) jurisdiction value must not itself become 'covered'"
            )
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_in_review_synthetic_claim_does_not_cover_even_via_admin(
        self,
        admin_client: Client,
        synthetic_source: str,
        coverage_pathway: dict[str, Any],
    ) -> None:
        """Even queried through `admin_client` (service_role -- the
        strongest possible "wider view" a caller could have, since RLS
        never restricts it at all), `covered_jurisdictions` must not
        count an in_review synthetic-sourced claim. Combined with the
        test below, which confirms there is no live path to a
        PUBLISHED synthetic claim at all, this is the closest a live
        test can get to exercising the non-synthetic defensive re-check
        `covered_jurisdictions`'s own docstring describes."""
        jurisdiction = coverage_pathway["jurisdiction"]
        claim_id = _insert_claim(
            admin_client,
            coverage_pathway["pathway"]["id"],
            synthetic_source,
            status="in_review",
            jurisdiction=jurisdiction,
        )
        try:
            assert jurisdiction not in covered_jurisdictions(admin_client)
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_publishing_a_synthetic_claim_is_rejected_even_for_admin(
        self,
        admin_client: Client,
        synthetic_source: str,
        coverage_pathway: dict[str, Any],
    ) -> None:
        """Confirms the premise the test above relies on: there is no
        live path to a published+synthetic claim, not even through
        service_role -- `forbid_publishing_synthetic_claims()`
        (db/migrations/0001_init.sql) has no service_role carve-out
        (unlike `enforce_claims_workflow()`, which does), so
        `covered_jurisdictions`'s own defensive non-synthetic re-check
        can never actually be exercised end-to-end. Proved here rather
        than only asserted in a comment."""
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": coverage_pathway["pathway"]["id"],
                    "field": "verified_charges",
                    "value": 1000,
                    "currency": "INR",
                    "source_id": synthetic_source,
                    "verification_date": "2026-09-01",
                    "verifier": run_name("coverage-test-fixture"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                    "jurisdiction": coverage_pathway["jurisdiction"],
                }
            ).execute()
