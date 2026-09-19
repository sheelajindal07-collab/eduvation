# Status

**Milestone:** M0 complete (BCI-001); M1 first vertical slice DONE
(BCI-002); **M2 eligibility + cost engines DONE** (BCI-003). **Commit:**
see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## What works right now — for real, verified this session
- `GET /careers` and `GET /compare` — live against the real Mumbai
  Supabase project. Proven end-to-end: a claim published against a real
  official source returns the correct trust label; a draft claim's
  value never reaches a guest response even though the row exists.
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
- Deployed and running on your Oracle VM alongside your other apps
  (`hisab`, `lekha`, `attendance-app`), same systemd/nginx conventions,
  nothing else touched.

**67 tests passing** (54 unit + 13 live DB), lint/typecheck clean, on
GitHub Actions too.

## Blockers
None.

## Next task
Timeline engine, a reservation/quota engine, wiring eligibility+cost
into an actual API route, or a design/UI usability round — steering
committee's call. See `tasks/BCI-003.md` for exact remaining scope.

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
Two other Claude sessions were active on this same repo during this
session (one did a documentation restructuring, coordinated via direct
messaging before merging — see `docs/DECISIONS.md`). If you're running
multiple sessions on purpose, that coordination worked cleanly; if not,
worth knowing it's happening.
