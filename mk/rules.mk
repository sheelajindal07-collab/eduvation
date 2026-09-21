# "Critical rule cases" gate — task RULES-11.
#
# This file is NOT included by the root Makefile yet — that's a separate
# lane's job (owner of Makefile-wiring; see docs/DEVELOPMENT-PLAN.md's
# never-parallel-edits rule for the root Makefile, which this task's own
# card forbids editing directly). Once wired in with a root-Makefile line
# such as:
#
#     include mk/*.mk
#
# `make test-rules` becomes available alongside the existing
# `test-unit`/`test-e2e`/`test-db` targets. Until then, run either line
# below directly.

.PHONY: test-rules

test-rules:
	pytest tests/unit/rules -q
	python -m tests.unit.rules.report
