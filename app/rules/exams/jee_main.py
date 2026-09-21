"""JEE (Main) — exam module, task RULES-6.

Copies app/rules/exams/neet_ug.py's template exactly: no literal fact
values in this module's own source, every real-world (or, here,
synthetic) fact lives in this exam's own case-table JSON
(`tests/unit/rules/cases/jee_main.json`), read at import time.

Unlike NEET-UG's reference module, this one reads
docs/content-drafts/jee-main-eligibility.md for SHAPE only, never
values (this task's own instruction) — that draft is explicitly
lower-confidence than the NEET-UG one, so nothing in its case-table JSON
should be read as an attempt at a real, sourced fact. See that JSON
file's own `"source_note"` for exactly which figures are invented and
why.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.rules.criteria_extra import NotChecked, passed_or_appearing_in_years
from app.rules.eligibility import Criterion
from app.rules.ruleset import RuleSet

# app/rules/exams/jee_main.py -> parents[0]=exams, [1]=rules, [2]=app,
# [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASE_TABLE_PATH = _REPO_ROOT / "tests" / "unit" / "rules" / "cases" / "jee_main.json"


def _load_case_table(path: Path = _CASE_TABLE_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_criteria(facts: dict[str, Any]) -> tuple[Criterion, ...]:
    """One `Criterion` per fact this module knows how to turn into a
    check. A fact absent from `facts` simply builds no criterion for it."""
    criteria: list[Criterion] = []

    eligible_years = facts.get("eligible_passing_years")
    if eligible_years:
        criteria.append(
            passed_or_appearing_in_years(
                frozenset(eligible_years),
                allow_appearing=facts.get("allow_appearing", True),
                source_claim_id=facts.get("passed_or_appearing_source_claim_id"),
            )
        )

    return tuple(criteria)


def build_rule_set(header: dict[str, Any]) -> RuleSet:
    """Turn one case-table JSON header (already parsed) into a `RuleSet`."""
    reviewed_on = header.get("reviewed_on")
    return RuleSet(
        exam_key=header["exam_key"],
        cycle=header["cycle"],
        cycle_end=date.fromisoformat(header["cycle_end"]),
        jurisdiction=header["jurisdiction"],
        rule_version=header["rule_version"],
        criteria=build_criteria(header.get("facts", {})),
        reviewed_by=header.get("reviewed_by"),
        reviewed_on=date.fromisoformat(reviewed_on) if reviewed_on else None,
        not_checked=tuple(
            NotChecked(name=n["name"], note=n["note"]) for n in header.get("not_checked", ())
        ),
    )


EXAM_KEY = "jee_main"
RULE_SETS: tuple[RuleSet, ...] = (build_rule_set(_load_case_table()),)
