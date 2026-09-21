# Local dev loop (DEPLOY-18 split; unchanged targets, moved out of the
# root Makefile — see that file's own header).

.PHONY: install dev css

install:
	pip install -e ".[dev]"
	npm install

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

css:
	npx tailwindcss -i ./app/web/styles/input.css -o ./app/static/css/app.css --minify
