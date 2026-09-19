# Status

**Milestone:** M0 complete (BCI-001); M1 data foundation drafted
(BCI-002, in progress). **Commit:** see `git log -1` on `main`.

## What works right now
`make lint`, `make typecheck`, `make test-unit` all pass for real. The
FastAPI app boots (`uvicorn app.main:app`) and serves `/healthz` and
`/docs` live. `db/migrations/0001_init.sql` (schema + RLS policies) and
`app/db/client.py` (RLS-aware client factory) are written but not yet
applied to any real project. `tests/db/test_rls.py` has 9 real,
non-trivial test cases for the guest/student A/student B/reviewer access
matrix — they currently **skip with a printed reason** (no Supabase
project configured yet), verified by actually running them, not assumed.

## Blockers
None for continuing engineering work. The next real step forward — making
`make test-db` go from 9 skipped to 9 passing — needs your Supabase
project (see below). Everything else can keep proceeding on synthetic
fixtures in the meantime.

## Next task
**BCI-002 — M1 first vertical slice**: explore → compare on synthetic
fixtures, verified against a real project. See `tasks/BCI-002.md`.

## Infrastructure (confirmed 2026-09-19)
Supabase, GitHub, Oracle hosting and a Gemini API key are ready — **on
accounts separate from this dev machine's connected tools**. The GitHub
CLI here is signed in as `maheshjin-bot`; the Supabase MCP tool here only
sees an unrelated org (`ridhivi`) with no free slot. Neither was touched
beyond read-only checks, and **the Supabase MCP tool will not be used on
this project again** per your instruction. Schema work proceeds as plain
SQL migration files in the repo for you to apply yourself.

## Needs your input (tracked in full in `docs/DECISIONS.md`)
1. **GitHub repo** — you're creating one yourself on your own account.
   Send me the URL + confirm push credentials are set up locally.
2. **Supabase project URL** — you're creating a fresh project in
   `ap-south-1` (Mumbai) — `project education` (Singapore) is not being
   used. Once created, send me the URL (not secret); put the actual keys
   into your own local `.env` — never paste secret values into chat. Then
   apply `db/migrations/0001_init.sql` via the SQL editor (see
   `db/migrations/README.md`) and `make test-db` should go from 9 skipped
   to 9 passing.
3. **Pilot state** — still assumed Gujarat (Annex C.2, "if confirmed").
   Confirm or name another state before the content track writes real
   admission-rule content.
4. **Named content reviewers** — who verifies the 50–100 programme
   records, 8–10 exam rule sets and 10–20 scholarships (Annex C.3)? Not
   blocking engineering, but blocks real publishable content.
5. **Gemini model** — confirmed provider is Gemini; which model (flash vs
   pro) can wait until M5 unless you have a preference now.
6. **Stack confirmation** — silence keeps the pinned FastAPI/Supabase/VPS
   stack. Say so only if you want the Next.js/Vercel alternative.

## Not claimed
No RLS assertion has actually executed against a real database — 9 real
test cases exist (`tests/db/test_rls.py`) and currently skip honestly.
No e2e test, no live AI call, no deployment has happened. `make test-e2e`
and `make build` are still placeholder targets (see `Makefile`) until
M1's UI and a hosting decision respectively give them something real to
run against; `make test-db` is real now, just unexercised.
