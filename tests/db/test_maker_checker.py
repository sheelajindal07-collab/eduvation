"""Live tests for db/migrations/0003_maker_checker.sql — the maker-checker
state machine and self-approval guard enforced at the trigger level
(CLAUDE.md non-negotiable: "Unapproved facts never reach public results
(maker-checker, enforced server-side, not by a button)").

Every "should fail" assertion here is testing a real Postgres trigger
raising a real exception against the live database — not application
code, and not a mock. `admin_client` is used only to seed a Source row
(claims need one to satisfy the foreign key); every assertion about what
a *reviewer* can or can't do runs as an actual reviewer-authenticated
client, matching tests/db/conftest.py's own rule.
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
    """A real (non-synthetic) source — required because a synthetic
    source can never be published at all (0001_init.sql's own trigger),
    which would make it useless for testing the publish/supersede path
    this file actually cares about."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("MAKER-CHECKER TEST FIXTURE (official)"),
                "official_url": "https://example.invalid/maker-checker-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _draft_payload(source_id: str, created_by: str | None, **overrides: object) -> dict:
    payload = {
        "entity_type": "Pathway",
        "entity_id": str(uuid.uuid4()),
        "field": "verified_charges",
        "value": 50000,
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": run_name("test-fixture-reviewer"),
        "review_due_date": DUE.isoformat(),
        "status": "draft",
        "created_by": created_by,
    }
    payload.update(overrides)
    return payload


def _cleanup(admin_client: Client, claim_id: str) -> None:
    admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestInsertMustBeDraft:
    def test_reviewer_can_insert_a_draft(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["status"] == "draft"
        finally:
            _cleanup(admin_client, claim_id)

    def test_reviewer_cannot_insert_directly_as_published(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        with pytest.raises(APIError):
            reviewer_client.table("claims").insert(
                _draft_payload(official_source, reviewer_id, status="published")
            ).execute()

    def test_reviewer_cannot_insert_directly_as_in_review(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        with pytest.raises(APIError):
            reviewer_client.table("claims").insert(
                _draft_payload(official_source, reviewer_id, status="in_review")
            ).execute()

    def test_service_role_is_exempt_and_can_seed_a_published_claim_directly(
        self, admin_client: Client, official_source: str
    ) -> None:
        """The exact fixture pattern every other test file in this repo
        already relies on (tests/db/test_api_explore_compare.py etc.)
        must keep working unchanged.

        `created_by` is left `None` here on purpose: it's a real foreign
        key to `auth.users` (0001_init.sql), and a fabricated UUID fails
        that constraint before the trigger under test is even reached --
        this test is about the service-role INSERT exemption, not
        authorship, and `created_by` is nullable precisely because no
        publishing-console API existed to set it correctly when M1's
        schema was written."""
        row = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, None, status="published"))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["status"] == "published"
        finally:
            _cleanup(admin_client, claim_id)


class TestSelfApprovalIsRejected:
    def test_author_cannot_approve_their_own_claim(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """The core guarantee this migration exists for."""
        reviewer_id, reviewer_client = reviewer
        draft = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            reviewer_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            with pytest.raises(APIError):
                reviewer_client.table("claims").update(
                    {"status": "published", "reviewed_by": reviewer_id}
                ).eq("id", claim_id).execute()
        finally:
            _cleanup(admin_client, claim_id)

    def test_publishing_without_a_reviewer_is_rejected(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        draft = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            reviewer_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            with pytest.raises(APIError):
                reviewer_client.table("claims").update({"status": "published"}).eq(
                    "id", claim_id
                ).execute()
        finally:
            _cleanup(admin_client, claim_id)


class TestTwoDistinctReviewers:
    def test_draft_to_in_review_to_published_with_different_checker(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer

        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            submitted = (
                maker_client.table("claims")
                .update({"status": "in_review"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert submitted["status"] == "in_review"

            published = (
                checker_client.table("claims")
                .update({"status": "published", "reviewed_by": checker_id})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert published["status"] == "published"
            assert published["reviewed_by"] == checker_id
            assert published["created_by"] == maker_id
        finally:
            _cleanup(admin_client, claim_id)

    def test_reviewer_can_send_a_draft_back_from_in_review(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer

        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            sent_back = (
                checker_client.table("claims")
                .update({"status": "draft"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert sent_back["status"] == "draft"
        finally:
            _cleanup(admin_client, claim_id)

    def test_draft_cannot_skip_straight_to_published(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        draft = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            with pytest.raises(APIError):
                reviewer_client.table("claims").update(
                    {"status": "published", "reviewed_by": reviewer_id}
                ).eq("id", claim_id).execute()
        finally:
            _cleanup(admin_client, claim_id)


class TestPublishedContentIsFrozen:
    def _publish(
        self,
        maker: tuple[str, Client],
        checker: tuple[str, Client],
        official_source: str,
    ) -> dict:
        maker_id, maker_client = maker
        checker_id, checker_client = checker
        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id))
            .execute()
            .data[0]
        )
        maker_client.table("claims").update({"status": "in_review"}).eq(
            "id", draft["id"]
        ).execute()
        return (
            checker_client.table("claims")
            .update({"status": "published", "reviewed_by": checker_id})
            .eq("id", draft["id"])
            .execute()
            .data[0]
        )

    def test_editing_a_published_claims_value_in_place_is_rejected(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        published = self._publish(reviewer, second_reviewer, official_source)
        claim_id = published["id"]
        _, checker_client = second_reviewer
        try:
            with pytest.raises(APIError):
                checker_client.table("claims").update({"value": 999999}).eq(
                    "id", claim_id
                ).execute()
        finally:
            _cleanup(admin_client, claim_id)

    def test_correction_via_supersede_is_the_only_legal_change(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """docs/DATA.md "Correction": a published claim can be
        superseded -- proven here by actually inserting the replacement
        claim and pointing the old one at it, the real shape a
        publishing-console correction would take."""
        published = self._publish(reviewer, second_reviewer, official_source)
        old_claim_id = published["id"]
        maker_id, maker_client = reviewer
        _, checker_client = second_reviewer

        new_draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id, value=60000))
            .execute()
            .data[0]
        )
        new_claim_id = new_draft["id"]
        try:
            superseded = (
                checker_client.table("claims")
                .update({"status": "superseded", "superseded_by": new_claim_id})
                .eq("id", old_claim_id)
                .execute()
                .data[0]
            )
            assert superseded["status"] == "superseded"
            assert superseded["superseded_by"] == new_claim_id
            # The old claim's own recorded value is untouched -- the
            # correction lives entirely in the new claim, never as a
            # silent overwrite of history.
            assert superseded["value"] == 50000
        finally:
            # old_claim_id.superseded_by references new_claim_id -- must
            # delete the referencing row first, or the FK constraint
            # blocks deleting the still-referenced replacement (Postgres
            # default: NO ACTION, not CASCADE).
            _cleanup(admin_client, old_claim_id)
            _cleanup(admin_client, new_claim_id)

    def test_a_superseded_claim_is_final(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        published = self._publish(reviewer, second_reviewer, official_source)
        claim_id = published["id"]
        maker_id, maker_client = reviewer
        _, checker_client = second_reviewer

        # `superseded_by` is a real foreign key to claims(id)
        # (0001_init.sql) -- a fabricated UUID fails that constraint
        # before the trigger under test is even reached. Needs an actual
        # replacement claim to point at, same as
        # test_correction_via_supersede_is_the_only_legal_change.
        replacement = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id))
            .execute()
            .data[0]
        )
        checker_client.table("claims").update(
            {"status": "superseded", "superseded_by": replacement["id"]}
        ).eq("id", claim_id).execute()
        try:
            with pytest.raises(APIError):
                checker_client.table("claims").update({"status": "draft"}).eq(
                    "id", claim_id
                ).execute()
        finally:
            # The superseded claim references the replacement -- must be
            # deleted first, or the FK constraint blocks deleting the
            # still-referenced replacement (Postgres default: NO ACTION).
            _cleanup(admin_client, claim_id)
            _cleanup(admin_client, replacement["id"])
