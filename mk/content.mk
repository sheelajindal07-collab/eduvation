# Content-track make targets (CONTENT-6 session 1).
#
# This file is included by the root Makefile via `include mk/*.mk`
# (that wiring belongs to a different lane -- this file does not touch
# the root Makefile itself). Until that include line lands, run these
# targets directly: `make -f mk/content.mk content-check`.
#
# `content-check` never touches the database and makes no network call
# -- it only runs the ordinary-code checks in
# scripts/content/check_sources.py (CONTENT-4) and
# scripts/content/validation.py (CONTENT-6) over whatever CSVs exist
# under content/ today. On the current, still-template content/ files
# it validates zero real rows and exits 0 -- it is not a claim that any
# content has been reviewed.

.PHONY: content-check content-coverage-report

content-check:
	python -m scripts.content.check_sources
	python -m scripts.content.validation

# `content-coverage-report` (CONTENT-8): a READ-ONLY report over the LIVE
# `claims` table -- counts/freshness/pending-review-age plus a
# publication-integrity check that exits non-zero on a real violation
# (synthetic-sourced publish, a bad source URL, no named verifier,
# maker == checker, an incomplete eligibility set). Unlike
# `content-check` above, this needs a real database and a real signed-in
# reviewer account -- never the service-role key (see
# scripts/content/coverage_report.py's own module docstring for why):
# set SUPABASE_URL/SUPABASE_PUBLISHABLE_KEY (as `make test-db-env`
# already writes to .env.test) plus BCION_REVIEWER_EMAIL/
# BCION_REVIEWER_PASSWORD for a real reviewer account before running
# this. FORMAT selects markdown/csv/both (default: markdown).
content-coverage-report:
	python -m scripts.content.coverage_report --format $(or $(FORMAT),markdown)
