"""Live tests for db/migrations/0017_publishing_evidence.sql (PUB-2) —
everything that is genuinely NEW schema, as opposed to
tests/db/test_maker_checker.py's own identity-binding/separate-steps/
in-review-revert additions, which extend a guarantee that file already
tests.

Covers: content_hash computation, the `tier` column and the
`critical_authorised` reviewer gate, sources.source_type/official_url
freezing once referenced by a published claim, and source_versions'
insert-only immutability. The storage bucket's own cross-user access is
tested in tests/db/test_access_matrix.py (TestStorageBucketAccessMatrix)
and its policy-existence is caught by tests/db/test_exposure_catalogue.py
— not duplicated here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from urllib.parse import urlsplit

import psycopg
import pytest
from postgrest.exceptions import APIError
from supabase import Client

from tests.db.conftest import _require_live, run_name

TODAY = date.today()
DUE = TODAY + timedelta(days=365)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _unavailable(reason: str) -> None:
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


def _database_url() -> str:
    """A second, loopback-only door into the same database — same
    pattern tests/db/test_exposure_catalogue.py and
    tests/db/test_access_matrix.py each already carry independently."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        _unavailable(
            "DATABASE_URL is not set. `make test-db-up` writes it into .env.test "
            "(mk/testdb.mk); see .env.test.example."
        )
    host = (urlsplit(url).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        pytest.fail(
            f"REFUSING TO CONNECT: DATABASE_URL points at {host!r}, which is not a "
            "local stack (CLAUDE.md).",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="module")
def sql() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_database_url(), connect_timeout=10, autocommit=True) as connection:
        yield connection


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


def _cleanup_claim(admin_client: Client, claim_id: str) -> None:
    admin_client.table("claims").delete().eq("id", claim_id).execute()


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("PUBLISHING-EVIDENCE TEST FIXTURE (official)"),
                "official_url": "https://example.invalid/publishing-evidence-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


@pytest.fixture
def critical_authorised_reviewer(
    admin_client: Client, second_reviewer: tuple[str, Client]
) -> tuple[str, Client]:
    """`second_reviewer` (a DIFFERENT person from the plain `reviewer`
    fixture, tests/db/conftest.py's own established pattern for "a
    different person reviews"), elevated: `reviewers.critical_authorised
    = true`. Only the service role can flip this column at all (0001's
    own "no policy = no access" shape on `reviewers`, unchanged by
    0017). Deliberately NOT built on top of `reviewer` itself — a test
    that needs both a maker AND a critical-authorised checker would
    otherwise get the SAME person for both, tripping the self-approval
    guard for a reason that has nothing to do with the critical-tier gate
    this fixture exists to test."""
    reviewer_id, reviewer_client = second_reviewer
    admin_client.table("reviewers").update({"critical_authorised": True}).eq(
        "user_id", reviewer_id
    ).execute()
    return reviewer_id, reviewer_client


