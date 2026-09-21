# Decisions log — BCION Lite

Dated decisions with reasons. Newest first. A superseded decision is marked,
never deleted.

---

## 2026-09-21 — Component and state contract v1 frozen in docs/UI.md
**Event:** DESIGN-1 (Wave 1 design-docs lane) added "Component and state
contract v1" to `docs/UI.md`: a component inventory checked directly
against the real templates and `app/web/styles/input.css` (not the plan),
and a state-vocabulary table every screen follows from here on.
**Decision:** frozen as v1. Two findings adopted as decisions, not just
observations:
1. `.field-input` is the canonical input class going forward.
   `app/web/styles/input.css` had a second, older `.input` class (used
   only by `reviewer_sign_in.html`) whose padding computes to roughly
   42px — under the 44–48px touch-target minimum. Every new screen uses
   `.field-input`; migrating `reviewer_sign_in.html` off `.input` is a
   separate, small implementation follow-up, not done by this freeze.
2. Foreign-currency and visa display fields are explicitly **not in v1**.
   The 2026-09-21 scope-widening entry below added foreign pathways to
   pilot scope without schema support for their currency/visa fields;
   `docs/CONTRACTS.md`'s money section is still an empty skeleton. Until
   SCOPE-2/RULES-1 land a currency-aware component, a foreign pathway's
   out-of-scope fields are omitted or shown `not_available` — never
   rendered with a bare ₹ symbol as if domestic.
**Amendments:** v1.1 and later are additive only over this table, never a
silent rewrite of an existing row — reviewed the same way this freeze was.
**Also corrected in the same pass:** `docs/UI.md`'s "Component set" and
"Usability rounds" headings had gone stale (one claimed a freeze at "Step
7/M2" that never happened; the other still described round 1 as running
"before the comparison/cost engines are built," which stopped being true
once those engines shipped in BCI-006). Both fixed in place.

