# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), M2 (BCI-003) all DONE. **M3
sign-in + saved plans + guest→account migration DONE** (BCI-004). **M4
maker-checker enforcement + publishing-console API DONE and verified
live** (BCI-005) — migration applied, every test that was skipping now
actually passes. **Core journey UI now complete end to end** — Explore
→ Compare → Requirements → Timeline calculator all have real,
zero-JS, browser pages (BCI-006), plus a reviewer console (sign-in +
review queue). **M5 groundwork shipped** — the grounded-explanation AI
adapter's safety layer (`app/ai/`), no route wired yet, no live API
calls made. **E2E Playwright wired up** — 6 real-browser smoke tests,
zero skips. **Pilot scope widened** (2026-09-21) — all-India admission
rules, foreign/study-abroad pathways added; see `docs/DECISIONS.md`.
**Guardian-consent gate merged AND live-verified against production**
(2026-09-21) — age gate at sign-up, emailed guardian confirmation for
under-18 accounts, hardened through two rounds of adversarial review
(one CRITICAL self-activation bypass, one HIGH self-as-guardian gap, one
MEDIUM `+tag` sub-addressing bypass, all fixed). Migrations `0004`,
`0005` and `0006` are all applied to the live project; going live for
the first time surfaced two real production bugs the skipped tests had
been hiding (both fixed, see "⚠️ Read this one"). **`tests/db/
test_guardian_consent.py`: 32 passed, 0 failed, 0 skipped, run by the
owner against production. Full `tests/db` suite (148 tests, every
cross-user access check in the app, not just guardian-consent):
148 passed, 0 failed — CLAUDE.md's "cross-user access is tested every
time auth, RLS or publication changes" requirement, satisfied live, not
by inspection.** **Two things still stand between this gate
and a real minor account**: a real email provider, and a named person's
sign-off (`docs/SECURITY.md`). 193 unit tests passing.
**Commit:** see `git log -1` on `main`. **Repo:**
[github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## Phase 1a — AI only (planned 2026-09-22, not started)
Owner decision: an AI-only build runs alongside Phase 1 in its own
lanes, touching no Phase 1 file, merged to `main` behind
`AI_ENABLED=false`, and "added" by flipping the flag after its exit gate.
Plan: `docs/plan/phase-1a-ai.md` (lead-only). 20 agent sessions across
up to 6 lanes, about 9 working days of dev time, 4 data-security + 2
ai-evaluator + 2 ux-qa passes. Every AI answer = two model passes
(select, then verify) + code validation; the model never writes a
sentence; free Gemini tier, so no student-typed text leaves the server
(test-enforced). AI-4 takes migration **0011**; the Phase 1 ledger
shifts by one. Waiting on the owner's "go" and five explicit yeses (plan
section 8a) plus AI-10 (key, free-tier terms and limits) before any live
call. `tasks/INDEX.md` Step 11 retagged `[P1a]`; four cards added
(AI-14 un-dropped, AI-18, AI-19, AI-20). No code changed.
**Day 1: AI-1 and AI-9 merged and verified live; AI-4 correctly blocked
(2026-09-22).** BCI-009 (AI-1), BCI-010 (AI-4) and BCI-011 (AI-9)
dispatched as three parallel worktree agents. **AI-4 found a live
collision** with a peer session's `consent-4` lane (CONSENT-4, split
into two migrations) before writing anything: `consent-4` already held
uncommitted `0011_admission_axis.sql` and `0012_safeguarding_schema.sql`,
already applied to the one shared migration-owner local stack this
repo's `supabase/config.toml` reserves. AI-4 stopped per
`.claude/agents/migration-owner.md`'s "never more than one open
migration" rule, applied nothing, touched no cloud project, its worktree
auto-removed (zero commits). `tasks/BCI-010.md` corrected: blocked until
`consent-4` merges, next-free number expected **0013** (confirm fresh,
not just via `ls`), plus two design gaps folded in (access-matrix guard
needs `tests/db/test_access_matrix.py` in Owned files; a database view
cannot be a matrix row). **AI-1 merged** (`app/ai/schemas.py`: six-value
`AIAnswerStatus`, `AskRequest`, `Answer`, typed provider errors, a
32-entry append-only `BANNED_PHRASES`, and `OutboundPayload` — a closed
four-field allow-list whose `record_values` keys must be
`<record_id>.<field>`, so untraceable text is a `ValidationError`, not a
review note; `docs/ARCHITECTURE.md`/`docs/CONTRACTS.md` each gained one
appended section). **AI-9 merged** (`evals/ask_bcion_questions.yaml`: 36
synthetic questions across 7 categories, 14 Hindi/Hinglish, 2 all-India,
2 abroad-out-of-coverage; 5 labelled `tests/fixtures/ai_invalid/`
fixtures; the proposed `.claude/agents/ai-evaluator.md` applied). **Lead
reconciliation on merge, verified live in this session, not on trust**:
`app/ai/grounding.py` had its own pre-existing 3-value `AIAnswerStatus`
(from M5) that briefly duplicated AI-1's 6-value superset — now a single
canonical definition, `grounding.py` re-exports from `schemas.py`
(identical spelling/meaning for the 3 shared values, zero behaviour
change, `ruff` + the full unit suite re-run clean after). AI-9's
`BANNED_PHRASES` fallback (written before AI-1 existed) swapped for the
canonical import; the shared `hedge_word.yaml` fixture (`probably`)
confirmed present in both before switching. **1097 unit tests passing
(up from 1020), lint clean**, both re-run by the lead in this session
after merge, not just quoted from an agent report. `AI_ENABLED` still
`false`; no live provider call made.

**Wave 2 merged and verified live (2026-09-22): AI-3, AI-5, UI-11.**
BCI-012 (AI-3), BCI-013 (AI-5) and BCI-014 (UI-11) dispatched as three
parallel worktree agents, all reporting green; all three merged clean,
no file conflicts. **AI-3**: `app/ai/gemini_provider.py` hardened - the
`google-genai` SDK's own retry disabled (proven with a fake that raises
a normally-retriable 503 and is invoked exactly once), every failure
class mapped to a typed error from `app/ai/schemas.py`, the API key
proven absent from every log line and exception string across all six
failure classes. `app/ai/mock_provider.py` gained sequenced responses
and a `raise_on_call` hook for the pipeline card ahead. **AI-5**:
`app/ai/retrieval.py` - published/non-synthetic re-filtering independent
of the caller's RLS scope, cost/timeline numbers from the real
`app/rules` engines, eligibility exposed as unevaluated `Criterion`
objects (never a fabricated outcome - no student input is ever
available here), an import guard proving no student-identity table is
ever touched. **UI-11**: `GET /ask` (JSON) + `GET /ask/view` (HTML),
deterministic mode only, the three canned prompts, exact `docs/UI.md`
fallback copy when AI is off or unpublished, no input element anywhere
(grep-tested), the three real `_ask.html` call sites now render working
links.

