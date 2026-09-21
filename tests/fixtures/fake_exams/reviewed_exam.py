"""A fake, fully-reviewed exam module for test_ruleset.py."""

from __future__ import annotations

from datetime import date

from app.rules.eligibility import minimum_age
from app.rules.ruleset import RuleSet

RULE_SETS = (
    RuleSet(
        exam_key="fake_reviewed_exam",
        cycle="2027",
        cycle_end=date(2027, 12, 31),
        jurisdiction="IN",
        rule_version="v1",
        criteria=(minimum_age(18),),
        reviewed_by="test-reviewer@example.org",
        reviewed_on=date(2026, 1, 1),
    ),
)