## 2026-09-21 — Rule approval lives in git JSON, not a database table —
## a stated deviation from build pack section 6
**Event:** the Wave 1 contract burst (`docs/CONTRACTS.md` "Rule approval
lives in git JSON") settled a conflict it found and flagged for the lead
to decide, rather than deciding it itself: build pack section 6 says
"Rule functions are reviewed, versioned and cite their source" without
specifying the versioning mechanism, and the existing `RuleSet`/case-table
design (`app/rules/`, `tests/unit/test_eligibility.py`) already stores an
exam's approved rule case table as a JSON file reviewed in a pull request,
not a database row.
**Decision:** keep it that way. A rule set's approved version is a
reviewed, committed JSON case table; `rule_version` on a `RuleSet` is that
file's own declared version string; changing a rule is a reviewed PR,
never a runtime edit through any console.
**Reason:** git already gives an immutable, attributable, diffable
approval trail for free. A `rule_versions` database table (as one reading
of build pack section 6 might imply) would need its own maker-checker
console, migration, and RLS policies for a mechanism this pilot's scale
does not need — 8-10 exams, each reviewed by a person before merge, not a
live-editable catalogue.
**What this does NOT change:** claims about facts (fees, eligibility
criteria's cited source, deadlines) still go through the real
maker-checker publishing workflow (`0003_maker_checker.sql`,
`app/api/claims.py`) exactly as before — this decision is scoped to the
rule *logic* (the Python function and its JSON case table), not the
factual claims that logic operates on.
**Deferred, not decided:** a formal `rule_versions` table remains possible
later (tracked as task RULES-18) if the pilot's scale or a reviewer
workflow ever needs it; nothing here forecloses that.

## 2026-09-21 — Guardian-consent gate mechanism decided and built —
## closes the CRITICAL gap flagged 2026-09-19, not yet fully live
**Event:** Owner decided the mechanism for the consent gate CLAUDE.md and
docs/SECURITY.md have called a launch gate since 2026-09-19 (see that
date's "M3 auth surface security-reviewed" entry below, finding #1): an
age gate on sign-up, and for anyone under 18, a guardian email that must
confirm via a separate emailed link before the account activates.
**Built:** `db/migrations/0004_guardian_consent.sql` (new
`student_accounts`/`guardian_consents` tables, RLS that denies the token
to every RLS-scoped client including the owning student, two
security-definer functions, two enforcement triggers — one of which is
defense-in-depth against a caller bypassing the application layer
entirely and calling Supabase's REST API directly with their own valid
token); `app/api/guardian_consent.py` (age arithmetic, the sign-in-time
enforcement point); `app/api/auth.py` (`date_of_birth` now required,
`guardian_email` required under 18); `app/notifications/` (new package,
a pluggable `EmailSender` mirroring `app/ai/`'s provider split —
`LoggingEmailSender` is what runs everywhere today, `SmtpEmailSender` is
real but unconfigured, gated exactly like `GeminiProvider`);
`app/web/consent_pages.py` (`GET /consent/confirm?token=...`).
**Named assumption:** 18 (India's legal majority age, Indian Majority
Act 1875) — no threshold was stated anywhere in the docs;
`app/api/guardian_consent.py`'s `MINOR_AGE_THRESHOLD_YEARS` is the one
place to change it. **Named, accepted residual gap:** date_of_birth is
self-declared with no identity documents (consistent with docs/
SECURITY.md's existing "no identity documents collected by Lite itself"
principle, not a new limitation) — a minor who independently discovers
Supabase's own profile-update API before their first sign-in could evade
ever getting a `student_accounts` row created; see
`app/api/guardian_consent.py`'s own docstring.
**Verified this session** (live, against the real but not-yet-migrated
project): `ruff`/`mypy` clean; `pytest tests/unit -q` 185 passed;
`pytest tests/db -q` 110 passed, 14 skipped (the new tests, correctly,
for the documented reason), 0 failed — no regression to any existing
live behaviour, adult sign-up/sign-in included.
**NOT done — explicitly out of this task's scope, both owner actions:**
(1) `db/migrations/0004_guardian_consent.sql` is NOT applied to the live
project — this session found no `DATABASE_URL` in its `.env` to apply it
via `scripts/apply_migrations.py`, and did not use the Supabase MCP tool
(off-limits for this project, see "Infrastructure accounts" below).
(2) No real email provider is configured anywhere — this task was
explicitly scoped not to sign up for or configure one, the same as
`GEMINI_API_KEY` needed the owner to provision Gemini. Until both are
done, `POST /auth/sign-up` refuses an under-18 sign-up outright (fails
closed, 503) rather than letting it through unprotected — see STATUS.md's
⚠️ section for exactly what each action unblocks.
**Owner action needed:** both of the above. See STATUS.md.

## 2026-09-21 — "No agent swarm" working rule removed: parallel
## multi-agent workflows allowed
**Event:** Owner instructed, directly, to remove the "No agent swarm" rule
from `CLAUDE.md`'s working rules, alongside a request to plan and run the
remaining build with as many parallel agents as useful.
**Reason:** owner's call — speed to the first phase, with quality kept by
review passes rather than by limiting concurrency.
**What replaces it:** one bounded task per *agent* (not per session);
parallel implementers only on disjoint files in separate worktrees; never
parallel edits to a migration, lockfile or shared schema; the lead session
verifies (runs the suite itself) and merges. These guardrails are the build
pack's own section 7 "Agents" conditions, kept — only the concurrency
ceiling ("lead plus one specialist" by default) is lifted.
**What this does NOT change:** every non-negotiable in `CLAUDE.md`; "no
whole-product attempts"; no student data to development agents; reviewer
agents stay read-and-test-only. The build pack's section 7 text still says
"default concurrency: lead plus one specialist" — superseded by this entry
per the conflict order, not edited (that file mirrors the online doc).

## 2026-09-21 — Pilot scope widened: all-India admission rules, foreign
## pathways for Indian students added — supersedes the one-state build pack
**Event:** Owner decided, in response to a direct question, to widen Lite's
scope beyond `docs/BCION-Lite-Build-Pack.md` section 2 as originally written:
1. **Admission rules go all-India**, replacing "one state, in detail
   (Gujarat if confirmed)". The build pack's "Left out" list explicitly named
   "national coverage" as out of scope for the pilot — that line is now
   superseded and removed.
2. **Foreign/study-abroad pathways for Indian students are new pilot scope**
   — not present anywhere in the original build pack, data model, or DPR
   Lite tab. Previously undiscussed.
**Reason:** owner's direct call on pilot ambition, not a technical finding.
**What this does NOT change (not asked, not assumed):** the 10–100
user/25-session load ceiling; the 20–30 career-family and 50–100
programme-record ceilings; the AI/consent/publishing non-negotiables in
CLAUDE.md; the FastAPI/Supabase/no-Next.js stack pin. These ceilings were
sized against a one-state pilot — all-India admission rules alone (36
states/UTs, each with its own board, counselling body and quota rules) is a
materially larger sourcing/verification workload than the build pack's
12-week schedule assumed, and foreign pathways add a second content
category (foreign fee currencies, visa/entry requirements, non-Indian
source verification) with no schema support yet. **Flagging for the owner,
not deciding unilaterally:** the career-family/programme-record ceilings
and the 12-week/16-step schedule in build-pack section 9 likely need
revisiting given this scope; not touched here since that wasn't asked.
**Owner action needed:** confirm whether the pilot's numeric ceilings
(career families, programme records, timeline) should also change, or
whether all-India + foreign scope is meant to be phased in gradually within
the existing ceilings (e.g. widen state coverage incrementally rather than
all 36 at once).

## 2026-09-20 — Migration 0003 applied: M4 genuinely verified, 4 real test
## bugs found and fixed (none in the trigger/migration itself)
**Event:** Owner applied `db/migrations/0003_maker_checker.sql` to the
live Supabase project. Every test in `tests/db/test_maker_checker.py`
and `tests/db/test_api_claims.py` that had been correctly *skipping*
(per `tests/db/conftest.py`'s established skip-if-not-applied pattern)
ran against real enforcement for the first time. Result: the
`enforce_claims_workflow` trigger and the tightened
`claims_update_reviewers` RLS policy both work exactly as designed —
every failure found was in test fixtures that had never been exercised
live, never in the migration/trigger logic they were testing.
**Bugs found and fixed:**
1. Two tests set `superseded_by` / `created_by` to a fabricated random
   UUID. Both are real foreign keys (`superseded_by → claims(id)`,
   `created_by → auth.users(id)`, `0001_init.sql`) — a made-up id fails
   that constraint before the trigger under test is even reached. Fixed:
   a real replacement claim for `superseded_by`; `None` (the column is
   nullable) for `created_by` where authorship wasn't the thing being
   tested.
2. Two tests' cleanup deleted a "replacement" claim before the claim
   referencing it via `superseded_by` — Postgres's default `NO ACTION`
   (not `CASCADE`) on that foreign key blocks deleting a still-referenced
   row. Fixed by reordering cleanup: delete the referencing row first.
3. `tests/db/test_api_claims.py` used a `second_reviewer` fixture defined
   only inside `tests/db/test_maker_checker.py` — a pytest fixture
   defined in one test file is invisible to every other file (the same
   class of scoping mistake `tests/db/conftest.py`'s own docstring
   already warns about for hooks specifically). Invisible while every
   test using it was being skipped; surfaced the moment skipping stopped.
   Fixed by moving `second_reviewer` to `tests/db/conftest.py`, alongside
   `reviewer`/`student_a`/`student_b`, where it always should have lived.
**Reason this is worth recording, not just fixing quietly:** none of
these four bugs were catchable by reading the code, lint, mypy, or
`pytest --collect-only` — they only exist at the intersection of "this
specific test actually runs" and "this specific foreign key or
fixture-scoping rule applies." This is precisely why `tasks/BCI-005.md`
said explicitly not to treat M4 as verified until the migration landed
and these tests were rerun green — that caveat wasn't hedging, it
identified a real, specific class of bug that then actually occurred.
**Result:** 213 tests passing, zero skipping — the first time this
project's full suite has been completely green with nothing waiting on
anything.
**Owner action needed:** none.

## 2026-09-20 — Dangerous URL scheme could reach an evidence link
## (`javascript:`/`data:`), fixed independently in two places
**Event:** A concurrent session's security review confirmed (adversarial
verify, all votes survived) that nothing validated the URL scheme on
`Source.official_url` before it was rendered into `href="{{ ... }}"` in
`_trust_badge.html`. Jinja's autoescape only HTML-entity-escapes; it does
not block a dangerous scheme. A `Source` row with
`official_url="javascript:alert(document.cookie)"` renders as a fully
clickable, script-executing link on the evidence badge — reproduced
live. Sources are reviewer-write-only today, so this needs a malicious
or compromised reviewer credential to set, but that is exactly the
"trusted-role write reaches render with no independent check" shape as
the maker-checker bugs already fixed this session, and gets worse once
M4's AI-extraction pipeline can populate a URL that no human has
scrutinized yet.
**Fixed in two places, independently, because the URL is built twice**:
`app/planning/comparison.py`'s `field_value_for()` (which
`app/api/compare.py` depends on) by the reviewing session, and
`app/api/eligibility.py`'s own separate `_safe_source_url()` helper by
this session — `check_eligibility` builds its source data directly
rather than going through `field_value_for()`, so one fix did not cover
the other. Both use the same pattern: a non-`http(s)` scheme degrades to
`None`, the same "unavailable" treatment already used for a missing or
unpublished source, rather than rendering the value.
**Owner action needed:** none.

## 2026-09-19 — M3 auth surface security-reviewed: one flagged gate, three
## bugs fixed
**Event:** A full read-only security review of M3's sign-in/saved-plans/
guest-migration surface (`app/api/auth.py`, `app/api/plans.py`,
`app/api/deps.py`, `db/migrations/0002_saved_plans.sql`), run against the
live Supabase project — header/response inspection, live probes beyond
the committed test suite (spoofed `student_id` insert, cross-user
delete, reviewer-vs-plan access), not a static read of the diff.
**Verified correct, no findings**: the full guest/student A/student
B/reviewer access matrix on `saved_plans`; the `saved_plans_own_row` RLS
policy genuinely matches `student_profiles`'s pattern with no reviewer
override; the guest→account pending-plan migration fix is correct end to
end and no client-suppliable field can attribute a plan to a different
student; `require_auth` coverage is complete across `plans.py`; the
`client.postgrest.aclose()` cleanup introduces no use-after-close bug.
**Findings, ranked:**
1. **CRITICAL, flagged not fixed — a human decision, not code.**
   `POST /auth/sign-up` has no age or consent gate at all: no birth-year
   field, no consent flag, nothing that disables a real minor's account.
   BCION Lite's primary user population is Class 8–12 students, i.e.
   minors. CLAUDE.md's non-negotiable ("real minor accounts stay
   disabled until the consent and safeguarding workflow is reviewed by a
   person") is not yet met, and this is not hypothetical — it's live
   code, already deployed to the Oracle VM. **Mitigating factor**: the
   VM is not yet publicly reachable, so today's actual exposure is
   limited to whoever already has VM access. **This is now recorded as a
   hard blocker on the pending "public domain" request** (see STATUS.md)
   — do not expose this publicly until resolved, whether via a real
   consent flow or an interim gate (e.g. invite-only sign-up for the
   pilot cohort). Both sessions working this repo flagged this to the
   owner independently and in parallel, on purpose — this is exactly the
   class of decision CLAUDE.md reserves for a person, not an agent.
2. High: the guest→account migration's deliberate "never fail sign-up
   over a bad plan" exception-swallow logs nothing anywhere. The exact
   failure it was designed to survive (a bad insert) already happened
   once this session and was only caught by hand-running a live test —
   a recurrence in production would be invisible. Not yet fixed.
3. Medium: `save_plan`'s catch-all mislabelled a nonexistent
   `pathway_id` (a foreign-key violation) and a malformed UUID as
   "already saved" (409) — only the genuine duplicate case matched that
   message. Fix owner: whichever session gets there first; check
   `git log` before assuming.
4. Medium: `PATCH`/`DELETE /plans/<malformed-id>` crashed to an
   unhandled 500 instead of a clean 404/422 — no UUID validation on the
   path parameter. Same fix-owner note as above.
5. Low/informational: a measured ~100–130ms timing gap between
   wrong-password and nonexistent-email on sign-in, plausibly from
   Supabase Auth's own bcrypt-only-if-the-account-exists behavior (not
   this repo's code). Not a mandatory fix at pilot scale; noted for
   awareness given the student population.
6. Low, test-coverage gap: no delete-cross-user or reviewer-vs-
   `saved_plans` test existed in the committed suite, despite both being
   correct when probed live. Recommended as permanent regression tests.
**Owner action needed:** decide on the consent-gate question (finding 1)
before agreeing to any public-domain/nginx request.

## 2026-09-19 — Maker-checker enforced server-side (M4 first slice,
## BCI-005): migration written, not yet applied
**Decision/event:** `db/migrations/0003_maker_checker.sql` closes the
exact gap `0001_init.sql`'s own comment flagged at M1: a claim can no
longer be inserted directly as `published` (must always start `draft`),
the author of a claim can never approve their own (`reviewed_by` must be
set and distinct from `created_by`, enforced by a trigger — RLS's
`using`/`with check` alone can't compare OLD vs NEW rows the way the
transition/immutability rules need), and a `published` claim's recorded
content is frozen — the only legal move is to `superseded`, paired with
a brand-new claim for the correction, never an in-place edit of a fact
already shown to a student as verified. `service_role` is exempt,
mirroring exactly what RLS already grants that role, so every existing
test fixture across the repo that seeds pre-published claims directly
keeps working unchanged. 12 new live tests
(`tests/db/test_maker_checker.py`) prove the full state machine;
correctly skip until the migration is applied.
**Reason:** CLAUDE.md's first non-negotiable: "Unapproved facts never
reach public results (maker-checker, enforced server-side, not by a
button)." This has been a documented, unenforced gap since M1.
**Known limitation, not fixed here:** `created_by`/`reviewed_by` are not
yet forced to equal the authenticated caller at the database level
(`created_by = auth.uid()`) — the publishing-console API that will
actually set these fields doesn't exist yet, so hardening this now would
be premature and untestable against real usage. Tracked in
`tasks/BCI-005.md` for whoever builds that API next.
**Owner action needed:** apply `db/migrations/0003_maker_checker.sql`
via the SQL Editor or `scripts/apply_migrations.py`, same process as
`0002`. Deliberately not applied by any agent — schema changes go
through the owner's own project only, never an agent's management-API
access (this session's Supabase MCP tool was available and was not used
for this, on purpose).

## 2026-09-19 — Supabase client-sharing fix: security-reviewed, two follow-up
## fixes applied
**Event:** `app/db/client.py`'s `get_anon_client()` was `@lru_cache`d, so
every request — guest and authenticated alike — shared one `Client`
object; `get_user_scoped_client()` mutated *that same shared object's*
postgrest auth header on every call. Under real concurrent requests this
is a genuine cross-user data-leak vector: one request's auth token could
be overwritten by another's before the first request's query executed,
or a guest request could silently inherit a previous request's
authenticated token instead of anonymous/RLS-restricted access. Found
and fixed same-day (commit `95b70f0`) while starting M3's auth work;
affected every route already shipped (compare, eligibility), not just
the new sign-in work that surfaced it.
**Fix:** every call to `get_anon_client()` / `get_user_scoped_client()`
now constructs a genuinely fresh, unshared `Client`. No caching.
**Independently reviewed** by this repo's `data-security-reviewer`
agent, invoked by a concurrent session specifically because CLAUDE.md's
non-negotiable requires cross-user access to be tested on every
auth/RLS change. The review verified the fix live against the real
Supabase project (header inspection via httpx event hooks, plus a
200-call/50-thread concurrency stress test against the actual client
functions — zero cross-contamination) and confirmed no remaining
cross-user leak path. It also surfaced two real follow-up issues, both
fixed same-day:
1. **Unclosed `httpx.Client` per request** — a fresh, unshared client is
   correct for isolation but nothing was closing the underlying
   connection pool afterward, relying on GC (which never proactively
   closes sockets). `app/api/deps.py`'s `get_db_client` and
   `require_auth` are now `yield`-based FastAPI dependencies that call
   `client.postgrest.aclose()` in a `finally` block after the response.
2. **Test coverage gap** — `tests/db/test_client_isolation.py` originally
   only asserted `a is not b` (distinct objects), which would still pass
   if some future change reintroduced sharing one level down (e.g. a
   shared mutable headers dict). Strengthened to assert the actual
   `Authorization` header value each client carries, plus a
   `ThreadPoolExecutor`-based concurrent smoke test.
A third finding — `Settings` (`app/core/config.py`) is cached but wasn't
`frozen=True`, so its safety rested on convention (nothing mutates it)
rather than enforcement — is now fixed: `frozen=True` added, so any
future mutation attempt fails loudly instead of silently corrupting the
process-wide cached instance.
**Not a finding, pre-existing and already self-disclosed**: the
maker-checker gap in `db/migrations/0001_init.sql` (author-cannot-
approve-own-claim) remains explicitly deferred to M4, unrelated to this
fix.
**Owner action needed:** none.

## 2026-09-19 — Reservation/quota engine: out of scope for Lite
**Decision:** No reservation/quota engine (state-quota, category-wise
seat-reservation percentages) is built for BCION Lite. `docs/rules/`
stays at the three engines the Lite Build Pack §6 rules contract
actually names: eligibility, cost, timeline.
**Reason:** `docs/ARCHITECTURE.md`'s directory comment for `app/rules/`
lists "eligibility, cost, timeline, reservation" — but that comment
describes the *national* DPR's full decision-engine set
(`docs/BCION-DPR-v1.1.md`), not a commitment Lite's own build pack made.
Lite Build Pack §6 ("Data and rules contracts") only specifies
eligibility, timeline and cost; reservation/domicile rules in the
national DPR carry state-specific legal review and quota complexity
(see `docs/BCION-DPR-v1.1.md`'s reservation/domicile risk entries) that
is explicitly national-platform scope, not Phase −2 pilot scope
(CLAUDE.md: "a technical spike and measurement instrument, not the
national platform"). Building it now risked scope creep with no product
owner sign-off.
**Owner confirmed:** leave it out of Lite; revisit only if a future
national-platform phase needs it.
**Owner action needed:** none. If this changes, update this entry and
`docs/ARCHITECTURE.md`'s `app/rules/` comment together so they stop
disagreeing.

## 2026-09-19 — DPR annex structure reconciled with the online v1.2 doc;
## new `docs/BCION-Lite-Build-Pack.md` is now Lite's operating spec
**Decision/event log:** The living Claude Doc ("BCION — DPR and White Paper
v1.1") was restructured upstream (its "v1.2" tab) since this repo's
`docs/BCION-DPR-v1.1.md` was written: the old Annex C (10–100 user pilot
review), Annex E (Claude Code execution blueprint) and Annex F (step-by-step
build guide) were consolidated into one companion document, the "Lite build
pack" tab, and Annex C/D were repurposed to a Glossary and an Assumptions
register respectively; Annex F no longer exists as a separate annex.
`docs/BCION-DPR-v1.1.md` has been updated to match: its old Annex C/D/E/F
content (the "Problems" review tables reasoning from the four original
source documents to the adopted decisions) is removed from the live file —
fully recoverable from git history before this commit — and replaced with
the new Annex C (Glossary), Annex D (Assumptions register) and a short
Annex E pointer. The full Lite operating plan (scope, stack, interface
brief, data contracts, operating rules, data-flow map, 16-step schedule,
budget, gates, Step 1 prompt, daily prompts) now lives in the new
`docs/BCION-Lite-Build-Pack.md`, mirroring the online doc's "Lite build
pack" tab word for word (including the Gemini/Mumbai infra confirmations
synced into that tab the same day). `CLAUDE.md`'s Mission and Links
sections were updated to point at the new file.
**What this changes:** Citations to "Annex C.2/C.3", "Annex D.2/D.3",
"Annex E.2/E.3/E.5/E.6" and "Annex F/F.2/F.3/F.4" scattered through
`docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/UI.md`, `docs/DATA.md`,
`docs/SECURITY.md`, `STATUS.md`, `tasks/BCI-001.md`, `tasks/BCI-002.md`,
`app/ai/__init__.py`, `app/db/client.py`, `app/db/__init__.py`,
`app/rules/__init__.py`, `app/data/models.py`, `db/migrations/0001_init.sql`,
`Makefile`, `.github/workflows/ci.yml` and the `.env*` comments now point
at annex sections that hold different content (C, D) or no longer exist
(F). The facts those citations describe are still correct and now live in
`docs/BCION-Lite-Build-Pack.md`'s numbered sections (3 Decisions, 4 Stack,
5 Interface brief, 6 Data and rules contracts, 7 Operating rules, 8
Data-flow map, 9 Master schedule, 12 Gates, 14 Step 1 prompt) — only the
citation labels are stale, not the content they point to.
**Status:** `docs/BCION-DPR-v1.1.md`, `docs/BCION-Lite-Build-Pack.md` and
`CLAUDE.md` done. The ~15 files listed above are **not yet updated** —
deliberately paused for owner confirmation before touching application
source code, CI config and env-file comments, particularly since the
GitHub-connection entry below shows another session concurrently active
on this same repo.
**Owner action needed:** say go-ahead (or hand-pick which files) to sweep
the remaining stale annex citations; each is a label-only fix (low risk,
git-reversible) but several are source files a concurrent session may
also be touching right now.

## 2026-09-19 — GitHub repo connected; two exposed secrets rotated
**Decision/event log:** Owner gave the repo URL
(`github.com/sheelajindal07-collab/eduvation`); this machine's account
(`maheshjin-bot`) had no access, so the owner sent a collaborator invite,
which was found and accepted via `gh api` (not the web UI), then all
commits were pushed. First CI run failed on a real, previously-unseen bug
(`setuptools` flat-layout package discovery choked on `db/` existing
alongside `app/` — never triggered locally since the editable install
had only run once, before `db/` existed); fixed with an explicit
`[tool.setuptools.packages.find]`, reproduced and re-verified the fix
locally before pushing, CI green on the next run. Owner then confirmed
rotating the two secrets pasted in chat earlier (JWT secret, service-role
key) — re-ran `make test-db` afterward and all 9 tests still pass,
confirming the new values are correctly in the owner's local `.env`.
**Status:** Done. Repo live with passing CI; no known exposed secrets
remain live.

## 2026-09-19 — Supabase project: "project education" (Singapore) not used;
## a fresh Mumbai (ap-south-1) project will be created instead
**Decision:** The owner showed an existing Supabase project, "project
education" (org "education", free tier, `ap-southeast-1` / Singapore,
ref visible as `auxdtzizsdjjgmksaiur` — unverified transcription from a
screenshot; re-confirm before relying on it for anything). Given the
choice between keeping it or creating a fresh India-region project, the
owner chose to create a new one in `ap-south-1` (Mumbai), matching
`docs/SECURITY.md`'s residency table. `project education` is **not**
used for BCION Lite and was not touched.
**Status:** DONE. Owner created a new project, also displayed as "project
education" (same org, confusingly the same display name as the Singapore
one — they are different projects) but region **South Asia (Mumbai),
ap-south-1**, compute `t4g.nano`. Project URL (from a screenshot,
re-verify against your own dashboard if anything seems off):
`https://bvacroguuhgqufelascd.supabase.co`. Status "Healthy", no
migrations applied yet, no repo connected, no backups yet — a genuinely
fresh project.
**Owner action needed next:** apply `db/migrations/0001_init.sql` via
this project's SQL Editor (paste the file's contents, click Run), then
put `SUPABASE_URL=https://bvacroguuhgqufelascd.supabase.co` plus the
anon/publishable key and JWT secret (Project Settings → API Keys) into
your own local `.env` — keys never shared in chat.

