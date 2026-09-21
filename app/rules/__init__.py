"""Deterministic decision engines: eligibility, cost, timeline, reservation.

No model tokens. M2 ("deterministic intelligence", Lite Build Pack §9),
with test cases per exam from the content track. See docs/DATA.md for the
three-outcome eligibility model and the three-amount cost model this
module implements.

- `eligibility.py`: built. Composable, source-cited criteria; an unknown
  input is `insufficient_information`, never `does_not_meet`.
- `criteria_dates.py`: built (RULES-2). Reference-date age criteria
  (`minimum_age_on_date`, `maximum_age_on_date`, `born_between`) — a real
  DOB cutoff, not today's naive integer-age subtraction.
- `criteria_extra.py`: built (RULES-3). Any-of subject groups,
  per-category marks thresholds, year-of-passing/appearing, minimum
  qualification level, and `NotChecked` declarations for conditions a
  rule set deliberately never evaluates.
- `ruleset.py`: built (RULES-4). `RuleSet` names one exam's criteria for
  one cycle and jurisdiction; `evaluate_ruleset` adds the honesty checks
  `evaluate_eligibility` alone can't (no registered rules, a stale
  cycle); `discover_rule_sets` is the auto-discovering registry over
  `app/rules/exams/*.py`, with a cycle/jurisdiction guard that never
  silently serves the wrong year's or state's rule.
- `exams/`: per-exam `RuleSet` modules (RULES-5 NEET-UG, RULES-6 JEE
  Main/GUJCET, ...) — see `app/rules/exams/__init__.py` for the
  convention.
- `cost.py`: built. Four amounts that never merge — verified charges
  (summed from fee-component claims, `None` if any is missing, never a
  silently-partial sum), estimated extras, confirmed assistance (the
  only thing that reduces what a student owes), and potential
  assistance (informational only — never subtracted).
- Timeline and reservation engines: not yet built.
"""
