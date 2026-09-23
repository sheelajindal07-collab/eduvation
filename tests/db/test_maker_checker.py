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

import threading
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


# =====================================================================
# PUB-2 (db/migrations/0017_publishing_evidence.sql): identity binding,
# the separate-steps rule, and the in-review auto-revert. These extend
# the SAME maker-checker guarantee this file already tests -- not a new
# concept -- so they live here rather than in tests/db/
# test_publishing_evidence.py, which covers 0017's genuinely NEW schema
# (content_hash, tier, source_versions, the sources identity freeze, the
# storage bucket).
# =====================================================================
class TestIdentityBinding:
    """0017: created_by and reviewed_by are never a client-supplied
    value, even if one is sent -- forced to the caller's own auth.uid()
    -- and created_by is frozen once a row exists."""

    def test_created_by_is_forced_even_when_a_different_value_is_sent(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        spoofed = str(uuid.uuid4())
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, spoofed))
            .execute()
        )
        claim_id = row.data[0]["id"]
        try:
            assert row.data[0]["created_by"] == reviewer_id
            assert row.data[0]["created_by"] != spoofed
        finally:
            _cleanup(admin_client, claim_id)

    def test_created_by_cannot_be_rewritten_after_insert(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The rewrite target is a REAL, existing user (the second
        reviewer fixture), not a random UUID -- a random id would also
        be rejected by the plain `claims_created_by_fkey` foreign key,
        which would make this test pass for the wrong reason (revert-to-
        prove caught exactly this: weakening ONLY the freeze check still
        left this test green, because the FK alone was doing the
        rejecting)."""
        reviewer_id, reviewer_client = reviewer
        second_id, _second_client = second_reviewer
        draft = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            with pytest.raises(APIError):
                reviewer_client.table("claims").update({"created_by": second_id}).eq(
                    "id", claim_id
                ).execute()
        finally:
            _cleanup(admin_client, claim_id)

    def test_reviewed_by_is_forced_even_when_a_different_value_is_sent(
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
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            spoofed = str(uuid.uuid4())  # neither the maker's nor the checker's own id
            published = (
                checker_client.table("claims")
                .update({"status": "published", "reviewed_by": spoofed})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert published["reviewed_by"] == checker_id
            assert published["reviewed_by"] != spoofed
        finally:
            _cleanup(admin_client, claim_id)

    def test_a_null_created_by_legacy_row_is_not_treated_as_self_approved_by_a_real_reviewer(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """NULL-safety, the half that stays reachable through the real API:
        docs/CONTRACTS.md's `IS NOT DISTINCT FROM` check must not treat a
        NULL created_by (a legacy/unknown-author row -- only the service
        role can seed one at all now that 0017's own insert-time forcing
        closes this for every real caller) as "the same identity" as a
        real reviewer's own auth.uid(). A naive `=` comparison would also
        happen not to raise here, but for the WRONG reason (NULL, not
        FALSE) -- this test pins the intended behaviour (ALLOW), not just
        the absence of an exception."""
        draft = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, None, status="in_review"))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        reviewer_id, reviewer_client = reviewer
        try:
            published = (
                reviewer_client.table("claims")
                .update({"status": "published"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert published["status"] == "published"
            assert published["reviewed_by"] == reviewer_id
            assert published["created_by"] is None
        finally:
            _cleanup(admin_client, claim_id)


class TestValueChangeAndApprovalAreSeparateSteps:
    def test_changing_value_in_the_same_update_that_publishes_is_rejected(
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
            with pytest.raises(APIError):
                checker_client.table("claims").update(
                    {"status": "published", "value": 999999}
                ).eq("id", claim_id).execute()
            still_in_review = (
                admin_client.table("claims").select("*").eq("id", claim_id).execute().data[0]
            )
            assert still_in_review["status"] == "in_review"
            assert still_in_review["value"] == 50000
        finally:
            _cleanup(admin_client, claim_id)


class TestEditingDuringReviewReturnsToDraft:
    def test_editing_value_while_in_review_drops_the_claim_back_to_draft(
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
            # No `status` field sent at all -- an ordinary content edit,
            # not an attempted approval.
            edited = (
                reviewer_client.table("claims")
                .update({"value": 60000})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert edited["status"] == "draft"
            assert edited["value"] == 60000
        finally:
            _cleanup(admin_client, claim_id)


# =====================================================================
# PUB-3 (db/migrations/0018_publish_functions.sql): publish_claim() and
# supersede_claim() -- atomic, RPC-called functions that extend the SAME
# maker-checker guarantee this file already tests, not a new concept, so
# they live here rather than a new file (mirrors 0017's own placement
# note directly above this section).
# =====================================================================
def _submitted_claim(
    maker_client: Client,
    maker_id: str,
    official_source: str,
    admin_client: Client,
    **overrides: object,
) -> dict:
    """A draft, submitted to in_review, then re-read via the service role
    so the caller gets the REAL current `content_hash` -- the maker's own
    insert response already has it, but re-reading after the `in_review`
    transition is what a real caller would do too."""
    draft = (
        maker_client.table("claims")
        .insert(_draft_payload(official_source, maker_id, **overrides))
        .execute()
        .data[0]
    )
    maker_client.table("claims").update({"status": "in_review"}).eq("id", draft["id"]).execute()
    return admin_client.table("claims").select("*").eq("id", draft["id"]).execute().data[0]


def _published_pair(
    admin_client: Client,
    official_source: str,
    maker_id: str,
    checker_id: str,
    **new_overrides: object,
) -> tuple[dict, dict]:
    """Two already-published claims on the SAME entity_type/entity_id/
    field (service role seeds both directly, same exemption every other
    fixture in this file already relies on) -- the shape supersede_claim()
    operates on. `_draft_payload` picks a fresh random `entity_id` per
    call by default, so it is pinned to ONE shared value here -- without
    this, `old`/`new` would never match and every "happy path" test would
    accidentally be exercising the mismatched-entity rejection instead."""
    shared_entity_id = str(uuid.uuid4())
    old = (
        admin_client.table("claims")
        .insert(
            _draft_payload(
                official_source,
                maker_id,
                status="published",
                reviewed_by=checker_id,
                entity_id=shared_entity_id,
            )
        )
        .execute()
        .data[0]
    )
    new_payload = _draft_payload(
        official_source,
        maker_id,
        status="published",
        reviewed_by=checker_id,
        entity_id=shared_entity_id,
        value=60000,
    )
    new_payload.update(new_overrides)
    new = admin_client.table("claims").insert(new_payload).execute().data[0]
    return old, new


class TestPublishClaimFunction:
    def test_publish_claim_succeeds_and_records_a_review_event(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        claim = _submitted_claim(maker_client, maker_id, official_source, admin_client)
        try:
            result = checker_client.rpc(
                "publish_claim",
                {"p_claim_id": claim["id"], "p_expected_hash": claim["content_hash"]},
            ).execute()
            published = result.data
            assert published["status"] == "published"
            assert published["reviewed_by"] == checker_id
            assert published["created_by"] == maker_id

            events = (
                admin_client.table("review_events")
                .select("*")
                .eq("claim_id", claim["id"])
                .execute()
                .data
            )
            assert len(events) == 1
            assert events[0]["action"] == "published"
            assert events[0]["actor_id"] == checker_id
        finally:
            _cleanup(admin_client, claim["id"])

    def test_publish_claim_rejects_a_stale_expected_hash(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The lost-update guard this card names: a caller whose loaded
        `content_hash` no longer matches the live row must be refused,
        not silently allowed to publish stale-relative-to-what-they-saw
        content."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        claim = _submitted_claim(maker_client, maker_id, official_source, admin_client)
        try:
            with pytest.raises(APIError) as excinfo:
                checker_client.rpc(
                    "publish_claim",
                    {"p_claim_id": claim["id"], "p_expected_hash": "0" * 64},
                ).execute()
            assert "BCPB3" in str(excinfo.value)

            still_in_review = (
                admin_client.table("claims").select("status").eq("id", claim["id"]).execute()
            )
            assert still_in_review.data[0]["status"] == "in_review"
        finally:
            _cleanup(admin_client, claim["id"])

    def test_publish_claim_on_a_claim_not_in_review_records_a_conflict_and_returns_null(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """A single, non-concurrent call against a DRAFT (never
        submitted) claim -- the same "not in_review" branch a losing
        concurrent caller hits, pinned here as its own deterministic
        case: no exception, a real logged conflict, and nothing published."""
        reviewer_id, reviewer_client = reviewer
        draft = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        try:
            result = reviewer_client.rpc(
                "publish_claim",
                {"p_claim_id": draft["id"], "p_expected_hash": draft["content_hash"]},
            ).execute()
            assert result.data["id"] is None, "a status conflict must return NULL, not a row"

            events = (
                admin_client.table("review_events")
                .select("*")
                .eq("claim_id", draft["id"])
                .execute()
                .data
            )
            assert len(events) == 1
            assert events[0]["action"] == "publish_conflict"
            assert events[0]["detail"]["reason"] == "not_in_review"

            unchanged = (
                admin_client.table("claims").select("status").eq("id", draft["id"]).execute()
            )
            assert unchanged.data[0]["status"] == "draft"
        finally:
            _cleanup(admin_client, draft["id"])

    def test_publish_claim_requires_an_authenticated_reviewer(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        guest_client: Client,
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        _student_id, student_client = student_a
        claim = _submitted_claim(maker_client, maker_id, official_source, admin_client)
        try:
            with pytest.raises(APIError) as excinfo:
                student_client.rpc(
                    "publish_claim",
                    {"p_claim_id": claim["id"], "p_expected_hash": claim["content_hash"]},
                ).execute()
            assert "BCPB1" in str(excinfo.value)

            with pytest.raises(APIError):
                guest_client.rpc(
                    "publish_claim",
                    {"p_claim_id": claim["id"], "p_expected_hash": claim["content_hash"]},
                ).execute()
        finally:
            _cleanup(admin_client, claim["id"])

    def test_two_concurrent_publish_claim_calls_yield_exactly_one_publish(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The revert-to-prove subject for this card (.claude/agents/
        migration-owner.md): with `publish_claim`'s row lock in place,
        two real, simultaneous HTTP requests against the SAME claim yield
        exactly one published row and exactly one logged conflict --
        never two published rows, never a silent second write. Mirrors
        `test_ai_usage.py::TestConcurrency`'s own real-connections
        pattern (Barrier + threads), over the RPC/HTTP layer here rather
        than raw psycopg, since `publish_claim` depends on `auth.uid()`
        (a real signed-in identity), which only PostgREST supplies."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        claim = _submitted_claim(maker_client, maker_id, official_source, admin_client)
        try:
            results: list[object] = [None, None]
            barrier = threading.Barrier(2)

            def attempt(idx: int) -> None:
                barrier.wait(timeout=10)
                try:
                    res = checker_client.rpc(
                        "publish_claim",
                        {"p_claim_id": claim["id"], "p_expected_hash": claim["content_hash"]},
                    ).execute()
                    results[idx] = res.data
                except APIError as exc:  # noqa: BLE001 -- captured for the assertion below
                    results[idx] = exc

            threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            published_results = [
                r for r in results if isinstance(r, dict) and r.get("status") == "published"
            ]
            null_results = [r for r in results if isinstance(r, dict) and r.get("id") is None]
            assert len(published_results) == 1, (
                f"exactly one of two concurrent publish_claim calls must succeed, got "
                f"{len(published_results)}: {results}"
            )
            assert len(null_results) == 1, (
                f"the loser must return NULL (a recorded conflict), not raise or silently "
                f"do nothing: {results}"
            )

            events = (
                admin_client.table("review_events")
                .select("*")
                .eq("claim_id", claim["id"])
                .execute()
                .data
            )
            published_events = [e for e in events if e["action"] == "published"]
            conflict_events = [e for e in events if e["action"] == "publish_conflict"]
            assert len(published_events) == 1, events
            assert len(conflict_events) == 1, events
        finally:
            _cleanup(admin_client, claim["id"])


class TestSupersedeClaimFunction:
    def test_supersede_claim_marks_old_superseded_and_records_an_audit_event(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, checker_client = second_reviewer
        old, new = _published_pair(admin_client, official_source, maker_id, checker_id)
        try:
            result = checker_client.rpc(
                "supersede_claim", {"p_old_id": old["id"], "p_new_id": new["id"]}
            ).execute()
            row = result.data[0]
            assert row["old_claim_id"] == old["id"]
            assert row["new_claim_id"] == new["id"]
            assert row["plans_flagged"] == 0  # no saved_plans exist for this fixture's entity_id

            refreshed_old = (
                admin_client.table("claims").select("*").eq("id", old["id"]).execute().data[0]
            )
            assert refreshed_old["status"] == "superseded"
            assert refreshed_old["superseded_by"] == new["id"]
            assert refreshed_old["value"] == 50000, (
                "the old claim's own recorded value is untouched"
            )

            audit_rows = (
                admin_client.table("audit_events")
                .select("*")
                .eq("entity_id", old["id"])
                .execute()
                .data
            )
            assert len(audit_rows) == 1
            assert audit_rows[0]["action"] == "claim_superseded"
            assert audit_rows[0]["actor_id"] == checker_id
            assert audit_rows[0]["detail"]["superseded_by"] == new["id"]
        finally:
            # audit_events.entity_id carries no FK (same shape as
            # claims.entity_id itself — see 0018's own header), so unlike
            # review_events.claim_id (which cascades from `claims`) it is
            # never cleaned up by deleting the claim below. Must go first,
            # or `second_reviewer`'s own teardown fails to delete its user
            # (db/migrations/README.md's own "created_by/reviewed_by ...
            # can break test teardown ordering" gotcha, same class, new
            # table).
            admin_client.table("audit_events").delete().eq("entity_id", old["id"]).execute()
            _cleanup(admin_client, old["id"])
            _cleanup(admin_client, new["id"])

    def test_supersede_claim_rejects_a_draft_replacement(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, checker_client = second_reviewer
        old, _never_published = _published_pair(admin_client, official_source, maker_id, checker_id)
        draft_replacement = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, maker_id, status="draft"))
            .execute()
            .data[0]
        )
        try:
            with pytest.raises(APIError) as excinfo:
                checker_client.rpc(
                    "supersede_claim",
                    {"p_old_id": old["id"], "p_new_id": draft_replacement["id"]},
                ).execute()
            assert "BCPB8" in str(excinfo.value)

            unchanged = (
                admin_client.table("claims").select("status").eq("id", old["id"]).execute()
            )
            assert unchanged.data[0]["status"] == "published"
        finally:
            _cleanup(admin_client, old["id"])
            _cleanup(admin_client, _never_published["id"])
            _cleanup(admin_client, draft_replacement["id"])

    def test_supersede_claim_rejects_a_mismatched_field(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, checker_client = second_reviewer
        old, mismatched = _published_pair(
            admin_client, official_source, maker_id, checker_id, field="a_totally_different_field"
        )
        try:
            with pytest.raises(APIError) as excinfo:
                checker_client.rpc(
                    "supersede_claim", {"p_old_id": old["id"], "p_new_id": mismatched["id"]}
                ).execute()
            assert "BCPB9" in str(excinfo.value)
        finally:
            _cleanup(admin_client, old["id"])
            _cleanup(admin_client, mismatched["id"])

    def test_supersede_claim_requires_critical_authorised_reviewer_when_tier_is_critical(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, checker_client = second_reviewer
        old, new = _published_pair(admin_client, official_source, maker_id, checker_id)
        admin_client.table("claims").update({"tier": "critical"}).eq("id", old["id"]).execute()
        try:
            with pytest.raises(APIError) as excinfo:
                checker_client.rpc(
                    "supersede_claim", {"p_old_id": old["id"], "p_new_id": new["id"]}
                ).execute()
            assert "BCPBA" in str(excinfo.value)

            admin_client.table("reviewers").update({"critical_authorised": True}).eq(
                "user_id", checker_id
            ).execute()
            result = checker_client.rpc(
                "supersede_claim", {"p_old_id": old["id"], "p_new_id": new["id"]}
            ).execute()
            assert result.data[0]["old_claim_id"] == old["id"]
        finally:
            admin_client.table("reviewers").update({"critical_authorised": False}).eq(
                "user_id", checker_id
            ).execute()
            # See test_supersede_claim_marks_old_superseded_and_records_an_audit_event's
            # own comment: audit_events.entity_id has no cascading FK.
            admin_client.table("audit_events").delete().eq("entity_id", old["id"]).execute()
            _cleanup(admin_client, old["id"])
            _cleanup(admin_client, new["id"])

    def test_supersede_claim_requires_an_authenticated_reviewer(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, _maker_client = reviewer
        checker_id, _checker_client = second_reviewer
        _student_id, student_client = student_a
        old, new = _published_pair(admin_client, official_source, maker_id, checker_id)
        try:
            with pytest.raises(APIError) as excinfo:
                student_client.rpc(
                    "supersede_claim", {"p_old_id": old["id"], "p_new_id": new["id"]}
                ).execute()
            assert "BCPB4" in str(excinfo.value)
        finally:
            _cleanup(admin_client, old["id"])
            _cleanup(admin_client, new["id"])
