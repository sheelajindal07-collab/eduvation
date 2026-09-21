# Test suites (DEPLOY-18 split; unchanged targets).

.PHONY: test-unit test-e2e test-db

test-unit:
	pytest tests/unit -v

test-e2e:
	pytest tests/e2e -v

test-db:
	pytest tests/db -v
