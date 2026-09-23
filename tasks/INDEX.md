# BCION Lite - task index and checklist

**DRAFT - generated 2026-09-21, finalised by DOCS-3 (sixth pass) - not yet owner-approved.** Nothing here authorises work.

Sources:

- Plan, waves, caps, gates: [../docs/DEVELOPMENT-PLAN.md](../docs/DEVELOPMENT-PLAN.md)
- Task definitions (lead-only reading; find a task with Grep on its id heading):
  [inventory-1-product](../docs/plan/inventory-1-product.md) (DATA, RULES, UI, AUTH, DESIGN, I18N, A11Y),
  [inventory-2-trust-content](../docs/plan/inventory-2-trust-content.md) (CONSENT, PUB, CONTENT, SCOPE, AI, SEC),
  [inventory-3-platform-launch](../docs/plan/inventory-3-platform-launch.md) (OPS, DEPLOY, QA, TRIAL, DOCS)
- State of what is built: `../STATUS.md` (this file is not a status tracker until DOCS-3 adopts it).

How to read it:

- Steps are the build pack section 9 steps. A task sits under the step named in its audit, so some early work appears under a late step (for example DEPLOY-6 under Step 14). The tag in brackets says **when** it runs: `W0`-`W5` = Phase 1 wave, `float` = Phase 1 only if a lane is free (else P2-A), `P2` / `P3` = later phase, `owner` = you do it, `new` = added by the plan (no inventory entry; defined in plan section 3).
- The inventory's own "Wave: N" field is a dependency depth, not these waves. Ignore it.
- 248 audit tasks + 12 added = 260. 19 are dropped for the pilot (listed at the end, no checkbox). One audited task (CONSENT-1) is listed but marked SUPERSEDED, not built - see Step 8.
- Existing cards: BCI-001..006 (done). Sessions 1 and 3 of plan section 15 become BCI-007 (DOCS-1), BCI-008 (DOCS-3). Session 2 (CONSENT-1) is skipped, superseded - no BCI-008 slot for it.

