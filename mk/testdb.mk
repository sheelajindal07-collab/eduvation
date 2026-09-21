# Local, throwaway Supabase stack + the whole-suite verification run (QA-2).
#
# Follows DEPLOY-18's split: the root Makefile is only `include mk/*.mk`,
# so this task adds a file here instead of editing that shared merge
# point. `test-unit` / `test-db` / `test-e2e` stay exactly where they
# are, in mk/test.mk — nothing here redefines them.
#
# The point of this file: every test run in this repo targets a local
# `supabase start` stack (supabase/config.toml) and never the owner's
# real project. Nothing below can reach a remote host — the only URLs
# involved are the ones the CLI prints for its own loopback containers,
# and `test-db-env` refuses to write an env file that isn't loopback.
#
# Requires: Docker, the Supabase CLI, and a POSIX shell for the recipes
# (on Windows that means running make from Git Bash, which is also where
# sh.exe on PATH comes from).
#
# Typical loop:
#     make test-db-up      # start the stack, apply migrations, write .env.test
#     make test-db         # or: pytest tests/db -v
#     make verify          # lint + unit + db + e2e, one line each
#     make test-db-down    # stop the stack (data is kept)
#     make test-db-reset   # wipe the database and re-apply migrations

TEST_ENV_FILE ?= .env.test
# Both the combined log and the short-lived per-suite logs are named
# `*.log`, which .gitignore already covers — so `make verify` leaves
# nothing untracked behind and needs no new ignore rule.
VERIFY_LOG ?= verify.log
VERIFY_LOG_PREFIX ?= verify-

# How `supabase status` field names map onto this repo's variable names
# (.env.example / app/core/config.py). Note `auth.anon_key`, NOT the
# newer `sb_publishable_...` key the CLI also prints: supabase-py builds
# a PostgREST client from it directly, and the legacy JWT-shaped key is
# the form that has been exercised against this codebase.
SUPABASE_ENV_NAMES := \
	--override-name api.url=SUPABASE_URL \
	--override-name auth.anon_key=SUPABASE_PUBLISHABLE_KEY \
	--override-name auth.service_role_key=SUPABASE_SERVICE_ROLE_KEY \
	--override-name auth.jwt_secret=SUPABASE_JWT_SECRET \
	--override-name db.url=DATABASE_URL

# The variables above are the only ones kept out of `supabase status`'s
# output; it also prints GRAPHQL_URL, MAILPIT_URL and friends, which
# nothing in this repo reads.
SUPABASE_ENV_KEEP := ^(SUPABASE_URL|SUPABASE_PUBLISHABLE_KEY|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_JWT_SECRET|DATABASE_URL)=

.PHONY: test-db-up test-db-down test-db-reset test-db-status test-db-env \
        test-db-migrate verify

## test-db-up — bring the local stack up, apply migrations, write .env.test.
# Safe to re-run: `supabase start` attaches to an already-running stack,
# and scripts/apply_migrations.py skips anything already recorded in
# `_schema_migrations`. The first run on a machine pulls several GB of
# images and takes minutes — that is the download, not a hang.
test-db-up:
	supabase start
	@$(MAKE) --no-print-directory test-db-env
	@$(MAKE) --no-print-directory test-db-migrate

## test-db-down — stop the containers. The database volume survives, so
# the next `test-db-up` is fast and still has the schema. Use
# `test-db-reset` when you want the data gone.
test-db-down:
	supabase stop

## test-db-reset — drop and recreate the local database, then re-apply
# every migration from db/migrations/. This is the "a prototype
# migration left the schema wrong" escape hatch, and the step docs/plan
# expects after the migration lane touches anything.
#
# `supabase db reset` alone is NOT enough here: supabase/config.toml
# deliberately keeps `[db.migrations] schema_paths = []`, because this
# repo's migrations live in db/migrations/ and are applied by
# scripts/apply_migrations.py, not by the CLI. So reset empties the
# database and apply_migrations.py refills it.
test-db-reset:
	supabase db reset
	@$(MAKE) --no-print-directory test-db-migrate

## test-db-status — what the CLI thinks is running, and on which ports.
test-db-status:
	supabase status

## test-db-env — (re)write $(TEST_ENV_FILE) from the running stack.
# The generated file is loopback-only by construction, and the guard
# below makes that an enforced fact rather than an assumption: if
# `supabase status` ever handed back a non-loopback API URL, this
# refuses to write the file at all. tests/db/conftest.py then re-checks
# the same property at run time, so a hand-edited .env.test is caught
# too.
#
# NOTE for the lead: `.env.test` is not matched by .gitignore's current
# patterns (`.env`, `.env.local`, `.env.*.local`). Adding a `.env.test`
# line there is a one-line follow-up this task did not own. Until then,
# `.env.test.local` — which IS already ignored — works identically;
# tests/db/conftest.py loads both, with `.local` winning.
test-db-env:
	@supabase status -o env $(SUPABASE_ENV_NAMES) 2>/dev/null \
		| grep -E '$(SUPABASE_ENV_KEEP)' > $(TEST_ENV_FILE).tmp
	@grep -qE '^SUPABASE_URL="?https?://(127\.0\.0\.1|localhost|\[::1\])(:[0-9]+)?/?"?$$' $(TEST_ENV_FILE).tmp \
		|| { echo "REFUSING to write $(TEST_ENV_FILE): 'supabase status' did not report a loopback API URL."; \
		     echo "Got: $$(grep '^SUPABASE_URL' $(TEST_ENV_FILE).tmp)"; \
		     rm -f $(TEST_ENV_FILE).tmp; exit 1; }
	@printf '%s\n' \
		'# GENERATED by `make test-db-env` — do not edit, do not commit.' \
		'# Values come from the local `supabase start` stack only. The keys' \
		'# below are the Supabase CLI fixed local demo keys: identical on' \
		'# every machine, worthless off this loopback stack, not secrets.' \
		'# See .env.test.example for what each name means.' \
		>> $(TEST_ENV_FILE).tmp
	@printf '%s\n' \
		'APP_ENV=development' \
		'APP_SECRET_KEY=local-test-only-not-a-secret' \
		'BCION_REQUIRE_LIVE=0' \
		'BCION_TEST_TARGET=' \
		>> $(TEST_ENV_FILE).tmp
	@mv $(TEST_ENV_FILE).tmp $(TEST_ENV_FILE)
	@echo "wrote $(TEST_ENV_FILE) (localhost stack)"

