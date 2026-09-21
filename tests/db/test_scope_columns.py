"""Live tests for db/migrations/0008_jurisdiction_currency.sql (SCOPE-3).

The risk line this file exists to cover, verbatim from the card:
"Omitting the freeze-trigger update lets a published GBP fee be
re-labelled INR in place - a maker-checker bypass."

0003's freeze list is a DENY-LIST, so any column added to `claims` after
it is editable in place on a published row unless somebody remembers to
add it. `TestPublishedClaimContentIsFrozen` below has one test per new
column that does exactly the forbidden edit and asserts it is refused,
and `test_every_frozen_column_from_0003_is_still_frozen` re-checks the
original nine so that re-creating the function cannot have quietly
dropped one.

Conventions follow tests/db/test_maker_checker.py: real reviewer-
authenticated clients for anything about what a reviewer can do,
`admin_client` (service_role) only to seed — it is exempt from this
trigger by 0003's documented carve-out, which is what lets a test start
from an already-published row.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import run_name

TODAY = date.today()
DUE = TODAY + timedelta(days=365)


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("SCOPE-3 TEST FIXTURE (official)"),
                "official_url": "https://example.invalid/scope-3-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _claim_payload(source_id: str, **overrides: object) -> dict:
    payload: dict = {
        "entity_type": "Pathway",
        "entity_id": str(uuid.uuid4()),
        "field": "verified_charges",
        "value": 9000,
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": run_name("scope-3-test-fixture"),
        "review_due_date": DUE.isoformat(),
        "status": "draft",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def published_claim(
    admin_client: Client, official_source: str, reviewer: tuple[str, Client]
) -> Iterator[str]:
    """A PUBLISHED claim carrying all three new columns, seeded by
    service_role (exempt from the workflow trigger — 0003's carve-out).

    Deliberately a GBP claim: the card's risk line is specifically about
    a published GBP fee being relabelled INR, so the fixture is the
    actual scenario, not a generic stand-in.
    """
    reviewer_id, _ = reviewer
    row = (
        admin_client.table("claims")
        .insert(
            _claim_payload(
                official_source,
                status="published",
                jurisdiction="GB",
                academic_cycle="2026-27",
                currency="GBP",
                created_by=None,
                reviewed_by=reviewer_id,
            )
        )
        .execute()
    )
    claim_id = row.data[0]["id"]
    yield claim_id
    admin_client.table("claims").delete().eq("id", claim_id).execute()


# --------------------------------------------------------------------
# Columns exist, defaults are right
# --------------------------------------------------------------------


class TestColumnsAndDefaults:
    def test_existing_claim_rows_read_IN(
        self, admin_client: Client, official_source: str
    ) -> None:
        """Acceptance, verbatim: "existing rows read 'IN'". A row
        inserted without naming the column — exactly what every row
        written before this migration looks like — must come back 'IN',
        not null."""
        row = admin_client.table("claims").insert(_claim_payload(official_source)).execute()
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["jurisdiction"] == "IN"
            assert row.data[0]["academic_cycle"] is None
            assert row.data[0]["currency"] is None
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_existing_source_rows_read_IN(
        self, admin_client: Client, official_source: str
    ) -> None:
        row = (
            admin_client.table("sources")
            .select("jurisdiction")
            .eq("id", official_source)
            .single()
            .execute()
        )
        assert row.data["jurisdiction"] == "IN"

    def test_a_guest_can_read_the_new_columns(
        self,
        guest_client: Client,
        admin_client: Client,
        official_source: str,
        reviewer: tuple[str, Client],
    ) -> None:
        """The columns are part of the world-readable published claim, so
        a guest must actually get them — a jurisdiction the student never
        sees would make CONTRACTS.md's "display-only for a non-IN
        pathway" rule unimplementable."""
        reviewer_id, _ = reviewer
        row = (
            admin_client.table("claims")
            .insert(
                _claim_payload(
                    official_source,
                    status="published",
                    jurisdiction="IN-MH",
                    currency="INR",
                    reviewed_by=reviewer_id,
                )
            )
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            seen = (
                guest_client.table("claims")
                .select("jurisdiction, currency")
                .eq("id", claim_id)
                .single()
                .execute()
            )
            assert seen.data["jurisdiction"] == "IN-MH"
            assert seen.data["currency"] == "INR"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestShapeConstraints:
    """Shape-only, never a covered-set list — docs/CONTRACTS.md forbids
    hardcoding which jurisdictions are in scope until SCOPE-1 is
    answered."""

    @pytest.mark.parametrize("bad", ["India", "in", "I", "INDI", "IN-", "IN_MH", ""])
    def test_a_malformed_jurisdiction_is_refused(
        self, admin_client: Client, official_source: str, bad: str
    ) -> None:
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                _claim_payload(official_source, jurisdiction=bad)
            ).execute()

    @pytest.mark.parametrize("good", ["IN", "GB", "IN-MH", "GB-ENG", "US-CA"])
    def test_well_formed_jurisdictions_are_accepted(
        self, admin_client: Client, official_source: str, good: str
    ) -> None:
        row = (
            admin_client.table("claims")
            .insert(_claim_payload(official_source, jurisdiction=good))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["jurisdiction"] == good
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    @pytest.mark.parametrize("bad", ["inr", "Inr", "US", "RUPEE", "1NR"])
    def test_a_malformed_currency_is_refused(
        self, admin_client: Client, official_source: str, bad: str
    ) -> None:
        """'US' matters specifically: `char(3)` BLANK-PADS, so without
        the `^[A-Z]{3}$` shape check a two-letter code would be silently
        stored as 'US ' and pass a naive uppercase-only test."""
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                _claim_payload(official_source, currency=bad)
            ).execute()

    @pytest.mark.parametrize("bad", ["2026-2027", "26-27", "FY2026", "2026-2", "next year"])
    def test_a_malformed_academic_cycle_is_refused(
        self, admin_client: Client, official_source: str, bad: str
    ) -> None:
        with pytest.raises(APIError):
            admin_client.table("claims").insert(
                _claim_payload(official_source, academic_cycle=bad)
            ).execute()

    @pytest.mark.parametrize("good", ["2026", "2026-27"])
    def test_well_formed_cycles_are_accepted(
        self, admin_client: Client, official_source: str, good: str
    ) -> None:
        row = (
            admin_client.table("claims")
            .insert(_claim_payload(official_source, academic_cycle=good))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["academic_cycle"] == good
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_a_null_currency_is_allowed(
        self, admin_client: Client, official_source: str
    ) -> None:
        """docs/CONTRACTS.md: "A money claim with a null currency renders
        not_available". Unknown is a real state and must not be defaulted
        to INR, which would invent a fact about a real fee."""
        row = (
            admin_client.table("claims")
            .insert(_claim_payload(official_source, currency=None))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["currency"] is None
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


# --------------------------------------------------------------------
# THE POINT OF THIS FILE — the freeze trigger covers the new columns
# --------------------------------------------------------------------


class TestPublishedClaimContentIsFrozen:
    """Every test here runs as a REAL reviewer, not service_role: the
    carve-out means service_role would sail through the trigger and the
    test would pass for the wrong reason, proving nothing."""

    def test_currency_cannot_be_relabelled_in_place(
        self, reviewer: tuple[str, Client], published_claim: str
    ) -> None:
        """The card's risk line, as a test: a published GBP fee must not
        become an INR fee while keeping its approval."""
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("claims").update(
                {"status": "superseded", "currency": "INR"}
            ).eq("id", published_claim).execute()

    def test_jurisdiction_cannot_be_changed_in_place(
        self, reviewer: tuple[str, Client], published_claim: str
    ) -> None:
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("claims").update(
                {"status": "superseded", "jurisdiction": "IN"}
            ).eq("id", published_claim).execute()

    def test_academic_cycle_cannot_be_changed_in_place(
        self, reviewer: tuple[str, Client], published_claim: str
    ) -> None:
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("claims").update(
                {"status": "superseded", "academic_cycle": "2027-28"}
            ).eq("id", published_claim).execute()

    def test_a_null_currency_cannot_be_filled_in_after_approval(
        self, admin_client: Client, official_source: str, reviewer: tuple[str, Client]
    ) -> None:
        """The NULL case, which is why the trigger uses `is distinct
        from` and not `<>`: `new.currency <> old.currency` evaluates to
        NULL — not true — when one side is NULL, so a `<>` comparison
        would let a published claim's blank currency be filled in after
        the fact. That is the same class of silent in-place edit, just
        starting from nothing instead of from a wrong value."""
        reviewer_id, client = reviewer
        row = (
            admin_client.table("claims")
            .insert(
                _claim_payload(
                    official_source,
                    status="published",
                    currency=None,
                    reviewed_by=reviewer_id,
                )
            )
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            with pytest.raises(APIError):
                client.table("claims").update(
                    {"status": "superseded", "currency": "INR"}
                ).eq("id", claim_id).execute()
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_a_clean_supersede_still_works(
        self, reviewer: tuple[str, Client], published_claim: str
    ) -> None:
        """The freeze must not have become "a published claim can never
        be superseded at all" — superseding WITHOUT touching content is
        the one legal move from `published`, and it has to keep
        working."""
        _, client = reviewer
        client.table("claims").update({"status": "superseded"}).eq(
            "id", published_claim
        ).execute()
        # Read back through the reviewer's own client; the row is now
        # terminal but still visible to a reviewer.
        row = (
            client.table("claims")
            .select("status, currency, jurisdiction, academic_cycle")
            .eq("id", published_claim)
            .single()
            .execute()
        )
        assert row.data["status"] == "superseded"
        assert row.data["currency"] == "GBP"
        assert row.data["jurisdiction"] == "GB"
        assert row.data["academic_cycle"] == "2026-27"

    @pytest.mark.parametrize(
        ("column", "new_value"),
        [
            ("value", 12345),
            ("verification_date", (TODAY - timedelta(days=5)).isoformat()),
            ("verifier", "someone-else"),
            ("entity_type", "Exam"),
            ("entity_id", str(uuid.uuid4())),
            ("field", "some_other_field"),
            ("extracted_by", "ai"),
        ],
    )
    def test_every_frozen_column_from_0003_is_still_frozen(
        self,
        reviewer: tuple[str, Client],
        published_claim: str,
        column: str,
        new_value: object,
    ) -> None:
        """Re-creating a function with `create or replace` replaces the
        WHOLE body, so the real hazard of this migration is not only
        "did the three new columns get added" but "did any of the
        original nine get dropped on the way". This re-checks them.

        (`source_id` and `created_by` are covered by
        tests/db/test_maker_checker.py's own suite, which needs extra
        fixtures to produce a second valid source/author.)
        """
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("claims").update({"status": "superseded", column: new_value}).eq(
                "id", published_claim
            ).execute()


class TestWorkflowStillWorksEndToEnd:
    """The re-created trigger must not have broken the ordinary path."""

    def test_a_reviewer_can_still_run_draft_to_review_to_published(
        self,
        admin_client: Client,
        official_source: str,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer

        row = (
            maker_client.table("claims")
            .insert(
                _claim_payload(
                    official_source,
                    created_by=maker_id,
                    jurisdiction="IN-KA",
                    academic_cycle="2026",
                    currency="INR",
                )
            )
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["status"] == "draft"
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            checker_client.table("claims").update(
                {"status": "published", "reviewed_by": checker_id}
            ).eq("id", claim_id).execute()
            final = (
                checker_client.table("claims")
                .select("status, jurisdiction, academic_cycle, currency")
                .eq("id", claim_id)
                .single()
                .execute()
            )
            assert final.data["status"] == "published"
            assert final.data["jurisdiction"] == "IN-KA"
            assert final.data["academic_cycle"] == "2026"
            assert final.data["currency"] == "INR"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_self_approval_is_still_refused(
        self, admin_client: Client, official_source: str, reviewer: tuple[str, Client]
    ) -> None:
        """Maker != checker, the guarantee 0003 exists for. Re-verified
        here because this migration re-creates the function that enforces
        it."""
        maker_id, maker_client = reviewer
        row = (
            maker_client.table("claims")
            .insert(_claim_payload(official_source, created_by=maker_id))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            with pytest.raises(APIError):
                maker_client.table("claims").update(
                    {"status": "published", "reviewed_by": maker_id}
                ).eq("id", claim_id).execute()
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_insert_must_still_be_draft(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _, client = reviewer
        with pytest.raises(APIError):
            client.table("claims").insert(
                _claim_payload(official_source, status="published")
            ).execute()


# --------------------------------------------------------------------
# Cross-user matrix (CLAUDE.md: rerun every time a policy changes)
# --------------------------------------------------------------------


class TestCrossUserAccess:
    def test_a_student_cannot_write_the_new_columns_on_a_published_claim(
        self, student_a: tuple[str, Client], published_claim: str
    ) -> None:
        """A non-reviewer has no claims UPDATE policy at all
        (0001/0003), so this is refused before the trigger is even
        reached — checked because SCOPE-3 adds columns, and a new column
        must not come with a new way in."""
        _, client = student_a
        result = (
            client.table("claims")
            .update({"currency": "INR"})
            .eq("id", published_claim)
            .execute()
        )
        assert result.data == []

    def test_student_b_cannot_either(
        self, student_b: tuple[str, Client], published_claim: str
    ) -> None:
        _, client = student_b
        result = (
            client.table("claims")
            .update({"jurisdiction": "IN"})
            .eq("id", published_claim)
            .execute()
        )
        assert result.data == []

    def test_a_guest_cannot_either(
        self, guest_client: Client, published_claim: str
    ) -> None:
        result = (
            guest_client.table("claims")
            .update({"currency": "INR"})
            .eq("id", published_claim)
            .execute()
        )
        assert result.data == []

    def test_a_guest_cannot_write_a_pathway_jurisdiction(
        self, guest_client: Client, admin_client: Client
    ) -> None:
        """`pathways.jurisdiction` is new and world-READABLE; it must not
        have become world-writable."""
        career_id = (
            admin_client.table("careers")
            .insert({"name": run_name("SCOPE-3 career")})
            .execute()
            .data[0]["id"]
        )
        try:
            pathway_id = (
                admin_client.table("pathways")
                .insert(
                    {
                        "career_id": career_id,
                        "name": run_name("SCOPE-3 pathway"),
                        "description": "fixture",
                    }
                )
                .execute()
                .data[0]["id"]
            )
            assert (
                guest_client.table("pathways")
                .update({"jurisdiction": "GB"})
                .eq("id", pathway_id)
                .execute()
                .data
                == []
            )
            still = (
                guest_client.table("pathways")
                .select("jurisdiction")
                .eq("id", pathway_id)
                .single()
                .execute()
            )
            assert still.data["jurisdiction"] == "IN"
        finally:
            # pathways cascade from careers (0001_init.sql).
            admin_client.table("careers").delete().eq("id", career_id).execute()
