# OPS-2 — structured logging / request-id middleware.
#
# uvicorn MUST always be launched with --no-access-log. Its own default
# access log writes a line straight to its own stream for every request
# (method, full path AND query string) that never passes through
# Python's `logging` handler/filter chain the way this app's own
# loggers do -- it bypasses app/core/logging.py's RedactionFilter
# entirely, and duplicates the one PII-free line
# RequestIdLoggingMiddleware already emits for the same request. See
# app/core/logging.py's module docstring for the full explanation.
#
# `logging-check` is a local, informational guard only (not wired into
# CI or any other target by this task): it lists any uvicorn invocation
# under mk/*.mk that doesn't carry the flag, so the gap is visible
# rather than silent. It never fails the build.
#
# Known gap today: mk/dev.mk's own `dev:` target (`uvicorn app.main:app
# --reload --host 0.0.0.0 --port 8000`) does not pass --no-access-log.
# mk/dev.mk is not owned by this task -- flagged here for whoever owns
# that file next, rather than edited directly.

.PHONY: logging-check

logging-check:
	@if grep -rn "uvicorn" mk/*.mk | grep -v "mk/logging.mk" | grep -v "no-access-log"; then \
		echo "logging-check: the uvicorn invocation(s) above are missing --no-access-log"; \
	else \
		echo "logging-check: ok"; \
	fi
