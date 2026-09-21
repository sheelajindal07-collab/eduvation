# Static checks (DEPLOY-18 split; unchanged targets).

.PHONY: lint typecheck

lint:
	ruff check app tests

typecheck:
	mypy app
