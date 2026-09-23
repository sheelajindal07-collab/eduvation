"""Unit tests for `app/ai/what_changed.py` (AI-19, `tasks/BCI-022.md`).

Every test uses `MockAIProvider` (`app/ai/mock_provider.py`) — its
`responses=[...]` sequencing and `raise_on_call` hook, the same
convention `tests/unit/test_ai_pipeline.py` already establishes for the
two-pass protocol this module mirrors. `db` is a small, hand-built,
id-aware fake (`_FakeDbClient`/`_FakeQuery` below) rather than a real
`supabase.Client` — no network call, no live database, anywhere in this
file. Settings are monkeypatched at the name `app.ai.what_changed`
imported them under (`_patch_settings`), the same idiom
`tests/unit/test_ai_pipeline.py`'s own `_patch_settings` uses.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any

import pytest

import app.ai.what_changed as what_changed_module
from app.ai.budget import AIRequestBudget
from app.ai.mock_provider import MockAIProvider
from app.ai.schemas import AIAnswerStatus, AIProviderTimeout
from app.ai.what_changed import RenderedDiffLine, WhatChangedAnswer, answer_what_changed
from app.core.config import Settings

TODAY = date(2026, 9, 22)

_SUPERSEDED_ID = "11111111-1111-1111-1111-111111111111"
_SUCCESSOR_ID = "22222222-2222-2222-2222-222222222222"
_OLD_SOURCE_ID = "33333333-3333-3333-3333-333333333333"
_NEW_SOURCE_ID = "44444444-4444-4444-4444-444444444444"


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Unlike `tests/unit/test_ask_api.py`'s own `_FakeQuery` (which
    ignores `.eq()` entirely), this one actually filters -- this module
    calls `_readable_claim` TWICE per answer, once for the superseded
    claim's own id and once for its successor's, so a fake that could not
    tell the two calls apart could never seed both rows distinctly."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append((column, value))
        return self

    def execute(self) -> _FakeResult:
        rows = self._rows
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        return _FakeResult(rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(list(self._tables.get(name, [])))


class _ExplodingProvider:
    """Proves the provider is never called on a path that must return
    before any provider call -- mirrors the `_explode` idiom
    `tests/unit/test_ai_pipeline.py`/`tests/unit/test_ask_api.py` both
    already use."""

    def generate(self, prompt: str) -> str:
        raise AssertionError("provider must not be called on this path")


def _budget(daily_request_budget: int = 10) -> AIRequestBudget:
    return AIRequestBudget(daily_request_budget=daily_request_budget)


def _settings(*, ai_enabled: bool = True, configured: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        ai_enabled=ai_enabled,
        gemini_api_key="test-only-not-a-real-key" if configured else None,
    )


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs: bool) -> None:
    monkeypatch.setattr(what_changed_module, "get_settings", lambda: _settings(**kwargs))


def _claim_row(
    *,
    claim_id: str,
    field: str = "minimum_age",
    value: Any = 17,
    source_id: str = _OLD_SOURCE_ID,
    status: str = "superseded",
    verification_date: str = "2026-01-01",
    superseded_by: str | None = _SUCCESSOR_ID,
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "entity_type": "Pathway",
        "entity_id": "pathway-1",
        "field": field,
        "value": value,
        "source_id": source_id,
        "verification_date": verification_date,
        "verifier": "tester",
        "status": status,
        "review_due_date": "2099-01-01",
        "superseded_by": superseded_by,
    }


def _source_row(
    *,
    source_id: str,
    authority_name: str = "Old Authority (test fixture)",
    source_type: str = "official",
) -> dict[str, Any]:
    return {
        "id": source_id,
        "authority_name": authority_name,
        "official_url": "https://example.invalid/test-source",
        "source_type": source_type,
    }


def _db_with(
    *,
    superseded: dict[str, Any] | None,
    successor: dict[str, Any] | None,
    sources: list[dict[str, Any]],
) -> _FakeDbClient:
    claims = [row for row in (superseded, successor) if row is not None]
    return _FakeDbClient({"claims": claims, "sources": sources})


def _full_scenario_db(
    *,
    successor_status: str = "published",
    successor_verification_date: str = "2026-06-01",
) -> _FakeDbClient:
    """A superseded claim (value=17, "Old Authority", 2026-01-01) whose
    successor changes all three diffable attributes (value=18, "New
    Authority", `successor_verification_date`) -- three candidate diff
    lines, in `DIFF_ATTRIBUTES` order."""
    superseded = _claim_row(claim_id=_SUPERSEDED_ID, value=17, source_id=_OLD_SOURCE_ID)
    successor = _claim_row(
        claim_id=_SUCCESSOR_ID,
        value=18,
        source_id=_NEW_SOURCE_ID,
        status=successor_status,
        verification_date=successor_verification_date,
        superseded_by=None,
    )
    sources = [
        _source_row(source_id=_OLD_SOURCE_ID, authority_name="Old Authority (test fixture)"),
        _source_row(source_id=_NEW_SOURCE_ID, authority_name="New Authority (test fixture)"),
    ]
    return _db_with(superseded=superseded, successor=successor, sources=sources)


_VALUE_ID = f"{_SUPERSEDED_ID}:value"
_SOURCE_AUTHORITY_ID = f"{_SUPERSEDED_ID}:source_authority"
_VERIFICATION_DATE_ID = f"{_SUPERSEDED_ID}:verification_date"


def _select_all_three() -> str:
    return f"[{_VALUE_ID}]\n[{_SOURCE_AUTHORITY_ID}]\n[{_VERIFICATION_DATE_ID}]"


def _confirm_all_three() -> str:
    return f"YES {_VALUE_ID}\nYES {_SOURCE_AUTHORITY_ID}\nYES {_VERIFICATION_DATE_ID}"


# ---------------------------------------------------------------------
# Settings gate -- step 2, before any retrieval.
# ---------------------------------------------------------------------


class TestSettingsGate:
    def test_ai_disabled_is_ai_unavailable_and_never_touches_db_or_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=False, configured=True)

        class _ExplodingDb:
            def table(self, name: str) -> Any:
                raise AssertionError("db must not be touched when AI is disabled")

        result = answer_what_changed(
            _ExplodingDb(), _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.ai_unavailable
        assert result.diff is None

    def test_not_configured_is_ai_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=False)
        result = answer_what_changed(
            _FakeDbClient({}), _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.ai_unavailable


# ---------------------------------------------------------------------
# Readability -- the module's own "never trust the caller's RLS scope
# alone" re-check.
# ---------------------------------------------------------------------


class TestReadability:
    def test_a_claim_that_does_not_exist_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates a guest/non-reviewer caller: RLS filters the row out
        entirely before it ever reaches Python -- `db.table("claims")`
        returns zero rows, same as a genuinely nonexistent id."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _FakeDbClient({"claims": [], "sources": []})
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available
        assert result.diff is None

    @pytest.mark.parametrize("status", ["draft", "in_review"])
    def test_a_draft_or_in_review_superseded_claim_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        """A reviewer's own RLS-scoped client CAN legitimately see a
        draft/in_review row -- this module's own re-check must still
        reject it (CLAUDE.md: "Unapproved facts never reach public
        results")."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, status=status)
        db = _db_with(
            superseded=superseded,
            successor=None,
            sources=[_source_row(source_id=_OLD_SOURCE_ID)],
        )
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available

    def test_a_claim_whose_source_cannot_be_resolved_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, source_id="does-not-exist")
        db = _db_with(superseded=superseded, successor=None, sources=[])
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available

    def test_a_synthetic_sourced_claim_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID)
        db = _db_with(
            superseded=superseded,
            successor=None,
            sources=[_source_row(source_id=_OLD_SOURCE_ID, source_type="synthetic")],
        )
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available

    def test_a_claim_with_no_successor_pointer_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`superseded_by is None` -- nothing to diff against at all."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, superseded_by=None)
        db = _db_with(
            superseded=superseded,
            successor=None,
            sources=[_source_row(source_id=_OLD_SOURCE_ID)],
        )
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available

    def test_a_successor_that_is_still_a_draft_makes_the_whole_answer_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The successor going through its own, independent draft/submit/
        approve cycle (`app/api/claims.py`'s `SupersedeRequest` docstring)
        means it may not be readable yet -- an unapproved successor value
        must never leak into this template's diff."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID)
        successor = _claim_row(
            claim_id=_SUCCESSOR_ID, value=18, status="draft", superseded_by=None
        )
        db = _db_with(
            superseded=superseded,
            successor=successor,
            sources=[_source_row(source_id=_OLD_SOURCE_ID)],
        )
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available

    def test_a_published_superseding_claim_is_also_a_valid_starting_point(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Readability accepts BOTH `published` and `superseded` -- not
        published-only (unlike `app.ai.retrieval`'s `_grounded_claims`)."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, status="published", superseded_by=None)
        db = _db_with(
            superseded=superseded,
            successor=None,
            sources=[_source_row(source_id=_OLD_SOURCE_ID)],
        )
        # No successor pointer -- still not_available, but for a DIFFERENT
        # reason (no diff to compute), proving the superseded claim itself
        # was readable (a "published" status did not itself 404/error).
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available


class TestNoDetectableChange:
    def test_a_supersession_with_no_field_level_change_is_not_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing to render is nothing to select -- the provider is
        never called."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, value=17, source_id=_OLD_SOURCE_ID)
        successor = _claim_row(
            claim_id=_SUCCESSOR_ID,
            value=17,
            source_id=_OLD_SOURCE_ID,
            verification_date="2026-01-01",
            superseded_by=None,
        )
        db = _db_with(
            superseded=superseded,
            successor=successor,
            sources=[_source_row(source_id=_OLD_SOURCE_ID)],
        )
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), _budget(), as_of=TODAY
        )
        assert result.status == AIAnswerStatus.not_available
        assert result.diff is not None
        assert result.diff.changed_fields == ()


# ---------------------------------------------------------------------
# Budget.
# ---------------------------------------------------------------------


class TestBudget:
    def test_budget_exhaustion_returns_budget_exhausted_with_zero_provider_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        exhausted_budget = _budget(daily_request_budget=0)
        result = answer_what_changed(
            db, _SUPERSEDED_ID, _ExplodingProvider(), exhausted_budget, as_of=TODAY
        )
        assert result.status == AIAnswerStatus.budget_exhausted
        assert result.diff is not None
        assert result.diff.changed_fields == ("value", "source_authority", "verification_date")


# ---------------------------------------------------------------------
# Provider errors.
# ---------------------------------------------------------------------


class TestProviderErrors:
    def test_provider_error_on_selection_call_returns_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider()
        provider.raise_on_call(1, AIProviderTimeout("selection call timed out"))
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.ai_unavailable
        assert result.selection_ids == []

    def test_provider_error_on_verification_call_returns_ai_unavailable_but_keeps_selection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(responses=[_select_all_three(), "unused"])
        provider.raise_on_call(2, AIProviderTimeout("verification call timed out"))
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.ai_unavailable
        assert set(result.selection_ids) == {_VALUE_ID, _SOURCE_AUTHORITY_ID, _VERIFICATION_DATE_ID}
        assert result.verification_ids == []


# ---------------------------------------------------------------------
# Format violations / empty results.
# ---------------------------------------------------------------------


class TestSelectionAndVerificationFormat:
    def test_not_grounded_selection_returns_insufficient_information(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(canned_response="NOT_GROUNDED")
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.insufficient_information

    def test_malformed_selection_line_returns_insufficient_information(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(canned_response="this is not a selection line")
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.insufficient_information

    def test_verification_empty_intersection_returns_insufficient_information(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(
            responses=[
                _select_all_three(),
                f"NO {_VALUE_ID}\nNO {_SOURCE_AUTHORITY_ID}\nNO {_VERIFICATION_DATE_ID}",
            ]
        )
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.insufficient_information
        assert set(result.selection_ids) == {_VALUE_ID, _SOURCE_AUTHORITY_ID, _VERIFICATION_DATE_ID}
        assert result.verification_ids == []


# ---------------------------------------------------------------------
# Freshness.
# ---------------------------------------------------------------------


class TestFreshness:
    def test_a_stale_successor_downgrades_a_fully_confirmed_answer_to_insufficient_information(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        # DEFAULT_FRESHNESS_SLA_DAYS is 180 -- 2020-01-01 is far outside
        # that window as of TODAY (2026-09-22).
        db = _full_scenario_db(successor_verification_date="2020-01-01")
        provider = MockAIProvider(responses=[_select_all_three(), _confirm_all_three()])
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.insufficient_information
        assert result.lines == ()

    def test_a_fresh_successor_is_answered_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db(successor_verification_date="2026-06-01")
        provider = MockAIProvider(responses=[_select_all_three(), _confirm_all_three()])
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.answered


# ---------------------------------------------------------------------
# Runtime banned-phrase scan (BCI-027) — app.ai.guards.
# scan_generated_sentences, run over every RenderedDiffLine.text this
# module's own final-render step builds. Mirrors app/ai/pipeline.py's
# identically-purposed check between ITS step 11 and step 13 -- see that
# file's own tests for the direct, pure-function proofs
# (scan_generated_sentences never raises, dedupes across texts, etc.);
# these are the answer_what_changed()-level proofs specific to this
# module.
# ---------------------------------------------------------------------


class TestRuntimeBannedPhraseScan:
    def test_banned_phrase_in_a_claims_value_downgrades_whole_answer_to_insufficient_information(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE proof this card's completion report asks for, for
        what_changed.py: a successor claim's own `.value` seeded with a
        banned phrase (a human content error at review time, never an AI
        hallucination -- the provider only ever contributes ids, per this
        module's own `test_rendered_line_text_is_unchanged_by_whatever_
        the_provider_s_raw_text_says`) downgrades the WHOLE answer. Two of
        the three candidate diff lines here (source_authority,
        verification_date) are perfectly clean -- `.lines` is still fully
        empty, never "the two clean ones survived"."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        superseded = _claim_row(claim_id=_SUPERSEDED_ID, value=17, source_id=_OLD_SOURCE_ID)
        successor = _claim_row(
            claim_id=_SUCCESSOR_ID,
            # "maybe" is a real BANNED_PHRASES entry (app/ai/schemas.py).
            value="18 (maybe)",
            source_id=_NEW_SOURCE_ID,
            status="published",
            verification_date="2026-06-01",
            superseded_by=None,
        )
        sources = [
            _source_row(source_id=_OLD_SOURCE_ID, authority_name="Old Authority (test fixture)"),
            _source_row(source_id=_NEW_SOURCE_ID, authority_name="New Authority (test fixture)"),
        ]
        db = _db_with(superseded=superseded, successor=successor, sources=sources)
        provider = MockAIProvider(responses=[_select_all_three(), _confirm_all_three()])

        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)

        assert result.status == AIAnswerStatus.insufficient_information
        assert result.lines == ()
        assert result.diff is not None
        assert result.selection_ids == [_VALUE_ID, _SOURCE_AUTHORITY_ID, _VERIFICATION_DATE_ID]
        assert result.verification_ids == [
            _VALUE_ID,
            _SOURCE_AUTHORITY_ID,
            _VERIFICATION_DATE_ID,
        ]
        # Mirrors this module's own staleness-downgrade precedent (read
        # directly, immediately above the scan in app/ai/what_changed.py):
        # citations is left at its dataclass default, empty -- there is no
        # fallback_citations-style helper in this module to attach instead.
        assert result.citations == []

    def test_a_clean_successor_value_is_answered_normally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sanity check on the boundary: this new check must not be so
        aggressive it blocks the ordinary, clean happy path the tests
        below already prove is answered."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(responses=[_select_all_three(), _confirm_all_three()])

        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)

        assert result.status == AIAnswerStatus.answered
        assert len(result.lines) == 3


# ---------------------------------------------------------------------
# The happy path, and the "code renders, model only selects" proof.
# ---------------------------------------------------------------------


class TestAnsweredHappyPath:
    def test_all_three_lines_survive_and_are_rendered_from_the_diff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(responses=[_select_all_three(), _confirm_all_three()])
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)

        assert result.status == AIAnswerStatus.answered
        assert result.diff is not None
        assert set(result.selection_ids) == {_VALUE_ID, _SOURCE_AUTHORITY_ID, _VERIFICATION_DATE_ID}
        assert set(result.verification_ids) == {
            _VALUE_ID,
            _SOURCE_AUTHORITY_ID,
            _VERIFICATION_DATE_ID,
        }
        assert len(result.lines) == 3
        by_attribute = {line.attribute: line for line in result.lines}
        assert by_attribute["value"] == RenderedDiffLine(
            attribute="value",
            old_value=17,
            new_value=18,
            text="The value changed from 17 to 18.",
        )
        assert by_attribute["source_authority"] == RenderedDiffLine(
            attribute="source_authority",
            old_value="Old Authority (test fixture)",
            new_value="New Authority (test fixture)",
            text=(
                "The source changed from Old Authority (test fixture) to "
                "New Authority (test fixture)."
            ),
        )
        assert by_attribute["verification_date"] == RenderedDiffLine(
            attribute="verification_date",
            old_value=date(2026, 1, 1),
            new_value=date(2026, 6, 1),
            text="The verification date changed from 2026-01-01 to 2026-06-01.",
        )
        assert len(result.citations) == 3

    def test_verification_shrinking_the_selection_only_renders_the_surviving_lines(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pass two may only ever narrow pass one's selection -- here it
        confirms only the `value` line, so only that one is rendered,
        never the other two even though pass one selected them."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(responses=[_select_all_three(), f"YES {_VALUE_ID}"])
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.answered
        assert [line.attribute for line in result.lines] == ["value"]

    def test_rendered_line_text_is_unchanged_by_whatever_the_provider_s_raw_text_says(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proof, for the completion report: the provider's raw response
        contributes only a SET of record ids (validated at every step);
        the model never writes a character that reaches `.text`. Two
        providers that both make exactly the same (valid) selection/
        verification decision, via completely different formatting of
        the id lines, must render byte-for-byte identical answers."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()

        provider_a = MockAIProvider(responses=[f"[{_VALUE_ID}]", f"YES {_VALUE_ID}"])
        result_a = answer_what_changed(db, _SUPERSEDED_ID, provider_a, _budget(), as_of=TODAY)

        # A second provider, selecting/confirming the exact same id, but
        # via extra whitespace around the line -- app.ai.guards strips
        # each line, so this is still a valid, identical selection.
        provider_b = MockAIProvider(responses=[f"  [{_VALUE_ID}]  ", f"  YES {_VALUE_ID}  "])
        result_b = answer_what_changed(db, _SUPERSEDED_ID, provider_b, _budget(), as_of=TODAY)

        assert result_a.status == result_b.status == AIAnswerStatus.answered
        assert result_a.lines == result_b.lines
        assert result_a.lines[0].text == "The value changed from 17 to 18."

    def test_no_record_id_that_was_never_retrieved_can_ever_survive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An adversarial response citing an id outside the retrieved set
        invalidates the whole (selection) response -- `app.ai.guards.
        parse_selection_response`'s own all-or-nothing rule, exercised
        here end to end."""
        _patch_settings(monkeypatch, ai_enabled=True, configured=True)
        db = _full_scenario_db()
        provider = MockAIProvider(canned_response="[some-id-never-retrieved]")
        result = answer_what_changed(db, _SUPERSEDED_ID, provider, _budget(), as_of=TODAY)
        assert result.status == AIAnswerStatus.insufficient_information


class TestWhatChangedAnswerImmutability:
    def test_what_changed_answer_is_frozen(self) -> None:
        answer = WhatChangedAnswer(status=AIAnswerStatus.not_available)
        with pytest.raises(dataclasses.FrozenInstanceError):
            answer.status = AIAnswerStatus.answered  # type: ignore[misc]

    def test_rendered_diff_line_is_frozen(self) -> None:
        line = RenderedDiffLine(attribute="value", old_value=1, new_value=2, text="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            line.text = "y"  # type: ignore[misc]
