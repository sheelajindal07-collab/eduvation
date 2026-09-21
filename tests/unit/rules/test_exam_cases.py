"""Shared, parametrised loader for every exam module's case table
(RULES-5/6/...).

Auto-discovers every `tests/unit/rules/cases/*.json` file and runs its
`"cases"` list against the matching `app.rules.exams.<exam_key>`
module's `RULE_SETS` — a new exam module needs no change to this file,
only its own module plus its own case-table JSON (see
`app/rules/exams/__init__.py` for the convention this loader assumes).

Also holds the "no literal fact values in the module" check named in
RULES-5's acceptance criteria: each exam module's own source is grepped
for the specific fact tokens (ages, subject names, dates) that belong
only in that exam's case-table JSON, never hardcoded in the .py file.
"""

from __future__ import annotations

import importlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.rules.eligibility import EligibilityInput
from app.rules.ruleset import RuleSet, evaluate_ruleset

CASES_DIR = Path(__file__).resolve().parent / "cases"

# Per exam_key, the literal fact tokens that must appear only in that
# exam's case-table JSON, never hardcoded in its app/rules/exams/*.py
# module. Whole-word/whole-token matches only, so this can't false
# -positive on an unrelated substring elsewhere in the file (a line
# number, an unrelated word that happens to contain the letters).
_FORBIDDEN_LITERAL_FACT_TOKENS: dict[str, tuple[str, ...]] = {
    "neet_ug": ("17", "Biology", "Biotechnology", "Physics", "Chemistry"),
}


def _load_case_files() -> list[Path]:
    return sorted(CASES_DIR.glob("*.json"))


def _load_header(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _rule_set_for(header: dict[str, Any]) -> RuleSet:
    module = importlib.import_module(f"app.rules.exams.{header['exam_key']}")
    matching = [
        rs
        for rs in module.RULE_SETS
        if rs.cycle == header["cycle"] and rs.jurisdiction == header["jurisdiction"]
    ]
    assert len(matching) == 1, (
        f"Expected exactly one RuleSet for exam_key={header['exam_key']!r} "
        f"cycle={header['cycle']!r} jurisdiction={header['jurisdiction']!r} in "
        f"{module.__name__}.RULE_SETS, found {len(matching)}."
    )
    return matching[0]


def _build_eligibility_input(data: dict[str, Any]) -> EligibilityInput:
    kwargs = dict(data)
    if kwargs.get("date_of_birth") is not None:
        kwargs["date_of_birth"] = date.fromisoformat(kwargs["date_of_birth"])
    if "subjects_studied" in kwargs:
        kwargs["subjects_studied"] = frozenset(kwargs["subjects_studied"])
    if kwargs.get("as_of") is not None:
        kwargs["as_of"] = date.fromisoformat(kwargs["as_of"])
    return EligibilityInput(**kwargs)


def _case_params() -> list[Any]:
    params = []
    for case_file in _load_case_files():
        header = _load_header(case_file)
        rule_set = _rule_set_for(header)
        for case in header["cases"]:
            params.append(
                pytest.param(
                    rule_set,
                    case,
                    id=f"{header['exam_key']}::{case['name']}",
                )
            )
    return params


def test_at_least_one_case_file_exists() -> None:
    assert _load_case_files(), "No case files found under tests/unit/rules/cases/."


def test_every_exam_has_at_least_twelve_cases() -> None:
    for case_file in _load_case_files():
        header = _load_header(case_file)
        assert len(header["cases"]) >= 12, (
            f"{case_file.name} has only {len(header['cases'])} cases; "
            "RULES-5/6's acceptance requires at least 12 per exam."
        )


def test_exam_modules_contain_no_literal_fact_values() -> None:
    for exam_key, forbidden_tokens in _FORBIDDEN_LITERAL_FACT_TOKENS.items():
        module = importlib.import_module(f"app.rules.exams.{exam_key}")
        assert module.__file__ is not None
        source = Path(module.__file__).read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert not re.search(rf"\b{re.escape(token)}\b", source), (
                f"app/rules/exams/{exam_key}.py contains the literal fact "
                f"value {token!r} -- facts must live only in that exam's "
                "case-table JSON, never hardcoded in the module."
            )


@pytest.mark.parametrize("rule_set,case", _case_params())
def test_case_matches_expected_outcome(rule_set: RuleSet, case: dict[str, Any]) -> None:
    input_obj = _build_eligibility_input(case["input"])
    as_of = date.fromisoformat(case["as_of"]) if case.get("as_of") else date.today()
    result = evaluate_ruleset(rule_set, input_obj, as_of=as_of)
    assert result.outcome.value == case["expected_outcome"], (
        f"{case['name']}: expected {case['expected_outcome']!r}, got "
        f"{result.outcome.value!r}. Reason: {case.get('reason', '')}"
    )