Migration ledger (Phase 1 order): 0007 DATA-12, 0008 SCOPE-3, 0009 AUTH-4, 0010 AUTH-5, 0011 PUB-2 (planning estimate — **actually real now as `0011_ai_usage.sql`/AI-4**, merged to main while PUB-2 was still unbuilt), 0012 PUB-3 (planning estimate — **actually real now as `0012_admission_axis.sql`/CONSENT-4**), 0013 SEC-6 (planning estimate — **actually real now as `0013_safeguarding_schema.sql`/CONSENT-4**), 0014 CONSENT-4 (**wrong on two counts: CONSENT-4 landed on 0012+0013, not one file at 0014 — see the migration-owner fix round below**). Phase 2: AUTH-7, AUTH-10, DATA-4, I18N-7, I18N-8, AUTH-15, OPS-6, TRIAL-5. Owner apply batches: DATA-10a (through 0008), DATA-10b (through 0010), PUB-4 (through 0012), DATA-10c (through 0014). **PROVISIONAL — re-verify against `ls db/migrations/` before the migration lane opens**: 0004 and 0005 are already real, taken by another session's guardian-consent gate, not this plan's — that is why the ledger starts at 0007, not 0004 (see docs/DEVELOPMENT-PLAN.md section 16 for the two collisions that moved this). **A third collision (2026-09-22, migration-owner fix round on CONSENT-4's own worktree):** AI-4 merged `0011_ai_usage.sql` to main and applied it to the shared test stack while CONSENT-4 was mid-review with its own two files sitting at (old) 0011/0012 — renumbered to real 0012 (`0012_admission_axis.sql`) and 0013 (`0013_safeguarding_schema.sql`); PUB-2, PUB-3 and SEC-6's planning slots above are now all stale and need re-verifying against a fresh `ls db/migrations/` (not silently renumbered here — that is those lanes'/the lead's call, not this fix round's). **0014** is also now real: `0014_account_active_grant_fix.sql` (this same fix round) — closes a live, pre-existing anon-key cross-user oracle in already-merged `0004_guardian_consent.sql`'s `account_active()`, unrelated to any planning-doc slot above.

Lockboard (lead only): `RESET` line goes here before the shared local stack is reset. Currently: none. (Migration `0015_ai_identity_binding.sql` applied to `bcion-lite-test` 2026-09-22 evening, additively, no reset - the account identity-hash oracle in `ai_reserve`/`ai_budget_remaining` is now closed there; 36/36 targeted live tests pass with the fix active. Full `tests/db` regression run for final confirmation.)

---

## Step 0 Prepare - DONE
## Step 1 Memory and rules (M0) - DONE (BCI-001)
Memory refresh tasks are under "Cross-cutting" below.

## Step 2 Scaffold and tests (M0) - DONE, hardening open
- [x] SEC-7 - Pinned lockfile, dependency audit, secret scan in CI [W1]
- [ ] QA-5 - CI: local-stack DB job, e2e job, caching, no-skip, fresh rebuild, additive-only check [W2]

## Step 3 Agent team (M0) - PARTIAL (two reviewers exist, never calibrated)
- [ ] QA-9 - data-security-reviewer calibration on seeded flaws, one session [W2]
- [ ] QA-9b - ux-qa-reviewer calibration and file edit [P2, new]

## Step 4 Data foundation (M1) - DONE (BCI-002..006, 0001-0003), hardening open
- [x] QA-1 - Docker + Supabase CLI; approve local test backend [W0, owner]
- [x] QA-2 - Local Supabase stack, target guard, strict no-skip, `make verify` [W1]
- [x] QA-3 - Run-tagged fixtures, sweeper, xdist (exclusive window on tests/db and tests/e2e) [W1]
- [x] DESIGN-5 - Three journeys plus the teacher demonstration journey [W1]
- [x] SCOPE-3 - Migration 0008: jurisdiction, cycle, currency columns, freeze-trigger update [W2]
- [x] QA-6 - Cross-user access matrix with a table guard [W2]
- [ ] SEC-6 - Migration 0013: grants and exposure hardening, catalogue test [W4]

## Step 5 Private staging (M1) - PARTIAL (app on the VM, localhost only)
- [ ] CONSENT-18 - Supabase dashboard sign-ups OFF [W0, owner, new]
- [ ] DEPLOY-1 - Record Oracle VM facts and hosting decisions [W0, owner]
- [x] DEPLOY-18 - Flags and wiring stub (config flags, middleware and router registry, mk/*.mk) [W1, new]
- [x] DEPLOY-5 - Readiness endpoint and read-only smoke script [W1]
- [x] DATA-15 - `--through NNNN` for apply_migrations.py [W2, new]
- [x] DATA-12 - Migration 0007: DB-gated demo mode for synthetic data [W2]
- [x] DATA-8 - Synthetic seed script [W2]
- [ ] DEPLOY-2 - Environment contract, hosting docs (its hosting facts for `docs/DECISIONS.md`/`STATUS.md` come back as proposed lines; the lead drafts D13/D16 in DOCS-5, not here) [W2]
- [x] DEPLOY-3 - Dockerfile, install from requirements.lock, make build, CI image build [W2]
- [ ] DEPLOY-4 - Compose file and nginx site templates [W2]
- [ ] DEPLOY-15 - Behind-proxy and config hardening; refuse unknown sign-up flag names [W2]
- [ ] DEPLOY-7 - Bring up private staging on the VM, owner-only [W2-W3, owner, days 8-10]

## Step 6 UI system and Explore (M1) - PARTIAL (Explore exists; no shell, no keys)
- [x] DESIGN-2 - Copy rules, microcopy deck, key convention (docs/COPY.md) [W1]
- [x] DESIGN-1 - Component and state contract v1 in docs/UI.md [W1]
- [x] DESIGN-3 - Banned-phrase lint test [W1]
- [x] I18N-1 - i18n mechanism, shared Jinja env, frozen key contract [W2]
- [x] UI-1 - App shell, nav, stub partials, macros, sample-data ribbon (2 sessions; does **not** edit the journey templates — A11Y-2 adds the `_save.html` include lines) [W2]
- [x] DESIGN-18 - Content component macros; fills `_ask` and `_why` stubs [W2]
- [ ] I18N-3 - Extract strings from existing templates, split by file; string-lint merges last [W3a]
- [x] UI-3 - Landing page and stateless quick start [W3a]
- [x] UI-4 - Suggestion rule and "why am I seeing this" [W3a] -- fix round (2026-09-23): unknown-preference link text, consistent capitalization, broadened-signal heading, pathway_detail_link reuse; known follow-up not yet carded: reusing pathway_detail_link changed the suggestion list's pathway-name display from a prominent standalone link to smaller text embedded in "See the full record for X" -- non-misleading, but less scannable; add a separate name heading matching explore.html's own two-part pattern
- [x] SCOPE-6 - Derived coverage and "not verified yet" states [W3b, DONE, merged; fix round: demo-mode security test, 44px touch targets, aria-current, honest copy]
- [ ] I18N-4 - Language switch with a prod flag [P2]

## Step 7 Compare and calculators (M2) + usability round 1 - PARTIAL (screens exist; no exam modules)
- [x] RULES-1 - Rules contract v2 [W1, contract burst]
- [~] I18N-6 - Name the Hindi reviewer, fix the critical-key list [W0, owner, day 3] — **reviewer named: Mahesh** (2026-09-22, docs/DECISIONS.md); critical-key list fix still open
- [ ] DESIGN-6 - Owner picks the round-1 vehicle [W0, owner, day 4]
- [x] RULES-2 - Date-based age criteria (input fields only; before SEC-5) [W2]
- [x] RULES-3 - Any-of subject groups, thresholds, qualification criteria [W2]
- [x] RULES-4 - RuleSet, registry, cycle and jurisdiction guard, honest empty result [W2]
- [x] RULES-5 - Reference exam module: NEET-UG [W2]
- [x] RULES-6 - JEE Main and GUJCET modules (one implementer) [W2]
- [x] RULES-10 - Itemised cost, Money type, public `safe_source_url` [W2] -- Money type + multi-component sums done and verified live; `safe_source_url` is still 3 separate private copies (comparison.py, eligibility.py, reviewer/queue.py), not yet consolidated to one public helper -- left for SCOPE-4, which needs it next anyway (see docs/DECISIONS.md 2026-09-22)
- [x] SEC-5 - Move eligibility inputs out of URLs [W2]
- [x] SCOPE-5 - State/UT and country code list, domicile select [W2]
- [x] UI-5 - Career card and pathway detail page [W3a]
- [x] RULES-8 - Wire RuleSets into the eligibility API [W3a] -- invented the "rule_key" claim-field convention (no prior one existed; see docs/DECISIONS.md 2026-09-22); non-IN pathway display-only gate still not implemented on the fallback path
- [x] RULES-9 - Timeline seeding from stage claims (session 1 W3a, session 2 W3b) -- invented the "stage:<order>:*" claim convention (no prior one existed; see docs/DECISIONS.md 2026-09-22)
- [x] UI-6 - Cost-assumption editing on Compare [W3b, DONE, merged; fix round: implausible-value plausibility ceiling; second fix round (2026-09-23): Funding/Work realities/Alternatives normalised to the dashed-border not_available badge, matching every other missing field on the same card]
- [x] SCOPE-4 - Currency-safe cost display [W3b] -- its disclosed follow-up (itemised fee_component:* claims with no legacy verified_charges claim showed "Not available" on the display line while the total used the components) is now closed: merged b75f939 (2026-09-22)
- [x] UI-7 - Timeline stage kinds and "Revise this scenario" [W3b] -- pathway_id/pathway_name are display-only context, not yet wired from any linking screen
- [x] RULES-16 - Requirements screen: DOB input, cycle label, "not checked here" list [W3b]
- [ ] QA-7 - Mobile and desktop viewport e2e, full guest journey [W3b]
- [ ] UI-15 - Owner phone walk-through and component-set freeze [W3, owner]
- [ ] TRIAL-8 - Usability round 1: guest only, ADULTS ONLY, on the round1-rc tag [W4, people]
- [ ] TRIAL-9 - Round-1 synthesis into a ranked fix list [W4]
- [ ] UI-19 - Round-1 fix round [float, else first P2 task]
- [ ] RULES-15 - CUET-UG and CLAT modules [P2]
- [ ] DATA-4 - Opportunity entities and pathway_transitions (no stage tables) [P2]
- [ ] SCOPE-7 - Foreign pathway "Visa and entry" block [P2, firm]
- [ ] UI-20 - Compare sections for assistance, backup routes, next key date, met/not met [P2, new]
- [ ] I18N-5 - Hindi catalogue machine draft [P2]
- [ ] I18N-15 - Message codes for eligibility and timeline text [P2]

## Step 8 Sign-in, plans, consent (M3) - PARTIAL and BLOCKED (no age or consent gate)
- ~~CONSENT-1~~ - **SUPERSEDED, not built.** Another session merged a real age + guardian-email consent gate (`db/migrations/0004_guardian_consent.sql`, `0005_guardian_consent_request_rpc.sql`, confirmed live in production) while this plan was being written — it does the actual job this stopgap was a cheap stand-in for, more completely. No checkbox; not counted in the 260 total's checklist.
- [x] CONSENT-2 - Owner names safeguarding people and the non-author reviewer [W0, owner, day 3] — **Mahesh, both seats** (2026-09-22, docs/DECISIONS.md); his actual read of docs/CONSENT.md is still the gate on CONSENT-4's merge
- [x] AUTH-1 - Session, guest and plan-store contract (owner explicit yes) [W1, contract burst]
- [x] CONSENT-3 - Consent and safeguarding design doc (placeholders; human read follows) [W1, contract burst]
- [x] SEC-2 - CSRF contract for cookie sessions [W2]
- [x] AUTH-4 - Migration 0009: guest server session [W2]
- [x] AUTH-5 - Migration 0010: next actions, plan validation [W2]
- [ ] AUTH-6 - My Plan and Save controls, guest mode, new files only, cross-user lines [W3a]
- [x] CONSENT-4 - Migrations 0012+0013 (renumbered from a stale 0014 planning slot — see the ledger note above): admission axis (`admitted_at`, `is_admitted()`, invite redemption via `pilot_invites`/`redeem_invite`) + safeguarding schema (`consents`, `safeguarding_staff`, `safeguarding_flags`, `withdraw_account()`) [W4, DONE, merged; 3-lens adversarial review, one fix round; also closed a live anon-key oracle on already-merged `account_active()` (0014), unrelated to this task's own scope but found while reviewing it] -- independently re-verified (2026-09-22 evening); two LOWs not carded, backlog only: (1) app/api/ask.py's 42501-as-404 catch should log when the caller isn't a guest, so a future grant misconfiguration doesn't silently look like "not found"; (2) 0012's `pilot_invites.used_by ... on delete set null` un-consumes an unexpired invite if the redeemer's auth.users row is ever deleted
- [ ] AUTH-2 - Student cookie session [float]
- [ ] AUTH-3 - Sign-in, sign-up (flagged off), sign-out pages [float]
- [ ] AUTH-14 - My Plan signed-in mode, `needs_review` banner [float]
- [ ] CONSENT-6 - Interim gate in the API: invite, 18+, terms [float]
- [ ] CONSENT-7 - Distress keyword rule with helpline response (fails open) [float]
- [ ] CONSENT-8 - Staff-only safeguarding queue [float]
- [ ] CONSENT-10 - Withdraw consent and 30-day deletion runbook [float]
- [ ] CONSENT-6b - Sign-up form fields and withdraw button [float, new]
- [ ] AUTH-9 - Student data export [P2]
- [ ] UI-13 - Utility menu pages and footer [P2]
- [ ] AUTH-7 - Guest-to-account migration [P2]
- [ ] AUTH-10 - Account deletion via definer function [P2]
- [ ] AUTH-15 - plan_versions [P2]
- [ ] CONSENT-5 - Owner: Supabase Auth settings, redirect allow-list, invite hand-out [P2, owner]
- [ ] CONSENT-9 - Human review of the Hindi/Hinglish phrase list and helpline [P2, human]
- [ ] CONSENT-11 - Non-author gate review of the consent workflow [P2, human]
- [ ] DATA-11 - Owner apply batch, schema review, human sign-off [P2, owner]
- [ ] AUTH-12 - Independent security review of the auth surface [P2]
- [ ] AUTH-17 - Shared-phone check on a real Android device [P2, human]
- [ ] QA-10 - Signed-in journey e2e, browser-level cross-user checks [P2]
- DESIGN-11, DESIGN-12 - shrunk to one consent-screen sentence inside CONSENT-3 (no separate card)

## Step 9 Publishing console (M4) - PARTIAL (console exists; self-approval bypass open)
- [x] PUB-13a - Owner names reviewers [W0, owner, day 3] — **Mahesh** (2026-09-22, docs/DECISIONS.md); account creation is PUB-13b
- [x] PUB-1 - Publishing contract incl. content hash (owner explicit yes) [W1, contract burst]
- [x] PUB-5 - Split reviewer_pages.py into a package [W1]
- [ ] PUB-2 - Migration 0011: identity enforcement, source versions, claim columns [W3]
- [ ] PUB-3 - Migration 0012: audit events, atomic publish functions, plan flag [W3]
- [ ] PUB-4 - Owner applies through 0012 after the adversarial review [W3-W4, owner]
- [ ] PUB-13b - Owner: checker account, reviewers rows, critical_authorised on staging [W3-W4, owner, new]
- [ ] SCOPE-13 - Reviewer-side currency and jurisdiction integrity [W4]
- [ ] PUB-6 - Sources and source-version API [P2]
- [ ] PUB-7 - Claims API completion [P2]
- [ ] PUB-8 - Console source and claim forms [P2]
- [ ] PUB-9 - Console review detail, published list, supersede flow [P2]
- [ ] PUB-10 - Console review-due view [P2]
- [ ] PUB-15 - Reviewer-flow e2e [P2]
- [ ] PUB-12 - Independent publication-integrity review [P2]
- [ ] PUB-14 - Two-reviewer dry run on five real records [P2]

## Step 10 Real pilot dataset (M4) - OPEN (drafts only)
- [~] CONTENT-1 - Owner names editor, checker, corrections owner [W0, owner, day 3] — **checker: Mahesh**; editor and corrections owner default to the owner until named (maker ≠ checker must hold) (2026-09-22, docs/DECISIONS.md)
- [ ] TRIAL-7 - Open the editor-hours log [W0, owner, day 4]
- [~] CONTENT-2 - Import contract: CSV templates, closed vocabulary, hash rule — **contract half done** (the content-hash field list and source_version rule are frozen in `docs/CONTRACTS.md` "Publishing evidence in Phase 1"); **artefacts still open**: `docs/CONTENT-IMPORT.md`, `content/templates/claims_import.csv`, `content/templates/sources_register.csv`, the closed `field` vocabulary — deliberately left outside the contract-burst agent's owned files, needs its own small session before CONTENT-3 [W1, contract burst]
- [x] CONTENT-3 - Offline draft extractor and inventory [W1]
- [ ] QA-12 - Sweep test residue out of the live project (before DATA-10a) [W2]
- [x] CONTENT-4 - Source register and allow-list checker (`make content-check`) [W2-W3, mixed]
- [x] CONTENT-5 - Curate the trial subset (deadline, backup, scholarship per family) [W2-W3, mixed]
- [x] CONTENT-15 - Editor and checker handbook [W2-W3, mixed]
- [x] CONTENT-6 - Importer session 1: validation, no DB writes [W2]
- [ ] CONTENT-6b - Importer DB half after PUB-3: upsert, tier, source_version, hash [W4, new]
- [ ] CONTENT-7 - Per-source review packets with hashes [W4]
- [ ] CONTENT-9 - Content batch 0: one family end to end on staging, timed [W4-W5, people]
- [ ] SCOPE-8 - Reviewer standard for non-Indian and state sources [W5 head start, else P2]
- [ ] SCOPE-14 - Draft admission-rules profiles for the trial states [W5 head start, else P2]
- [ ] CONTENT-8 - Coverage, freshness and integrity report [P2]
- [ ] RULES-7 - NDA, SSC CGL, IBPS PO modules (only for exams with verified claims) [P2]
- [ ] RULES-12 - Human review of each exam's rule case table [P2, human]
- [ ] CONTENT-10 - Content batch 1: full trial subset verified and published [P2, human]
- [ ] SCOPE-9 - Human verification of the trial coverage set [P2, human]
- [ ] CONTENT-11 - Cycle-roll recheck for tier-1 exam claims [P2, human]

## Step 11 Bounded AI (M5) - PHASE 1a: AI ONLY, alongside Phase 1, merged behind the flag (owner decision 2026-09-22; plan in `docs/plan/phase-1a-ai.md`, lead-only)
Every card here carries the three Phase 1a rules: answer or refuse, never guess; two model verifications plus code validation on every call; free Gemini tier, so no student-typed text ever leaves. AI-4 takes migration **0011**; the Phase 1 ledger above shifts by one (PUB-2 0012, PUB-3 0013, SEC-6 0014, CONSENT-4 0015). Production `AI_ENABLED` stays false; AI-17 stays a Phase 2 gate.
- [x] AI-2 - AI_ENABLED flag, kill switch, /readyz reports it [W2]
- [ ] AI-10 - Owner: free-tier terms and limits recorded, restricted key, provider-side cap [P1a day 1, owner]
- [x] AI-1 - AI contract, schemas, typed errors, outbound allow-list model [P1a L1, day 1, DONE, merged]
- [x] AI-3 - Provider hardening: retries off, typed errors, two-pass mock, injectable client [P1a L4, DONE, merged]
- [x] AI-5 - Retrieval of approved records, import guard [P1a L5, DONE, merged; live fixture bug found+fixed at merge, see docs/DECISIONS.md]
- [x] AI-9 - AI evaluator agent (proposed file) and 36-question evaluation set [P1a L3, day 1, DONE, merged; .claude/agents/ai-evaluator.md applied]
- [x] UI-11 - Ask BCION shell, deterministic first, no input element [P1a L6, DONE, merged; router registered, i18n reconciled to askbcion.* at merge]
- [x] AI-4 - Migration 0011: ai_usage, atomic two-call reservation, per-identity and global caps, RLS [P1a L2, migration-owner, DONE, merged on its own third stack; not yet applied to the shared test stack - see lockboard]
- [x] AI-6 - Two-pass pipeline (selection + verification), prompts, guards, outbound allow-list [P1a L4, DONE, merged]
- [x] AI-7 - Ask BCION route wired to the pipeline; identity = account or guest session [P1a L6, DONE, merged; JSON route renders sentences/citations, HTML template markup still needed - follow-up]
- [x] AI-8 - AI-off journey regression (flag off; mock failing) [P1a L6, DONE, merged]
- [x] AI-11 - Capped evaluation runner; first run synthetic on the local stack, second on staging [P1a L3 script, DONE, merged; first live-data run complete on the local stack, see STATUS.md]
- [ ] AI-16 - Hindi-preferring person reviews Hindi answers and AI-20 drafts [P1a, human; needs I18N-6]
- [ ] AI-12 - Fix round, enable on staging (or dev, recorded), kill-switch drill [P1a L4 + owner]
- [ ] AI-17 - Owner sign-off to enable AI on production (after AI-13) [P2, owner - unchanged]
- [x] AI-14 - AI-assisted claim extraction drafts: paste text, extraction + verification pass, verbatim-span check, draft only [P1a L8, x2, un-dropped, DONE, merged]
- [x] AI-18 - Next-steps template over a server-owned, claim-bound action catalogue [P1a L10, x2, new, DONE, merged]
- [x] AI-19 - What-changed summary over the superseded_by diff [P1a L10, new, DONE, merged; currently reviewer-only in effect, see STATUS.md]
- [x] BCI-025 (UI-12, new, not in the original card set) - `/ask/view` now renders all four AI content kinds and resolves `next_steps`/`what_changed`'s own id shapes, matching `GET /ask`'s JSON contract [P1a follow-up, DONE, merged 2026-09-23]
- [x] BCI-026 (new, audit follow-up) - the database-backed AI budget (0011/0015) is now actually wired into the live Ask BCION routes, replacing the shared global-only counter [P1a follow-up, DONE, merged 2026-09-23]
- [x] BCI-027 (new, audit follow-up) - a real per-request banned-phrase scan now runs over generated answer sentences, not just fixed labels at import time [P1a follow-up, DONE, merged 2026-09-23]
- [x] AI-20 - Hindi content drafts, offline batch with back-translation check, CSV for the reviewer [P1a L9, DONE, merged]

## Step 12 Hindi, accessibility, difficult states (M6) - OPEN
- [x] A11Y-1 - Difficult-states and cache-class contract [W1, contract burst]
- [x] I18N-2 - Locale-aware formatting helpers [W2]
- [x] A11Y-4 - Cache-Control middleware, shared-device hygiene [W2] -- e2e shared-device test written but not passing in CI/local pytest yet, blocked on a pytest-playwright environment hang tracked separately
- [x] A11Y-5 - Guard test: no service worker or client persistence [W2]
- [x] A11Y-2 - State macros and base.html landmarks [W3a]
- [x] A11Y-3 - Global HTML error pages [P2, DONE, merged]
- [ ] I18N-7 - Hindi label columns [P2]
- [ ] I18N-8 - Search schema [P2]
- [ ] I18N-9 - Search route and Explore search box [P2]
- [ ] I18N-10 - Synonym list [P2]
- [ ] I18N-12 - Hindi expansion and font-stack pass [P2]
- [ ] A11Y-6 - Viewport, zoom and axe matrix [P2]
- [ ] A11Y-7 - Keyboard-order and focus e2e [P2]
- [ ] A11Y-8 - Weak-connection treatment, page-weight budget [P2]
- [ ] A11Y-14 - Reviewer templates and form hint association [P2]
- [ ] DESIGN-15 - Hindi draft and review of critical microcopy [P2]
- [ ] I18N-11 - Human Hindi review of critical keys [P2, human]
- [ ] A11Y-11 - Human screen-reader, keyboard and phone spot check [P2, human]
- [ ] A11Y-12 - Fix round from the spot check [P2]
- [ ] I18N-13 - New-screen key compliance sweep [P2]
- [ ] A11Y-9 - Verify difficult states on feature screens [P2]
- [ ] CONTENT-17 - Hindi review of trial-subset critical content [P2, human]
- [ ] I18N-16 - Delta Hindi review for late keys [P2]
- [ ] CONTENT-20 - Owner declares the content freeze before DEPLOY-12 [P2, owner, new]

## Step 13 Operational safety and release review - OPEN
- [ ] OPS-1 - Owner: vendors, backup tier, VM region, n8n status [W0, owner]
- [x] OPS-2 - PII-free structured logging and request id [W2, DONE, already merged -- app/core/logging.py, configure_observability(app), tests/unit/test_logging_redaction.py (16 passed); checkbox was stale, found while scouting the next wave 2026-09-23]
- [x] RULES-11 - "Critical rule cases" gate command [W2]
- [x] SEC-3 - Proxy rate limiting [P2] (nginx config, not yet wired into a live deploy — DEPLOY-4/7 to wire in)
- [ ] TRIAL-5 - usage_events table and metric views [P2]
- [ ] TRIAL-16 - Usage event write hook [P2]
- [ ] OPS-4 - Error tracking with scrubbed payloads [P2]
- [ ] OPS-6 - "Report a problem" form and feedback table [P2]
- [ ] OPS-7 - RUNBOOK.md and RELEASE_CHECKLIST.md [P2]
- [ ] OPS-9 - Backup dump and restore-check scripts [P2]
- [ ] OPS-10 - 25-session load script [P2]
- [ ] RULES-13 - Calibration fixtures and property sweeps [P2]
- [ ] DATA-13 - Owner apply of the ten-user-trial batch, grant audit [P2, owner]
- [ ] OPS-8 - Uptime check live and alert tested [P2, owner]
- [ ] OPS-15 - Restore drill [P2, owner]
- [ ] OPS-16 - Run the load test on staging (owner-run) [P2]
- [ ] SEC-14 - Purge pre-hardening VM logs [P2, owner]
- [ ] QA-16 - Release-candidate run against staging (owner-run) [P2]
- [ ] SEC-10 - Pre-release security review [P2]
- [ ] SEC-13 - Human security and child-data sign-off [P2, human]
- [ ] OPS-5 - Jobs table [P3, only if something enqueues work]
- [ ] OPS-14 - Worker process [P3, only if something enqueues work]

## Step 14 Production deployment (M6) - OPEN
- [ ] DEPLOY-17 - Protect main, restrict repo and VM access [W1-W2, owner]
- [ ] DEPLOY-9 - Pause flag (`MAINTENANCE_MODE` only) [W2]
- [ ] DEPLOY-6 - Owner-run deploy and rollback script with a migration-level guard [W2]
- [ ] DEPLOY-10 - Release checklist and runbook deploy sections [P2]
- [ ] DEPLOY-11 - Owner: clean production Supabase project and VM prod env [P2, owner]
- [ ] DATA-14 - Owner: apply all migrations to production, audit grants [P2, owner, new]
- [ ] DEPLOY-12 - Release review of the candidate commit [P2]
- [ ] DEPLOY-13 - Production deploy, public hostname, pause drill [P2, owner]

## Step 15 Ten-person trial - OPEN
- [x] TRIAL-2 - Research pack: scripts, scoring sheet, adult consent sheet [W1]
- [x] TRIAL-10 - Go/no-go template and batch expansion checklist [W2 filler]
- [ ] TRIAL-3 - Decision-quality instrument, English draft [W4]; Hindi half [P2]
- [ ] TRIAL-4 - Owner approves Step 15 gates and pause limits [end of P2, owner]
- [ ] TRIAL-11 - Ten-person trial, round 2, instrument pre-test [P3, people]
- [ ] DESIGN-16 - Round 2 script delta and scoring [P3]
- [ ] TRIAL-12 - Go/no-go report [P3]
- [ ] DESIGN-14 - Teacher pack [P3, before the first school session]

## Step 16 Expand to 100 - OPEN
- [ ] TRIAL-14 - School-channel approach letter (send before the holidays) [P1 weeks 2-3 prep, owner]
- [ ] TRIAL-19 - Recruit the expansion cohort [P3, owner]
- [ ] OPS-12 - Expansion batch ops check script [P3]
- [ ] TRIAL-6 - Pilot metrics script [P3]
- [x] AI-13 - Spend, fallback and two-pass disagreement metrics; threshold alert via the email sender (before AI-17) [P1a L7, DONE, merged]
- [ ] CONSENT-12 - Under-18 school-mediated guardian consent route [P3]
- [ ] CONSENT-14 - Human review and sign-off before real minor accounts [P3, human]
- [ ] TRIAL-17 - Week-4 post-test [P3, human]
- [ ] TRIAL-13 - Batch expansion 10 -> 25 -> 50 -> 100 [P3, owner]
- [ ] CONTENT-12 - Content batch 2: demand-driven growth [P3]
- [ ] SCOPE-11 - Widen verified coverage in batches [P3, human]
- [ ] TRIAL-18 - DPR measurements write-up (measurement 8 "not measured") [P3]

## Cross-cutting
- [x] DOCS-1 - Commit pending memory edits, one CLAUDE.md line, clean stale worktrees [W0] — **done**: `.claude/settings.json` deny rules and the CLAUDE.md line are committed and pushed (`2a9d6d2`); main is clean; the one existing worktree (`wf_9b7797a4-e76-1`) has real uncommitted work (the "Held, not merged" student sign-up UI, `STATUS.md`) and is deliberately left alone, not removed
- [x] SEC-15 - Owner: move live Supabase keys out of the repo folder (blocks any fan-out) [W0, owner, new] — **done, owner-confirmed 2026-09-21**
- [ ] SEC-16 - Owner: rotate the staging service-role key, JWT secret and DB password once QA-2 is merged (earlier agent sessions could read the pre-SEC-15 values) — hard precondition of DEPLOY-7 and PUB-13b [W1-W2, owner, new]
- [~] TRIAL-1 - Owner kickoff: name people, recruit adult round-1 testers, name a second moderator [W0, owner] — **second moderator: Mahesh** (2026-09-22); the five adult tester profiles are still to be recruited — 2-3 week lead time, start now
- [ ] SCOPE-1 - Owner confirms phasing and the trial coverage set (explicit yes) [W0, owner]
- [ ] RULES-17 - Owner answers the six rules decisions [W0, owner]
- [ ] CONSENT-17 - Record the DigiLocker route as deferred [W0, owner]
- [~] DOCS-3 - Task-card template, this index finalised, ledgers, card stubs [W0] — **3a done** (this index finalised, ledger, `tasks/TEMPLATE.md`, `docs/CONTRACTS.md` skeleton); **3b open** (per-task card stubs — mechanical, does not gate fan-out, generated from the inventories on demand)
- [ ] DOCS-2 - Slim STATUS.md [W0-W1]
- [ ] DOCS-5 - KNOWN_ISSUES.md, decisions digest, D16 draft [W0-W1]
- [x] DOCS-4 - Parallel-work protocol (docs/PARALLEL.md) [W1]
- [x] DOCS-13 - implementer.md, migration-owner.md, reviewer path fix, .claude/settings.json [W1]
- [x] DOCS-6 - docs/COSTS.md, per-batch metrics line, tripwire [W1, same session as DOCS-4]
- [x] SCOPE-2 - Jurisdiction, cycle, currency, coverage contract [W1, contract burst]
- [x] UI-2 - Split pages.py into per-screen modules [W1]
- [x] SEC-1 - Security middleware, trusted hosts, env guard [W1]
- [x] CONTENT-18 - Scrub researcher email from drafts [W1]
- [x] QA-4 - Parallel-agent testing contract (docs/TESTING.md) [W2]
- [x] DOCS-12 - Refresh CLAUDE.md links and verified commands [W2]
- [ ] DATA-10a - Owner: QA-12 sweep, apply through 0008, synthetic seed [W2, owner]
- [ ] DATA-10b - Owner: apply through 0010, redeploy staging [W3, owner]
- [ ] DATA-10c - Owner: apply through 0014 [W4-W5, owner]
- [ ] SEC-8 - Data-flow map confirmed, owner acceptance [P2]
- [ ] AUTH-18 - Contingency fix session for review findings [P2, only if needed]

## Dropped for the pilot (19; decision D16 lists the build-pack deviations)
A11Y-13, SCOPE-12, RULES-14, RULES-18, SEC-11, CONSENT-13, CONSENT-15, CONSENT-16, PUB-16, OPS-11, OPS-13, UI-16, AUTH-13 (banner substitute in AUTH-14), I18N-14 (Gujarati strings restored only for a Gujarati-medium cohort), ~~AI-14~~ (un-dropped into Phase 1a, 2026-09-22), CONTENT-19, DEPLOY-14, DOCS-10 (its deny rules land with DOCS-1 on day 1, before any fan-out; DOCS-13 adds only the implementer allowlist), TRIAL-15.
