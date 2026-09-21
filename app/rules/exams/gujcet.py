"""GUJCET (Gujarat Common Entrance Test) — exam module, task RULES-6.

Copies app/rules/exams/neet_ug.py's template exactly: no literal fact
values in this module's own source, every real-world (or, here,
synthetic) fact lives in this exam's own case-table JSON
(`tests/unit/rules/cases/gujcet.json`), read at import time.

This exam's draft (docs/content-drafts/gujcet-eligibility.md) is the
least-confirmed of the three this rules lane used — age, marks and
domicile are each explicitly "not found" there. Per this task's own
instruction, this module reads that draft for SHAPE only, never values:
an any-of two-merit-group subject split mirroring the draft's own
fact 1 framing (two named subject combinations sharing two subjects and
differing in a third), and a Gujarat (`GJ`) jurisdiction — GUJCET/ACPC
being a state-specific exam, distinct from NEET-UG's `IN`-wide one,
which is exactly the shape `app.rules.ruleset`'s jurisdiction guard
exists to keep separate. Every fact value in this exam's case-table JSON
is invented for engine-test purposes only; see that file's own
`"source_note"` for the actual subject names and thresholds used.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.rules.criteria_dates import minimum_age_on_date
from app.rules.criteria_extra import NotChecked, minimum_marks_by_category, subject_groups
from app.rules.eligibility import Criterion
from app.rules.ruleset import RuleSet

# app/rules/exams/gujcet.py -> parents[0]=exams, [1]=rules, [2]=app,
# [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASE_TABLE_PATH = _REPO_ROOT / "tests" / "unit" / "rules" / "cases" / "gujcet.json"


def _load_case_table(path: Path = _CASE_TABLE_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_criteria(facts: dict[str, Any]) -> tuple[Criterion, ...]:
    """One `Criterion` per fact this module knows how to turn into a
    check. A fact absent from `facts` simply builds no criterion for it."""
    criteria: list[Criterion] = []

    minimum_age = facts.get("minimum_age")
    minimum_age_cutoff = facts.get("minimum_age_cutoff")
    if minimum_age is not None and minimum_age_cutoff is not None:
        criteria.append(
            minimum_age_on_date(
                minimum_age,
                date.fromisoformat(minimum_age_cutoff),
                source_claim_id=facts.get("minimum_age_source_claim_id"),
            )
        )

    subject_group_lists = facts.get("required_subject_groups")
    if subject_group_lists:
        criteria.append(
            subject_groups(
                [frozenset(group) for group in subject_group_lists],
                source_claim_id=facts.get("required_subject_groups_source_claim_id"),
            )
        )

    marks_thresholds = facts.get("minimum_marks_by_category")
    if marks_thresholds:
        criteria.append(
            minimum_marks_by_category(
                marks_thresholds,
                source_claim_id=facts.get("minimum_marks_by_category_source_claim_id"),
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


EXAM_KEY = "gujcet"
RULE_SETS: tuple[RuleSet, ...] = (build_rule_set(_load_case_table()),)
