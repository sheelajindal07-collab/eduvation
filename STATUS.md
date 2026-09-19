# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004). **M4
maker-checker enforcement + publishing-console API built, awaiting
migration** (BCI-005). **First real UI shipped** — Explore → Compare,
the first screens anyone could actually click through (BCI-006).
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
- **`GET /explore`, `GET /compare/view` — an actual UI, for the first
  time, now reviewed and fixed.** Every route before this was JSON-only;
  nobody could click through any of it. Real Tailwind-styled pages: pick
  2-3 pathways on Explore (works with zero JavaScript — a plain HTML
  form), see them compared with trust-labelled fields and the four cost
  figures kept visually distinct, closing with docs/UI.md's exact
  required prompt. `ux-qa-reviewer` — unusable until now, its own
  trigger condition never having been met in this project — walked every
  scenario live (0/1/2/4 pathways, malformed/nonexistent ids,
  zero-claims pathways, an XSS probe) and found real issues, all fixed
  same session: a malformed `pathway_id` crashed to a bare 500 with no
  way back (very plausible given this product's WhatsApp-shared-link
  reality); every evidence link said "Official source" regardless of the
  actual trust label, directly contradicting the badge next to it for
  institution-reported/stale fields; the comparison grid never actually
  stacked on mobile despite a comment claiming it did; field order
  didn't match docs/UI.md; money figures were inconsistently formatted;
  a color-contrast pair measured just under WCAG AA; checkbox tap
  targets were 16px against ~44px guidance. No XSS found (Jinja
  autoescaping confirmed on); the zero-JS claim confirmed genuinely true.
  9 new regression tests plus the original 6, all live.
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

**213 tests total** (188 passing + 25 correctly skipping pending the
0003 migration — verified live this session, not just collected),
lint/typecheck clean, CI green on every push this session. One test
(`test_sign_up_new_email_succeeds_or_requires_confirmation`) has now
flaked twice under the full suite's combined load, passing both times in
isolation — plausibly Supabase Auth rate-limiting real sign-ups across
this repo's growing test count in one run. Second occurrence means it's
a real pattern now, not a one-off; worth a proper fix (retry/backoff, or
spacing out sign-up-heavy tests), not just another note.

