"""Per-exam RuleSet modules — Lite Build Pack §6, tasks RULES-5/6/7/....

`app/rules/ruleset.py::discover_rule_sets` finds every module here via
`pkgutil` and collects whatever each one exposes as a module-level
`RULE_SETS: tuple[app.rules.ruleset.RuleSet, ...]`. The convention every
module in this package follows (set by RULES-5's `neet_ug.py`, the
template every later exam copies):

- No literal fact values in the module's own source (no hardcoded ages,
  dates, subject names, marks thresholds, ...). Every real-world fact
  lives in that exam's own case-table JSON
  (`tests/unit/rules/cases/<exam_key>.json`) under a `"facts"` key, next
  to the `"source_note"` that says where each fact came from (a
  `docs/content-drafts/*.md` research draft) and whether it is a
  genuinely sourced figure or synthetic/invented purely to exercise the
  engine. The module reads that JSON at import time and turns `"facts"`
  into `Criterion`s, omitting (never guessing) a criterion whose fact is
  absent.
- The same JSON file's header also carries the rule set's identity
  (`exam_key`, `cycle`, `cycle_end`, `jurisdiction`, `rule_version`) and
  review metadata (`reviewed_by`, `reviewed_on`) — see
  docs/CONTRACTS.md "Rule approval lives in git JSON": a rule set's
  approval is a reviewed pull request against this file, never a runtime
  database edit.
- `tests/unit/rules/test_exam_cases.py`'s loader test runs every
  `cases/*.json` file's own case table against the matching module's
  `RULE_SETS` automatically — a new exam module needs no change to that
  test file, only its own module plus its own case-table JSON.

A module here is excluded from a production-mode registry listing
(`discover_rule_sets(app_env="production")`) until its case table's
`reviewed_by`/`reviewed_on` are both set by a human reviewer (RULES-12) —
see `app.rules.ruleset.RuleSet.is_reviewed`.
"""
