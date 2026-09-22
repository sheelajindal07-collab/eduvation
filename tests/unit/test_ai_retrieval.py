"""Tests for app/ai/retrieval.py (AI-5).

Two families:

1. Behavioural tests against a fake Supabase-shaped client (`_FakeQuery`
   below actually applies `.eq()`/`.in_()` filters, unlike some other
   fakes in this test suite that pre-bake exactly one table's worth of
   rows and ignore filters — here the filtering behaviour itself is part
   of what several tests assert). The fake stands in for a "reviewer-
   scoped" RLS client by simply returning draft/in_review/superseded/
   synthetic-backed rows mixed in with published ones: this module never
   knows or cares who is asking, so a fake that hands back a superset of
   rows a real reviewer's RLS-scoped client could see is exactly the
   right double for "does this module defend itself regardless of the
   caller's own visibility", without needing a real Supabase/RLS stack
   (that live proof is `tests/db/test_ai_retrieval_live.py`).

2. `TestImportGuard`, which inspects this module's own AST/source text so
   a future edit that adds a student-identity-bearing import fails a test
   rather than depending on a human catching it in review.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, timedelta
from typing import Any

import app.ai.retrieval as retrieval
from app.planning.comparison import DEFAULT_FRESHNESS_SLA_DAYS
from app.rules.eligibility import Criterion

TODAY = date(2026, 9, 22)


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Enough of Supabase's fluent `.select().eq().in_().execute()`
    interface to actually apply `eq`/`in_` filters against an in-memory
    table of row dicts."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def in_(self, column: str, values: list[Any]) -> _FakeQuery:
        self._rows = [r for r in self._rows if r.get(column) in values]
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(list(self._tables.get(name, [])))


OFFICIAL_SOURCE = {
    "id": "src-official",
    "authority_name": "GSEB",
    "official_url": "https://gseb.example.invalid",
    "source_type": "official",
}
INSTITUTION_SOURCE = {
    "id": "src-institution",
    "authority_name": "Some College",
    "official_url": "https://college.example.invalid",
    "source_type": "institution_self_declared",
}
SYNTHETIC_SOURCE = {
    "id": "src-synthetic",
    "authority_name": "TEST FIXTURE",
    "official_url": "https://example.invalid",
    "source_type": "synthetic",
}


def _claim_row(
    *,
    claim_id: str,
    entity_type: str = "Pathway",
    entity_id: str = "pathway-1",
    field: str,
    value: Any,
    source_id: str,
    status: str = "published",
    verification_date: date = TODAY,
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "value": value,
        "source_id": source_id,
        "verification_date": verification_date.isoformat(),
        "verifier": "test-reviewer",
        "status": status,
        "review_due_date": date(2099, 1, 1).isoformat(),
    }


def _client(claims: list[dict[str, Any]], sources: list[dict[str, Any]]) -> _FakeDbClient:
    return _FakeDbClient({"claims": claims, "sources": sources})


class TestFetchEntityRecordsExclusion:
    """Every case here models a client that COULD return the row (a
    "reviewer-scoped" RLS client, standing in as described in the module
    docstring) -- the assertion is that retrieval.py drops it anyway."""

    def test_draft_claim_is_excluded_even_though_the_row_was_returned(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1",
                field="minimum_age",
                value=18,
                source_id="src-official",
                status="draft",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records == ()

    def test_in_review_claim_is_excluded(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1",
                field="minimum_age",
                value=18,
                source_id="src-official",
                status="in_review",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records == ()

    def test_superseded_claim_is_excluded(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1",
                field="minimum_age",
                value=18,
                source_id="src-official",
                status="superseded",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records == ()

    def test_synthetic_backed_published_claim_is_excluded(self) -> None:
        """Defence in depth: the DB trigger (0001_init.sql) is meant to
        forbid a synthetic-backed claim from ever reaching `published` at
        all, but this module must independently refuse to surface one
        even if that ever fails or a caller constructs the state directly
        (matches `app/planning/comparison.py`'s identical test)."""
        claims = [
            _claim_row(
                claim_id="c1",
                field="minimum_age",
                value=18,
                source_id="src-synthetic",
                status="published",
            )
        ]
        db = _client(claims, [SYNTHETIC_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records == ()

    def test_published_claim_with_unresolvable_source_is_excluded(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1",
                field="minimum_age",
                value=18,
                source_id="does-not-exist",
                status="published",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records == ()

    def test_mixed_batch_only_the_published_non_synthetic_claim_survives(self) -> None:
        """A single fetch returning a full mix of statuses/sources (the
        broadest, most realistic model of "a reviewer-scoped client's
        SELECT") -- exactly one record should survive."""
        claims = [
            _claim_row(
                claim_id="draft-1", field="minimum_age", value=18, source_id="src-official",
                status="draft",
            ),
            _claim_row(
                claim_id="review-1", field="maximum_age", value=25, source_id="src-official",
                status="in_review",
            ),
            _claim_row(
                claim_id="superseded-1", field="minimum_marks_percentage", value=50.0,
                source_id="src-official", status="superseded",
            ),
            _claim_row(
                claim_id="synthetic-1", field="required_subjects", value="Physics,Chemistry",
                source_id="src-synthetic", status="published",
            ),
            _claim_row(
                claim_id="real-1", field="domicile_states", value="Gujarat",
                source_id="src-official", status="published",
            ),
        ]
        db = _client(claims, [OFFICIAL_SOURCE, SYNTHETIC_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert [r.field for r in records] == ["domicile_states"]
        assert records[0].id == "real-1"
        assert records[0].value == "Gujarat"
        assert records[0].source_authority == "GSEB"


class TestFetchEntityRecordsValues:
    def test_published_official_fresh_claim_is_included_with_evidence(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="published",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert len(records) == 1
        record = records[0]
        assert record.id == "c1"
        assert record.field == "minimum_age"
        assert record.value == 18
        assert record.source_authority == "GSEB"
        assert record.source_url == "https://gseb.example.invalid"
        assert record.is_stale is False

    def test_stale_claim_is_included_but_flagged(self) -> None:
        old_date = TODAY - timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS + 1)
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="published", verification_date=old_date,
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert len(records) == 1
        assert records[0].is_stale is True
        assert records[0].value == 18  # still shown -- stale is not not_available

    def test_claim_exactly_at_sla_boundary_is_not_stale(self) -> None:
        boundary_date = TODAY - timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS)
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="published", verification_date=boundary_date,
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records[0].is_stale is False

    def test_institution_reported_claim_is_included(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="verified_charges", value=50000,
                source_id="src-institution", status="published",
            )
        ]
        db = _client(claims, [INSTITUTION_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert records[0].source_authority == "Some College"

    def test_records_are_sorted_by_field_name(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="verified_charges", value=1, source_id="src-official"
            ),
            _claim_row(
                claim_id="c2", field="minimum_age", value=2, source_id="src-official"
            ),
            _claim_row(
                claim_id="c3", field="domicile_states", value="Gujarat", source_id="src-official"
            ),
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert [r.field for r in records] == [
            "domicile_states",
            "minimum_age",
            "verified_charges",
        ]

    def test_only_this_entitys_claims_are_returned(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", entity_id="pathway-1", field="minimum_age", value=18,
                source_id="src-official",
            ),
            _claim_row(
                claim_id="c2", entity_id="pathway-2", field="minimum_age", value=21,
                source_id="src-official",
            ),
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_pathway_records(db, "pathway-1", as_of=TODAY)
        assert len(records) == 1
        assert records[0].value == 18

    def test_career_records_are_scoped_to_entity_type_career(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", entity_type="Career", entity_id="career-1",
                field="typical_progression", value="Engineer", source_id="src-official",
            ),
            _claim_row(
                claim_id="c2", entity_type="Pathway", entity_id="career-1",
                field="minimum_age", value=18, source_id="src-official",
            ),
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        records = retrieval.fetch_career_records(db, "career-1", as_of=TODAY)
        assert [r.field for r in records] == ["typical_progression"]


class TestFetchEntityRecordsValidation:
    def test_unknown_entity_type_raises(self) -> None:
        db = _client([], [])
        try:
            retrieval.fetch_entity_records(db, "Exam", "id-1", as_of=TODAY)
        except ValueError:
            pass
        else:
            raise AssertionError("expected a ValueError for an unrecognised entity_type")


class TestFetchClaimRecord:
    def test_returns_none_for_a_draft_claim(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="draft",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        assert retrieval.fetch_claim_record(db, "c1", as_of=TODAY) is None

    def test_returns_none_for_a_missing_claim(self) -> None:
        db = _client([], [])
        assert retrieval.fetch_claim_record(db, "does-not-exist", as_of=TODAY) is None

    def test_returns_a_record_for_a_published_claim(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="published",
            )
        ]
        db = _client(claims, [OFFICIAL_SOURCE])
        record = retrieval.fetch_claim_record(db, "c1", as_of=TODAY)
        assert record is not None
        assert record.field == "minimum_age"
        assert record.value == 18


class TestPathwayCostSummary:
    def test_delegates_to_the_real_cost_engine(self) -> None:
        """Not re-deriving the arithmetic here -- assert the total matches
        what app/rules/cost.py itself would compute for this claim set."""
        claims = [
            _claim_row(
                claim_id="c1", field="verified_charges", value=50000, source_id="src-official",
            )
        ]
        sources = [dict(OFFICIAL_SOURCE)]
        # verified_charges claims need a currency to be usable
        # (docs/CONTRACTS.md "Money and currency") -- add it directly on
        # the row since `_claim_row` does not set one by default.
        claims[0]["currency"] = "INR"
        db = _client(claims, sources)
        summary = retrieval.pathway_cost_summary(db, "pathway-1", as_of=TODAY)
        assert summary.verified_charges.total is not None
        assert summary.verified_charges.total.amount == 50000
        assert summary.verified_charges.total.currency == "INR"
        # No confirmed assistance, no additional-expenses hint published:
        # net_to_arrange is verified charges + zero.
        assert summary.net_to_arrange is not None
        assert summary.net_to_arrange.amount == 50000

    def test_draft_fee_claim_never_reaches_the_total(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="verified_charges", value=50000, source_id="src-official",
                status="draft",
            )
        ]
        claims[0]["currency"] = "INR"
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        summary = retrieval.pathway_cost_summary(db, "pathway-1", as_of=TODAY)
        assert summary.verified_charges.total is None
        assert summary.verified_charges.complete is False


class TestPathwayTimeline:
    def test_delegates_to_the_real_timeline_engine(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="stage:1:name", value="Class 12", source_id="src-official"
            ),
            _claim_row(
                claim_id="c2", field="stage:1:duration_weeks", value=52,
                source_id="src-official",
            ),
            _claim_row(
                claim_id="c3", field="stage:2:name", value="Entrance prep",
                source_id="src-official",
            ),
            _claim_row(
                claim_id="c4", field="stage:2:duration_weeks", value=26,
                source_id="src-official",
            ),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        result = retrieval.pathway_timeline(db, "pathway-1", as_of=TODAY)
        assert result.complete is True
        assert result.total_weeks == 78

    def test_a_draft_stage_duration_makes_the_total_unknown(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="stage:1:name", value="Class 12", source_id="src-official"
            ),
            _claim_row(
                claim_id="c2", field="stage:1:duration_weeks", value=52, source_id="src-official",
                status="draft",
            ),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        result = retrieval.pathway_timeline(db, "pathway-1", as_of=TODAY)
        assert result.total_weeks is None
        assert result.complete is False
        # The stage still shows -- an unpublished duration is not the
        # same as "no stage exists at all".
        assert len(result.stages) == 1


class TestPathwayEligibilityCriteria:
    def test_builds_criterion_objects_from_published_claims(self) -> None:
        claims = [
            _claim_row(claim_id="c1", field="minimum_age", value=18, source_id="src-official"),
            _claim_row(
                claim_id="c2", field="required_subjects", value="Physics,Chemistry",
                source_id="src-official",
            ),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        criteria = retrieval.pathway_eligibility_criteria(db, "pathway-1")
        assert len(criteria) == 2
        assert all(isinstance(c, Criterion) for c in criteria)
        names = {c.name for c in criteria}
        assert names == {"minimum_age", "required_subjects"}
        by_name = {c.name: c for c in criteria}
        assert by_name["minimum_age"].source_claim_id == "c1"

    def test_draft_eligibility_claim_is_never_built_into_a_criterion(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value=18, source_id="src-official",
                status="draft",
            ),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        criteria = retrieval.pathway_eligibility_criteria(db, "pathway-1")
        assert criteria == ()

    def test_unparseable_claim_value_is_skipped_not_raised(self) -> None:
        claims = [
            _claim_row(
                claim_id="c1", field="minimum_age", value="seventeen", source_id="src-official"
            ),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        criteria = retrieval.pathway_eligibility_criteria(db, "pathway-1")
        assert criteria == ()

    def test_criteria_are_never_evaluated_no_outcome_is_produced(self) -> None:
        """This module must never fabricate a meets/does_not_meet/
        insufficient_information outcome -- it has no student input and
        never will. `Criterion` objects carry a `check` callable, not a
        result; this asserts retrieval.py never calls it."""
        claims = [
            _claim_row(claim_id="c1", field="minimum_age", value=18, source_id="src-official"),
        ]
        db = _client(claims, [dict(OFFICIAL_SOURCE)])
        criteria = retrieval.pathway_eligibility_criteria(db, "pathway-1")
        assert len(criteria) == 1
        assert callable(criteria[0].check)
        # The returned tuple has no `.outcome`/`.explanation` of its own
        # -- those only exist once *a caller* -- never this module --
        # calls `.check(some_input)`.
        assert not hasattr(criteria[0], "outcome")
        # And retrieval.py itself never imports the machinery that WOULD
        # let it evaluate one -- see the module docstring's "Eligibility
        # -- criteria, never an evaluated outcome" section.
        assert "evaluate_eligibility" not in dir(retrieval)
        assert "EligibilityInput" not in dir(retrieval)


class TestShortId:
    def test_a_normal_claim_id_passes_through_unchanged(self) -> None:
        assert retrieval._short_id("00000000-0000-0000-0000-000000000001") == (
            "00000000-0000-0000-0000-000000000001"
        )

    def test_an_overlong_id_is_shortened_deterministically(self) -> None:
        from app.ai.schemas import MAX_ID_CHARS

        long_id = "x" * (MAX_ID_CHARS + 50)
        short = retrieval._short_id(long_id)
        assert len(short) <= MAX_ID_CHARS
        assert short == retrieval._short_id(long_id)  # deterministic

    def test_two_different_overlong_ids_shorten_to_different_values(self) -> None:
        from app.ai.schemas import MAX_ID_CHARS

        a = retrieval._short_id("a" * (MAX_ID_CHARS + 10))
        b = retrieval._short_id("b" * (MAX_ID_CHARS + 10))
        assert a != b


class TestImportGuard:
    """See the module docstring's "What this module does NOT do" section.
    `retrieval.py` must never import anything from a student-identity-
    bearing table or module."""

    _FORBIDDEN_SUBSTRINGS = ("student_profile", "saved_plan", "guest_session")

    def test_no_import_statement_names_a_forbidden_module_or_symbol(self) -> None:
        source = inspect.getsource(retrieval)
        tree = ast.parse(source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported_names.add(module)
                for alias in node.names:
                    imported_names.add(alias.name)
                    imported_names.add(f"{module}.{alias.name}")

        lowered = {name.lower() for name in imported_names}
        offending = {
            name
            for name in lowered
            for forbidden in self._FORBIDDEN_SUBSTRINGS
            if forbidden in name
        }
        assert not offending, f"retrieval.py imports a forbidden name: {sorted(offending)}"

    def test_no_forbidden_substring_in_any_non_docstring_string_literal(self) -> None:
        """Belt-and-suspenders beyond the import-statement walk above: also
        rejects a forbidden table/module name appearing in an ordinary
        string literal (e.g. a stray `.table("student_profiles")`), not
        just in an `import` statement -- the card's own wording ("no
        student-identity-bearing TABLE or module") covers both shapes.

        Docstrings are deliberately excluded from this scan -- this
        module's OWN docstring names the forbidden words in prose, to
        explain the rule it exists to satisfy, which is not a violation
        of it."""
        source = inspect.getsource(retrieval)
        tree = ast.parse(source)

        docstring_node_ids: set[int] = set()
        doc_owners: list[ast.AST] = [tree]
        doc_owners.extend(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
        for owner in doc_owners:
            body = getattr(owner, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_node_ids.add(id(body[0].value))

        offending: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_node_ids
            ):
                lowered = node.value.lower()
                for forbidden in self._FORBIDDEN_SUBSTRINGS:
                    if forbidden in lowered:
                        offending.append((forbidden, node.value))

        assert not offending, (
            f"retrieval.py has a forbidden substring in a non-docstring string "
            f"literal: {offending}"
        )

    def test_the_only_tables_this_module_queries_are_claims_and_sources(self) -> None:
        """A narrower, positive assertion alongside the negative ones
        above: enumerate every `.table("...")` call literal in the source
        and assert the set is exactly `{"claims", "sources"}`."""
        source = inspect.getsource(retrieval)
        tree = ast.parse(source)
        table_names: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                table_names.add(node.args[0].value)
        assert table_names == {"claims", "sources"}

    def test_module_does_not_import_student_profile_model(self) -> None:
        """A direct, symbol-level check: `app.data.models.StudentProfile`
        specifically must never be imported here, even though
        `app.data.models` itself (for `Claim`/`Source`/...) legitimately
        is."""
        assert "StudentProfile" not in dir(retrieval)
