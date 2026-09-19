# BCION Lite — verified commands (docs/ARCHITECTURE.md, CLAUDE.md)
# Substitutions per Annex F.3: pnpm scripts -> make targets.

.PHONY: dev lint typecheck test-unit test-e2e test-db build install

install:
	pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check app tests

typecheck:
	mypy app

test-unit:
	pytest tests/unit -v

test-e2e:
	@echo "Playwright e2e not wired yet (no UI to drive before M1's vertical slice). See STATUS.md."

test-db:
	pytest tests/db -v

build:
	@echo "Docker build not wired yet — no Dockerfile until hosting is provisioned (docs/DECISIONS.md)."
