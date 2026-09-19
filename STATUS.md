# Status

**Milestone:** M0 complete (BCI-001); M1 data foundation **verified live**
(BCI-002, in progress). **Commit:** see `git log -1` on `main`.

## What works right now — for real, verified this session
`make lint`, `make typecheck`, `make test-unit` all pass. The FastAPI app
boots and serves `/healthz`/`/docs` live. **The real Supabase project
(Mumbai, `ap-south-1`) has the schema applied, and `make test-db` passes
9/9 against it** — guest, student A, student B and reviewer access are
each independently verified by RLS, not mocked. That's 27 tests total (18
unit + 9 live DB), all green. `app/planning/comparison.py` implements the
full trust-label rules from `docs/DATA.md` with 12 dedicated tests.

## Blockers
None. Engineering can continue freely — the database is live and tested.

## Next task
**BCI-002 — M1 first vertical slice**: wire the actual `/explore` and
`/compare` API routes to the (now real) database via `app/db/client.py`,
using the comparison-assembly logic already built. See `tasks/BCI-002.md`.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`), schema applied, RLS verified by 9 passing tests. `DATABASE_URL` not yet in `.env` — needed for `scripts/apply_migrations.py` to apply *future* migrations without the dashboard. |
| GitHub | Owner creating a repo on their own account (not this machine's `maheshjin-bot`). Not yet connected. |
| Oracle hosting | Confirmed ready; specifics gathered at the deployment milestone (M6). |
| AI provider | Gemini, owner-confirmed. Not used before M5 — no key needed yet. |

**Two secrets were pasted into chat during setup** (a JWT secret, then a
service-role key) — owner was asked to rotate both in the Supabase
dashboard as a precaution; neither was written to any file by me.

## Needs your input (tracked in full in `docs/DECISIONS.md`)
1. **GitHub repo URL** — once created, send it + confirm push credentials
   work locally.
2. **`DATABASE_URL` in your `.env`** (optional, for automated future
   migrations) — Project Settings → Database → Connection string → URI.
   See `db/migrations/README.md` for the one-time bootstrap note (0001
   was applied manually, before this script existed).
3. **Pilot state** — still assumed Gujarat (Annex C.2, "if confirmed").
4. **Named content reviewers** — who verifies real programme
   records/exam rules/scholarships (Annex C.3)? Not blocking engineering.
5. **Gemini model** — flash vs pro can wait until M5.
6. **Stack confirmation** — silence keeps FastAPI/Supabase/VPS.

## Not claimed
No e2e test, no live AI call, no deployment has happened yet. `make
test-e2e` and `make build` are still placeholder targets until M1's UI
and a hosting decision respectively give them something real to run
against. `scripts/apply_migrations.py` is written and passes lint/
typecheck but has not actually been run (no `DATABASE_URL` yet).