# =====================================================================
# content_hash
# =====================================================================
class TestContentHash:
    def test_content_hash_is_set_on_insert(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = row["id"]
        try:
            assert row["content_hash"]
            assert isinstance(row["content_hash"], str)
            assert len(row["content_hash"]) == 64  # sha256, hex-encoded
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_changing_a_hashed_field_changes_the_hash(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = row["id"]
        try:
            before = row["content_hash"]
            updated = (
                reviewer_client.table("claims")
                .update({"value": 999})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert updated["content_hash"] != before
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_changing_a_non_hashed_field_does_not_change_the_hash(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """`tier` is deliberately NOT one of docs/CONTRACTS.md's frozen
        content_hash fields — it is curation metadata (how often this
        fact needs rechecking / who may approve it), not the fact
        itself."""
        reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = row["id"]
        try:
            before = row["content_hash"]
            updated = (
                reviewer_client.table("claims")
                .update({"tier": "annual"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert updated["content_hash"] == before
        finally:
            _cleanup_claim(admin_client, claim_id)


# =====================================================================
# tier + critical_authorised
# =====================================================================
class TestTierDefaultsAndCriticalGate:
    def test_tier_defaults_to_cycle(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        claim_id = row["id"]
        try:
            assert row["tier"] == "cycle"
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_an_ordinary_reviewer_cannot_publish_a_critical_tier_claim(
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
            .insert(_draft_payload(official_source, maker_id, tier="critical"))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            with pytest.raises(APIError):
                checker_client.table("claims").update({"status": "published"}).eq(
                    "id", claim_id
                ).execute()
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_a_critical_authorised_reviewer_can_publish_a_critical_tier_claim(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        critical_authorised_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = critical_authorised_reviewer
        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id, tier="critical"))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        try:
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            published = (
                checker_client.table("claims")
                .update({"status": "published"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert published["status"] == "published"
            assert published["reviewed_by"] == checker_id
            assert published["approved_draft_version"] == published["content_hash"]
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_a_non_critical_claim_needs_no_special_authorisation(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The previous release keeps working: an ordinary reviewer,
        publishing an ordinary (non-critical) claim, is unaffected by
        this migration."""
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id))
            .execute()
            .data[0]
        )
        claim_id = draft["id"]
        assert draft["tier"] == "cycle"
        try:
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            published = (
                checker_client.table("claims")
                .update({"status": "published"})
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert published["status"] == "published"
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_an_ordinary_reviewer_cannot_launder_a_critical_claim_by_changing_tier_in_the_same_publish_call(  # noqa: E501
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """Live-reproduces the data-security-reviewer's finding on the
        original PUB-2 diff, fixed in this same migration file (not a new
        migration -- 0017 had not been applied anywhere but this migration
        owner's own dedicated stack): a claim is submitted as
        tier='critical' and reaches in_review exactly as any other
        critical claim would. Then, in ONE update call, a reviewer who is
        NOT critical_authorised (`second_reviewer`, deliberately distinct
        from the maker so this is never a self-approval failure instead)
        sets BOTH `status: 'published'` AND `tier: 'cycle'` at once --
        attempting to launder the claim past the critical-tier gate in the
        very act of approving it, since the gate used to read `new.tier`
        (the POST-update value) rather than the tier the claim actually
        carried going into review.

        `tier` is now folded into the trigger's own `content_changed` set
        (the same protection `value`/`source_id`/every other content field
        already had), so this combined update is rejected outright by the
        existing "content cannot change in the same update that publishes
        it" guard -- before the critical-tier gate is ever reached -- the
        same way changing `value` in the same call that publishes already
        was. The claim must be left exactly as it was: still in_review,
        still tier=critical, not published and not silently downgraded
        either."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(official_source, maker_id, tier="critical"))
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
                    {"status": "published", "tier": "cycle"}
                ).eq("id", claim_id).execute()
            still = (
                admin_client.table("claims")
                .select("status, tier")
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert still["status"] == "in_review", (
                "the combined status+tier update must not have published the claim"
            )
            assert still["tier"] == "critical", (
                "the combined status+tier update must not have laundered the tier down "
                "either -- the whole request is rejected, not partially applied"
            )
        finally:
            _cleanup_claim(admin_client, claim_id)


# =====================================================================
# sources.source_type / official_url freeze
# =====================================================================
class TestSourceIdentityFreeze:
    def _publish_a_claim_on(
        self,
        admin_client: Client,
        maker: tuple[str, Client],
        checker: tuple[str, Client],
        source_id: str,
    ) -> str:
        maker_id, maker_client = maker
        checker_id, checker_client = checker
        draft = (
            maker_client.table("claims")
            .insert(_draft_payload(source_id, maker_id))
            .execute()
            .data[0]
        )
        maker_client.table("claims").update({"status": "in_review"}).eq(
            "id", draft["id"]
        ).execute()
        published = (
            checker_client.table("claims")
            .update({"status": "published"})
            .eq("id", draft["id"])
            .execute()
            .data[0]
        )
        return str(published["id"])

    def test_flipping_source_type_on_a_source_used_by_a_published_claim_is_rejected(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        claim_id = self._publish_a_claim_on(
            admin_client, reviewer, second_reviewer, official_source
        )
        _reviewer_id, reviewer_client = reviewer
        try:
            with pytest.raises(APIError):
                reviewer_client.table("sources").update({"source_type": "synthetic"}).eq(
                    "id", official_source
                ).execute()
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_flipping_official_url_on_a_source_used_by_a_published_claim_is_rejected(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        claim_id = self._publish_a_claim_on(
            admin_client, reviewer, second_reviewer, official_source
        )
        _reviewer_id, reviewer_client = reviewer
        try:
            with pytest.raises(APIError):
                reviewer_client.table("sources").update(
                    {"official_url": "https://example.invalid/a-different-url"}
                ).eq("id", official_source).execute()
        finally:
            _cleanup_claim(admin_client, claim_id)

    def test_a_source_with_no_published_claim_can_still_be_edited(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """The previous release keeps working: editing a source that
        exists but backs no PUBLISHED claim yet (draft-only, or no claim
        at all) is completely unaffected."""
        _reviewer_id, reviewer_client = reviewer
        updated = (
            reviewer_client.table("sources")
            .update({"official_url": "https://example.invalid/edited-before-publish"})
            .eq("id", official_source)
            .execute()
            .data[0]
        )
        assert updated["official_url"] == "https://example.invalid/edited-before-publish"

    def test_editing_an_unrelated_field_on_a_referenced_source_still_works(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        claim_id = self._publish_a_claim_on(
            admin_client, reviewer, second_reviewer, official_source
        )
        _reviewer_id, reviewer_client = reviewer
        try:
            updated = (
                reviewer_client.table("sources")
                .update({"authority_name": run_name("renamed authority, same identity")})
                .eq("id", official_source)
                .execute()
                .data[0]
            )
            assert updated["authority_name"].startswith("renamed authority, same identity")
        finally:
            _cleanup_claim(admin_client, claim_id)


# =====================================================================
# source_versions — insert-only, immutable
# =====================================================================
class TestSourceVersionsImmutability:
    def test_a_reviewer_can_insert_a_source_version(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        row = (
            reviewer_client.table("source_versions")
            .insert(
                {
                    "source_id": official_source,
                    "checked_on": TODAY.isoformat(),
                    "checked_by": run_name("pub-2-test-reviewer"),
                    "status": "confirmed",
                }
            )
            .execute()
            .data[0]
        )
        try:
            assert row["source_id"] == official_source
        finally:
            admin_client.table("source_versions").delete().eq("id", row["id"]).execute()

    def test_a_non_reviewer_cannot_insert_a_source_version(
        self, student_a: tuple[str, Client], official_source: str
    ) -> None:
        _student_id, student_client = student_a
        with pytest.raises(APIError):
            student_client.table("source_versions").insert(
                {
                    "source_id": official_source,
                    "checked_on": TODAY.isoformat(),
                    "checked_by": run_name("pub-2-test-student"),
                    "status": "confirmed",
                }
            ).execute()

    def test_a_source_version_cannot_be_updated_by_anyone_including_a_reviewer(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        row = (
            admin_client.table("source_versions")
            .insert(
                {
                    "source_id": official_source,
                    "checked_on": TODAY.isoformat(),
                    "checked_by": run_name("pub-2-test-immutable"),
                    "status": "confirmed",
                }
            )
            .execute()
            .data[0]
        )
        try:
            result = (
                reviewer_client.table("source_versions")
                .update({"status": "changed"})
                .eq("id", row["id"])
                .execute()
            )
            assert result.data == [], (
                "a reviewer's update to a source_version matched a row — "
                "0017 adds no UPDATE policy at all, for anyone"
            )
            still = (
                admin_client.table("source_versions")
                .select("status")
                .eq("id", row["id"])
                .execute()
                .data[0]
            )
            assert still["status"] == "confirmed"
        finally:
            admin_client.table("source_versions").delete().eq("id", row["id"]).execute()

    def test_a_source_version_cannot_be_deleted_by_a_reviewer(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        row = (
            admin_client.table("source_versions")
            .insert(
                {
                    "source_id": official_source,
                    "checked_on": TODAY.isoformat(),
                    "checked_by": run_name("pub-2-test-delete"),
                    "status": "confirmed",
                }
            )
            .execute()
            .data[0]
        )
        try:
            result = (
                reviewer_client.table("source_versions").delete().eq("id", row["id"]).execute()
            )
            assert result.data == []
            assert (
                admin_client.table("source_versions")
                .select("id")
                .eq("id", row["id"])
                .execute()
                .data
            )
        finally:
            admin_client.table("source_versions").delete().eq("id", row["id"]).execute()


# =====================================================================
# NULL-safety of the self-approval operator — logic level. 0017's own
# created_by-forcing (docs/CONTRACTS.md item 1) makes a live "both NULL,
# authenticated" row structurally unreachable through the real RLS-scoped
# API from here on (the intended, stronger outcome — two independent
# fixes close the same bug class). Proven at the SQL-expression level
# instead, the same "logic, not live" honesty
# tests/db/test_exposure_catalogue.py's own storage-bucket revert-to-prove
# already uses for an analogous reason.
# =====================================================================
class TestSelfApprovalOperatorIsNullSafe:
    def test_two_nulls_are_treated_as_the_same_identity_and_blocked(
        self, sql: psycopg.Connection
    ) -> None:
        row = sql.execute("select (NULL::uuid is not distinct from NULL::uuid)").fetchone()
        assert row is not None and row[0] is True, (
            "0017's self-approval check uses IS NOT DISTINCT FROM specifically so two "
            "NULLs compare as the SAME identity (blocked) — this is that operator, "
            "exercised directly."
        )

    def test_a_real_id_is_never_treated_as_the_same_identity_as_null(
        self, sql: psycopg.Connection
    ) -> None:
        row = sql.execute("select (gen_random_uuid() is not distinct from NULL::uuid)").fetchone()
        assert row is not None and row[0] is False

    def test_the_original_naive_equals_operator_would_have_hidden_the_two_null_case(
        self, sql: psycopg.Connection
    ) -> None:
        """What 0003's ORIGINAL `=` comparison actually returns for two
        NULLs: NULL (neither true nor false) — which is exactly why
        `raise exception ... if new.reviewed_by = new.created_by` would
        silently fail to fire for a two-NULL row. The bug 0017's operator
        change closes."""
        row = sql.execute("select (NULL::uuid = NULL::uuid) is null").fetchone()
        assert row is not None and row[0] is True
