# Image build (DEPLOY-18 split; DEPLOY-3 wires the target itself).

.PHONY: build

# DEPLOY-3: builds the runtime image from the repo-root Dockerfile.
# Installs from requirements.lock with --require-hashes (see that
# Dockerfile's own header) — nothing here floats.
build:
	docker build -t bcion-lite:local .
