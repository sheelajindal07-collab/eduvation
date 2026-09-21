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

.PHONY: content-check

content-check:
	python -m scripts.content.check_sources
	python -m scripts.content.validation
