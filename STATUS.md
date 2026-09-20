# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004). **M4
maker-checker enforcement + publishing-console API DONE and verified
live** (BCI-005) — migration applied, every test that was skipping now
actually passes. **First real UI shipped** — Explore → Compare, the
first screens anyone could actually click through (BCI-006).
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
  API on top of it — now live and genuinely proven, not just written.**
  You applied `db/migrations/0003_maker_checker.sql`: a claim must always
  be inserted as a draft, the author of a claim can never approve their
  own, a published claim's recorded content is frozen (a correction
  means a new claim, never an in-place edit). `app/api/claims.py`
  (`POST /claims`, `/submit`, `/approve`, `/reject`, `/supersede`,
  `GET /claims`) sits on top of it, all wired to the real, live database.

## The migration landing found 4 real bugs — in the tests, not the trigger
The moment `0003` was applied, every test that had been correctly
skipping (never run against real enforcement before) actually ran for
the first time — and found genuine problems, all in test fixtures that
had never been exercised live, not in the migration/trigger logic
itself:
1. Two tests set `superseded_by`/`created_by` to a fabricated random
   UUID. Both are real foreign keys (`superseded_by → claims(id)`,
   `created_by → auth.users(id)`, `db/migrations/0001_init.sql`) — a
   made-up id fails that constraint before the trigger under test is
   even reached. Fixed by using a real replacement claim / `None`
   (nullable) respectively.
