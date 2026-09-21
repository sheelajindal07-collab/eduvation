# DEPLOY-5 — read-only smoke check against a running deployment.
# Usage: make smoke URL=http://localhost:8000 [ENV=development]

.PHONY: smoke

smoke:
	python scripts/smoke.py $(URL) $(if $(ENV),--expected-env $(ENV),)
