# Decisions log — BCION Lite

Dated decisions with reasons. Newest first. A superseded decision is marked,
never deleted.

---

## 2026-09-22 — Phase 1a inserted: an AI-only build phase, with three rules on every AI card
**Decision (owner, in chat, 2026-09-22):** "Phase 1a should only AI
implementation"; "fast reliable quality, more work in less time"; "AI has
to give correct answers, no speculation, no maybe"; "every AI call should
be reviewed/verified two times"; "we are using free Gemini". The lead
turned this into `docs/plan/phase-1a-ai.md` (lead-only) and a pointer
section in `docs/DEVELOPMENT-PLAN.md` section 4.
**What this changes:**
- Phase 1a runs **alongside** Phase 1 (owner clarification, same day:
  "start separately, without touching Phase 1, add it when ready"). AI
  cards touch no Phase 1 file, merge to `main` behind `AI_ENABLED=false`
  as each goes green, and the module is "added" by flipping the flag on
  staging after the plan's exit gate (AI-12). The 6-lane cap is shared;
  Phase 1's exit gate is unchanged and it loses at most the two AI-4
  migration days. A long-lived integration branch was rejected: same
  isolation, plus a big-bang merge.
- The cuts-and-moves row "All AI tasks except AI-2 ... Phase 2" is
  superseded. AI-14 (extraction drafts) is un-dropped — a D16 change; it
  still can never publish (the DB rule from 0001/0003 stands).
- Four cards added: AI-14 (rescheduled), AI-18 next-steps template, AI-19
  what-changed summary, AI-20 Hindi content drafts. All run the same
  two-pass shape and the same "code renders, model only selects" rule.
- Migration ledger: AI-4 takes **0011**; PUB-2 0012, PUB-3 0013, SEC-6
  0014, CONSENT-4 0015. Reserved at session open, as always.
- Rule 1, correctness: the model never authors a sentence; a banned-phrase
  unit test (hedges, guarantees, rank and personality language, in
  English, Hindi and Hinglish) fails the build.
- Rule 2, double verification: every runtime answer = a selection call +
  an adversarial verification call over the selected ids only, then code
  validation; disagreement → refusal. Reviewer-facing calls (extraction,
  Hindi drafts) do the same and then go to a human.
- Rule 3, free tier: accepted only because no student-typed text leaves
  the server (enforced by an outbound allow-list test). The follow-up
  field is not built until CONSENT-7 exists and a paid, no-training tier
  is chosen. Quota errors = cap hit, no retry.
**Still needs the owner's explicit yes (plan section 8a):** P1a-1 run it
alongside under the shared cap, flag-gated; P1a-2 the 0011 slot; P1a-3 the free-tier acceptance with the
AI-10 facts; P1a-4 live answers for guests on dev/staging keyed on the
guest-session id; P1a-5 AI-14 un-dropped. Provisional 24-hour defaults
(8b): flash model, caps, fixed prompts only, i18n-key Hindi, email
alerts, SDK kept, pasted-text extraction.
**Status:** Planned, not started. No code changed in this entry.

---

