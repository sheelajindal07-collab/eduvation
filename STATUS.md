# Status

**Milestone:** M0 complete (BCI-001); M1 data foundation **verified live**
(BCI-002, in progress). **Commit:** see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green.

## What works right now — for real, verified this session
`make lint`, `make typecheck`, `make test-unit` all pass, on GitHub Actions
too (not just locally — caught and fixed a real packaging bug that only
showed up on a clean CI install). The FastAPI app boots and serves
`/healthz`/`/docs` live. **The real Supabase project (Mumbai,
`ap-south-1`) has the schema applied, and `make test-db` passes 9/9
against it** — guest, student A, student B and reviewer access are each
independently verified by RLS, not mocked. Re-verified after the owner
rotated the two keys pasted in chat earlier: still 9/9. 27 tests total
(18 unit + 9 live DB), all green.

## Blockers
None. Engineering can continue freely — the database is live and tested,
the repo is on GitHub with passing CI.

## Next task
**BCI-002 — M1 first vertical slice**: wire the actual `/explore` and
`/compare` API routes to the (now real) database via `app/db/client.py`,
using the comparison-assembly logic already built. See `tasks/BCI-002.md`.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`), schema applied, RLS verified by 9 passing tests, keys rotated after being pasted in chat. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, pushed via a collaborator invite accepted for this machine's account, CI green. |
| Oracle hosting | Confirmed ready; specifics gathered at the deployment milestone (M6). |
| AI provider | Gemini, owner-confirmed. Not used before M5 — no key needed yet. |

## Needs your input (tracked in full in `docs/DECISIONS.md`) — none blocking
1. **`DATABASE_URL` in your `.env`** (optional, for automated future
   migrations) — Project Settings → Database → Connection string → URI.
2. **Pilot state** — still assumed Gujarat (Annex C.2, "if confirmed").
3. **Named content reviewers** — who verifies real programme
   records/exam rules/scholarships (Annex C.3)? Not blocking engineering.
4. **Gemini model** — flash vs pro can wait until M5.
5. **Stack confirmation** — silence keeps FastAPI/Supabase/VPS.

## Not claimed
No e2e test, no live AI call, no deployment has happened yet. `make
test-e2e` and `make build` are still placeholder targets until M1's UI
and a hosting decision respectively give them something real to run
against. `scripts/apply_migrations.py` is written and passes lint/
typecheck but has not actually been run (no `DATABASE_URL` yet).
