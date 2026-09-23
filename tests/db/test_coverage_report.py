"""scripts/content/coverage_report.py (CONTENT-8), against the live stack.

Three things are proved here, live where the card requires it to be live
and pure where the card's own violation is structurally impossible to
seed live (see `TestPublishedBackedBySyntheticSource` below):

1. **The counts are right**, against a small, hand-counted, clearly
   labelled batch -- `TestHandCountedBatch` below states the expected
   figures in a comment right next to the assertion that checks them,
   the same "worked out by hand... cross-checked against build_report's
   output" shape `tests/db/test_ai_spend_report.py` already uses for
   AI-13's own report script.
2. **The INTEGRITY section genuinely catches each of the five violation
   types this card names**, seeded for real against the live database
   (never a bare Python object standing in for a database row, except
   the one violation the schema makes structurally impossible to create
   at all -- see that class's own docstring), and stops catching each
   one once it is fixed.
3. **The read-only guarantee is real**, by AST inspection of the
   script's own source (not a substring/regex scan, which a comment
   could fool either way) -- `TestReadOnlyGuarantee` -- proven not to be
   a vacuous check via its own revert-to-prove test.

All live tests sign in as a REAL reviewer via `scripts.content.
coverage_report.build_reviewer_client` (the same `app.api.auth.
authenticate` call `app/web/reviewer/auth.py`'s sign-in route makes) --
never the service-role key. Service-role (`admin_client`) is used only
to SEED and clean up fixture rows, exactly as every other file in this
suite already restricts it to (see `tests/db/conftest.py`'s own
docstring).

Every violation this file seeds is only reachable at all via a direct
service-role INSERT: `db/migrations/0003_maker_checker.sql`'s
`enforce_claims_workflow` trigger steps aside entirely for
`auth.role() = 'service_role'`, which is exactly what makes these
otherwise-trigger-blocked shapes possible to construct for this test in
the first place -- no other fixture in this suite writes a published
claim this way on purpose, so residue from an unrelated test colliding
with this file's own assertions is not expected; every assertion below
still filters by this file's own known claim/entity ids rather than
asserting a global-zero count, matching this suite's own RUN_ID-isolation
convention (`tests/db/conftest.py` "QA-3").
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from supabase import Client

from scripts.content.coverage_report import (
    ClaimRecord,
    SourceRecord,
    build_report,
    build_reviewer_client,
    exit_code_for,
    fetch_claims,
    fetch_sources,
    render_csv,
    render_markdown,
)
from scripts.content.coverage_report import (
    main as coverage_report_main,
)
from tests.db.conftest import run_email, run_name

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "content" / "coverage_report.py"

TODAY = date.today()
NOW = datetime.now(UTC)
FAR_FUTURE_DUE = (TODAY + timedelta(days=365)).isoformat()


# ---------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def reviewer_credentials(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed reviewer with a KNOWN password -- same
    shape as `tests/db/test_reviewer_console.py`'s own fixture of the
    same name (that file's docstring explains why `tests/db/conftest.py`'s
    `reviewer` fixture, random password never exposed, does not fit
    here: this file needs to actually sign in through
    `build_reviewer_client`, not just get an already-authenticated
    client)."""
    email = run_email("coveragereport", domain="example.com")
    password = uuid.uuid4().hex
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)  # cascades to the reviewers row


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    """A real, allow-listed, non-synthetic source -- `nta.ac.in` is a
    real line in `content/allowed_domains.txt` today, so this is a
    genuinely clean source for every claim in this file that is NOT
    itself testing the bad-source-url violation."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("COVERAGE REPORT TEST OFFICIAL SOURCE"),
                "official_url": "https://nta.ac.in/coverage-report-test",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _insert_claim(
    admin_client: Client,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    source_id: str,
    status: str,
    value: Any = None,
    verifier: str = "COVERAGE REPORT TEST VERIFIER",
    verification_date: date = TODAY,
    review_due_date: date | None = None,
    created_by: str | None = None,
    reviewed_by: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Every claim this file seeds goes through this one helper, straight
    via the service-role `admin_client` -- see module docstring for why
    that is the only way to reach several of these shapes at all."""
    payload: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "value": value,
        "source_id": source_id,
        "verification_date": verification_date.isoformat(),
        "verifier": verifier,
        "status": status,
        "review_due_date": (review_due_date or date.fromisoformat(FAR_FUTURE_DUE)).isoformat(),
    }
    if created_by is not None:
        payload["created_by"] = created_by
    if reviewed_by is not None:
        payload["reviewed_by"] = reviewed_by
    if created_at is not None:
        payload["created_at"] = created_at.isoformat()
    result = admin_client.table("claims").insert(payload).execute()
    return cast("str", result.data[0]["id"])