## test-db-migrate — apply db/migrations/*.sql to the LOCAL stack, then
# make PostgREST notice.
#
# That second step is not optional: PostgREST caches the database schema
# at boot and serves 404/PGRST202 for anything added afterwards, so a
# migration applied over a raw psycopg connection (which is what
# scripts/apply_migrations.py does — docs/DECISIONS.md rules out the
# management API) is invisible to every test until the cache is
# reloaded. `NOTIFY pgrst, 'reload schema'` is the documented way to do
# that. Composed with psycopg's `sql.Literal` rather than hand-quoted:
# NOTIFY takes a string literal, not a bind parameter, and this keeps
# the recipe free of nested quotes that make/sh would have to fight over.
test-db-migrate:
	@url=$$(supabase status -o env --override-name db.url=DATABASE_URL 2>/dev/null \
		| grep '^DATABASE_URL=' | cut -d'"' -f2); \
	case "$$url" in \
		*@127.0.0.1:*|*@localhost:*|*@\[::1\]:*) ;; \
		*) echo "REFUSING to migrate: '$$url' is not a loopback database."; exit 1 ;; \
	esac; \
	DATABASE_URL="$$url" python scripts/apply_migrations.py && \
	DATABASE_URL="$$url" python -c "import os, psycopg; from psycopg import sql; \
conn = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True); \
conn.execute(sql.SQL('notify pgrst, {}').format(sql.Literal('reload schema'))); \
print('PostgREST schema cache reloaded')"

# ---------------------------------------------------------------------
# make verify
# ---------------------------------------------------------------------
# One line per suite — lint, unit, db, e2e — each PASS, FAIL or SKIP
# with pytest's own counts. Full output of every suite always goes to
# $(VERIFY_LOG); a suite's output is only printed to the terminal when
# that suite fails, so a green run is four lines and a red run shows you
# exactly what broke without a rerun.
#
# SKIP is reported separately from PASS on purpose. "0 failed" and
# "actually ran" are different claims, and a suite that skipped itself
# into a green tick is the specific failure mode this whole task exists
# to remove (CLAUDE.md: never claim a test passed without running it).
# To make skipping impossible rather than merely visible, run with
# BCION_REQUIRE_LIVE=1 — tests/db/conftest.py then turns every
# "not configured" / "migration missing" skip into a hard error:
#
#     BCION_REQUIRE_LIVE=1 make verify
#
# $(1) = short label, $(2) = command to run.
define bcion_verify_suite
	@log=$(VERIFY_LOG_PREFIX)$(1).log; \
	if $(2) > $$log 2>&1; then status=PASS; else status=FAIL; fi; \
	summary=$$(grep -aE '(passed|failed|error|skipped|no tests ran|All checks passed)' $$log \
		| tail -1 | sed -e 's/^[= ]*//' -e 's/[= ]*$$//'); \
	if [ -z "$$summary" ]; then summary="(no summary line; see $(VERIFY_LOG))"; fi; \
	if [ "$$status" = PASS ] && echo "$$summary" | grep -q 'skipped' \
		&& ! echo "$$summary" | grep -qE '[0-9]+ passed'; then status=SKIP; fi; \
	printf '%-6s %-5s %s\n' '$(1)' "$$status" "$$summary"; \
	{ printf '\n===================== %s (%s) =====================\n' '$(1)' "$$status"; \
	  cat $$log; } >> $(VERIFY_LOG); \
	if [ "$$status" = FAIL ]; then \
		echo "--- $(1) output ---"; cat $$log; echo "--- end $(1) ---"; \
		echo '$(1)' >> $(VERIFY_LOG_PREFIX)failures.log; \
	fi; \
	rm -f $$log
endef

verify:
	@rm -f $(VERIFY_LOG_PREFIX)failures.log; : > $(VERIFY_LOG)
	@echo "verify — full logs: $(VERIFY_LOG)"
	$(call bcion_verify_suite,lint,ruff check app tests)
	$(call bcion_verify_suite,unit,pytest tests/unit -q)
	$(call bcion_verify_suite,db,pytest tests/db -q)
	$(call bcion_verify_suite,e2e,pytest tests/e2e -q)
	@if [ -e $(VERIFY_LOG_PREFIX)failures.log ]; then \
		echo "verify: FAILED —" $$(tr '\n' ' ' < $(VERIFY_LOG_PREFIX)failures.log); \
		rm -f $(VERIFY_LOG_PREFIX)failures.log; exit 1; \
	fi
	@echo "verify: all suites green"
