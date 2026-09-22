"""Unit tests for `app/ai/actions.py` (AI-18, `tasks/BCI-021.md`).

Pure, no database, no provider, no pipeline — `next_step_actions_from_citations`
takes plain `app.ai.guards.citation_for_record`-shaped dicts (never a real
`RetrievedRecord`/`Answer`, so this module stays independent of every
forbidden-to-edit AI file, see `TestActionTextIsCodeOnly` below) and this
file constructs its own fixtures by hand.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from typing import Any

import pytest

from app.ai import actions
from app.ai.actions import (
    ACTION_TEMPLATE_RULES,
    NextStepAction,
    next_step_actions_from_citations,
)


def _citation(
    *,
    field: str,
    value: Any,
    record_id: str = "claim-1",
    source_authority: str | None = "Central Board (SYNTHETIC test fixture)",
    source_url: str | None = "https://example.invalid/source",
    is_stale: bool = False,
) -> dict[str, Any]:
    """`app.ai.guards.citation_for_record`'s exact output shape, built by
    hand — this file never imports that (forbidden-to-edit) module."""
    return {
        "record_id": record_id,
        "field": field,
        "value": value,
        "source_authority": source_authority,
        "source_url": source_url,
        "is_stale": is_stale,
    }


class TestCatalogueShape:
    def test_exactly_the_two_fields_this_card_documents(self) -> None:
        """Locks the catalogue's field vocabulary down -- a silent
        addition/removal here changes what a verified fact can become an
        action, which must be a deliberate, reviewed change."""
        assert [rule.claim_field for rule in ACTION_TEMPLATE_RULES] == [
            "application_window",
            "documents_required",
        ]


class TestDeadlineShapedField:
    def test_produces_a_register_before_action_citing_the_claim(self) -> None:
        citation = _citation(
            field="application_window",
            value="1 March 2027 to 30 April 2027",
            record_id="claim-deadline-1",
            source_authority="CBSE (test fixture)",
            source_url="https://example.invalid/cbse",
            is_stale=False,
        )
        result = next_step_actions_from_citations([citation])
        assert result == (
            NextStepAction(
                text="Register before 1 March 2027 to 30 April 2027.",
                claim_id="claim-deadline-1",
                source_authority="CBSE (test fixture)",
                source_url="https://example.invalid/cbse",
                is_stale=False,
            ),
        )

    def test_a_blank_value_produces_no_action(self) -> None:
        for blank in ("", "   ", None):
            citation = _citation(field="application_window", value=blank)
            assert next_step_actions_from_citations([citation]) == ()

    def test_a_non_scalar_value_produces_no_action(self) -> None:
        """A list/dict value for a deadline-shaped field is a shape this
        module refuses to invent formatting for -- never guessed at."""
        for odd_value in ([1, 2, 3], {"start": "1 March"}):
            citation = _citation(field="application_window", value=odd_value)
            assert next_step_actions_from_citations([citation]) == ()

    def test_a_numeric_value_is_rendered_as_its_own_string(self) -> None:
        citation = _citation(field="application_window", value=2027)
        result = next_step_actions_from_citations([citation])
        assert result[0].text == "Register before 2027."


class TestDocumentNamingField:
    def test_a_comma_separated_string_produces_one_collect_action_per_document(
        self,
    ) -> None:
        citation = _citation(
            field="documents_required",
            value="Class 10 marksheet, Passport-size photo",
            record_id="claim-docs-1",
        )
        result = next_step_actions_from_citations([citation])
        assert [action.text for action in result] == [
            "Collect Class 10 marksheet.",
            "Collect Passport-size photo.",
        ]
        assert all(action.claim_id == "claim-docs-1" for action in result)

    def test_a_list_value_is_also_accepted(self) -> None:
        citation = _citation(
            field="documents_required",
            value=["Class 10 marksheet", "Passport-size photo"],
            record_id="claim-docs-2",
        )
        result = next_step_actions_from_citations([citation])
        assert [action.text for action in result] == [
            "Collect Class 10 marksheet.",
            "Collect Passport-size photo.",
        ]

    def test_duplicate_documents_in_one_claim_are_not_repeated(self) -> None:
        citation = _citation(
            field="documents_required",
            value=["Class 10 marksheet", "Class 10 marksheet", "Passport-size photo"],
        )
        result = next_step_actions_from_citations([citation])
        assert [action.text for action in result] == [
            "Collect Class 10 marksheet.",
            "Collect Passport-size photo.",
        ]

    def test_blank_entries_are_dropped_but_real_ones_survive(self) -> None:
        citation = _citation(field="documents_required", value=["", "  ", "Passport-size photo"])
        result = next_step_actions_from_citations([citation])
        assert [action.text for action in result] == ["Collect Passport-size photo."]

    def test_an_empty_value_produces_no_action(self) -> None:
        for empty in ("", [], None, {"not": "a list"}):
            citation = _citation(field="documents_required", value=empty)
            assert next_step_actions_from_citations([citation]) == ()


class TestFieldsOutsideTheCatalogue:
    def test_a_field_with_no_rule_produces_no_action(self) -> None:
        """`location` is a real, published, verified field elsewhere in
        this codebase (app/api/compare.py's COMPARISON_FIELDS) -- being
        real and verified is not enough to make it an action; only
        catalogue membership is (module docstring)."""
        citation = _citation(field="location", value="New Delhi")
        assert next_step_actions_from_citations([citation]) == ()

    def test_a_citation_missing_record_id_is_skipped(self) -> None:
        citation = _citation(field="application_window", value="15 June 2027")
        del citation["record_id"]
        assert next_step_actions_from_citations([citation]) == ()


class TestOrderIsPreserved:
    def test_actions_follow_citation_order_never_reordered_or_interleaved(self) -> None:
        """`citations` arrives in the two-pass pipeline's own
        selection-then-verification-confirmed order (app/ai/pipeline.py
        step 11) -- this function must not re-sort it."""
        citations = [
            _citation(field="documents_required", value=["B doc"], record_id="claim-b"),
            _citation(field="location", value="Pune", record_id="claim-loc"),
            _citation(field="application_window", value="1 May 2027", record_id="claim-a"),
        ]
        result = next_step_actions_from_citations(citations)
        assert [action.claim_id for action in result] == ["claim-b", "claim-a"]
        assert [action.text for action in result] == [
            "Collect B doc.",
            "Register before 1 May 2027.",
        ]


class TestActionTextIsCodeOnly:
    """Proof, for the completion report: no action text exists that was
    not built from a specific claim's own fields — see
    `next_step_actions_from_citations`'s docstring."""

    def test_action_text_is_a_pure_function_of_the_citation_s_own_value(self) -> None:
        """Byte-for-byte: the returned text is exactly the fixed template
        string with the citation's OWN `value` substituted in, nothing
        else from the citation (not `source_authority`, not `record_id`)
        ever appears inside `.text`."""
        citation = _citation(
            field="application_window",
            value="SOME DISTINCTIVE VALUE 12345",
            source_authority="A SOURCE NAME THAT MUST NEVER APPEAR IN ACTION TEXT",
        )
        result = next_step_actions_from_citations([citation])
        assert result[0].text == "Register before SOME DISTINCTIVE VALUE 12345."
        assert "SOURCE NAME" not in result[0].text

    def test_module_never_imports_an_ai_provider_pipeline_or_guards_module(self) -> None:
        """AST-inspection import guard, mirroring
        `tests/unit/test_ai_retrieval.py`'s own `TestImportGuard` —
        structural proof that no model/provider output could ever reach
        `.text`, not merely a discipline this module happens to follow."""
        forbidden_substrings = (
            "adapter",
            "gemini_provider",
            "mock_provider",
            "pipeline",
            "guards",
            "retrieval",
        )
        source = inspect.getsource(actions)
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
                    imported_names.add(f"{module}.{alias.name}")

        lowered = {name.lower() for name in imported_names}
        offending = {
            name
            for name in lowered
            for forbidden in forbidden_substrings
            if forbidden in name
        }
        assert not offending, f"app/ai/actions.py imports a forbidden name: {sorted(offending)}"

    def test_next_step_action_is_frozen(self) -> None:
        """A caller (`app/api/ask.py`) must not be able to mutate an
        already-built action in place."""
        action = NextStepAction(
            text="Register before 1 May 2027.",
            claim_id="claim-a",
            source_authority=None,
            source_url=None,
            is_stale=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            action.text = "something else"  # type: ignore[misc]
