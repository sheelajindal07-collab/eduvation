# Status

**Milestone:** M0 complete (BCI-001); M1 first vertical slice DONE
(BCI-002); **M2 eligibility + cost + timeline engines DONE** (BCI-003).
**Commit:** see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## What works right now — for real, verified this session
- `GET /careers` and `GET /compare` — live against the real Mumbai
  Supabase project. Proven end-to-end: a claim published against a real
  official source returns the correct trust label; a draft claim's
  value never reaches a guest response even though the row exists.
- `GET /compare` now returns a real computed `net_to_arrange`, not just
  the raw verified-charges figure — wired to `app/rules/cost.py` via
  `app/planning/comparison.py::assemble_cost_summary()`. "Assumption
  editing" (Lite Build Pack §6) is live too:
  `?estimated_additional_expenses=<value>` overrides the estimate for
  that one request, never persisted. Proven live: a pathway with no
  published `verified_charges` claim still returns `net_to_arrange:
  null` even when the override is present — the override never papers
  over a genuinely missing figure.
- `app/rules/eligibility.py` — the three-outcome eligibility engine
  (meets / does_not_meet / insufficient_information), with the core
  safety property tested explicitly: an unknown input never becomes a
  rejection, and a definite failure is never masked by an unrelated
  unknown when several criteria combine.
- `app/rules/cost.py` — four cost amounts that never merge: verified
  charges (summed from fee-component claims, `None` if any is missing —
  never a silently-partial total), estimated extras, confirmed
  assistance (the only thing that reduces what a student owes), and
  potential assistance (shown, but **never subtracted** — an unawarded
  scholarship must never look like money in hand).
- `app/rules/timeline.py` — stages sum to a total honest about two
  things: an unknown-duration stage makes the total `None` (never a
  partial sum shown as real), and overlapping stages (prep, applications,
  internships) are genuinely subtracted, not blindly added — an overlap
  that exceeds either stage's own duration raises rather than silently
  clamping. Also: `expand_attempts()` for user-chosen retry counts,
  parallel activities that are visible but never added to the total, and
  backup pathways that compute their own independent timeline.
- Deployed and running on your Oracle VM alongside your other apps
  (`hisab`, `lekha`, `attendance-app`), same systemd/nginx conventions,
  nothing else touched.

**92 tests passing** (83 unit + 18 live DB — 5 of the live-DB tests
belong to a concurrent session's in-progress eligibility endpoint, see
"Concurrent sessions" below), lint/typecheck clean, on GitHub Actions too.

Also fixed this session: a real circular import between
`app/planning/comparison.py` and `app/rules/cost.py` (comparison.py now
calls into cost.py; cost.py already imported one type from
comparison.py) — deferred under `TYPE_CHECKING`, verified with
`python -c "import app.main"` plus the full suite. A concurrent session
caught the same bug independently and flagged it before seeing this fix
land; both sessions confirmed the fix in real time.

## Blockers
None.

## Next task
Wiring `app/rules/timeline.py` into an API route, a reservation/quota
engine, itemised fee components (a content-workflow decision, not
engineering), or a design/UI usability round — steering committee's
call. See `tasks/BCI-003.md` for exact remaining scope. (Eligibility
wiring may already be done by the time you read this — check
`app/api/eligibility.py`.)

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`), schema applied, RLS verified. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input — none blocking
1. **Public domain for the deployed app** — if you want `/compare` etc.
   reachable from outside the VM, give me a domain/subdomain and I'll
   add an nginx site (same pattern as your other apps).
2. **Pilot state** — still assumed Gujarat, confirm or correct.
3. **Named content reviewers** — not blocking engineering.
4. **Gemini model** — can wait until M5.

## Not claimed
No e2e test, no live AI call. The deployed app is reachable only from
inside the VM (`127.0.0.1:8010`) — not yet exposed publicly.
`scripts/apply_migrations.py` is written but not yet run (no
`DATABASE_URL` in `.env` yet — optional).

## Concurrent sessions note
Multiple other Claude sessions have been active on this same repo across
this and earlier sessions today (a documentation restructuring, the
eligibility/cost engines, and — as of this update — an in-progress
eligibility API endpoint (`app/api/eligibility.py`,
`tests/db/test_api_eligibility.py`, not yet committed) built by a
session running in parallel with this one). Coordination happened live
via direct cross-session messaging this time (a real circular-import bug
was caught independently by both sessions within moments of each other
and confirmed fixed before either committed). If you're running multiple
sessions on purpose, this is working; if not, worth knowing it's
happening — check `git log` and `git status` before starting a new
session's task to see what's in flight.
