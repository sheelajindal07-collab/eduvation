# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
first slice shipped** (BCI-004: sign-in + saved plans). **Commit:** see
`git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## What works right now — live routes, all verified
- `GET /careers` — published careers/pathways.
- `GET /compare?pathway_id=X&pathway_id=Y` — trust-labelled fields plus
  a real computed `net_to_arrange`; assumption editing via query param.
- `GET /eligibility?pathway_id=X&age=..&...` — criteria built
  dynamically from a pathway's own published claims.
- `POST /timeline` — stateless Career Life Span Calculator.
- `POST /auth/sign-up`, `POST /auth/sign-in` — real Supabase Auth,
  proven to actually authenticate against RLS (not just well-formed).
- `POST/GET/PATCH/DELETE /plans` — save/list/edit/delete a plan, **fully
  verified live**: owner applied `0002_saved_plans.sql`, all 7 tests
  re-run and pass for real, including student B provably unable to see
  or edit student A's saved plan through the actual API.
- Deployed on your Oracle VM alongside `hisab`/`lekha`/`attendance-app`,
  nothing else touched.

**126 tests passing, zero skipped** (92 unit + 34 live DB), lint/
typecheck clean, CI green on every push this session.

## Blockers
None.

## Also this session: a real security bug found and fixed
`app/db/client.py`'s database client was a shared singleton — under
real concurrent traffic, one user's access token could have leaked onto
another user's request, or a guest could have inherited a signed-in
user's identity. Found while building the auth work, fixed immediately,
regression-tested, deployed. Nothing in current public/production use
was exposed (the app isn't publicly reachable yet). Full details in
`docs/DECISIONS.md`.

## Next task
Rest of M3 (guest→account plan migration, then a deliberate, separate
decision on full consent/safeguarding for real minor accounts — see
`tasks/BCI-004.md`), or M4/M5 — your call once M3's first slice is
verified.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`). Schema `0001` and `0002` both applied and verified. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input — none blocking
1. **Public domain** — if you want the app reachable from outside the
   VM, send a domain/subdomain and I'll add an nginx site.
2. **Pilot state** — still assumed Gujarat, confirm or correct.
3. **Named content reviewers**, **Gemini model** — not blocking.

## Not claimed
No e2e test, no live AI call, no public exposure of the deployed app
yet, no guest→account plan migration yet (next slice of M3). No real
content exists — every test uses clearly-labelled synthetic fixtures.

## Concurrent sessions — multiple sessions worked this repo today
This session shared the repo with at least one other active Claude
session for a significant stretch (same machine, same working
directory). Coordination happened via direct cross-session messaging:
file-touch lists exchanged before editing, commits kept separate when
both sides had uncommitted work, a real circular-import bug caught and
fixed collaboratively. See `docs/DECISIONS.md` for the full log. If
you're running multiple sessions on purpose, this worked cleanly; if
not, worth knowing.
