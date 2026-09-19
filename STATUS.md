# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004). **M4
maker-checker enforcement + publishing-console API built, awaiting
migration** (BCI-005). **Commit:** see `git log -1` on `main`. **Repo:**
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
- **Maker-checker, enforced at the database, plus the publishing console
  API on top of it** — neither existed before this session:
  `db/migrations/0003_maker_checker.sql` (a claim must always be
  inserted as a draft, the author of a claim can never approve their
  own, a published claim's recorded content is frozen — a correction
  means a new claim, never an in-place edit) and `app/api/claims.py`
  (`POST /claims`, `/submit`, `/approve`, `/reject`, `/supersede`,
  `GET /claims`) on top of it. **Neither is live yet** — same as 0002,
  the migration needs you to run it via the SQL Editor first; every
  route in `claims.py` 403s/400s until then, and its 12 tests correctly
  skip rather than pretend to pass.

**163 tests total** (138 passing + 25 correctly skipping pending the
0003 migration — verified with `pytest --collect-only`), lint/typecheck
clean, CI green on every push this session.

## Blockers
None on engineering. **One real blocker on judgment, below.**

## ⚠️ Read this one — sign-up is live with no age/consent gate
A full security review of M3's auth surface (run this session,
independent read-only agent, verified live against the real database —
not a static-analysis guess) confirmed something worth your immediate
attention, not just a someday item: **`POST /auth/sign-up` accepts
anyone, any age, right now — no birth-year field, no consent flag,
nothing in the code that disables a real minor's account.** This project
exists for Class 8–12 students, i.e. minors are the primary user. Before
M3, the whole app was anonymous/stateless, so this couldn't matter; M3 is
exactly what introduced real persistent accounts, and the consent gate
CLAUDE.md and `docs/SECURITY.md` call a **launch gate** hasn't been
built.
**What limits the actual exposure right now**: the app is still
localhost-only on your VM — nobody outside it can reach `/auth/sign-up`
today. That's the only thing standing between this and a real problem,
not any code. **This is a hard blocker before the public-domain request
below** (item 1) — don't say yes to public exposure until this is
resolved one way or another (a real consent flow, or a simple interim
gate like an invite-only/reviewer-approved sign-up for the pilot).
Full write-up: `docs/DECISIONS.md`, and the review agent's own findings
(ask either session to relay the full transcript if you want it
verbatim).

## Other bugs found and fixed this session (not assumed away)
1. **Security**: the database client was a shared singleton — under real
   concurrent traffic, one user's access token could have leaked onto
   another user's request. Found, fixed, regression-tested. An
   independent review then found and fixed a follow-on connection-leak
   issue in the same area, plus hardened the regression tests and config.
2. The guest→account plan migration silently failed every call at
   first — an insert that forgot to set `student_id` was correctly
   rejected by RLS, invisible because the function's own "never fail
   sign-up over a bad plan" design swallows the exception. Fixed; **now
   also logs the failure** (`user_id`/`pathway_id` only — never the
   student-supplied notes/figures) so a recurrence won't be invisible
   again.
3. **Fixed**: `POST /plans`'s error handling mislabelled two distinct
   failures (a nonexistent `pathway_id`, a malformed UUID) as "already
   saved" — now 404 and 422 respectively, 409 reserved for a genuine
   duplicate. A malformed `plan_id` on update/delete used to crash to a
   raw 500 — now a clean 422, checked before any query runs.
4. **Test-coverage gaps closed**: the review's live probes (reviewer vs.
   saved_plans, delete cross-user) were correct but had no permanent
   regression test — 6 new tests added, all passing
   (`tests/db/test_api_plans.py`).

Full details on all of these in `docs/DECISIONS.md`.

## Next task
**The consent-gate decision above is the one that actually matters right
now** — everything else is normal backlog. Once that's resolved: apply
`db/migrations/0003_maker_checker.sql` (same as 0002 — SQL Editor or
`scripts/apply_migrations.py`) so `app/api/claims.py` actually goes live
and can be verified for real (right now every one of its tests is a
skip, not a pass — don't treat M4 as proven until that's rerun green).
After that: a reviewer-facing UI for the publishing console (the API
exists, nothing shows it to a human yet), M5 (bounded AI), or a
content/design pass — your call.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`). Schema `0001`/`0002` applied and verified; `0003` (maker-checker) written, awaiting your application. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input
1. **Consent/safeguarding gate — see the ⚠️ section above.** Blocks
   item 2 below. Not blocking engineering elsewhere, but blocking any
   move toward public reachability.
2. **Public domain** — hold until item 1 is resolved. Once it is, send a
   domain/subdomain and I'll add an nginx site.
3. **Apply `0003_maker_checker.sql`** — same process as 0002 (SQL
   Editor, or `scripts/apply_migrations.py` if `DATABASE_URL` is set).
4. **Pilot state** — still assumed Gujarat, confirm or correct.
5. **Named content reviewers**, **Gemini model** — not blocking.

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