## 2026-09-19 — Migrations applied via a direct script, not the dashboard
## or the MCP tool, going forward
**Decision:** Owner applied `0001_init.sql` manually via the SQL Editor
once, confirmed working (all 9 RLS tests pass live), then said not to
require that manual step again. Since the Supabase MCP tool and any
equivalent management-API route are both off-limits (per the earlier
"Infrastructure accounts" entry), the alternative is a direct Postgres
connection: `scripts/apply_migrations.py`, using `psycopg` and a
`DATABASE_URL` the owner puts in their own `.env` — never in chat, never
committed. It tracks applied migrations in a `_schema_migrations` table
so re-running is safe. This is fully auditable (it's ~80 lines, read
top to bottom) and touches only the one database `DATABASE_URL` points
at — categorically different from a broad management-API/MCP capability.
**Status:** Script written, lint/typecheck clean. Not yet run (no
`DATABASE_URL` in `.env` yet) — `0001_init.sql`'s effects already exist
in the database (applied manually), so the first real run needs to
record that fact in `_schema_migrations` rather than re-apply it (see
`db/migrations/README.md` "One-time bootstrap note").
**Owner action needed:** add `DATABASE_URL` to your local `.env`
(Project Settings → Database → Connection string → URI, password filled
in yourself) whenever you're ready for me to apply future migrations
directly instead of using the SQL Editor.