**Lead-level fixes this session, not from an agent report:**
- **A real bug, caught only by live verification.** AI-5's own agent
  could not reach the shared local Postgres/Docker stack in its worktree
  and said so plainly rather than claiming a pass. Running its live test
  file myself against the real stack surfaced a genuine fixture bug: it
  tried to seed a claim that is both `published` and backed by a
  synthetic source, to test-drive `app.ai.retrieval`'s own defensive
  re-filter - but `forbid_publishing_synthetic_claims()` refuses that
  write for every role, including the service role, so the fixture
  crashed before any test ran (6 errors). Fixed by turning the refusal
  itself into an explicit, passing assertion (a new
  `TestSyntheticSourceCanNeverBePublishedLive` test) rather than
  papering over it - this is the correct, stronger proof: the
  non-negotiable is enforced at the database layer, not only in Python.
  `tests/db/test_ai_retrieval_live.py` + `tests/db/test_ask_view.py`:
  **18 passed, 0 errors**, re-run clean after the fix.
- **Router registration** (`ask`, `ask_pages`) applied to `app/main.py`
  as the two proposed one-liners UI-11's report gave, plus
  `EXPECTED_ROUTERS` - confirmed the frozen-registry guard still passes
  and the app boots.
- **i18n namespace reconciled.** UI-11 introduced a new `ask.*` key
  namespace; an existing `askbcion.*` namespace already covered this
  area (pre-dating this session). Renamed all 8 new keys to
  `askbcion.*` across both locale files, both templates and both route
  modules - verified no stray `ask.*` reference remains, JSON still
  valid, lint clean.
