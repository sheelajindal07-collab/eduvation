"""NEET (UG) — reference exam module, task RULES-5.

The template every later exam module (RULES-6/7/...) copies. This
module's own source contains no literal fact values: no hardcoded age,
cutoff date, subject name or threshold. Every real-world fact this rule
set checks lives in this exam's own case-table JSON
(`tests/unit/rules/cases/neet_ug.json`), under its `"facts"` key, next to
a `"source_note"` recording where each fact came from and how confident
it is — see `app/rules/exams/__init__.py` for the convention, and
docs/content-drafts/neet-ug-eligibility.md for the underlying (draft,
unverified) research this exam's facts were drawn from.

An absent fact means its criterion is simply not built for this rule
set — never a guessed criterion and never a crash — matching the
draft's own recommendation to publish no claim at all for a figure it
could not confirm (`_build_criteria` below).

The JSON file's header also carries this rule set's identity (cycle,
cycle_end, jurisdiction, rule_version) and review metadata (reviewed_by,
reviewed_on) — see docs/CONTRACTS.md "Rule approval lives in git JSON":
approving this rule set is a reviewed pull request against that file,
never a runtime edit.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.rules.criteria_dates import minimum_age_on_date
from app.rules.criteria_extra import NotChecked, subject_groups
from app.rules.eligibility import Criterion
from app.rules.ruleset import RuleSet

# app/rules/exams/neet_ug.py -> parents[0]=exams, [1]=rules, [2]=app,
# [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASE_TABLE_PATH = _REPO_ROOT / "tests" / "unit" / "rules" / "cases" / "neet_ug.json"


def _load_case_table(path: Path = _CASE_TABLE_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_criteria(facts: dict[str, Any]) -> tuple[Criterion, ...]:
    """One `Criterion` per fact this module knows how to turn into a
    check. A fact absent from `facts` simply builds no criterion for it —
    never a guess, never a crash on a missing key."""
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

    return tuple(criteria)


def build_rule_set(header: dict[str, Any]) -> RuleSet:
    """Turn one case-table JSON header (already parsed) into a `RuleSet`.
    A separate function from module-load time so a future caller with
    real published claims (RULES-8) can build this exam's `RuleSet` from
    a differently-sourced header without needing this module's own
    on-disk case table at all."""
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


EXAM_KEY = "neet_ug"
RULE_SETS: tuple[RuleSet, ...] = (build_rule_set(_load_case_table()),)