## Open findings from the background UX review, not yet fixed
A read-only `ux-qa-reviewer` pass this session (separate from the two
maker-checker bugs above, already fixed) flagged two more real gaps,
still open:
1. **HIGH** — `GET /eligibility`'s `CriterionResultOut.source_claim_id`
   and `POST /timeline`'s `StageOut`/`ParallelActivityOut.source_claim_id`
   are bare claim UUIDs with no route that resolves one into an actual
   displayable source (authority name, official link, verification
   date) — unlike `GET /compare`, which already does this via
   `FieldValueOut.source_url`/`verification_date`. Fine while these two
   screens are JSON-only; becomes a real problem the moment someone
   builds the eligibility or timeline/cost-calculator UI screens (next
   on `tasks/BCI-006.md`'s list) — docs/UI.md requires "source
   authority, applicable cycle, verification date, official link" on
   every fact shown, and right now those two screens have nowhere to
   get it from. Whoever picks up that UI work should resolve this
   first, following `app/api/compare.py`'s existing
   `_row_to_source`/`sources_by_id` pattern.
2. **LOW** — `app/api/auth.py`'s docstring cites a guest-session design
   (anonymous server session, random token, 7-day expiry, "never
   localStorage") that docs/UI.md describes but no route actually
   implements yet, and the citation to `docs/DECISIONS.md` for it
   doesn't point at anything real. Not a live bug (nothing currently
   claims this exists at runtime), just a docs-accuracy gap worth
   closing before someone builds a guest-session route assuming the
   docstring already describes what's there.

## Design mockup (2026-09-19, separate session — no repo code touched)
A design canvas of the whole app now exists, built from `docs/UI.md` and
`docs/PRODUCT.md`: the seven student screens at phone width (quick start,
explore, compare with a working route switch, time and cost, programme
detail, my plan, Ask BCION), the comparison screen on desktop, the
reviewer publishing console, and a difficult-states sheet.
Link (private to the owner until shared):
https://claude.ai/artifact/UfLEdwJgiswwBPGu8cbXVo
Every figure on it is sample data under a "not verified facts" ribbon;
bracketed items are blanks for real records. Not rendered or reviewed by
a person yet — it is a starting point for usability round 1, not a frozen
component set.

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
5. **Fixed** (commit `1d92af3`): `app/planning/comparison.py`'s cost
   assembly read `estimated_additional_expenses_hint` straight out of
   the claims dict for both the displayed breakdown and
   `net_to_arrange`'s arithmetic — the one field on the whole comparison
   screen that skipped `field_value_for()`'s published/synthetic-source
   checks. A draft or synthetic-sourced hint could have leaked into a
   real total. Found by a background UX-review agent, independently
   re-verified, fixed with a shared `_estimated_additional_expenses_hint()`
   helper both call sites now use. Also fixed the adjacent display
   inconsistency the same review flagged: the breakdown used to show
   blank/`None` for "no hint" while the total below it silently assumed
   ₹0 for the same case — the breakdown now shows 0.0 too, so the line
   item always matches what the total was computed from. 6 new
   regression tests in `tests/unit/test_comparison.py`.
6. **Fixed, more serious** (commit `0e57606`): `GET /eligibility`
   trusted RLS visibility as a proxy for "this claim is published" —
   true for a guest/student, but a reviewer's own RLS-scoped client can
   also SELECT draft/in_review/superseded claims (by design, so they
   can review them; `db/migrations/0001_init.sql`'s
   `claims_select_published` policy is `status = 'published' or
   is_reviewer()`). `_criteria_from_claims` built a criterion from
   whatever came back with no status check, so a reviewer calling
   `/eligibility` on a pathway with an unapproved draft criterion got
   an actual **eligibility outcome** computed from it — not just a
   wrong displayed number, a wrong "meets"/"does_not_meet". Fixed by
   filtering to published claims first. Proved the test catches the
   real bug, not just green-by-luck: reverted the fix locally, confirmed
   the new regression test in `tests/db/test_api_eligibility.py` fails,
   restored the fix, confirmed it passes again.

Full details on all of these in `docs/DECISIONS.md`.

## Next task
**The consent-gate decision above is the one that actually matters right
now** — everything else is normal backlog. Once that's resolved: apply
`db/migrations/0003_maker_checker.sql` (same as 0002 — SQL Editor or
`scripts/apply_migrations.py`) so `app/api/claims.py` actually goes live
and can be verified for real (right now every one of its tests is a
skip, not a pass — don't treat M4 as proven until that's rerun green).
After that: more UI screens (quick start, timeline/cost calculator, a
reviewer console for the publishing API — see `tasks/BCI-006.md` for the
full "not done yet" list, including that Playwright e2e still isn't
wired), M5 (bounded AI), or a content/design pass — your call.

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

## Content drafts — NEET (UG) added and cross-checked (2026-09-19)
`docs/content-drafts/neet-ug-eligibility.md` — draft research only, same
rules as the GUJCET draft: unverified, unpublished, nothing inserted into
the database. Two independent official sources now, not one: NTA's
official NEET (UG)-2026 Information Bulletin (124-page text PDF), plus a
same-session follow-up that reached NMC's own site (retrying past the
earlier redirect/404) and read the actual primary law it's based on —
**Graduate Medical Education Regulations, 2023** and its 16.06.2023
Corrigendum, both official Gazette of India notifications, full text.
Age and required-subjects are now confirmed by both documents, verbatim,
independently. Worth knowing the regulation's original text said the age
cutoff was 31 **January**, corrected to 31 **December** three months
later by the corrigendum — the version now in force matches the
bulletin. The regulation's own silence on a Class-12 marks floor,
domicile and exam-attempt limits strengthens (not just repeats) those
three "not found" conclusions from the bulletin alone. Full corroboration
log in the draft's own "Corroboration done this session" section. Three
things worth knowing before anyone builds a NEET pathway on it:
1. **The bulletin has no Class 12 marks floor and no upper age limit.**
   The widely repeated "50% PCB" / "age 25" figures are not in it — the
   draft publishes no claim for either rather than guessing. (The
   `maximum_age(25)` in `tests/unit/test_eligibility.py`'s NEET-style
   fixture is synthetic and fine as an engine test, but must never be
   copied into content.)
2. **Two rules-engine gaps would give students wrong answers** if NEET
   claims were published as-is: minimum age is "17 by 31 Dec of the exam
   year" (a DOB cutoff — today's integer-age check would wrongly reject a
   16-year-old who qualifies), and subjects are "Biology **or**
   Biotechnology" (`required_subjects` is all-of only). No code changed
   this session; both need a decision first.
3. **It's the 2026 cycle, already sat (03 May 2026).** The 2027 bulletin
   wasn't out; DOB cutoff and fees are 2026-only.
No tests run this session — docs-only change, no code touched.

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
