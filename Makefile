# BCION Lite — verified commands (docs/ARCHITECTURE.md, CLAUDE.md)
# Substitutions per Lite Build Pack §10: pnpm scripts -> make targets.

.PHONY: dev css lint typecheck test-unit test-e2e test-db build install

install:
	pip install -e ".[dev]"
	npm install

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

css:
	npx tailwindcss -i ./app/web/styles/input.css -o ./app/static/css/app.css --minify

lint:
	ruff check app tests

typecheck:
	mypy app

test-unit:
	pytest tests/unit -v

test-e2e:
	@echo "UI exists now (app/web/, tasks/BCI-006.md) but Playwright itself isn't wired yet -- tests/db/test_web_pages.py covers the explore/compare journey via FastAPI's TestClient in the meantime. See STATUS.md."

test-db:
	pytest tests/db -v

build:
	@echo "Docker build not wired yet — no Dockerfile until hosting is provisioned (docs/DECISIONS.md)."