## 2026-09-19 — AI provider naming fixed: Gemini, not a stale Anthropic
## field name left over from the original (superseded) assumption
**Decision:** `app/core/config.py`'s `anthropic_api_key` field and
`ai_provider` default were still "anthropic" even though the Gemini
decision (above) was recorded the same day — an inconsistency between
the docs and the code. Renamed to `gemini_api_key` / default `"gemini"`;
`.env.example` and `app/ai/__init__.py`'s docstring updated to match.
Caught while fixing `tests/unit/test_health.py` (below), not something
the owner had to flag separately.
**Status:** Done. No behaviour change (M0–M4 make no AI calls either way).

## 2026-09-19 — GitHub: owner will create the repo on their own account
**Decision:** The owner is on a GitHub account different from this
machine's authenticated `gh` CLI (`maheshjin-bot`) and has no repo yet.
They'll create one themselves (private, e.g. `bcion-lite`) and set up
push credentials for that account on this machine (e.g. a personal
access token via `gh auth login` or a credential-manager entry) — I will
not use the `maheshjin-bot` session for this project.
**Status:** Waiting on the repo URL + local credentials being ready.
**Owner action needed:** create the repo, tell me the URL, and confirm
push access works locally (or say if you'd like help setting up the
credential once the repo exists).

---

