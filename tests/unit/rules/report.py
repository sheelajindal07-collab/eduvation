"""The "critical rule cases" gate — task RULES-11.

Runs every registered exam's own case table (the same tables
`test_exam_cases.py` exercises via pytest) and prints a per-exam summary
table: exam, cycle, rule_version, cases passed, reviewed_by, reviewed_on.
Exits non-zero — the CI-gate behaviour this script exists for — when:

1. Any case in any exam's case table doesn't match its expected outcome.
   This is the primary purpose: a content or engine change that silently
   breaks a previously-correct case must fail CI, not just a local test
   run someone forgot to check.
2. An exam's review metadata is only half set (`reviewed_by` given
   without `reviewed_on`, or vice versa). `app.rules.ruleset
   .RuleSet.is_reviewed` requires both together for a reason — a rule
   set that looks reviewed by one field but not the other is a data
   -entry mistake in the case-table JSON header, not a legitimate state,
   and should never ship silently.
3. An exam that IS fully reviewed (`reviewed_by` and `reviewed_on` both
   set — i.e. eligible to be shown in a production-mode registry
   listing, see `app.rules.ruleset.discover_rule_sets`) has zero cases in
   its table or zero criteria in its built `RuleSet`. A rule set that is
   both reviewed AND exposed to real students absolutely must have real
   test coverage behind it; "reviewed but untested" is exactly the
   dangerous combination this gate exists to catch before it reaches a
   student. (Every exam module as of RULES-11 ships with `reviewed_by`/
   `reviewed_on` unset — RULES-12's human review is a separate, later
   task — so this condition cannot fire yet; it is here so the very
   first review that DOES land is already covered by the gate, not added
   as an afterthought once something reviewed ships broken.)

Approval lives in each case-table JSON header (`reviewed_by`,
`reviewed_on`), changed only by a reviewed pull request against that
file — see docs/CONTRACTS.md "Rule approval lives in git JSON". This
script never writes to a database and never mutates a case-table file.

Run via `make test-rules` (see `mk/rules.mk`) or directly:
    python -m tests.unit.rules.report
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Any

from app.rules.ruleset import RuleSet, evaluate_ruleset
from tests.unit.rules.test_exam_cases import (
    _build_eligibility_input,
    _load_case_files,
    _load_header,
    _rule_set_for,
)


def _run_exam_cases(
    rule_set: RuleSet, cases: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    """Returns (number passed, names of failing cases)."""
    passed = 0
    failures: list[str] = []
    for case in cases:
        input_obj = _build_eligibility_input(case["input"])
        as_of = date.fromisoformat(case["as_of"]) if case.get("as_of") else date.today()
        result = evaluate_ruleset(rule_set, input_obj, as_of=as_of)
        if result.outcome.value == case["expected_outcome"]:
            passed += 1
        else:
            failures.append(
                f"{case['name']}: expected {case['expected_outcome']!r}, "
                f"got {result.outcome.value!r}"
            )
    return passed, failures


def _format_table(rows: list[dict[str, str]]) -> str:
    columns = ["exam_key", "cycle", "rule_version", "cases_passed", "reviewed_by", "reviewed_on"]
    widths = {c: max(len(c), *(len(row[c]) for row in rows)) for c in columns} if rows else {
        c: len(c) for c in columns
    }
    header_line = "  ".join(c.ljust(widths[c]) for c in columns)
    separator = "  ".join("-" * widths[c] for c in columns)
    lines = [header_line, separator]
    for row in rows:
        lines.append("  ".join(row[c].ljust(widths[c]) for c in columns))
    return "\n".join(lines)


def main() -> int:
    case_files = _load_case_files()
    if not case_files:
        print("No case files found under tests/unit/rules/cases/ -- nothing to report.")
        return 1

    exit_code = 0
    rows: list[dict[str, str]] = []
    problems: list[str] = []

    for case_file in case_files:
        header = _load_header(case_file)
        rule_set = _rule_set_for(header)
        exam_key = header["exam_key"]
        cases = header["cases"]

        passed, failures = _run_exam_cases(rule_set, cases)
        if failures:
            exit_code = 1
            problems.append(f"[{exam_key}] {len(failures)} failing case(s):")
            problems.extend(f"    - {f}" for f in failures)

        reviewed_by = header.get("reviewed_by")
        reviewed_on = header.get("reviewed_on")
        partially_reviewed = (reviewed_by is None) != (reviewed_on is None)
        if partially_reviewed:
            exit_code = 1
            problems.append(
                f"[{exam_key}] review metadata is only half set "
                f"(reviewed_by={reviewed_by!r}, reviewed_on={reviewed_on!r}) -- "
                "both must be set together, or neither."
            )

        is_reviewed = reviewed_by is not None and reviewed_on is not None
        if is_reviewed and (len(cases) == 0 or len(rule_set.criteria) == 0):
            exit_code = 1
            problems.append(
                f"[{exam_key}] is fully reviewed (registered-public) but has "
                f"{len(cases)} case(s) and {len(rule_set.criteria)} criterion/criteria -- "
                "a reviewed, public exam must have real test coverage."
            )

        rows.append(
            {
                "exam_key": exam_key,
                "cycle": header["cycle"],
                "rule_version": header["rule_version"],
                "cases_passed": f"{passed}/{len(cases)}",
                "reviewed_by": reviewed_by or "-",
                "reviewed_on": reviewed_on or "-",
            }
        )

    print(_format_table(rows))
    if problems:
        print()
        print("FAILED:")
        for line in problems:
            print(line)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