def _delete_claims(admin_client: Client, claim_ids: list[str]) -> None:
    for claim_id in claim_ids:
        admin_client.table("claims").delete().eq("id", claim_id).execute()


def _live_claims_and_sources(
    reviewer_credentials: dict[str, str],
) -> tuple[list[ClaimRecord], dict[str, SourceRecord]]:
    """Sign in as the given reviewer and fetch every claim/source this
    account's RLS scope can see -- the same real round-trip
    `scripts.content.coverage_report.main` makes."""
    client = build_reviewer_client(
        email=reviewer_credentials["email"], password=reviewer_credentials["password"]
    )
    try:
        return fetch_claims(client), fetch_sources(client)
    finally:
        client.postgrest.aclose()


# ---------------------------------------------------------------------
# 1. Hand-counted batch
# ---------------------------------------------------------------------


class TestHandCountedBatch:
    """One small, clearly labelled batch across two synthetic "Pathway"
    entity ids, with every figure worked out by hand in the comments
    right below, then checked against `build_report`'s real output built
    from LIVE-fetched-then-filtered rows (fetched via a genuine reviewer
    session, not a bare Python object)."""

    def test_counts_freshness_and_pending_age_match_the_hand_count(
        self, admin_client: Client, reviewer_credentials: dict[str, str], official_source: str
    ) -> None:
        pathway_1 = str(uuid.uuid4())
        pathway_2 = str(uuid.uuid4())
        claim_ids: list[str] = []

        try:
            # Pathway 1 -- HAS a published claim, so it IS "a published
            # pathway" and appears in pathway_coverage.
            claim_ids.append(
                _insert_claim(
                    admin_client,
                    entity_type="Pathway",
                    entity_id=pathway_1,
                    field="fee",
                    value=50000,
                    source_id=official_source,
                    status="published",
                    review_due_date=TODAY + timedelta(days=10),  # due within 14 AND 30
                )
            )
            claim_ids.append(
                _insert_claim(
                    admin_client,
                    entity_type="Pathway",
                    entity_id=pathway_1,
                    field="eligibility.age",
                    value=17,
                    source_id=official_source,
                    status="published",
                    review_due_date=TODAY - timedelta(days=5),  # already stale
                )
            )
            claim_ids.append(
                _insert_claim(
                    admin_client,
                    entity_type="Pathway",
                    entity_id=pathway_1,
                    field="eligibility.category",
                    value="general",
                    source_id=official_source,
                    status="published",
                    review_due_date=TODAY + timedelta(days=25),  # due within 30, NOT 14
                )
            )
            claim_ids.append(
                _insert_claim(
                    admin_client,
                    entity_type="Pathway",
                    entity_id=pathway_1,
                    field="duration",
                    value="4 years",
                    source_id=official_source,
                    status="draft",  # never published -> "not available" for pathway_1
                    created_at=NOW - timedelta(days=6),
                )
            )
            # Pathway 2 -- NO published claim at all, so it must NOT
            # appear in pathway_coverage, and its in_review claim must
            # NOT count towards freshness (published-only scope).
            claim_ids.append(
                _insert_claim(
                    admin_client,
                    entity_type="Pathway",
                    entity_id=pathway_2,
                    field="fee",
                    value=99000,
                    source_id=official_source,
                    status="in_review",
                    review_due_date=TODAY + timedelta(days=1),
                    created_at=NOW - timedelta(days=20),
                )
            )

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            my_claims = [c for c in all_claims if c.id in claim_ids]
            assert len(my_claims) == 5  # every seeded row round-tripped through RLS

            report = build_report(
                my_claims,
                all_sources,
                as_of=TODAY,
                allowed_domains=frozenset({"nta.ac.in"}),
            )

            # -- Hand count --
            # entity_status_counts: (Pathway, published)=3, (Pathway, draft)=1,
            # (Pathway, in_review)=1
            counts = {(r.entity_type, r.status): r.count for r in report.entity_status_counts}
            assert counts == {
                ("Pathway", "published"): 3,
                ("Pathway", "draft"): 1,
                ("Pathway", "in_review"): 1,
            }

            # pathway_coverage: only pathway_1 (has a published claim).
            # published fields = {fee, eligibility.age, eligibility.category} -> 3
            # all fields seen = + duration -> not_available = {duration} -> 1
            assert len(report.pathway_coverage) == 1
            row = report.pathway_coverage[0]
            assert row.pathway_id == pathway_1
            assert row.published_field_count == 3
            assert row.not_available_field_count == 1
            assert row.not_available_fields == ("duration",)

            # freshness (published only): fee due_within_14/30, eligibility.category
            # due_within_30 only, eligibility.age stale.
            assert report.freshness.due_within_14_days == 1
            assert report.freshness.due_within_30_days == 2
            assert report.freshness.stale_past_review_due == 1

            # pending_review_age: draft={duration}, age 6 days; in_review={pathway_2
            # fee}, age 20 days.
            by_status = {r.status: r for r in report.pending_review_age}
            assert by_status["draft"].count == 1
            assert by_status["draft"].average_age_days == 6.0
            assert by_status["draft"].oldest_age_days == 6
            assert by_status["in_review"].count == 1
            assert by_status["in_review"].average_age_days == 20.0
            assert by_status["in_review"].oldest_age_days == 20

            # This batch is entirely clean (official, allow-listed source;
            # named verifier; no created_by/reviewed_by set at all) -- no
            # finding of ours should appear.
            assert [f for f in report.integrity_findings if f.claim_id in claim_ids] == []

            # Rendering doesn't blow up and carries the batch's own figures.
            markdown = render_markdown(report)
            assert pathway_1 in markdown
            assert "duration" in markdown
            csv_text = render_csv(report)
            assert "entity_status_counts" in csv_text
        finally:
            _delete_claims(admin_client, claim_ids)