## 2026-09-19 — Infrastructure accounts: owner-provided, separate from this
## machine's connected tools; MCP/CLI management tools not used for them
**Decision:** The owner confirmed Supabase, GitHub, Oracle hosting and a
Gemini API key are ready to use — but on accounts **different** from the
ones already authenticated in this dev session (GitHub CLI was signed in
as `maheshjin-bot`; the session's Supabase MCP tool only saw an org named
`ridhivi` with unrelated projects and no free-project slot). The owner
explicitly said to use different accounts and **not to use the Supabase
MCP tool** for this project.
**What this changes:**
- No project was created and nothing was touched in the `ridhivi`
  Supabase org or under `maheshjin-bot` on GitHub (checked read-only:
  `list_projects`/`list_organizations`/`get_cost`/`confirm_cost` — no
  write action was taken before the instruction arrived).
- Supabase schema work proceeds as **versioned SQL migration files in the
  repo** (`db/migrations/`), for the owner to apply via their own
  project's SQL editor or the Supabase CLI — not applied by an agent
  through the management API.
- GitHub remote/push is deferred until the owner gives a repo URL (their
  own account) or says to create one there.
- AI provider: "Gemini API ready" is read as Google Gemini; the adapter
  interface is written provider-agnostic regardless (per Annex E.2), so
  this costs nothing to get right or wrong before M5.
