# SEC-7 — dependency audit and secret scan. Mirrors the two extra CI jobs
# in .github/workflows/ci.yml so a developer can run the same checks
# locally before pushing.

.PHONY: audit secret-scan

audit:
	pip install --quiet pip-audit
	pip-audit -r requirements-dev.lock

# Requires the gitleaks binary (https://github.com/gitleaks/gitleaks) on
# PATH -- CI runs the equivalent via gitleaks/gitleaks-action instead of
# this target.
secret-scan:
	gitleaks detect --source . --no-git -v