# ---------------------------------------------------------------------
# 2. Integrity -- each violation type
# ---------------------------------------------------------------------


class TestPublishedBackedBySyntheticSource:
    """`db/migrations/0001_init.sql`'s `forbid_publishing_synthetic_claims`
    trigger refuses this INSERT for every role, including service_role
    (already proven live by `tests/db/test_ai_retrieval_live.py`'s
    `TestSyntheticSourceCanNeverBePublishedLive`) -- there is no live
    INSERT path to this row shape at all. Proven instead directly
    against `build_report`, the exact pure function the live path also
    calls, with a hand-built record standing in for the row the database
    itself will never allow to exist."""

    def test_finding_present_then_absent(self) -> None:
        synthetic_source = SourceRecord(
            id="src-synthetic",
            authority_name="Synthetic Test Source",
            official_url="https://nta.ac.in/x",
            source_type="synthetic",
        )
        claim = ClaimRecord(
            id="claim-synthetic",
            entity_type="Pathway",
            entity_id="pathway-synthetic",
            field="fee",
            value=1,
            source_id="src-synthetic",
            verification_date=TODAY,
            verifier="A Real Person",
            status="published",
            review_due_date=TODAY + timedelta(days=180),
            created_by="user-a",
            reviewed_by="user-b",
            created_at=NOW,
            updated_at=NOW,
        )

        dirty = build_report(
            [claim],
            {"src-synthetic": synthetic_source},
            as_of=TODAY,
            allowed_domains=frozenset({"nta.ac.in"}),
        )
        assert dirty.integrity_ok is False
        assert exit_code_for(dirty) == 1
        assert any(
            f.check == "published_backed_by_synthetic_source" and f.claim_id == "claim-synthetic"
            for f in dirty.integrity_findings
        )

        official_source_record = SourceRecord(
            id="src-synthetic",
            authority_name="Synthetic Test Source",
            official_url="https://nta.ac.in/x",
            source_type="official",
        )
        clean = build_report(
            [claim],
            {"src-synthetic": official_source_record},
            as_of=TODAY,
            allowed_domains=frozenset({"nta.ac.in"}),
        )
        assert clean.integrity_ok is True
        assert exit_code_for(clean) == 0