2. Two tests' cleanup deleted a "replacement" claim before the claim
   that referenced it via `superseded_by` — Postgres's default `NO
   ACTION` (not `CASCADE`) on that foreign key blocks deleting a row
   that's still referenced. Fixed by reordering cleanup to delete the
   referencing row first.
3. `tests/db/test_api_claims.py` used a `second_reviewer` fixture
   defined only inside `tests/db/test_maker_checker.py` — invisible to
   any other file, and invisible to pytest's own fixture-not-found check
   while every test using it was being skipped. Moved to
   `tests/db/conftest.py`, alongside `reviewer`/`student_a`/`student_b`,
   where it always should have lived.
None of these were bugs a human or an agent could have caught by
reading the code — they only exist at the intersection of "this test
runs for real" and "this specific foreign key/fixture-scoping rule
applies," which is exactly why the task card said not to treat M4 as
verified until this exact moment.

**229 tests passing, zero skipped** — verified live, this session.
Lint/typecheck clean, CI green on every push this session.

**Fixed** (commit `1919c4d`): the flaky `test_sign_up_new_email_
succeeds_or_requires_confirmation` above — root cause found, not
papered over with a retry. `app/api/auth.py`'s sign-up handler caught
every Supabase Auth error as a bare `Exception` and flattened it to a
plain 400, discarding the structured status Supabase's own
`AuthApiError` carries. The test then had to guess whether a 400 was
"the known rate-limit case" by string-matching "rate limit" in the
free-text message — fragile, since Supabase has more than one
rate-limit error code (`over_email_send_rate_limit`,
`over_request_rate_limit`, confirmed live by inspecting
`supabase_auth.errors`) and nothing guarantees every variant's message
contains that exact substring. Fixed by propagating Supabase's real
`exc.status` (429 for a rate limit, confirmed against the actual
project, which is currently saturated from this session's own testing)
instead of hardcoding 400; the three affected tests now check
`status_code == 429` directly. Full suite rerun clean after the fix.

## Background UX review findings — both now fixed
A read-only `ux-qa-reviewer` pass this session (separate from the two
maker-checker bugs above) flagged two gaps; both closed:
1. **HIGH, fixed** — `GET /eligibility`'s `CriterionResultOut` was a bare
   `source_claim_id` UUID with no route resolving it to a displayable
   source, unlike `GET /compare`. Fixed the same way: fetches the
   claim/source rows it already has and resolves each criterion's
   `source_authority`/`source_url`/`verification_date`, same
   `_row_to_source`/`sources_by_id` pattern as `compare.py`. Draft claims
   still can't leak a source either — the existing published-only filter
   already covers the new fields since a criterion never exists for an
   unpublished claim in the first place. `POST /timeline` intentionally
   still doesn't resolve sources — it's stateless by design (no DB access
   at all), so resolution belongs to whatever builds its stage list, not
   to the route itself; noted for whoever builds that UI screen.
   **Caught while building this, same day, by a concurrent session's
   independent security review**: nothing validated the URL scheme on
   `Source.official_url` before it reached `href="{{ ... }}"` in a
   template — a `javascript:`/`data:` URI would render as a fully
   clickable, script-executing link on the evidence badge. Reviewer-
   write-only today, but the same "trusted-role write reaches render
   with no independent check" shape as the maker-checker bugs above.
   Fixed here with a `_safe_source_url()` guard (degrade a non-http(s)
   scheme to `None`, same pattern as any other "unavailable" field); the
   other session fixed the equivalent gap in `app/planning/comparison.py`
   (this route builds its URL independently, so neither fix covered the
   other). 3 new tests total across both fixes
   (`tests/db/test_api_eligibility.py`).
2. **LOW, fixed** (commit `86cffce`, other session) —
   `app/api/auth.py`'s docstring accuracy gap closed.

## Dedicated security review of the new UI surface — 6 real findings, all fixed
Separate from the UX review above: a security/correctness pass (4
independent reviewers, one dimension each — maker-checker/provenance,
XSS, cross-user/RLS, general correctness — every finding adversarially
re-verified 3x before being trusted) over `app/api/compare.py`'s
`assemble_comparisons()` refactor, `app/web/pages.py`, the Jinja
templates, and `app/planning/comparison.py`. 9 candidates, all survived
verification; 6 were real bugs/gaps (3 informational — confirmed no
regression from the earlier refactor, confirmed no RLS-bypass exists,
confirmed the reviewer role is currently unreachable through this UI at
all, which is fail-safe not a leak). All 6 real ones fixed same
session, independently re-verified again (2 more adversarial passes,
plus hand-tested against 13 bypass strings myself before merging).
Commits `fb776a2`, `39e4782`.
1. **HIGH, XSS** — `field_value_for()`'s `source_url` had no scheme
   check before reaching `href="{{ fv.source_url }}"` in
   `_trust_badge.html`. A `javascript:`/`data:` URI on `Source.official_url`
   rendered as a fully clickable, script-executing link on an evidence
   badge explicitly framed as "official source" — same class the other
   session independently caught in `eligibility.py`'s own copy of this
   pattern the same day. Fixed with `_safe_source_url()`: allowlists
   `http`/`https` only, via `urlsplit` (robust against
   case/whitespace/embedded-control-character bypasses).
2. **LOW** — `verification_date` was the one field in `field_value_for()`
   not gated on `label != not_available` — an unpublished/synthetic
   claim's date leaked even though its value/source were correctly
   hidden. Now gated identically to the other three fields.
3. **MEDIUM** — `GET /compare` (JSON) had zero UUID-shape validation;
   a malformed `pathway_id` crashed to an unhandled 500. `GET
   /compare/view` (HTML) already had this fix from the UX review, but
   the refactor that shared `assemble_comparisons()` between both
   routes never carried it to the JSON side. Now both return a clean
   422, matching `plans.py`'s established convention.
4. **LOW** — requesting the same `pathway_id` twice passed validation
   and silently rendered the same pathway twice as a fake comparison.
   JSON route now 400s; HTML route degrades to the existing friendly
   message.
5. **MEDIUM, test coverage** — no test authenticated as a reviewer
   against `/compare`/`/explore`/`/compare/view`. The reviewer role is
   the *only* one whose RLS-scoped client can fetch a draft claim row
   at all, so a guest-only test suite was only proving RLS filters
   correctly, never actually exercising `field_value_for()`'s own
   independent status re-check end-to-end. Added, mirrors the existing
   pattern in `test_api_eligibility.py`.
6. **MEDIUM, test coverage** — `/compare/view` (HTML) had no live
   regression pinning its draft/synthetic-claim protection, unlike the
   JSON route. Added.

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
now** — everything else is normal backlog. All engineering milestones
through M4 are done and genuinely verified (migration applied, zero
tests skipping). Candidates for what's next, all your call: more UI
screens (quick start, timeline/cost calculator, a reviewer console for
the publishing API — see `tasks/BCI-006.md`'s full "not done yet" list,
including that Playwright e2e still isn't wired), M5 (bounded AI), or a
content/design pass.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`). Schema `0001`/`0002`/`0003` all applied and verified — the full test suite is genuinely green with nothing skipping. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input
1. **Consent/safeguarding gate — see the ⚠️ section above.** Blocks
   item 2 below. Not blocking engineering elsewhere, but blocking any
   move toward public reachability.
2. **Public domain** — hold until item 1 is resolved. Once it is, send a
   domain/subdomain and I'll add an nginx site.
3. **Pilot state** — still assumed Gujarat, confirm or correct.
4. **Named content reviewers**, **Gemini model** — not blocking.

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
