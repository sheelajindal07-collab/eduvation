# Local dev loop (DEPLOY-18 split; unchanged targets, moved out of the
# root Makefile — see that file's own header).

.PHONY: install dev css

# Every make target below (and in the other mk/*.mk files, since they
# all share this one `make` run) resolves `python`/`pip`/`mypy`/`pytest`/
# `ruff`/`uvicorn` etc. against this project's own .venv first, never a
# dev machine's global site-packages. Without this, a Python install
# that's shared across other projects on the same machine can leak an
# unrelated package into the tool an `mk/*.mk` target invokes bare (e.g.
# a stray global `numpy` pulling in a stub mypy can't parse under this
# project's pinned python_version — see STATUS.md). CI is unaffected: it
# never runs `make install`, it installs into its own fresh runner.
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
else
    VENV_BIN := .venv/bin
endif
export PATH := $(abspath $(VENV_BIN)):$(PATH)

# SEC-7: installs only from the hashed, pinned lockfile (Linux/py3.11 —
# see requirements-dev.lock's own header for why that's not this dev
# machine on Windows/macOS). `--require-hashes` refuses anything not
# pinned-with-hash in that file; the local `app` package itself is never
# in it (it's the project being built, not a dependency), so it's
# installed separately, editable and with `--no-deps` so pip doesn't try
# to re-resolve its declared dependencies outside the hash-checked step.
install:
	test -d .venv || python3 -m venv .venv
	pip install --require-hashes -r requirements-dev.lock
	pip install -e . --no-deps
	npm install

dev:
	# --no-access-log: OPS-2's own request-id middleware logs a
	# redacted, route-template-only line for every request. uvicorn's
	# default access log would duplicate that with the raw path
	# (including any query string) and isn't redacted, so it stays off.
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --no-access-log

css:
	npx tailwindcss -i ./app/web/styles/input.css -o ./app/static/css/app.css --minify