class TestPublishedBackedByBadSourceUrl:
    def test_finding_present_then_absent_live(
        self, admin_client: Client, reviewer_credentials: dict[str, str], official_source: str
    ) -> None:
        bad_source_row = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": run_name("COVERAGE REPORT TEST AGGREGATOR SOURCE"),
                    # wikipedia.org is on scripts/content/check_sources.py's
                    # own AGGREGATOR_DOMAINS block-list.
                    "official_url": "https://wikipedia.org/coverage-report-test",
                    "source_type": "official",
                }
            )
            .execute()
        )
        bad_source_id = bad_source_row.data[0]["id"]
        claim_id = None
        try:
            claim_id = _insert_claim(
                admin_client,
                entity_type="Pathway",
                entity_id=str(uuid.uuid4()),
                field="fee",
                value=1,
                source_id=bad_source_id,
                status="published",
            )

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            dirty_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert any(f.check == "published_backed_by_bad_source_url" for f in dirty_findings)

            # Fix: re-point the same claim at the clean official source
            # (a direct service-role UPDATE, same bypass the seed used).
            admin_client.table("claims").update({"source_id": official_source}).eq(
                "id", claim_id
            ).execute()

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            clean_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert clean_findings == []
        finally:
            if claim_id is not None:
                _delete_claims(admin_client, [claim_id])
            admin_client.table("sources").delete().eq("id", bad_source_id).execute()


class TestPublishedNoNamedVerifier:
    def test_finding_present_then_absent_live(
        self, admin_client: Client, reviewer_credentials: dict[str, str], official_source: str
    ) -> None:
        claim_id = _insert_claim(
            admin_client,
            entity_type="Pathway",
            entity_id=str(uuid.uuid4()),
            field="fee",
            value=1,
            source_id=official_source,
            status="published",
            verifier="",  # blank -- the violation
        )
        try:
            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            dirty_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert any(f.check == "published_no_named_verifier" for f in dirty_findings)

            admin_client.table("claims").update({"verifier": "A Real Reviewer"}).eq(
                "id", claim_id
            ).execute()

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            clean_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert clean_findings == []
        finally:
            _delete_claims(admin_client, [claim_id])