- Oracle hosting: noted ready; specifics (region, compute shape, whether
  Docker is already installed) are gathered when deployment work starts
  (M6 / Annex F Step 13-14), not blocking now.
**Status:** Confirmed by owner. Supersedes the 2026-09-19 "Hosting ...
not yet provisioned" entry below for account *availability*, but not for
account *identity* — real URLs/keys are still not in this repo and still
won't be; only `.env`, never committed (`CLAUDE.md` non-negotiable).
**Owner action needed:** when ready, give (a) the GitHub repo URL to push
to (or "create one, here's the account"), and (b) confirm Gemini vs a
different provider. Supabase project URL/keys go straight into your own
local `.env` — never paste them into chat.

---

## 2026-09-19 — Stack pinned to FastAPI/Supabase/VPS (not Next.js/Vercel)
**Decision:** Use the Annex E.2/F.2 pinned stack (FastAPI monolith, Supabase
Mumbai, Tailwind + server-rendered templates or a light PWA, one VPS worker,
n8n off the request path) as the default for this repo.
**Reason:** Annex F.2 states one condition for using Next.js/Vercel instead:
the owner intends Claude Code (not themself) to remain the front-end
maintainer long-term and wants per-PR preview deployments. That condition
has not been stated by the owner. The pinned stack is also runnable and
testable without a paid hosting account (local `uvicorn`, local/staging
Postgres), which fits where this project currently is (pre-provisioning).
**Status:** Assumption — flip only via an explicit owner instruction,
recorded here.
**Owner action to confirm or flip:** none needed to keep this; say so
explicitly to switch to Next.js/Vercel.

