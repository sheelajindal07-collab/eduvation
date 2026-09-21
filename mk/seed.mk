# Synthetic sample-data seeding (DATA-8, scripts/seed_synthetic.py).
#
# Dev/staging only — the script's own two-factor guard (APP_ENV, and the
# project ref in SUPABASE_URL against BCION_PRODUCTION_PROJECT_REF)
# refuses a production target regardless of what these targets are asked
# to do. Never run against a real project without the owner's own
# SUPABASE_SERVICE_ROLE_KEY loaded in their own terminal — see
# scripts/seed_synthetic.py's own docstring.

.PHONY: seed seed-purge seed-demo

## seed — insert labelled synthetic sample content (dev/staging only).
seed:
	python scripts/seed_synthetic.py

## seed-purge — remove every row this script has ever seeded.
seed-purge:
	python scripts/seed_synthetic.py --purge

## seed-demo — seed, then also turn demo_mode on (db/migrations/0007_demo_mode.sql).
seed-demo:
	python scripts/seed_synthetic.py --enable-demo-mode
