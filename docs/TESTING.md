# Testing — the local-stack contract for parallel agents (QA-4)

One local Supabase stack (Docker + Supabase CLI, `supabase/config.toml`)
backs every `tests/db` run in this repo. Nothing here ever reaches the
owner's real project — `mk/testdb.mk`'s `test-db-env` refuses to write a
non-loopback `.env.test`, and `tests/db/conftest.py` re-checks the same
thing at run time.

## The loop
```
make test-db-up      # start the stack, apply migrations, write .env.test
make test-db         # or: pytest tests/db -v
make verify          # lint + unit + db + e2e, one PASS/FAIL/SKIP line each
make test-db-down    # stop the stack (data survives)
make test-db-reset   # wipe the database and re-apply every migration
```
First run pulls several GB of images — that's the download, not a hang.

## Rules for an implementer working in a worktree
- Copy `.env.test` from the shared stack into your worktree rather than
  running your own `supabase start` — one stack per machine, not one per
  worktree. `.env.test.local` (already gitignored) overrides it if you
  need a one-off value; never commit either file.
- Run targeted tests against that shared stack with `BCION_REQUIRE_LIVE=1`
  so a skip (missing env, an unapplied migration) is a hard failure you
  see now, not a silent green you find out about at merge time.
- Never run the full `tests/db` suite and a migration owner's
  `test-db-reset` at the same time — the lead schedules migration work as
  its own exclusive window (`docs/DEVELOPMENT-PLAN.md` 6.4). Everything
  else is safe concurrently: every seeded row/user is tagged with a
  `BCION_RUN_ID` (printed at the start of every `pytest tests/db`) and
  swept on its own at the end of the run, so two runs — or one run split
  across `make test-db-parallel` / `pytest -n auto tests/db` workers — can
  never collide or clean up each other's rows.
- If a run is killed before it can clean up (Ctrl-C, an OOM), finish the
  sweep by hand: `make test-db-sweep RUN_ID=<the printed id>`.
- A migration prototype that might get the schema wrong uses a **second**
  stack on alternate ports, not the shared one — ask the lead before
  starting a second stack rather than assuming a free port.
- The lead runs the full suite (`make verify`) before merging any branch,
  regardless of what you ran locally.

## CI
`ci.yml`'s `lint-typecheck-test` job runs ruff, mypy, `pytest tests/unit`
and `pytest tests/db` (against real repo-secret credentials — never
skips) on every push/PR. `pytest tests/e2e` is not yet a CI job — it runs
locally today (`make test-e2e`); wiring it into CI as its own job,
alongside the local-stack DB job, is tracked separately (QA-5).

**mypy: run the plain `mypy app` (`mk/quality.mk`'s `typecheck` target),
never `mypy app --follow-imports=skip`.** A local, unpinned `numpy` in
this machine's shared Python environment (not in either lockfile, not
imported by any app code) makes a plain `mypy app` crash on a stub-syntax
error, and `--follow-imports=skip` was used session over session as a
workaround (see `docs/DECISIONS.md`/`STATUS.md`, 2026-09-21 entries) —
but that flag doesn't just skip numpy, it skips resolving every
third-party import, which silently hid a real `arg-type` error (A11Y-3's
exception-handler typing) that only CI's clean, lockfile-only mypy run
caught (docs/DECISIONS.md, 2026-09-22). If `mypy app` still crashes on
the numpy stub locally, verify the specific file(s) in isolation
(`mypy app/path/to/file.py` — doesn't pull in the same transitive
resolution) and let CI be the authoritative full-project check, rather
than reaching for `--follow-imports=skip` again.