## 2026-09-19 — Pilot state: Gujarat (assumed, pending confirmation)
**Decision:** Draft/scaffold content assumptions (admission body names,
CET name) around Gujarat: GSEB, GUJCET, ACPC (engineering/pharmacy),
ACPUGMEC (medical), GCAS (general degree) — names to be verified against
current official sources before any content is published.
**Reason:** Annex C.2, problem #8 names Gujarat as "the natural choice for
a Surat-based builder," explicitly "if confirmed." No confirmation has been
given yet.
**Status:** Assumption, [PA]. Does not block M0 (no real content is
published at M0). **Must be confirmed before the content track starts
writing real Gujarat-specific admission rules (Annex F.4, alongside Step 1,
week 1).**
**Owner action needed:** confirm Gujarat, or name a different pilot state.

## 2026-09-19 — AI provider: Anthropic Claude API (assumed)
**SUPERSEDED same day — see below.** Original text kept for the record:
implement the AI provider adapter (`app/ai/`) against the Anthropic
Messages API first, behind a provider-agnostic interface. Reason: no
provider was specified in the annexes beyond "one hosted model behind a
provider adapter"; Anthropic was the reasonable default in a Claude Code
project.

## 2026-09-19 — AI provider: Google Gemini API (owner-confirmed)
**Decision:** Owner confirmed "Gemini API ready." Adapter
(`app/ai/`, built at M5) targets the Gemini API as the first
implementation, behind the same provider-agnostic interface — swapping
providers later stays a small, contained change.
**Status:** Confirmed. Still does not require a live key until M5;
M0–M4 make no AI calls.
**Owner action needed:** none, unless you want a specific Gemini model
pinned (e.g. flash vs pro) ahead of M5 — otherwise that's chosen at M5
based on the cost/latency numbers at the time.

