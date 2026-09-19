# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004).
**Commit:** see `git log -1` on `main`. **Repo:**
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
  proven to actually authenticate against RLS. Sign-up optionally
  accepts a `pending_plan` and saves it as the new account's first plan
  in the same request — the guest→account migration.
- `POST/GET/PATCH/DELETE /plans` — save/list/edit/delete a plan, fully
  verified live, including student B provably unable to see or edit
  student A's plan through the real API.
- Deployed on your Oracle VM alongside `hisab`/`lekha`/`attendance-app`,
  nothing else touched.

**132 tests passing, zero skipped** (92 unit + 40 live DB), lint/
typecheck clean, CI green on every push this session.

## Blockers
None. **M3's engineering scope is complete.**

## Two real bugs found and fixed this session (not assumed away)
1. **Security**: the database client was a shared singleton — under
   real concurrent traffic, one user's access token could have leaked
   onto another user's request. Found while building the auth work,
   fixed, regression-tested. A concurrent session's independent security
   review then found and fixed a follow-on connection-leak issue in the
   same area. Nothing in production was exposed (app isn't public yet).
2. The guest→account plan migration silently failed every single call
   at first — an insert that forgot to set `student_id` was correctly
   rejected by RLS, but the function's own "never fail sign-up over a
   bad plan" design meant that failure was invisible until a live test
   actually checked the row got created. Fixed by passing the user id
   through explicitly.

Full details on both in `docs/DECISIONS.md`.

## Next task
Only genuinely open M3 item: **full consent/safeguarding review before
real minor accounts are enabled** — this is deliberately a human
decision, not something any commit should do as a side effect
(docs/SECURITY.md). A concurrent session flagged wanting to be looped in
on that specifically. Otherwise: M4 (mock tests, teacher dashboard) or
M5 (bounded AI) are the next milestones, or a content/design pass — your
call.

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
4. **Consent/safeguarding review** — needs your (or a designated
   reviewer's) eyes before real minor accounts can be enabled. Not
   urgent — nothing currently allows a real account of any age to do
   anything unsafe; this gate matters before that changes.

## Not claimed
No e2e test, no live AI call, no public exposure of the deployed app
yet. No real content exists — every test uses clearly-labelled synthetic
fixtures; nothing has been published as a verified fact for an actual
student to see.

## Concurrent sessions — multiple sessions worked this repo today
This session shared the repo with at least one other active Claude
session for a significant stretch (same machine, same working
directory). Coordination happened via direct cross-session messaging
throughout: file-touch lists exchanged before editing, commits kept
separate when both sides had uncommitted work, a circular-import bug and
later a resource-leak bug each caught and fixed collaboratively, a
second independent security-review pass run on request. See
`docs/DECISIONS.md` for the full log. If you're running multiple
sessions on purpose, this worked cleanly; if not, worth knowing.
