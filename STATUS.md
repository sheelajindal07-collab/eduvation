# Status

**Milestone:** M0 complete (BCI-001); **M1 first vertical slice DONE**
(BCI-002). **Commit:** see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green.

## What works right now — for real, verified this session
`GET /careers` and `GET /compare` are live and working against the real
Mumbai Supabase project — not mocked, not synthetic-only. A student can
genuinely: see published careers, compare two or three pathways, and get
correctly trust-labelled fields (verified vs. estimate vs. not-available)
sourced from real database rows. Proven end-to-end by seeding a claim
against a real official source and watching the API return the right
label. Just as important, the negative case is proven too: a draft
claim's value never reaches a guest response, even though the row exists
— tested directly, not assumed.

**31 tests passing** (18 unit + 13 live DB), lint/typecheck clean, on
GitHub Actions too. Along the way, caught and fixed: a packaging bug
that only appeared on a clean install (not locally), a ruff false
positive on FastAPI's own idiom, and two real mypy type gaps.

## Blockers
None. The core M1 slice from the DPR's own spec (Annex E.3: "published
career record → explore → compare two options") is genuinely built and
verified.

## Next task
Design/UI round (Annex D.3 usability round 1) before adding more
engines, or start on the eligibility/cost rule engines (M2 scope,
`app/rules/`) — steering committee's call. See `tasks/BCI-002.md` for
full detail on what shipped.

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