## 2026-09-22 — RULES-9: a second invented claim convention (timeline stages), plus real database-backed prefill
**Event:** `app/planning/timeline_assembly.py`'s `stages_from_claims()` reads a
pathway's published timeline stages from claims for the first time. As with
RULES-8's `rule_key`, **no stage-claim convention existed anywhere in this
codebase** (`db/migrations/*.sql`, `docs/DATA.md`) — invented here, documented
in the module rather than guessed silently: one atomic claim per fact, same
"atomic field, not a JSON blob" shape every other engine already uses
(`minimum_age`, `verified_charges`, RULES-10's `fee_component:<name>`):
```
stage:<order>:name                         str, required for the stage to exist at all
stage:<order>:duration_weeks                int, whole weeks
stage:<order>:kind                          "required" | "optional" (never "user_assumption")
stage:<order>:overlap_weeks_with_previous   int, defaults to 0
```
`<order>` is numeric and fixes the resulting `Stage` list's own sequence — unlike
`fee_component:*` (alphabetical, no inherent order), a stage's position decides
what `overlap_weeks_with_previous` even means. A published `name` with an
unpublished `duration_weeks` still produces a real `Stage` — the student sees
the stage exists, its duration honestly marked unknown — through the same
`field_value_for()` gating every other engine in this codebase already uses.
**Recording this alongside RULES-8's `rule_key` entry**: two Rules-adjacent
tasks in one day both had to invent a content convention nobody had written
down. Whoever builds content-authoring tooling next needs to reconcile (or
deliberately reject) both.
**`compute_timeline()` hardened**: a negative duration or overlap now raises a
new `TimelineValidationError(ValueError)` — a `ValueError` subclass so every
existing `except ValueError` keeps matching, while the API/web layers now
catch the specific name. Maps to a clean 400 on `POST /timeline`, a friendly
styled alert on the HTML page. `0` stays valid (an "instant transition" stage).
**`GET /timeline/view?pathway_id=X` now does real work**, not just the
display-only echo UI-7 added and explicitly flagged as its own follow-up: a
genuine database-backed fetch of the pathway's name and published stages,
pre-filling the calculator. Degrades to the existing friendly DB-unavailable
message when Supabase isn't reachable — the calculator still renders and
works, blank, matching every other screen's established convention. `POST`
stays fully stateless; no new database dependency there.
**No second duration-formatting helper was added.** `app/i18n/formatting.py`'s
`format_duration_weeks` already was the "weeks → about N years M months"
helper the card asked for; new tests pin its exact rounding at the five
required boundary cases (0, 51, 52, 53, 260 weeks) rather than duplicating it.
**Verified live:** `tests/unit` 981 → 1020 passed; `tests/db` 574 → 579
passed, 8 xfailed, 0 skipped, 0 failed — run in the implementer's own
worktree and again against the shared local stack after merge.

## 2026-09-22 — UI-7: timeline stage kinds, "Revise this scenario" never framed as a failure
**Event:** `app/rules/timeline.py`'s `Stage` gains an optional `kind` field
(`"required" | "optional" | "user_assumption"`) plus a `display_kind` property
that falls back to the existing two-way `required` bool for every `Stage`
built before this field existed — purely additive; `compute_timeline()` never
reads it, so it can never change a total, and the JSON API's
`StageIn`/`StageOut` (`app/api/timeline.py`) are untouched. The timeline
calculator now shows each stage's kind as a text+icon badge (never colour
alone) and adds "Revise this scenario": a second submit button that appends
one bounded (max 6) "extra attempt" row, tagged `user_assumption`, styled and
worded as a normal part of planning rather than a setback — no failure
badge, no "you failed" language (`docs/UI.md`'s own explicit rule). The new
row is already named the moment it's added, so it's a real stage — which
means `compute_timeline`'s existing "any unknown duration makes the total
unknown" rule already covers it correctly with no special-casing.
**A real discrepancy found, not assumed:** the task card's premise was that
`GET /timeline/view` already accepted `pathway_id` for pre-fill. It did not —
that was a planned line in the pre-plan inventory that was never actually
implemented. Added `pathway_id`/`pathway_name` as an optional, **display-only**
pair (no database lookup — this module still has zero `Depends(get_db_client)`
anywhere) rather than wiring a real lookup, since the card's own scope says
"no data dependency" and no screen currently links here with a pathway
context to test against. Wiring an actual caller (Compare or Requirements
linking into the calculator with a real pathway) is a follow-up task's job.
**Verified live:** `tests/unit` 968 → 981 passed; `tests/db` 574 passed, 8
xfailed, 0 skipped, 0 failed (run twice — implementer's worktree and again
against the shared stack after merge).

## 2026-09-22 — RULES-8: the eligibility engine now uses the rules registry, and invents the "rule_key" claim convention doing it
**Event:** `GET /eligibility`'s `_criteria_from_claims` used to be the whole
story — a generic claim-shape reader, never touching the Rules lane's own
registry/case-table mechanism (`RULES-2..6,11`, already merged). RULES-8 wires
a real lookup in ahead of it: a pathway's published claim on a new field,
`rule_key` (value = the exam module's `exam_key`; the same claim row's own
`academic_cycle`/`jurisdiction` columns from migration `0008` complete the
match), resolves through `app.rules.ruleset`'s exact-match registry. No
`rule_key` claim published → falls back to the generic builders unchanged.
**No such claim-field convention existed before this task** — it was invented
here, in the absence of one, because the task required it to exist. Recording
it here rather than letting it stay implicit in one file's docstring: whoever
next builds content-authoring around named rule sets (a `PUB-*`/`CONTENT-*`
task) needs to either adopt this convention or deliberately change it — this
is a proposal made real by code, not a settled contract decision.
**An unpublished `rule_key` is ignored entirely, not honoured as "named but
not_checked."** A reviewer's RLS-scoped client can see draft claims; letting a
draft `rule_key` change the outcome would blank a pathway's real published
criteria based on an unapproved row — the same maker-checker bypass shape
this codebase already guards against elsewhere, pointed in the other
direction. Two published `rule_key` claims on one pathway resolve
deterministically (latest `verification_date`, ties broken by claim id) — the
full contract rule ("loser flagged for review") isn't built anywhere in this
codebase yet; only the deterministic half was in scope here.
**Two real bugs found and fixed, unrelated to the registry work itself:** (1)
a non-UUID `pathway_id` 500'd — the same validation gap already closed on
`compare.py`/`requirements_pages.py` had never been carried to this route. (2)
A claim value stored as a JSON list (allowed since `RULES-3`) was stringified
with `str(value).split(",")`, turning `["Physics","Chemistry"]` into the
literal garbage subject names `"['Physics'"` / `"'Chemistry']"` — a student
who had studied both would have been told they were missing a subject called
`['Physics'`.
**A real, previously-wrong behaviour, now matching the already-settled
contract:** `docs/CONTRACTS.md`'s "Three eligibility outcomes" section
requires a pathway with no published rules to return `insufficient_information`
+ `no_verified_rules`, "never a guess" — the pre-existing code instead
vacuously reported the student "meets" criteria that didn't exist. Fixed; the
test that had pinned the old (wrong) behaviour was rewritten, not deleted.
**Also consolidates a known duplication:** `app/planning/comparison.py`'s
`_safe_source_url` is now public (`safe_source_url`, old private name kept as
a compatibility alias for an existing test file), and `app/api/eligibility.py`
now imports it instead of keeping its own strictly-weaker `startswith(...)`
copy — the two had already silently diverged (missing `.strip()`) before
this task noticed.
**Disclosed, not fixed:** `docs/CONTRACTS.md`'s "a non-`IN` pathway's fields
are display-only, never fed to the eligibility engine" is not implemented on
the fallback path. No live impact today (no non-`IN` pathway content is
published yet), but a real gap for whoever builds foreign-pathway eligibility
content next.
**Verified live:** `tests/unit` 966 passed; `tests/db` 574 passed, 8 xfailed,
0 skipped, 0 failed (up from 552, +22 for the new registry/edge-case tests) —
run in the implementer's own worktree and again against the shared local
stack after merge.

## 2026-09-22 — Cache-Control middleware for shared/borrowed phones (A11Y-4)
**Decision.** Every response now sets `Cache-Control` explicitly — nothing is
left to a browser or intermediate cache's own default. `CachePolicyMiddleware`
(`app/web/cache_policy.py`) fills the `cache_policy` slot `app/main.py`'s
registry reserved (DEPLOY-18): **no-store** by default; a short (5-minute)
`public` max-age ONLY for an anonymous GET (no `Cookie`, no `Authorization`) on
the exact allow-list `/explore`, `/compare/view`, `/timeline/view` (GET only —
the POST on `/timeline/view` is not on it); a long (1-year) `public,
immutable` max-age for `/static/*`. `/requirements/view` stays no-store even
though its current GET signature carries no personal field (SEC-5 made those
POST-only) — a future change adding one should not have to remember to touch
this file too.
**Ordering.** `cache_policy` sits inward of `security_headers` in the frozen
slot order, so `SecurityHeadersMiddleware`'s own unconditional no-store for any
cookie/Bearer request runs later in the response chain and wins — a strict
superset that also covers `/static/*` for a credentialed request, which
`cache_policy` itself does not separately check.
**Reviewer sign-out** also sends `Clear-Site-Data: "cache"` — deliberately not
`"cookies"`, so it can never sign out an unrelated same-site session (a future
`bcion_student_session`) on a shared device; the console's own session cookie
is already cleared server-side regardless.
**Known, flagged footgun:** `/static/*`'s long max-age assumes cache-busted
filenames, which don't exist yet (`app.css`/`explore-select.js` are referenced
by plain names) — a deployed CSS/JS change may not reach an already-visiting
browser until the cache expires. Accepted per the task card; not this task's
job to add hashing.
**Verified live:** `tests/unit` 903 → 966 passed (across this and SCOPE-4);
`tests/db` 552 passed, 8 xfailed, 0 skipped, 0 failed, run twice.
**Not landed:** the new `tests/e2e/test_shared_device.py` is correctly
implemented (verified by hand via standalone Playwright scripts reproducing
the real sign-in/sign-out/back-button flow in under 2 seconds) but could not
be run cleanly under `pytest`/`pytest-playwright` in this environment — a
reproducible hang on a click that triggers server-side navigation, which also
affects the pre-existing, unmodified reviewer-queue test in
`tests/e2e/test_smoke.py` (found independently by SEC-2's own verification
earlier the same day). Not a defect in this task's code; a dedicated
investigation is queued separately.