## 2026-09-19 — Hosting/Supabase/n8n/WhatsApp: not yet provisioned
**PARTIALLY SUPERSEDED same day** — see "Infrastructure accounts" entry
above. Supabase and Oracle hosting are confirmed ready by the owner (on
accounts separate from this session's connected tools, which must not be
used to manage them). n8n and WhatsApp Cloud API status is still
unconfirmed. Original text kept for the record: all external accounts
were assumed not yet provisioned, built to run and test locally
(`uvicorn`, pytest, ruff, mypy) without requiring any of them; reasoning
was that Annex C/E/F's cost tables read as if a VPS, a Supabase project
and WhatsApp access already existed for "a builder who runs FastAPI,
Supabase, n8n and the WhatsApp Cloud API" with nothing in this repo
confirming that for *this* project.
**Still open:** n8n instance status; WhatsApp Business/Cloud API status;
Oracle hosting specifics (region, compute shape, Docker availability) —
gathered at the deployment milestone (M6), not blocking now.

## 2026-09-19 — Named fact reviewers: not yet assigned
**Decision:** The publishing console (maker-checker) is built so that ANY
two distinct accounts can act as maker/checker; no specific person is
hard-coded. Real content review capacity (who actually verifies the 50–100
programme records, 8–10 exam rule sets, 10–20 scholarships) is an open
owner decision, tracked in `STATUS.md`, not blocking M0–M3 engineering.
**Reason:** Annex C's Owner Checklist before M0 lists "pilot scope and the
named fact reviewers" as an owner decision; Annex C's Problem #2 says the
content track (not the code) is the actual long pole.
**Owner action needed:** name who verifies content (yourself, an editor,
a small reviewer pool) before Week 1 of the content track in earnest.

## 2026-09-19 — Repository and version control
**Decision:** Git-initialised in place (`F:\the competetion project`),
branch `main`. No remote configured. The dev machine's GitHub CLI is
signed in as `maheshjin-bot`, but the owner uses a **different** GitHub
account for this project — that account was not used or touched.
**Reason:** Annex E.4 owner checklist item ("repository location and
branch permissions"); the working directory was already given.
**Owner action needed:** give the target repo's URL (existing empty repo)
or say "create one" plus which account, so a remote can be added and
`.github/workflows/ci.yml` starts running.
