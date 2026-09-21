"""A fake, NOT-yet-reviewed exam module for test_ruleset.py -- both
`reviewed_by` and `reviewed_on` are left unset, same as a real exam
module ships before RULES-12's human review fills them in."""

from __future__ import annotations

from datetime import date

from app.rules.eligibility import minimum_age
from app.rules.ruleset import RuleSet

RULE_SETS = (
    RuleSet(
        exam_key="fake_unreviewed_exam",
        cycle="2027",
        cycle_end=date(2027, 12, 31),
        jurisdiction="IN",
        rule_version="v1",
        criteria=(minimum_age(18),),
    ),
)