## 2026-09-22 — SCOPE-4: the rupee sign now exists in exactly one place, and "no total" says why
**Event:** SCOPE-4 closed the display half of RULES-10's Money work. Both
`compare.html` and `_trust_badge.html` wrote `₹` as a literal in front of
whatever number they were handed, so a fee published in any other currency
was shown to a student as rupees. Both now format through a `money` Jinja
filter over `format_money(amount, currency)`; a repo-wide guard test
(`tests/unit/test_formatting.py`) fails if any template, or any Python
string literal outside `app/i18n/formatting.py`, ever reintroduces a
currency symbol.
**Wire shape changed:** `GET /compare`'s `cost.net_to_arrange` is now
`{"amount": int, "currency": str} | None` plus a separate
`cost.net_to_arrange_unavailable_reason` = `"missing" | "mixed_currencies"
| null`, and every `FieldValueOut` carries `currency`. `docs/CONTRACTS.md`
requires a mixed-currency total to be shown as such; a bare `null` could
not distinguish it from an unpublished charge. No real content is
published yet (see this file's own "Not claimed" note in STATUS.md), so
this has no live-user impact today.
**Disclosed gap from RULES-10, now closed:** a money claim with a null
currency renders `not_available` on the DISPLAY path too, not just in the
arithmetic — the regression test RULES-10 added to pin the known
inconsistency now asserts the consistent, correct behaviour instead.
**Two correctness fixes to RULES-10's own arithmetic, reviewed and
accepted here, not assumed:** (1) an all-non-INR pathway with zero
confirmed assistance was incorrectly reported as a currency mismatch — a
well-defined `Money(0, "INR")` for "nothing awarded" was being summed
against real charges in another currency, which is not a real term of
that sum and should not participate in the currency check at all; fixed
by only including the confirmed-assistance term when one exists. (2) a
student's cost-assumption override was hard-coded to INR regardless of
the pathway's own charges currency, manufacturing a currency clash the
student never created; it now inherits the pathway's charges currency
(falling back to INR only when that currency itself is unknown), shown
alongside the figure. Both proven live with a new GBP-only pathway test
and a mixed INR+GBP fee-component pathway test.
**Verified live:** `tests/unit` 903 → 935 passed; `tests/db` 548 → 552
passed, 8 xfailed, 0 skipped, 0 failed (run twice — once in the
implementer's own worktree, once again against the shared local stack
after merge).
**Known follow-up, not in scope here:** when a pathway publishes itemised
`fee_component:*` claims and no legacy `verified_charges` claim, the
"Verified charges" display line shows "Not available" while the
computed total (correctly) uses the components — a display-only gap, not
tracked as its own task yet.

## 2026-09-22 — Declarative cross-user access matrix (QA-6); a real thread leak found and fixed at its source
**Event:** `tests/db/access_matrix.py` + `tests/db/test_access_matrix.py`
turn CLAUDE.md's "cross-user access is tested every time auth, RLS or
publication changes" into a standing, self-enforcing guard: 224 cells
(14 public tables — 7 more than the task's original inventory line
named, since `0004`/`0007`/`0009`/`0010` each added tables since it was
written — × guest/student A/student B/reviewer × select/insert/update/
delete), each citing the exact migration and policy it comes from, plus
a psycopg check that fails the run outright if any public table has RLS
disabled or has zero matrix rows. A table a future migration adds and
nobody documents here can no longer pass by silent omission. Two
placeholder cells (export, storage) are `xfail(strict=True)` — they turn
red the day either capability is actually built, rather than staying
silently absent forever.
**Verified, not assumed:** every cell was read out of the actual SQL
first; the one cell where a live run disagreed with that reading
(`guardian_consents`/insert/student A) was investigated to a real,
documented explanation (PostgREST applies a table's SELECT policies to
an `INSERT ... RETURNING` row; that table deliberately has none) rather
than edited to match. The guard itself was proven both ways: a fake
extra table correctly reports zero coverage; a shrunk `careers` entry
correctly lists every missing cell.
**A real bug found along the way, fixed at its source, not just worked
around:** every RLS-scoped test client that signs a user in starts a
refresh-token background thread that keeps the client alive past its
test (not garbage; `gc.collect()` cannot touch it). At 500+ tests this
exhausted file descriptors and crashed the whole `tests/db` run
(`OSError: Too many open files`), which -- fixed only inside QA-6's own
new file at first -- would have kept happening to every other test file
the moment enough of them ran together. Fixed properly in
`tests/db/conftest.py`'s four role fixtures (`student_a`/`student_b`/
`reviewer`/`second_reviewer`), which every file in the directory shares.
**Verified live:** `tests/db` went from 303 passed (before QA-6) to 548
passed + 8 xfailed, 0 skipped, 0 failed (after QA-6 and the conftest.py
fix, and after SEC-2's own new tests on top) — run twice, once inside
the implementing agent's own worktree and once again against the shared
local stack after merge.

## 2026-09-22 — CSRF for cookie sessions: Origin check, Referer fallback, fail closed
**Decision.** A state-changing request (POST/PUT/PATCH/DELETE) that carries one
of this app's session cookies is rejected with 403 unless every origin-declaring
header it sends names a host in `ALLOWED_HOSTS` (`Settings.allowed_hosts_list`,
the same list `TrustedHostMiddleware` uses), and it sends at least one. `Origin`
is the primary; `Referer` is the fallback for browsers that omit `Origin` on a
same-site navigation. When BOTH are present both are checked — a disagreement is
a rejection, not "whichever one passes". A cookie-bearing POST with NEITHER
header is rejected: fail closed, never fail open. `Origin: null` has no host and
falls under the same rule.
**Why no CSRF token.** The reviewer console's forms are deliberately zero-JS, so
there is no client-side script to carry a per-session token into a hidden field,
and inventing one would mean giving up the zero-JS requirement. `SameSite=Lax`
on the cookie stays the first defence; this is the second, for what SameSite
does not cover (a client that ignores the attribute, a same-site different-host
subdomain, any future relaxation of the cookie's flags). The reviewer cookie's
flags are UNCHANGED by SEC-2 — SameSite=Lax, HttpOnly, Secure in production only.
**Shape.** `app/core/csrf.py`'s `require_same_origin(*cookie_names)` returns a
FastAPI dependency, applied per route rather than as middleware, because these
routes must also read the session. SEC-1's `OriginCheckMiddleware` keeps the same
rule for the future `bcion_student_session`; the dependency is never more
permissive than it, and a unit test pins that so the two cannot drift. Merging
them is a one-line follow-up for whichever task next owns `app/main.py`.
**Sign-in is deliberately not gated.** The sign-in POST does not yet carry the
cookie — it is the request that creates it — so the guard is a no-op there;
gating it would lock reviewers out of signing in, which is worse than the login
CSRF it would prevent. The dependency is still attached, so an already-signed-in
session re-posting the form IS checked. `POST /reviewer/sign-out` is deliberately
unguarded (forced sign-out alters no verified data and is the escape hatch if a
client ever holds a cookie but sends no Origin).
**Two operational consequences worth recording.** (1) `ALLOWED_HOSTS` must list
EXACT hostnames — `TrustedHostMiddleware` understands `*.example.com` and this
check deliberately does not, so a wildcard entry passes the Host check and fails
the origin check (closed, but it will look like "the console stopped accepting
posts"). (2) SEC-1 sets `Referrer-Policy: no-referrer` app-wide, so real browsers
send no `Referer` to this app at all: `Origin` is the header actually doing the
work, and the `Referer` fallback is for clients and intermediaries that behave
differently.
**Error surfaces carry codes, not prose.** `/reviewer/queue?error=` was a
URL-encoded free-text message reproduced verbatim in an authenticated page's
error alert — no markup injection (Jinja autoescapes) but a ready-made
text-injection/phishing surface. It is now a short code looked up in a fixed
dict; an unrecognised code renders a generic message. The code is the contract,
the message is not, matching `docs/CONTRACTS.md`'s error shape.
**Verified live, not just written:** revert-to-prove on both changes (guard
removed → a forged cross-origin POST really does publish a claim, confirmed by
reading the row back independently, not just checking the status code; error map
reverted → the two reflection tests fail). 856 unit / 319 db tests passing in
the branch's own worktree before merge; 320 db tests passing against the shared
local stack after merge.

## 2026-09-22 — RULES-10's Money type: a fee claim with no currency now shows as unavailable, not INR
**Event:** RULES-10 (cost engine multi-component sums, merged today) also
built the `Money(amount, currency)` type `docs/CONTRACTS.md`'s "Money and
currency" section had already settled, including its explicit rule: a
claim with a null `currency` renders `not_available` rather than being
assumed INR. Confirmed by running the full `tests/db` suite live before
pushing (not just trusting the merge): exactly one test failure,
`test_net_to_arrange_is_computed_live_and_assumption_is_editable`, whose
own fixture claim never set `currency` and expected the old
assume-a-total behaviour. Fixed by setting `currency: "INR"` on that
fixture — the correct fix, not a workaround, since a real reviewer
verifying an INR fee would now need to record that too.
**Consequence for content, not code:** `db/migrations/0008_jurisdiction_currency.sql`
deliberately gives `currency` no backfill default (unlike `jurisdiction`,
which does default existing rows to `IN`) — so **every fee-shaped claim
written from here on must have `currency` set at write time**, or its
`net_to_arrange`/total will correctly, silently show as unavailable
rather than a wrong number. This is not a live-content regression today
— `STATUS.md`'s "Not claimed" section already states nothing real has
been published as a verified fact yet, only synthetic fixtures — but it
is a real requirement for whoever builds the content-import path next
(`CONTENT-6`/`PUB-2` and later, per the plan) and for `scripts/
seed_synthetic.py`, which already passes `currency="INR"` on its own fee
fixtures and needs no change.
**Also disclosed, not yet fixed:** a null-currency claim's OWN display
field (`cost.verified_charges`, built by the still-untouched
`assemble_cost_breakdown`/`ProgrammeCostBreakdown` path) still shows its
normal trust label even when the computed total next to it is
unavailable — a visible inconsistency a student would see, pinned by a
new regression test (`test_a_fee_claim_with_no_currency_makes_
net_to_arrange_unavailable`) so SCOPE-4 has a failing case to turn green
when it unifies the two display paths, per its own scoped job in the
CONTRACTS.md note above.

## 2026-09-22 — Shell-lane follow-ups closed; PUB-5 unblocks the reviewer-auth serial chain
**Event:** Two disclosed gaps from the Shell lane merge closed same day:
`app/web/consent_pages.py` now imports the one shared Jinja environment
(`app/web/templating.py`) instead of building its own — the "no second
environment" guard test's exemption for it is gone, the guard now
actually covers it. `docs/CONTRACTS.md`'s "Keys and components" section,
left as a placeholder since the contract-burst freeze, is filled in for
real (I18N-1's key rules, the DESIGN-1/DESIGN-2/UI-1 component and shell
contracts, both frozen additive-only).
Also merged: **AI-2** (`ai_model`, `ai_max_input_tokens`,
`ai_max_output_tokens`, `ai_per_account_daily_cap` — names/defaults only,
no provider wiring) and **PUB-5** (`app/web/reviewer_pages.py` split into
`app/web/reviewer/{auth,queue}.py` plus stub modules for future console
lanes — pure mechanical refactor, no route or behaviour change, all 10
existing console tests plus the 2 e2e reviewer tests pass unchanged).
**Reason PUB-5 first:** `docs/DEVELOPMENT-PLAN.md`'s 6.4 conflict table
serialises `SEC-2 -> DEPLOY-15 -> A11Y-4` on this file; PUB-5 has no
dependencies of its own ("can run immediately") and SEC-2 explicitly
depends on it, so it went in ahead of that chain rather than blocking it.
**Found while checking dependencies, not by the checkbox alone:**
`tasks/INDEX.md` had `DEPLOY-5` (readyz + `scripts/smoke.py` + `make
smoke`) already checked `[x]`, but `AI-2` was unchecked despite
`app/core/config.py` already carrying `ai_enabled`/`ai_configured` from
DEPLOY-18's flag block — a genuinely partial implementation, not a false
checkbox. Verified both against the actual code before dispatching any
agent work, so the AI-2 agent only built the four fields that were
actually missing, not a duplicate of DEPLOY-5.
**Owner action still open, unrelated to the above:** `DEPLOY-1` (record
the Oracle VM facts formally) is unchecked and blocks `DEPLOY-2`; the
underlying facts already live in `STATUS.md`'s "Infrastructure" table,
so this is a paperwork gap, not a missing decision.

## 2026-09-22 — i18n key naming, placeholder syntax and the fallback rules
**Event:** I18N-1 built the i18n mechanism (`app/i18n/`,
`app/web/templating.py`). Its task card requires these rules to be
recorded here, because every later string-extraction task (I18N-3,
I18N-13, I18N-15) and the human Hindi review (I18N-11) are built against
them. Written by the implementer at the card's explicit instruction;
normally this file is lead-only.

**Decision — keys.** Catalogue keys are exactly `docs/COPY.md` section
2's convention, unchanged: flat, dot-separated,
`screen.component.purpose`, lower snake_case, one key per fixed string.
No nesting, ever — `app/i18n/__init__.py` raises at import if a
catalogue file contains a nested object, a non-string value or a
duplicated key, so the convention is enforced by code rather than by
review. `docs/COPY.md` remains the source of truth for the English
wording; `en.json` copies it verbatim and a unit test parses COPY.md's
own tables to prove no key silently drifts or disappears.

**Decision — the `_meta.*` exception.** Keys beginning `_meta.` carry
catalogue provenance (locale, review status, reviewer, date), not screen
text, and are the only keys exempt from the three-segment rule. Nothing
renders them. `hi.json` ships with `_meta.review_status: "unreviewed"`
and an empty reviewer: it is a development agent's draft, not a
translation anyone has checked. `HINDI_UI_ENABLED` stays false in
production until I18N-11's named human reviewer fills that block in.

**Decision — one string, one key (I18N-2's "not available").** The
display formatters render `None` — a missing fee, an unparsable
verification date, an absent duration — using
`global.trust_badge.not_available`, the key that already exists, rather
than a second key carrying the same words. `docs/COPY.md` section 2:
"do not give the same string two different keys". A missing number and a
missing fact read identically to a student, so they share one string and
one future translation.

**Decision — placeholders.** `{name}` only, matching `docs/COPY.md`
("plain `{name}` interpolation, no other templating syntax").
Substitution is a regex pass, deliberately **not** `str.format`:
`str.format` raises `KeyError` when a caller forgets a variable and
`ValueError` on a stray brace in a translation, and a missing UI
variable must never be able to crash a page. An unknown placeholder is
left standing (visible and greppable); a stray brace stays a brace. A
unit test asserts the two locales declare the same placeholder names for
every key, so a translation cannot quietly drop `{date}`.

**Decision — fallbacks, never a blank.** The locale resolver order is
the `lang` cookie, then `en`; no `Accept-Language` sniffing (a borrowed
or shared phone's OS language is not evidence of what this student
reads). A key missing from Hindi falls back to English **per key**, not
per file, so a half-translated catalogue is half-Hindi rather than
half-empty. A key missing from English too renders as the key itself —
ugly on purpose; I18N-3's string-lint is what keeps one off a real
screen.

**Decision — `lang` is an allow-list, never a path.** Only `en` and `hi`
are ever accepted; anything else (absent, empty, a typo, another
language, `../../etc/passwd`) becomes `en`. Catalogue filenames are
constants loaded once at import — there is no code path where a cookie
value reaches the filesystem, and a parametrised test asserts exactly
that for ten traversal-shaped values. The cookie holds one of two fixed
tokens and no personal data.

**Decision — one Jinja environment.** `app/web/templating.py` owns the
single `Jinja2Templates` instance; `app/web/common.py` re-exports it and
`app/web/reviewer_pages.py` imports it. Two environments (the state
before this task) meant a global or filter registered on one was
silently absent on the other — a `t()` call working on `/compare/view`
and raising on `/reviewer/queue`, found only when a reviewer loaded the
page. A unit test fails if any module under `app/web/` constructs its
own.

**Known consequence to design around, not a blocker:** `app/main.py`'s
`_is_cookie_bearing` treats *any* cookie as a reason to send
`Cache-Control: no-store`. Once a language switcher actually sets the
`lang` cookie, public pages carrying it stop being cacheable. Whoever
builds the switcher and the PWA caching task should decide that together
rather than discover it.

## 2026-09-21 — Demo mode is a database read policy, never a publish path
**Event:** DATA-12 (migration `0007_demo_mode.sql`, Wave 2 migration lane)
added a way to show synthetic sample content to anonymous staging
visitors before real verified content exists.
**Decision:** an owner-writable `app_settings.demo_mode` flag, checked by
a `demo_mode()` stable function. A new `claims` SELECT policy makes an
`in_review` claim visible to `anon` only when it is *both* `in_review`
**and** synthetic-sourced — never a real (non-synthetic) draft, under any
combination. `forbid_publishing_synthetic_claims()`
(`db/migrations/0001_init.sql`) is untouched: no synthetic claim can be
published by any caller, including `service_role`, demo mode or not.
Outside development, the app refuses to start with `DEMO_MODE=true` and
`APP_ENV=production` set together.
**Reason:** the alternative (a signed-in reviewer preview) needs a real
person and a real session for every staging demo; this needs only a flag,
and the database — not the application layer — is what a curious or
malicious anonymous caller cannot talk their way around.
**Verified, independently re-checked (data-security-reviewer, live
against the branch's own local stack) before merging:** RLS-enabled with
zero policies plus an explicit `revoke all` on `app_settings`; every
combination of `demo_mode`/`status`/`source_type` tested; the synthetic-
publish trigger re-confirmed intact.
**What this does NOT change:** the maker-checker workflow, the freeze
trigger, or any other publication rule. A published, non-synthetic
record is exactly as protected with demo mode on as with it off.

## 2026-09-21 — Migration lane (DATA-15, DATA-12, SCOPE-3, DATA-8, AUTH-4,
## AUTH-5) merged — real numbers 0007-0010, independently security-reviewed
**Event:** Wave 2's migration lane landed all six tasks in one session,
on its own local Supabase stack, then an independent data-security-
reviewer pass (live against that same stack, not taken on trust) before
merging to `main`.
**What's real now:** `claims`/`pathways`/`sources` carry jurisdiction/
academic-cycle/currency columns, with the maker-checker freeze trigger
extended to cover them (`0008`) — closing the exact bypass named in
SCOPE-3's own risk line, reproduced live before the fix and closed after.
Guest server sessions (`0009`) with SHA-256-hashed tokens and
`SECURITY DEFINER` RPCs are the only way into `guest_sessions`/
`guest_plans`. A student's current-decision flag and up-to-three derived
next actions (`0010`), reading only published, non-synthetic claims.
**Two real bugs found by review and fixed in the same merge, not left
open:** (1) `_schema_migrations` — the table `scripts/apply_migrations.py`
itself creates to track what's applied — had no RLS or grant revocation;
confirmed live that the anon key could read and write/delete the owner's
own applied-migrations ledger. Fixed with the same
`enable row level security` + `revoke all from anon, authenticated`
pattern this lane established for `app_settings`/`guest_sessions`.
(2) `PATCH /plans/{id}` with `is_current: true` cleared the caller's
existing current plan *before* confirming the target plan update would
succeed, as two separate requests — a 404 on the target (bad id, a plan
deleted or raced away elsewhere) silently left the student with zero
current plans. Fixed to check the target exists first; both fixes proven
by a failing-then-passing regression test (revert-to-prove), not just
asserted.
**Tracked, not fixed, correctly disclosed rather than silently patched:**
`claims.approved_draft_version` was never added to the maker-checker
freeze trigger's frozen-column list (`0001_init.sql`'s own note said "M4"
would add this; `0003` and this lane's `0008` both did not). Confirmed
real by independent review, and confirmed **dormant** — nothing in the
codebase writes that column today, so there is nothing to bypass yet. It
becomes a real gap the moment a publishing-console feature starts writing
and relying on it; whoever builds that closes this in the same migration.
**Verified, this session:** 605 unit tests, 303 db tests (0 skipped) —
migrations 0007-0010 now applied to the shared local test stack too, not
only the migration lane's own separate one.

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