class TestMakerEqualsChecker:
    """Also proves the real CLI-level `main()` exit code, not just
    `build_report`'s own findings list -- see module docstring point 2.
    `db/migrations/0003_maker_checker.sql`'s own trigger already refuses
    this for any non-service_role UPDATE/INSERT, so this shape is only
    reachable at all via a direct service-role write, exactly as this
    file's own module docstring explains."""

    def test_finding_present_then_absent_live(
        self, admin_client: Client, reviewer_credentials: dict[str, str], official_source: str
    ) -> None:
        same_person = reviewer_credentials["user_id"]
        claim_id = _insert_claim(
            admin_client,
            entity_type="Pathway",
            entity_id=str(uuid.uuid4()),
            field="fee",
            value=1,
            source_id=official_source,
            status="published",
            created_by=same_person,
            reviewed_by=same_person,
        )
        try:
            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            dirty_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert any(f.check == "maker_equals_checker" for f in dirty_findings)

            # Fix: clear reviewed_by (an unreviewed claim can't be
            # published either, so status must drop back to draft too) --
            # the simplest real fix, rather than fabricating a second
            # real reviewer account just to set a different reviewed_by.
            admin_client.table("claims").update({"reviewed_by": None, "status": "draft"}).eq(
                "id", claim_id
            ).execute()

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            clean_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.claim_id == claim_id
            ]
            assert clean_findings == []
        finally:
            _delete_claims(admin_client, [claim_id])

    def test_main_exit_code_flips_on_a_real_violation(
        self,
        admin_client: Client,
        reviewer_credentials: dict[str, str],
        official_source: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BCION_REVIEWER_EMAIL", reviewer_credentials["email"])
        monkeypatch.setenv("BCION_REVIEWER_PASSWORD", reviewer_credentials["password"])

        baseline_code = coverage_report_main([])
        capsys.readouterr()  # discard baseline output

        same_person = reviewer_credentials["user_id"]
        claim_id = _insert_claim(
            admin_client,
            entity_type="Pathway",
            entity_id=str(uuid.uuid4()),
            field="fee",
            value=1,
            source_id=official_source,
            status="published",
            created_by=same_person,
            reviewed_by=same_person,
        )
        try:
            # A real finding always means exit 1, unconditionally --
            # unlike the "back to baseline" check below, this direction
            # needs no assumption about the rest of the live table's
            # state.
            dirty_code = coverage_report_main([])
            assert dirty_code == 1
            dirty_output = capsys.readouterr().out
            assert claim_id in dirty_output
            assert "maker_equals_checker" in dirty_output
        finally:
            _delete_claims(admin_client, [claim_id])

        after_code = coverage_report_main([])
        capsys.readouterr()
        assert after_code == baseline_code
        if baseline_code == 0:
            assert after_code == 0


class TestIncompleteEligibilitySet:
    """The `required_fields` convention this card's own module docstring
    documents: an entity-level declaration claim (`field=
    "required_fields"`, a comma-separated `value`) plus whichever of
    those fields have (or have not) actually reached `published`."""

    def test_finding_present_then_absent_live(
        self, admin_client: Client, reviewer_credentials: dict[str, str], official_source: str
    ) -> None:
        pathway_id = str(uuid.uuid4())
        declaration_id = _insert_claim(
            admin_client,
            entity_type="Pathway",
            entity_id=pathway_id,
            field="required_fields",
            value="fee,duration",
            source_id=official_source,
            status="draft",  # editorial metadata, any status is fine
        )
        fee_claim_id = _insert_claim(
            admin_client,
            entity_type="Pathway",
            entity_id=pathway_id,
            field="fee",
            value=50000,
            source_id=official_source,
            status="published",
        )
        claim_ids = [declaration_id, fee_claim_id]
        try:
            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            dirty_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.check == "incomplete_eligibility_set" and f.entity_id == pathway_id
            ]
            assert len(dirty_findings) == 1
            assert "duration" in dirty_findings[0].detail

            duration_claim_id = _insert_claim(
                admin_client,
                entity_type="Pathway",
                entity_id=pathway_id,
                field="duration",
                value="4 years",
                source_id=official_source,
                status="published",
            )
            claim_ids.append(duration_claim_id)

            all_claims, all_sources = _live_claims_and_sources(reviewer_credentials)
            clean_findings = [
                f
                for f in build_report(
                    all_claims, all_sources, as_of=TODAY, allowed_domains=frozenset({"nta.ac.in"})
                ).integrity_findings
                if f.check == "incomplete_eligibility_set" and f.entity_id == pathway_id
            ]
            assert clean_findings == []
        finally:
            _delete_claims(admin_client, claim_ids)


# ---------------------------------------------------------------------
# 3. Read-only guarantee -- real AST inspection, proven non-vacuous.
# ---------------------------------------------------------------------

_FORBIDDEN_WRITE_METHODS = frozenset({"insert", "update", "delete", "upsert", "rpc"})


def _write_calls_in_source(source_text: str) -> list[str]:
    """Every `<something>.<forbidden-method>(...)` call anywhere in
    `source_text`, found by real AST inspection -- not a substring or
    regex scan, which a comment quoting a forbidden method name (as this
    very file's own module docstring does, describing what must be
    ABSENT) could trivially fool in either direction."""
    tree = ast.parse(source_text)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _FORBIDDEN_WRITE_METHODS
        ):
            found.append(f"line {node.lineno}: .{node.func.attr}(...)")
    return found


class TestReadOnlyGuarantee:
    def test_the_script_calls_no_write_method_anywhere(self) -> None:
        """Confirms `scripts/content/coverage_report.py` genuinely has no
        write path -- not on its happy path, not in an `except:` branch,
        not anywhere -- for the actual, current file on disk."""
        source_text = SCRIPT_PATH.read_text(encoding="utf-8")
        assert _write_calls_in_source(source_text) == []

    def test_the_scanner_is_not_vacuous(self) -> None:
        """Revert-to-prove: a scanner that always returns `[]` would make
        the test above pass for the wrong reason. Confirms it really
        does flag a write call when one exists, on every forbidden
        method name."""
        for method in sorted(_FORBIDDEN_WRITE_METHODS):
            injected = f"client.table('x').{method}({{'a': 1}}).execute()\n"
            found = _write_calls_in_source(injected)
            assert found, f"scanner failed to catch an injected .{method}(...) call"