- **A second real bug, also caught only by running the full regression.**
  The first full `tests/db` run (598 tests) surfaced 2 failures in
  `tests/db/test_web_pages.py`, a Phase 1 file no wave-2 card touched.
  Root cause: `compare.html`'s own header comment already documented the
  fix needed ("the detail link only renders for a pathway_id this screen
  actually resolved to a real name... same guard already used below")
  but the guard was only ever wired to the `pathway_detail_link` call,
  never to the `ask_bcion(...)` call sitting right above it - a latent
  gap invisible while `_ask.html`'s macro was an empty stub, and real
  the moment UI-11 filled it in: a comparison request naming a
  nonexistent pathway id now rendered a live Ask BCION link whose `href`
  carried that raw id straight into the page, defeating the "This
  pathway" heading fallback the same file exists to guarantee. Fixed by
  wrapping both of `compare.html`'s `ask_bcion(...)` calls in the exact
  `{% if c.pathway_id in pathway_names %}` guard the file's own comment
  already named - a two-line, single-purpose fix, not a new feature; no
  other change to the file. `TestComparePage`/`TestRequirementsPage`:
  27 passed after the fix (the second flaky-looking failure did not
  recur once isolated and re-run, and stayed green after this fix too -
  logged as an observed flake, not chased further).
- Full unit suite re-run after every change in this session:
  **1173 passed** (up from 1097 after wave 1), lint clean throughout,
  including after the `compare.html` fix. Full `tests/db` regression run
  twice: first run (598 tests) found the 2 failures above; **second run,
  after the fix, confirmed clean: 621 passed, 8 xfailed, 0 failed**
  (grew from 598 to 621 between runs - `consent-4`'s own merges landing
  concurrently on the shared stack, not a Phase 1a change). Wave 2 is
  fully verified end to end.

**Wave 3, AI-6, AI-14 and AI-20 all merged (2026-09-22).**
BCI-015 (AI-6, AI-14, AI-20) dispatched as three parallel worktree
agents; two finished and were merged as soon as they were ready,
without waiting for the third - **AI-6**: `app/ai/pipeline.py`'s
`answer()` orchestration is the actual two-pass mechanism Rule 2
requires: validate template -> check `AI_ENABLED` -> retrieve via
`app.ai.retrieval` -> reserve 2 calls -> selection pass -> code-validate
-> verification pass over only the selected ids -> code-validate ->
intersect -> freshness check -> code-generated sentences (reusing
`grounding.py`'s citation/sentence pattern, never duplicating it) ->
settle usage. Every failure path returns a usable `Answer` with
deterministic fact cards, never an unhandled exception, never
model-authored text - 30 passed, full unit suite 1203 at merge time.
**AI-20**: `scripts/ai_translate_drafts.py`, an offline owner-run script
- translation pass, then a *separate* back-translation-check pass,
token-overlap agreement scored and flagged (never silently accepted),
writes a CSV for a human Hindi reviewer, hash-proven to never write
`en.json`/`hi.json` or touch the database - 25 passed. **AI-14**:
`app/ai/extraction.py` - a pasted-document extraction pass proposing
`field/value/quoted_span` triples, then a separate adversarial
verification pass, then a mechanical verbatim-substring re-check in
code that never trusts the model's own verification answer alone.
Correctly found two of its card's assumptions were stale (`claims_forms.py`
and `sources.py`, named as reusable, are actually empty stubs) and
adapted using the closest already-established pattern instead of
guessing - the new `/reviewer/extract` page calls `app/api/claims.py`'s
existing `create_claim()` directly (the same pattern `queue.py` already
uses for its own actions, since the real `POST /claims` route is
Bearer-only and a plain form can't attach that header), so no new
database write path exists; every write still goes through the
existing, already-tested claims API and its maker-checker enforcement.
Wired into the running app as the lead's own one-line fix (`app/web/
reviewer/__init__.py` now includes the new router under the existing
`reviewer_pages` slot - `app/main.py` itself needed no change, since
that file only ever imports one combined router per console package).
23 unit + 16 live db tests pass through the actually-wired app, not
just its own standalone test harness. **All three merged clean, no
file conflicts. Full unit suite: 1251 passed.**

Next: relaunch AI-4 once `consent-4` merges; open wave 4 (AI-7 wires
the pipeline into the Ask BCION route; AI-8 the AI-off regression;
AI-18/AI-19 the next-steps and what-changed templates) once AI-7's
dependency (AI-6, now merged) clears it to start.

## Development plan — Wave 1 done, Wave 2's migration/eligibility lanes done (2026-09-21)
`docs/DEVELOPMENT-PLAN.md` is being executed for real. `tasks/INDEX.md`
finalised (DOCS-3a); `docs/CONTRACTS.md` fully frozen (all 7 Wave 1
contract-burst tasks + A11Y-1); `docs/PARALLEL.md`/`docs/COSTS.md`/
`.claude/agents/implementer.md`+`migration-owner.md` exist (DOCS-4/13/6).
**Merged, in order:** contract burst (7) → design docs (4) →
docs-and-scripts (3, scrubbed the owner's personal email from 116
content-draft files) → content-prep (5) → Rules lane (`RULES-2..6,11`) →
mechanical lane (`DEPLOY-18,SEC-7,UI-2,SEC-1,DEPLOY-5`: the shared
middleware/flag registry, a hashed lockfile) → **QA-2/QA-3** (local
Supabase test stack, RUN_ID-tagged concurrent-safe tests — the first
real local-DB testing in this project's history) → eligibility lane
(`SEC-5,SCOPE-5`: no personal data in a URL anywhere now, real state/UT
+ country jurisdiction codes) → **migration lane**
(`DATA-15,DATA-12,SCOPE-3,DATA-8,AUTH-4,AUTH-5`: migrations `0007`-`0010`
— demo mode, jurisdiction/cycle/currency columns with the freeze trigger
correctly extended, hashed-token guest sessions, plan-actions).
**Real bugs found and fixed, not just accepted from agent reports** —
by the migration lane's own author (an `ON CONFLICT` firing before an
`INSERT` trigger; a 400 that was an existence oracle, now 404), by an
independent data-security-reviewer pass run before merging (live against
the real stack, not on trust): `_schema_migrations` had no RLS/grant
protection — anon could read *and delete* the owner's own
applied-migrations ledger, confirmed live via curl, now fixed; `PATCH
/plans/{id}` cleared a student's current plan before confirming the
target update would succeed, so a 404 silently left them with zero
current plans, now fixed and proven by a failing-then-passing regression
test; a case-sensitivity gap in the seed script's production-ref check.
Earlier: SEC-7's CI jobs found a real `pytest` CVE, then a
`pytest-asyncio` version that crashed outright under the fix (installed
and confirmed, not just read a warning); merging `supabase/` broke `ruff`
for everyone (fixed with `known-third-party`).
**Tracked, correctly disclosed, not yet fixed:**
`claims.approved_draft_version` was never added to the maker-checker
freeze trigger (a pre-existing gap, not introduced this session) —
confirmed real, confirmed **dormant** (nothing writes that column yet),
becomes a real bypass the moment a publishing-console feature starts
relying on it.
**Real numbers, this session: 605 unit tests (up from 193), 303 db tests,
zero skipped** (migrations `0007`-`0010` now applied to the shared local
stack too, not only the migration lane's own separate one). CI green
throughout. A 3-concurrent-lane measurement (228s wall clock, zero
flakes) supports the plan's default DB-lane cap of 3 with evidence.
**Migration ledger, now settled:** `0001`-`0006` are the merged
guardian-consent gate (another session, confirmed live in production);
`0007`-`0010` are this plan's own (demo mode, jurisdiction/currency,
guest sessions, plan actions) — no longer provisional, all four real
numbers used and applied. **CONSENT-1 superseded**, ~25 stale plan
references fixed.
**Still open:** the locked worktree `wf_9b7797a4-e76-1` ("Held, not
merged" student sign-up UI) still needs its own bounded merge task — not
yet carded. Small flagged follow-up, not yet started: moving
`explore.html`'s inline `<script>` to tighten the CSP.
**Root cause found for the "`mypy app` is a no-op" note every agent
carried this session:** it isn't a project problem — this specific
Windows dev machine has a stray, unpinned `numpy` install in its user
Python 3.12 site-packages (not in `requirements-dev.lock` at all; this
project has no numpy dependency) whose type stub uses Python-3.12-only
syntax mypy can't parse, aborting the whole run before it reaches any
real file. **CI's `mypy` has been the only place it actually ran all
session**, in a clean, lockfile-only, numpy-free install — and it caught
one genuine issue on the very next push after this note was written: a
missing `cast(...)` in `app/web/guest_session.py` (migration lane),
fixed immediately, matching this codebase's own established pattern
used at five other call sites. Trust CI's `mypy` result, not a local run,
on this machine, until someone cleans up its global Python install.
**Shell lane merged** (`I18N-1, I18N-2, UI-1, DESIGN-18`), plus two
disclosed follow-ups closed same day: `consent_pages.py` now shares the
one Jinja environment (no more test exemption), and `docs/CONTRACTS.md`'s
"Keys and components" section is frozen for real. `AI-2` (AI settings:
model/token/daily-cap names) and `PUB-5` (split `reviewer_pages.py` into
`app/web/reviewer/{auth,queue}.py` plus stubs for future console lanes,
zero behaviour change, unblocks the `SEC-2 → DEPLOY-15 → A11Y-4` chain
that all three serialise on) are also merged. 790 unit tests passing.
**All six of that day's parallel lanes now merged and CI-green**:
`DEPLOY-3` (real Dockerfile, non-root, hash-checked install, `make
build` wired, a `build-image` CI job verified on GitHub's own runner),
`A11Y-2` (state macros, `base.html` landmarks, `explore.html`'s inline
script moved to a static file), `RULES-10` (multi-component fee sums,
plus — a genuine gap in the original task card, caught from the
agent's own report before merge — the full `Money(amount, currency)`
type `docs/CONTRACTS.md` had already settled was RULES-10's job; a real
live-DB test failure this surfaced was found and fixed by running the
full suite before pushing, not trusting the merge), `SEC-2` (CSRF
Origin/Referer check for reviewer cookie POSTs, fixed error codes
replacing reflected free text — revert-to-prove verified: without the
guard, a forged cross-origin POST really does publish a claim), `QA-6`
(224-cell declarative cross-user access matrix + an RLS-coverage guard
— also found and fixed, at its source in `tests/db/conftest.py`, a real
thread leak that would have crashed `tests/db` under enough concurrent
tests). `tests/db`: 548 passed, 8 xfailed, 0 skipped, 0 failed.
`tests/unit`: 903 passed. Full details, including every real bug found
along the way, in `docs/DECISIONS.md`'s 2026-09-22 entries.
**Next:** `A11Y-4` (Cache-Control middleware — depends only on `A11Y-1`,
done; SEC-2 merging clears the file-serial rule the plan put it behind).
`DEPLOY-15` is next in that same file-serial chain but its OWN real
dependency (`DEPLOY-2`, not just SEC-1) is still blocked: `DEPLOY-2`
needs `DEPLOY-1` (owner: record the real Oracle VM facts — the
substance already lives in this file's "Infrastructure" table, just not
yet copied into a `docs/DECISIONS.md` entry the way `DEPLOY-1` wants
it). `DEPLOY-4`/`DEPLOY-6` are behind the same `DEPLOY-2` gate.
`QA-12` (sweeping test residue from the **live** project) and `DATA-10a`
are owner-run, not agent work, by design. **`SCOPE-4` merged** —
currency-safe cost display, closing the display gap RULES-10 disclosed:
no currency symbol literal exists outside `app/i18n/formatting.py`
anywhere now; `/compare`'s `net_to_arrange` carries its own currency
plus a `"missing"` vs `"mixed_currencies"` reason when it's unavailable,
shown as two different sentences to a student, never conflated. Also
fixed two real bugs in RULES-10's own arithmetic along the way (a
non-INR pathway with no confirmed assistance was wrongly flagged
mixed-currency; a student's cost override was hard-coded INR
regardless of the pathway's actual currency) — both reviewed and
accepted here, proven live with new GBP/mixed-currency pathway tests.
`tests/unit`: 935 passed. `tests/db`: 552 passed, 8 xfailed, 0 skipped,
0 failed. See `docs/TESTING.md` (new, QA-4) for the local-stack
contract every parallel lane follows.

**`A11Y-4` merged** — `Cache-Control` on every response now (no-store by
default; a short public max-age only for an anonymous GET on an exact
allow-list; a long max-age for `/static/*`); reviewer sign-out also
sends `Clear-Site-Data: "cache"`. `tests/unit`: 966 passed. `tests/db`:
552 passed, 8 xfailed. **Not yet green:** the new e2e shared-device test
hits a reproducible pytest-playwright hang shared with a pre-existing
reviewer-queue e2e test — both are correctly written and verified by
hand outside pytest; the hang itself is a queued follow-up, not an app
bug.

**`RULES-8` merged** — `GET /eligibility` now resolves through the
rules-engine registry (a pathway's published `rule_key` claim, plus its
own `academic_cycle`/`jurisdiction` columns) instead of only the
generic claim-shape reader; falls back to the generic path when no
`rule_key` is published. Fixed two real bugs along the way (a
non-UUID `pathway_id` 500, a JSON-list claim value rendered as garbage
subject names) and one real wrong-behaviour bug the contract had
already settled (a pathway with zero rules used to vacuously report
"meets" — now correctly `insufficient_information`). `tests/unit`: 966
passed. `tests/db`: 574 passed, 8 xfailed, 0 skipped, 0 failed.
**Needs your input:** RULES-8 had to invent the `rule_key`
claim-field convention (which claim field names a pathway's rule set) —
no such convention existed before this task, and it isn't a contract
decision, just what the code needed to exist. Whoever builds
content-authoring around named rule sets next should either adopt it
or deliberately change it; see `docs/DECISIONS.md`'s 2026-09-22 "RULES-8"
entry for the exact shape. Also disclosed, not fixed: a non-`IN`
(foreign) pathway's claims still reach the eligibility engine on the
fallback path, contrary to `docs/CONTRACTS.md` — no live impact today
(no foreign-pathway content exists yet), flagged for a follow-up.

**`RULES-9` merged** — `GET /timeline/view?pathway_id=X` now does a real
database-backed prefill (the pathway's name + published stages), not
just UI-7's display-only echo; degrades to the usual friendly message
when the database is unreachable. `compute_timeline()` rejects a
negative duration/overlap cleanly (400 on the API, a styled alert on
the page) instead of accepting nonsense or crashing. **A second
invented claim convention, same day as RULES-8's**: timeline stages
are now `stage:<order>:name/duration_weeks/kind/
overlap_weeks_with_previous` claims — again, nothing existed before
this task. Two Rules-adjacent conventions invented in one session is
worth a deliberate look before real content authoring starts; see
`docs/DECISIONS.md`'s 2026-09-22 "RULES-9" entry. `tests/unit`: 1020
passed. `tests/db`: 579 passed, 8 xfailed, 0 skipped, 0 failed.

**`A11Y-5` merged** — a guard test scans `app/web/templates/` and
`app/static/` and fails on any `serviceWorker`/`localStorage`/
`sessionStorage`/`indexedDB`/`caches.`/`sw.js` reference, proven (via a
planted-string fixture) to actually catch something rather than
passing vacuously. Nothing on the tree trips it today. `tests/unit`:
968 passed.

**`UI-7` merged** — the timeline calculator shows each stage's kind
(required/optional/your-assumption) as a text+icon badge, and adds
"Revise this scenario" (a bounded extra-attempt row, framed as a normal
part of planning, never a failure). A real gap found along the way: the
task card assumed `pathway_id` pre-fill already existed on this route —
it didn't, so it's added now as display-only context (no DB lookup;
nothing links here with a pathway yet, flagged as a follow-up). This
unblocks **`RULES-9`** (timeline seeding from published stage claims —
its other two dependencies, `RULES-1` and `UI-2`, were already done).
`tests/unit`: 981 passed. `tests/db`: 574 passed, 8 xfailed, 0 skipped,
0 failed.

**`UI-3` and `UI-5` merged** — `GET /` is a real "Find your next step"
landing page (three choices) instead of a bare redirect; a new `GET
/start` chain asks four skippable questions, zero-JS, no cookie/
`localStorage` anywhere, ending at `/start/results` (the real
suggestion-matching logic is `UI-4`'s job). `GET /pathways/{id}/view`
is the new pathway/career detail page, built entirely through the same
`field_value_for()` gate Compare already uses, and fills in
`_components.html`'s `pathway_detail_link` stub — its first real
caller. That surfaced a real regression (a raw pathway UUID could leak
into Compare's page via the newly-live link for an unresolved pathway),
found and fixed before merge, confirmed independently by two separate
review passes, not accepted on the implementer's word. `tests/unit`:
1029 passed (pre-dating the peer session's later AI-1/AI-9 work, which
brought the total to 1097). `tests/db`: 592 passed for UI-5
specifically, both live while the local stack was up. See
`docs/DECISIONS.md`'s 2026-09-22 entry for the full detail, including
why this session's own post-merge db re-run didn't complete locally
(Docker Desktop's engine not responding on this machine — CI's own live
run against the real staging project is this push's DB verification).

**`RULES-16` merged** — the requirements screen gets a real
`date_of_birth` field (POST-only, never stored/logged/linked, same
guarantees CLAUDE.md treats as absolute), plus the rest of RULES-8's
response surfaced for the first time: cycle/jurisdiction shown once
near the results, `rule_version` in the evidence line, a "Not checked
here" list, and a combined stale-evidence warning. Verifying this
branch's own merge independently caught a live bug in unrelated,
still-uncommitted work elsewhere in the session (`_ask.html` leaking a
raw pathway UUID on Compare, the exact class UI-5 already fixed for a
neighbouring macro) — flagged to that work's owner before it was
committed, not fixed here. `tests/db`: 590 passed, 8 xfailed, 0
skipped, 0 failed, run live before the unrelated WIP above existed.
Docker is confirmed healthy again as of this session (the owner
restarted it) — full `tests/db` also independently re-confirmed clean
at 592 passed after the fix, on the real local stack.

**`SEC-3` merged** — nginx per-IP rate limiting, `deploy/nginx/
ratelimit.conf`: four zones (`bcion_auth` 30r/m burst 20 for
`/auth/*`+`/reviewer/sign-in`; `bcion_plans_write` 60r/m burst 30 for
`/plans` writes, via a `map $request_method` empty-key exclusion for
GET/HEAD rather than `limit_except` — nginx rejects `limit_req` inside
`limit_except`, found live against a local `nginx:stable` Docker
container, not assumed; `bcion_ask` 30r/m burst 15 for `GET /ask`; a
shared `bcion_perip_conn` 20-connection cap) plus `app/static/429.html`
and a new `docs/SECURITY.md` section documenting this as Layer 1
alongside Supabase Auth's own independent Layer 2 rate limiting. **This
is a documented config snippet only — no nginx deployment exists yet**
(this app has no public domain/reverse proxy in front of it — see
"Needs your input" below); DEPLOY-4/7 wires it into a real site file
when that work starts. Live-tested with real request bursts against a
local Docker nginx (not just `nginx -t` syntax check): confirmed the
GET/HEAD exclusion passes unlimited, a `POST /plans` burst passes
exactly 31 requests before 429s, `GET /ask` passes exactly 16 — and one
real bug in the *test stub itself* was caught this way (a `return 200`
stand-in finalizes in nginx's REWRITE phase, before PREACCESS-phase
rate limiters ever run; switching to a content-phase `try_files` stub
fixed it — the production `proxy_pass` directives were never at risk).
**Open question for the owner**: the task card named POST/PATCH/DELETE
for `/plans`; the merged config excludes GET/HEAD instead, which also
covers `PUT /plans/{id}/actions/{action_key}`, a write the card didn't
name — flagging for confirmation that's the intended scope. Purely
additive (`3 files changed, 370 insertions(+)`, no existing file logic
changed except the `docs/SECURITY.md` addition). Verified before merge:
ruff clean, mypy clean (81 files), `pytest tests/unit -q` 1251 passed;
CI green on `main` post-push (build-image, lint-typecheck-test
including live DB/RLS tests against the real staging project,
secret-scan).

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
  in the same request — the guest→account migration. **`date_of_birth`
  is now required** (see the guardian-consent section below) — no
  regression for the existing 18+ behaviour, verified live this session.
- `GET /consent/confirm?token=...` — the guardian-consent confirmation
  page (new this session; not yet live-verifiable, see the ⚠️ section
  above and the dedicated section below).
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
- **Reviewer console (2026-09-21) — the publishing-console API now has a
  human-usable browser UI.** Until now every claims.py route was
  curl/Postman-only; nothing let a reviewer actually sign in and act on
  the queue. `GET/POST /reviewer/sign-in`, `POST /reviewer/sign-out`,
  `GET /reviewer/queue`, `POST /reviewer/claims/{id}/{submit,approve,
  reject}` — zero-JS plain forms, calling straight into claims.py's own
  route functions (one code path, not a second reimplementation).
  **First browser-reachable authenticated session this app has ever
  had**: every prior route only ever read an `Authorization: Bearer`
  header, which no plain browser GET/form-POST can attach — a new
  cookie-based session (`app/web/reviewer_pages.py`) fixes this,
  deliberately scoped to `/reviewer/*` only; `app/api/deps.py`'s
  header-only contract backing the JSON API and the student-facing pages
  is untouched. Cookie: httponly always, `samesite=lax` always (the CSRF
  defense for the zero-JS forms, since there's no script to carry a
  separate token), `secure` only in production, sized to Supabase's own
  token lifetime rather than an invented longer session, scoped to
  `/reviewer` only, never logged.
  Built via a workflow (implementer + a `data-security-reviewer` pass +
  a `ux-qa-reviewer` pass), then one fix round after review found a real
  HIGH-severity bug: the three write actions had no error handling, so
  self-approval (the first thing any reviewer would try, on their own
  draft) — or any other rejected transition — dead-ended in a raw
  unstyled JSON blob with no way back to the queue. Fixed: all three now
  redirect to the queue with a visible, styled error. Also fixed:
  missing aria-labels on identical per-claim buttons, a touch target
  under 44px, a raw `None` shown for a null claim value, an unhandled
  500 if the DB client itself failed to construct, and a hardcoded
  test-fixture password. Independently re-verified before merging — read
  every diff directly, ran the full suite myself, and live-reproduced
  the self-approval fix against the real database (303 redirect, styled
  error, claim status genuinely unchanged). 10 new live tests
  (`tests/db/test_reviewer_console.py`). A follow-up 16-lens deep audit
  found 11 more real issues (DB-unavailable crashing every route, the
  same rate-limit-swallowing gap `authenticate()` had, queue rows
  showing bare UUIDs instead of resolved names/sources, missing
  logging, two more a11y issues, unstable queue ordering, test gaps) —
  all fixed and independently re-verified.
- **Requirements + Timeline calculator screens (2026-09-21) — the core
  journey (explore → compare → calculate time and cost → see
  requirements → save next actions) now has a browser page for every
  step except the last.** `GET /requirements/view?pathway_id=X` wraps
  the same `check_eligibility()` the JSON API uses, showing each
  criterion's outcome *and* trust label side by side (a real fix: the
  first version only showed the outcome, missing CLAUDE.md's "every
  published fact has a source, a verification date and a verifier" for
  exactly the kind of consequential fact this screen exists to show).
  `GET/POST /timeline/view` wraps `compute_timeline()` directly, with a
  pre-filled edit-and-resubmit loop. Compare now links forward into
  both. Built via workflow + UX/correctness review, one fix round (8
  real findings, including the trust-label gap above and a DB-
  unavailable 500 shared with the pre-existing Compare route), merged
  after resolving a real CSS merge conflict and independently
  re-verifying live (153 unit + 30 db tests, all passing).
- **M5 groundwork (2026-09-21) — the grounded-explanation AI adapter's
  safety layer, `app/ai/`, no HTTP route yet, no live API call made
  anywhere.** Built behind a pluggable provider interface (mock for
  tests, a real Gemini provider gated behind a construction-time check
  when no key is configured — mirrors `SupabaseNotConfiguredError`'s
  pattern). **Adversarial review found a CRITICAL bug before anything
  used this code**: the first version let the AI provider write the
  full explanation sentence itself and only checked that its citation
  tag pointed at a real claim — meaning a citation to a genuine claim
  could carry a completely fabricated sentence next to it ("the fee is
  ₹50,000... this pathway guarantees admission"), and nothing caught
  it. Direct hit on CLAUDE.md's #1 rule, "AI never invents facts."
  **Fixed architecturally, not with a smarter filter**: the provider is
  now only ever asked to *select* which claim ids are relevant (bare
  `[claim_id]` lines, nothing else accepted) — every fact-bearing
  sentence in the final answer is generated by this module's own code,
  by template substitution over the already-trusted claim data. There
  is no code path by which a character the provider wrote can reach the
  answer text. Also added: freshness/SLA staleness checking (mirrors
  `trust_label_for_claim`), so a severely-overdue published claim no
  longer produces a full-confidence answer. 20 tests, including the
  literal exploit reproduction (now rejected) and an independent
  "framing text" smuggling attempt (also rejected). Re-verified by me
  before merging: read the module in full, ran all 20 tests, and wrote
  my own adversarial probe with additional bypass attempts — none
  succeeded.
- **E2E Playwright (2026-09-21)** — `make test-e2e` was a stale
  placeholder all session; now runs 6 real-browser smoke tests against
  a genuine `uvicorn` subprocess (not `TestClient`, which never opens a
  real socket). Explore→Compare, Requirements, Timeline, and the
  reviewer console's zero-JS sign-in→queue journey, all passing live,
  zero skips.

## Held, not merged — needs your decision
**Student sign-up + save-plan UI** is built (cookie session mirroring
the reviewer console, cross-user isolation verified, zero-JS) but is
still sitting **unmerged** in its own worktree. Adversarial review found
it makes real account creation prominently reachable to minors for the
first time — a global "Sign in" nav link plus an auto-redirect from
"Save this plan" — with no age/consent gate, exactly what CLAUDE.md and
`docs/SECURITY.md` reserve as a human-reviewed launch gate, not a side
effect of a commit. You decided (2026-09-21) on the mechanism: an age
gate at sign-up, and for anyone under 18, a guardian email that must
confirm via a separate emailed link before the account activates.

**That gate is now built and merged to `main`** (see "⚠️ Read this
one" and "Guardian-consent gate: adversarial-review fixes" below) —
`db/migrations/0004_guardian_consent.sql`, `app/notifications/`, age
check + guardian-email validation on `POST /auth/sign-up`, enforcement
in `authenticate()`. **No email-sending provider exists anywhere in
this codebase yet**: it's built against a pluggable interface
(mirroring M5's Gemini-gating pattern) — a safe logging default that
never reaches a real inbox until you provision a real provider (SMTP
relay or a transactional email API) the same way Supabase/GitHub/Gemini
needed real credentials from you. The student sign-up worktree still
needs to (a) merge on top of this now-landed gate, not before it, and
(b) get its own known bug fixed first — `_migrate_pending_plan`'s
silent-swallow design means a stale/nonexistent `pathway_id` at sign-up
silently drops the guest's plan while still showing a success redirect
to an empty "My Plan" page (found by adversarial review, not yet
fixed).

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

**239 tests passing, zero skipped** — verified live, this session
(includes the reviewer console's 10 new live tests). Lint/typecheck
clean, CI green on every push this session.

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
**One real blocker remains, below — narrower than before, not gone.**

## ⚠️ Read this one — guardian-consent gate is LIVE and tested; one owner action plus one owner sign-off remain
`db/migrations/0004_guardian_consent.sql`, `0005_guardian_consent_request_rpc.sql`
and `0006_guardian_consent_token_pgcrypto_schema.sql` are all applied to
the live Supabase project (you applied 0004 yourself via the SQL Editor;
0005 and 0006 through `scripts/apply_migrations.py`, now that
`DATABASE_URL` is in your own environment). `guardian_consent_schema_is_live()`
returns `True` against production. `tests/db/test_guardian_consent.py`
— the full sign-up/sign-in/confirm/RLS/RPC suite, 32 tests — has now
actually **run** against production, not skipped: **32 passed, 0
failed.**

**Applying 0004 for real surfaced two genuine production bugs no test
had ever exercised before** (every guardian-consent test had only ever
skipped, in every environment, until today):

1. **`create_guardian_consent_request()`'s `guardian_consents` insert
   failed outright** — `new row violates row-level security policy`.
   `guardian_consents` deliberately has zero SELECT policies (the token
   must never be readable, not even by the owning student), but
   supabase-py's default `Prefer: return=representation` asks Postgres
   to return the inserted row via `RETURNING`, and Postgres applies
   SELECT policies to that too. **Fixed**: `0005` adds a `SECURITY
   DEFINER` RPC that does the insert and reads the token back
   server-side, in the same statement, as the function owner — no
   REST-level `RETURNING`, so no SELECT policy is ever needed. Also
   derives the student from `auth.uid()` internally rather than a
   client-supplied id — a real security improvement, not just a
   workaround. See `app/api/guardian_consent.py`'s
   `create_guardian_consent_request` docstring.
2. **The token-generation trigger 500'd on every insert**: `function
   gen_random_bytes(integer) does not exist`. `0001_init.sql` enables
   `pgcrypto`, but Supabase installs its functions into an `extensions`
   schema, not `public` — confirmed live via `pg_proc`/`pg_namespace`.
   PostgREST sessions don't have `extensions` on their search_path, so
   the unqualified `gen_random_bytes(32)` call in `0004`'s trigger
   failed for every caller, through both the raw insert path and 0005's
   new RPC (the trigger fires on both). **Fixed**: `0006`
   schema-qualifies the call (`extensions.gen_random_bytes`). This one
   would have hit regardless of #1 — it's a separate, independent bug.

Both fixes also updated `guardian_consent_schema_is_live()` and
`tests/db/conftest.py`'s matching skip-check to require *every* one of
`0004`/`0005`/`0006`'s marker functions, not just `0004`'s — so any
future gap between applying one migration and the next degrades safely
to the existing clean 503 ("not yet available"), never a 500.

**What's still outstanding, only one of it a code/deployment gap:**

1. **Provision a real email provider** (any SMTP relay — SendGrid, SES,
   Mailgun, Resend, a plain mailbox all expose one) and put the
   credentials in your own environment (`SMTP_HOST`/`SMTP_USERNAME`/
   `SMTP_PASSWORD`/`SMTP_FROM_ADDRESS`, see `.env.example`). Until then,
   `app/notifications/logging_sender.py`'s `LoggingEmailSender` is what
   actually runs — it logs what would be sent (including the real
   confirmation link/token) and reaches no real inbox.
   `app/notifications/smtp_sender.py`'s `SmtpEmailSender` is a complete,
   working implementation (stdlib `smtplib`) gated exactly like
   `app/ai/gemini_provider.py` — set those four values and it's live,
   nothing else to build. **Note**: while `LoggingEmailSender` runs, its
   `INFO`-level log line includes the raw confirmation token — drop that
   to `DEBUG` or redact it before any real log aggregation/shipping is
   wired up, not after.
2. **A named human's review/sign-off** (`docs/SECURITY.md`) before any
   real minor account is enabled — this is a CLAUDE.md non-negotiable
   and not something any amount of AI review or live testing in this
   thread can substitute for, no matter how thoroughly it's been
   verified technically.

Previously, this section described `POST /auth/sign-up` as fully open
with no code path disabling a minor's account at all — that gap is
closed and verified live now.

**Also new this session**: `.env` was moved out of the repo entirely
(now `%USERPROFILE%\.secrets\bcion-lite.env`, loaded into a terminal
session only when needed — see `docs/DECISIONS.md`) so no agent session
ever has contact with real credentials, and `scripts/
bootstrap_schema_migrations.py` (new) records `0001`-`0004`'s
hand-applied history in `_schema_migrations` so `scripts/
apply_migrations.py` doesn't try to re-run them.

### What was built this session, file by file
- `db/migrations/0004_guardian_consent.sql` — `student_accounts`
  (`date_of_birth`, `account_status`), `guardian_consents` (`token`,
  `status`, `expires_at`), two enforcement triggers (age-vs-status on
  insert; insert-must-be-pending, mirroring `0003`'s "insert must be
  draft"), two security-definer functions (`my_guardian_consent_status`,
  `confirm_guardian_consent`), RLS with no SELECT policy at all on
  `guardian_consents` (the token is unreadable through the normal API,
  by anyone, ever) and no UPDATE policy on either table (only the
  security-definer confirm function can transition status). Own docstring
  has the full reasoning, including why two new tables rather than
  columns on `student_profiles`.
- `app/api/guardian_consent.py` (new) — age arithmetic
  (`MINOR_AGE_THRESHOLD_YEARS = 18`, named assumption), the sign-up-time
  request creator, and `enforce_guardian_consent_gate` — the actual
  sign-in-time enforcement, called from `app.api.auth.authenticate()` so
  both `POST /auth/sign-in` and the reviewer console's sign-in get it for
  free. Also `guardian_consent_schema_is_live()`, the "has 0004 been
  applied yet" probe that lets the rest of the app degrade safely (fail
  CLOSED for a minor sign-up, no-op for everyone else) while it hasn't.
- `app/api/auth.py` — `SignUpRequest.date_of_birth` (required),
  `.guardian_email` (required only when under 18); `AuthResponse` gained
  `account_status`/`message`, `access_token` is now optional (null on a
  pending account). `authenticate()` calls the gate above.
- `app/notifications/` (new package) — `sender.py` (the `EmailSender`
  Protocol), `logging_sender.py` (`LoggingEmailSender`, what actually
  runs everywhere today), `smtp_sender.py` (`SmtpEmailSender`, real and
  working but gated exactly like `GeminiProvider`, unconfigured
  everywhere), `factory.py` (`get_email_sender()`, picks between the
  two), `guardian_consent_email.py` (the email's actual text).
- `app/web/consent_pages.py` + `templates/consent_confirm.html` (new) —
  `GET /consent/confirm?token=...`, zero-JS, one generic failure message.
- `app/core/config.py` — `app_base_url`, `smtp_*` fields (all unset by
  default), `email_configured` property. `.env.example` documents the
  new names (values still nowhere in the repo).
- `tests/db/test_guardian_consent.py` (new, 14 tests, all correctly
  SKIP today — see above), `tests/unit/test_guardian_consent.py` (new,
  age-arithmetic + EmailSender-gating unit tests, all passing).
  `tests/db/test_api_auth.py` updated (`date_of_birth` added to every
  existing sign-up call) and `tests/db/conftest.py` gained the 0004
  skip-detection, mirroring 0003's own pattern exactly.
- **Verified this session, live, against the real (unmigrated) project**:
  `ruff check app tests` clean; `mypy` clean on every file this task
  touched (`mypy app --follow-imports=skip` — whole-app baseline, 41
  files, clean; a plain `mypy app` currently fails on an unrelated,
  pre-existing environment issue — numpy 2.5.2's own type stub uses
  Python-3.12-only syntax, reproduced identically on `app/ai/
  gemini_provider.py` alone, a file this task never touched — not caused
  by or specific to this session's changes); `pytest tests/unit -q` — 185
  passed; `pytest tests/db -q` — **110 passed, 14 skipped (the new
  guardian-consent tests, for the documented reason above), 0 failed** —
  i.e. every pre-existing live test still passes unchanged, including the
  adult sign-up/sign-in paths this task's own instructions called out as
  important not to regress.

## Guardian-consent gate: adversarial-review fixes (2026-09-21, merged
## to `main`)
Two independent adversarial reviews of the migration above (`1a714d5` in
the worktree this landed from) found a **CRITICAL complete bypass** and
**two HIGH gaps**, all closed this session, plus one MEDIUM and two
LOW/doc-only items. All fixes live in `db/migrations/0004_guardian_consent.sql` itself
(still unapplied anywhere, so editing it in place is correct — see the
file's own "append-only" note), `app/api/guardian_consent.py`,
`app/api/auth.py`, `docs/SECURITY.md`, and `tests/db/test_guardian_consent.py`.

1. **CRITICAL — complete bypass, `guardian_consents.token`.** The INSERT
   RLS policy constrained only `student_id`; nothing forced `token` to be
   server-generated. A caller could INSERT their own pending-consent row
   with a SELF-CHOSEN `token`/`guardian_email`, then call the
   anon-grantable `confirm_guardian_consent(p_token)` RPC with that same
   token to activate their own account with zero real guardian
   involvement. The migration's own comments *claimed* a trigger already
   prevented this — no such trigger existed. **Fixed**: a new BEFORE
   INSERT trigger (`enforce_guardian_consent_server_token`, mirroring
   `enforce_account_status_matches_age`'s existing pattern) unconditionally
   overwrites `token` (via `pgcrypto`'s `gen_random_bytes`, hex-encoded)
   and `expires_at` on every insert — a client-supplied value is silently
   replaced, never merely rejected, so the row is still usefully created.
   `app/api/guardian_consent.py`'s `create_guardian_consent_request` no
   longer generates the token client-side (dead code removed,
   `secrets.token_urlsafe` import gone) — it reads the real token back
   from the INSERT's own response instead, the same "trust what the
   database actually wrote" pattern `_migrate_pending_plan` already uses
   for a saved plan's id. **New tests**:
   `TestTokenAndExpiryAreServerGenerated` (2 tests) — proves a
   client-supplied token is overwritten and the attacker's chosen value
   can never confirm anything; same for `expires_at`.
2. **MEDIUM — no DB-level rate limit on `guardian_consents` inserts.**
   Idempotency was only ever enforced in Python (catching a unique-
   violation on the *`student_accounts`* insert). A direct API caller
   could otherwise INSERT unlimited `guardian_consents` rows with
   arbitrary `guardian_email` values — a spam vector once a real email
   provider exists. **Fixed**: a partial unique index
   (`guardian_consents_one_pending_per_student`, on `student_id` where
   `status = 'pending'`) enforces "at most one outstanding pending
   request per student" at the database layer regardless of caller;
   `create_guardian_consent_request` also now catches this
   unique-violation gracefully (same idempotent-return shape as the
   existing `student_accounts` case). **New test**:
   `TestOnlyOnePendingConsentPerStudent`.
3. **HIGH — a minor could name themselves as their own guardian.**
   Nothing stopped `guardian_email` from case-insensitively equalling the
   student's own sign-up `email`. Not exploitable today (no real email
   provider configured) but a complete, trivial defeat the moment one is.
   **Fixed**: `POST /auth/sign-up` now rejects this with a 400, same
   posture as the adjacent "guardian_email is required" check. **New
   test**: `test_under_18_sign_up_with_guardian_email_same_as_own_email_is_rejected`.
   **Follow-up (MEDIUM, a second adversarial pass, same day)**: that fix
   compared emails case-insensitively but exact-match, which a live
   re-check defeated via `+tag` sub-addressing — `name+guardian@gmail.com`
   still delivers to `name@gmail.com`'s inbox on Gmail, Outlook/M365,
   ProtonMail and FastMail (RFC 5233 "Sieve Subaddress"), so a minor could
   type that as `guardian_email` and still self-confirm. **Fixed**:
   `app.api.auth._normalize_email_for_self_check` strips a `+tag` suffix
   from the local part on both sides of the comparison before this
   check runs — deliberately NOT stripping dots too, since (unlike
   Gmail) most other providers treat a dotted and undotted local part as
   different mailboxes, and doing so would falsely reject a genuinely
   different guardian's real address. **New tests**:
   `test_under_18_sign_up_with_plus_tagged_own_email_as_guardian_is_rejected`
   (reproduces the exact bypass live, confirms it's now closed) and
   `test_under_18_sign_up_with_genuinely_different_guardian_dotted_email_is_accepted`
   (confirms the fix doesn't over-correct into false positives).
4. **HIGH — the gate wasn't backed by RLS on the tables that actually
   hold student data.** `enforce_guardian_consent_gate` is the ONLY place
   that ever blocked a pending account — real for every session this
   app's own `authenticate()` issues, but not a database guarantee: any
   future auth path that mints/accepts a session without going through
   `authenticate()` (password reset, magic link, OAuth, a future browser
   client talking to Supabase directly) would silently bypass this gate
   completely for `saved_plans`/`student_profiles`, which had zero
   reference to `account_status` in their own RLS. **Fixed**: a new
   `account_active(uid)` security-definer function (mirrors `is_reviewer()`
   exactly; default-open when a uid has no `student_accounts` row at all,
   since not every account is gated) is now ANDed into both
   `student_profiles_own_row` and `saved_plans_own_row`'s USING/WITH
   CHECK clauses. **New tests**: `TestAccountActiveGatesOtherOwnRowTables`
   (2 tests) — a pending account's own, validly-obtained-outside-the-app
   token can no longer read its own `saved_plans`/`student_profiles` row.
5. **LOW — no cross-user access-matrix coverage on this migration's own
   tables.** `tests/db/test_guardian_consent.py` never exercised
   `student_b`/`guest_client`/`reviewer` at all — CLAUDE.md requires this
   "every time auth, RLS or publication changes." **Fixed**: new
   `TestCrossUserAccessMatrix` (6 tests), mirroring
   `tests/db/test_api_plans.py`'s own pattern exactly.
6. **LOW, documentation only — no code change.** `app/notifications/
   logging_sender.py` logs the full email body, including the raw
   confirmation token, at `INFO` level — deliberate today (nowhere else
   for the token to go), but must be dropped to `DEBUG` or redacted
   before any real log aggregation/shipping exists. Noted in
   `docs/SECURITY.md` and above.

**Verified this session** (`ruff check app tests` clean; `mypy app
--follow-imports=skip` clean, 41 files — the same pre-existing,
unrelated numpy/3.12 stub issue on a plain `mypy app` noted above
recurred and was worked around the same way; `pytest tests/unit -q` —
185 passed in the worktree, 191 passed after merging with `main`'s own
unit-test additions): `pytest tests/db -q` — **110 passed, 28 skipped, 0
failed** (28 = the prior 26 plus 2 new tests for the `+tag` follow-up
above — every one of them correctly SKIPS, for the same documented
reason as before: migration `0004` is still not applied to the live
project). The `+tag` bypass itself, and the fix closing it, were both
live-reproduced directly against a running `TestClient` (not just unit-
tested) before this was merged — see the `+tag` item above. **What I
could NOT verify live**: the actual trigger/index/RLS behaviour these
fixes add — same limitation as the original build, unchanged by this
session. I did not attempt to apply the migration myself (no
`DATABASE_URL` in the source worktree's `.env`; the Supabase MCP tool
remains off-limits per `docs/DECISIONS.md` "Infrastructure accounts").
**Merged to `main`** (from `worktree-wf_7ee1927f-553-1`, after the
`+tag` fix and a manual conflict resolution in `app/api/auth.py` against
the reviewer-console-audit-fixes work that landed on `main` in the
meantime — both sets of fixes are preserved, see the merge commit).
**Owner action needed before any of this is real**: apply the
(now-fixed) `0004_guardian_consent.sql` to the live project, then re-run
`pytest tests/db -q` for a genuine pass/fail on all 28 guardian-consent
tests plus the pre-existing 110+. **Also still outstanding, per
`docs/SECURITY.md`**: a named human's review/sign-off before any real
minor account is enabled — not something any AI review in this thread
can substitute for.

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
**Stale as of 2026-09-21 — kept for history, not current guidance.** This
section predates the plan (`docs/DEVELOPMENT-PLAN.md`) and the M5/E2E
work below it; both "not done yet" items it names (a reviewer console,
Playwright e2e) are done. **Current pointer:** see this file's own top
section ("Development plan") for what's merged and what's in flight —
the plan's wave/lane tables (`docs/DEVELOPMENT-PLAN.md` sections 5, 6.4,
8.8) are what actually govern "what's next" now, not this paragraph.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`). Schema `0001`-`0006` all applied and verified, including the guardian-consent gate — see the ⚠️ section above. `tests/db/test_guardian_consent.py`: 32 passed, 0 failed, live against production. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input
1. **Consent/safeguarding gate — see the ⚠️ section above.** The
   mechanism is built, migrated, and live-tested against production (32
   passed, 0 failed); **one concrete action remains**: provision a real
   email provider (SMTP credentials in your own environment, no longer
   `.env` — see `docs/DECISIONS.md`). Plus a named human's sign-off
   before any real minor account is enabled. Blocks item 2 below.
   Not blocking engineering elsewhere, but blocking any move toward
   public reachability — arguably more so than before, since a
   not-yet-merged worktree (`.claude/worktrees/wf_9b7797a4-e76-1`,
   confirmed still present via `git worktree list` this session, branch
   `worktree-wf_9b7797a4-e76-1` — its contents were not read or touched;
   this session is isolated to its own worktree) is building a browser-
   facing student sign-up UI on `app/web/student_pages.py`, a file that
   does not exist on this session's own base branch. **That UI's own
   `student_sign_up_submit()` will need a `date_of_birth` field (and a
   `guardian_email` field, shown conditionally once age is known) added
   to its form and forwarded to `POST /auth/sign-up` exactly as the JSON
   API now requires — whoever merges that work next should read this
   entry and `app/api/auth.py`'s `SignUpRequest` before wiring the
   form**, or that screen will 400 on every under-18 submission (or, if
   it hand-builds its own request body without the new fields, silently
   422 with FastAPI's own "field required" error) until it's updated.
2. **Public domain** — hold until item 1 is resolved (both parts). Once
   it is, send a domain/subdomain and I'll add an nginx site.
3. **Pilot scope widened (2026-09-21, resolved)** — admission rules now
   all-India (was one-state/Gujarat), plus foreign/study-abroad pathways
   for Indian students added as new scope. See `docs/DECISIONS.md`
   2026-09-21. **Open follow-up**: whether the numeric ceilings (20–30
   career families, 50–100 programme records, 12-week schedule) also
   change or whether the wider scope is phased in within them — not yet
   answered.
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
E2E exists and runs locally/in a worktree (`make test-e2e`, zero skips)
but is **not yet a CI job** (tracked: QA-5). No live AI call anywhere —
the M5 safety layer exists but nothing calls a real provider yet, and
`ai_enabled` defaults false. No public exposure of the deployed app yet
(no domain, no nginx site — see "Needs your input" above). No real
content exists — every test uses clearly-labelled synthetic fixtures;
nothing has been published as a verified fact for an actual student to
see.

## E2E strict-mode locator fix (2026-09-22)
`tests/e2e/test_smoke.py::TestRequirementsAndTimelineJourney::
test_timeline_view_computes_a_total_from_one_filled_stage` was failing
with a Playwright strict-mode violation: `page.get_by_text("52 weeks")`
matched both the total (`<p class="text-2xl font-semibold
text-charcoal">` in `app/web/templates/timeline_calculator.html`) and a
second echo of the same number in the per-stage breakdown `<span
class="text-neutral">` that UI-7/RULES-9 added. Test-only fix: narrowed
the locator to `page.locator("p.text-2xl.font-semibold.text-charcoal")`
(`tests/e2e/test_smoke.py:292`), which is unambiguous — the breakdown
list uses a `<span>`, not a `<p>`, with different classes. No app
behaviour changed. Verified against the already-running local Supabase
stack (`bcion-lite-test`, up from earlier work this session) with
migrations already applied: the target test passes cleanly on repeated
isolated runs.
Also ran the full `tests/e2e/test_smoke.py` file once: 1 passed
(this one), 5 failed, all with unrelated `Page.goto: Timeout 30000ms
exceeded` errors (reviewer sign-in, requirements view, compare view, and
— on that run only — this same timeline test) rather than any
locator/content mismatch. Re-running the timeline test alone immediately
after passed clean again, so this looks like environment resource
contention (two full local Supabase stacks — `bcion-lite-test` and
`bcion-lite-migration` — were both up for over an hour from concurrent
work) rather than a real regression. Not investigated further — out of
scope for this task; worth a look if it recurs.

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
