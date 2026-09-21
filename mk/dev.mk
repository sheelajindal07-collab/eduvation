# Local dev loop (DEPLOY-18 split; unchanged targets, moved out of the
# root Makefile — see that file's own header).

.PHONY: install dev css

# SEC-7: installs only from the hashed, pinned lockfile (Linux/py3.11 —
# see requirements-dev.lock's own header for why that's not this dev
# machine on Windows/macOS). `--require-hashes` refuses anything not
# pinned-with-hash in that file; the local `app` package itself is never
# in it (it's the project being built, not a dependency), so it's
# installed separately, editable and with `--no-deps` so pip doesn't try
# to re-resolve its declared dependencies outside the hash-checked step.
install:
	pip install --require-hashes -r requirements-dev.lock
	pip install -e . --no-deps
	npm install

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

css:
	npx tailwindcss -i ./app/web/styles/input.css -o ./app/static/css/app.css --minify
