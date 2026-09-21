# Task inventory - Product build

Generated 2026-09-21 by the planning workflow from verified area audits. DRAFT - task cards under tasks/ still need owner approval before work starts.

## Data foundation and schema gaps

Area: `data-schema`

Verified by reading 0001-0003, the runner, models.py, ci.yml and app code; nothing executed. 6 of 25 section-6 tables exist plus reviewers. The NULL/foreign created_by self-approval bypass in 0003 is real; approved_draft_version is never written; _schema_migrations has no RLS. Audit errors fixed: eligibility rules live in app/rules (rule_version already exists on Criterion); an in-memory AI budget guard already exists; the proposed staging demo default cannot work under RLS; pathways.description and career names go public with no review; consent gate was ordered too late. Corrected plan: seven serial append-only migrations (0004-0010), CI rebuild, seed, three owner apply steps, one human sign-off. About 13 dev sessions, 3 human hours.

### Already done

- Append-only numbered migrations with a runner that records applied files in _schema_migrations, skips applied ones, supports --dry-run, and uses DATABASE_URL which the app does not read - F:\the competetion project\scripts\apply_migrations.py (lines 44-98); F:\the competetion project\db\migrations\README.md. Only 0001-0003 exist.
- Evidence core: sources (authority_name, official_url, source_type enum incl. synthetic) and claims (entity_type/entity_id/field, jsonb value, source_id, verification_date date, verifier, status enum, review_due_date, superseded_by, approved_draft_version, extracted_by, created_by, reviewed_by) - F:\the competetion project\db\migrations\0001_init.sql lines 16-71
- Synthetic-sourced claim can never be published (DB trigger, applies to service_role too - no exemption in this function) - F:\the competetion project\db\migrations\0001_init.sql lines 76-93
- careers and pathways: world-readable, reviewer-write RLS (note: no review state on these rows - see gaps) - F:\the competetion project\db\migrations\0001_init.sql lines 31-44, 144-154
- student_profiles with own-row RLS; reviewers table with no policy and is_reviewer() security-definer with pinned search_path - F:\the competetion project\db\migrations\0001_init.sql lines 99-122, 176-177
- saved_plans: unique (student_id, pathway_id), own-row RLS, touch_updated_at trigger, cascade from auth.users; plan_versions explicitly deferred - F:\the competetion project\db\migrations\0002_saved_plans.sql
- Maker-checker state machine in DB: insert-as-draft only, draft->in_review->published, self-approval blocked only when created_by is non-NULL, published content frozen, supersede-only correction, service_role exempt, marker function maker_checker_schema_version() - F:\the competetion project\db\migrations\0003_maker_checker.sql lines 58-144
- App layer sets created_by/reviewed_by from the caller's resolved user id (app-level only) - F:\the competetion project\app\api\claims.py lines 148, 164, 221-222
- RLS-aware client factory - F:\the competetion project\app\db\client.py (not re-read line by line; audit claim accepted, consistent with claims.py usage)
- Pydantic models: Source, Claim, Career, Pathway, StudentProfile, enums; in-memory-only Exam, Institution, ProgrammeCost, Scholarship - F:\the competetion project\app\data\models.py class list lines 21-121
- Rule functions already carry a per-criterion rule_version field (default 'v1') and source_claim_id - F:\the competetion project\app\rules\eligibility.py lines 57-69, 112-243
- In-memory AI request-count budget guard and provider adapter already exist (not DB-backed; resets on restart; does not track rupee spend) - F:\the competetion project\app\ai\budget.py, adapter.py, gemini_provider.py, mock_provider.py, grounding.py
- RLS matrix tests in three classes; maker-checker, claims API, plans, reviewer console live-DB tests; labelled synthetic fixtures - F:\the competetion project\tests\db\test_rls.py lines 24, 68, 95; tests\db\test_maker_checker.py etc. exist; tests\fixtures\synthetic_data.py. Pass count from STATUS.md only.
- CI runs ruff, mypy, unit tests; tests/db step skips without secrets; no rebuild job - F:\the competetion project\.github\workflows\ci.yml
- Claims model, trust labels, freshness tiers, source allow-list and minimisation documented - F:\the competetion project\docs\DATA.md

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| Maker-checker bypass at DB layer (confirmed in 0003 lines 110-118 and 134-136): created_by is not forced to auth.uid(); `new.reviewed_by = new.created_by` is NULL when created_by is NULL so no exception; RLS `is distinct from` is TRUE. A reviewer with own token can insert with NULL/foreign created_by then self-approve. created_by is also mutable while draft/in_review. | Build pack s6 Publishing; s12 Built-means ('no bypass'); CLAUDE.md non-negotiable 2 | launch-blocker |
| Approval not bound to exact draft: approved_draft_version never written by any code (grep: reads only in compare.py:127, eligibility.py:79, models.py:77). In_review content editable between view and approve; no hash, no invalidation. | Build pack s6 Publishing; s7 Quality gates Publication | launch-blocker |
| No consents table, no account_state or birth_year; DB cannot keep a minor's account disabled, freeze on withdrawal, or record a deletion request. Sign-up has no age gate (app/api/auth.py docstring admits it). | Build pack s6 Consent and safeguarding; s9 Step 8; CLAUDE.md non-negotiable 4 | launch-blocker |
| careers and pathways rows (name, pathways.description - free fact-bearing text) become world-readable the moment one reviewer inserts them: no draft/listed state, no second person. This sidesteps maker-checker for descriptive content. | CLAUDE.md non-negotiable 2; build pack s6 Publishing; 0001 comment 'never embedded loose on the entity itself' | phase1-required |
| No review_events or audit_events tables; publication not atomic with an audit event; no append-only history. | Build pack s6 Tables; s6 Publishing | phase1-required |
| _schema_migrations created in public with no RLS and no revoke (apply_migrations.py lines 63-70); Supabase default grants expose it to anon/authenticated via PostgREST. | Build pack s7 Quality gates Access | phase1-required |
| Claims lack unit, jurisdiction, academic cycle, source document version, source publication date, checked timestamp (only verification_date date exists). No claims.updated_at touch trigger either. | Build pack s6 'Every critical claim carries' | phase1-required |
| No source_versions table; sources has no allow_listed flag or freshness tier. | Build pack s6 Tables (Evidence); docs/DATA.md Source allowlist, Freshness tiers | phase1-required |
| No exams, exam_cycles, institutions, programmes, scholarships tables; all claims hang on entity_type 'Pathway' (compare.py:174, eligibility.py:197); claims.entity_type is unconstrained text. 120 content drafts (exams, scholarships, institutions, 11 foreign countries) have no entity to attach to. | Build pack s6 Tables (Opportunities); s9 Steps 9-10; DECISIONS 2026-09-21 scope | phase1-required |
| No pathway_stages / pathway_transitions; timeline page uses blank hand-typed, pathway-independent rows (app/web/pages.py 320-436). | Build pack s6 Tables (Careers), Timeline ('backup transitions') | phase1-required |
| No Hindi columns or locale convention for entity names/descriptions or claim text values. | Build pack s12 Built-means ('English and Hindi critical content reviewed') | phase1-required |
| No way to show synthetic demo data to a guest on staging: anon RLS only returns published claims and synthetic claims can never be published. Staging demo/usability round 1 has nothing to show. | Build pack s9 Step 4 seeds, Step 5-6 prototype with test-labelled content; CLAUDE.md non-negotiable 4 | phase1-required |
| No seed script (scripts/ holds only apply_migrations.py). | Build pack s9 Step 4 ('seeds') | phase1-required |
| No rebuild-from-scratch check; ci.yml has no DB service; 0001 bootstrap was manual. | Build pack s9 Step 4; s7 Quality gates Operations; s12 Built-means ('reviewed migrations') | phase1-required |
| No plan_versions; no mechanism to flag plans affected by a superseded claim ('What changed'). | Build pack s6 Tables (Student work), Publishing; s9 Step 8 | phase1-required |
| No feedback table; no staff-only support-queue / distress table. | Build pack s6 Tables (Operations), Consent and safeguarding; s9 Steps 8, 13 | phase1-required |
| No jobs table for the Postgres-backed worker. | Build pack s4; s6 Tables; s9 Step 13 | phase1-required |
| No durable ai_usage ledger. An in-memory request-count guard exists (app/ai/budget.py) but resets on restart, records no actual tokens/cost, and cannot enforce the monthly rupee cap. | Build pack s7 Spend controls; s12 'spending limits and alerts have been tested' | phase1-required |
| rule_version exists per Criterion but is not surfaced in the API result, not recorded against a saved plan, and nothing forces a bump when a rule changes. No rule_versions/rule_test_cases DB tables. | Build pack s6 Eligibility; s7 Quality gates Eligibility ('rule version') | phase1-nice |
| No reminders table. | Build pack s6 Tables (Student work) | phase1-nice |
| models.py, docs/DATA.md and db/migrations/README.md lag the schema (README describes only what 0001 creates). | Build pack s9 Step 4 ('typed access'); s7 Memory in files | phase1-nice |
| No access_grants table. | Build pack s6 Tables (Identity) | defer |
| No field-level encryption; no sensitive columns exist. | Build pack s8 row 1 | defer |
| No server-side guest session table; pending_plan is passed at sign-up. | Build pack s6 Guest sessions | defer |

### Owner decisions

- Keep student_profiles as the build pack's 'profiles' table rather than renaming? - blocks: DATA-5 - recommended default: Keep student_profiles; note the naming in DATA.md.
- How does staging show synthetic demo data to a guest, given RLS hides unpublished claims from anon and synthetic claims can never be published? - blocks: DATA-12, DATA-8, usability round 1 - recommended default: DB-gated demo mode (DATA-12): a settings row only the owner connection can flip, a select policy limited to synthetic-sourced in_review claims, permanent sample-data ribbon, app refuses to start in production with it on. Trigger never relaxed; no service role on request path.
- Add an is_listed state with a second-person listing check on careers, pathways and new entities? - blocks: DATA-4 - recommended default: Yes, and move pathways.description facts into claims over time. Cheapest way to stop unreviewed descriptive text going public.
- Consent route for the pilot - blocks: DATA-5 - recommended default: School-mediated, staff-recorded consent rows, invite-only accounts; guardian_token kept as an enum value only, not built.
- Jurisdiction representation on claims - blocks: DATA-3, DATA-4 - recommended default: country (ISO-3166 alpha-2, default IN) plus region (state/UT code or ALL); currency ISO-4217 carried in unit. Use this if the scope area has not answered within one day.
- Hindi storage convention - blocks: DATA-3, DATA-4 - recommended default: name_hi nullable columns on entities; a locale column on claims for text values, each translation its own reviewed claim.
- rule_versions/rule_test_cases as DB tables or code registry? - blocks: DATA-9 - recommended default: Code registry plus pytest.
- Store marks, category or income in the pilot? - blocks: Possible extra migration and key management - recommended default: Do not store; eligibility stays stateless per request, so no encryption work.
- Create access_grants and a server-side guest session table? - blocks: Nothing on the critical path - recommended default: Defer both; keep client-held pending_plan.
- May dev agents apply migrations to dev/staging? - blocks: DATA-10, DATA-11, DATA-13 turnaround - recommended default: Owner applies to dev, staging and prod; agents apply only to the throwaway CI/local database from DATA-2. About 1.5 owner hours total.

### Tasks

#### DATA-4 - Migration 0008: opportunity entities, pathway stages/transitions, entity listing state

- What: Thin tables only (ids, names, name_hi, country, FKs; facts stay in claims): exams, exam_cycles, institutions, programmes, scholarships, pathway_stages (order, duration_weeks, required, overlap), pathway_transitions (kind=backup). World-read, reviewer-write. CHECK on claims.entity_type. Add is_listed (default false) plus listed_by on careers/pathways and new entities; public select requires is_listed; listed_by must differ from creator. Extend seed script with stages.
- Acceptance: Guest/student A/student B/reviewer matrix tests pass per table; unknown entity_type rejected; unlisted entity invisible to anon; creator cannot list own entity; no fee/date column on entity tables; existing rows backfilled as listed; rebuild passes.
- Wave: 5 · Step: 7 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: PUB-2, SCOPE-3
- Touches: db/migrations/0008_opportunities_stages.sql; app/data/models.py; scripts/seed_synthetic.py; tests/db/test_rls_opportunities.py; tests/db/conftest.py; docs/DATA.md
- Reviewers: data-security-reviewer
- Risk: is_listed changes what Explore returns; fixtures that insert careers must set it. Keep tables thin so later additive columns are cheap.

#### DATA-8 - Synthetic seed script for dev and staging

- What: scripts/seed_synthetic.py inserts 3-5 clearly labelled synthetic careers, pathways, sources (source_type=synthetic) and in_review claims using the current schema; turns demo mode on only when asked. Refuses when environment is production or the URL matches the production project ref. Idempotent, with --purge. Uses the owner-held credential, never run with prod values.
- Acceptance: Two runs give identical row counts; exits non-zero under production; no seeded claim is published; staging Explore and Compare show rows with the sample-data label once DATA-12 is applied.
- Wave: 1 · Step: 5 · Needed by: staging-demo · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: DATA-12
- Touches: scripts/seed_synthetic.py; tests/unit/test_seed_guard.py; db/migrations/README.md; Makefile
- Reviewers: data-security-reviewer
- Risk: Never weaken the 0001 synthetic trigger to make the demo work.

#### DATA-10 - Owner: apply batch A (0004-0005) to dev and staging

- What: Owner runs scripts/apply_migrations.py --dry-run then the real apply on dev after DATA-1 and DATA-12 merge, runs make test-db, confirms zero skips; repeats on staging when it exists and runs the seed there. Never from an agent session holding production credentials.
- Acceptance: _schema_migrations lists 0004-0005 on dev and staging; make test-db output with zero skipped pasted into STATUS.md; no applied file edited afterwards.
- Wave: 5 · Step: cross · Needed by: staging-demo · Executor: owner · Model tier: none · Dev sessions: 0 · Human hours: 0.75
- Depends on: PUB-2, DATA-12, DATA-8, SCOPE-3
- Touches: STATUS.md
- Reviewers: human
- Risk: Latent fixture bugs surface on live apply; budget one follow-up dev session.

#### DATA-11 - Owner: apply batch B (0006-0009), schema review and human sign-off

- What: Owner applies 0006-0009 to dev and staging. A data-security-reviewer agent runs a read-only pass over every public table's RLS, grants to anon/authenticated, security-definer functions and search_path. A person who is not the author reads the consent/account-state policy summary and signs a dated DECISIONS.md entry.
- Acceptance: No open critical/high findings; signed dated DECISIONS.md entry; make test-db green with zero skips; rebuild check green on the same commit.
- Wave: 7 · Step: 8 · Needed by: real-users-gate · Executor: mixed · Model tier: strongest · Dev sessions: 1 · Human hours: 2
- Depends on: PUB-2, DATA-4, CONSENT-4, AUTH-15, DATA-10, PUB-4, SEC-6, AUTH-7, AUTH-10, CONSENT-2
- Touches: docs/DECISIONS.md; STATUS.md
- Reviewers: data-security-reviewer, human
- Risk: Finding a non-author human reviewer.

#### DATA-12 - Migration 0005: DB-gated demo mode for synthetic data on staging

- What: New app_settings single-row table (demo_mode boolean default false; no anon/authenticated write; changeable only via the owner's direct connection) and demo_mode() stable function. Add a claims select policy: status='in_review' AND demo_mode() AND source is synthetic. API responses carry is_sample=true for such claims. The synthetic publish trigger is untouched; synthetic claims are still never published.
- Acceptance: With demo_mode false anon sees zero in_review claims (test); with true anon sees only synthetic-sourced in_review claims, never official drafts; authenticated users cannot flip demo_mode; read path marks them sample; production config check refuses start when demo_mode is on.
- Wave: 0 · Step: 5 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0
- Depends on: none
- Touches: db/migrations/0005_demo_mode.sql; app/api/explore.py; app/api/compare.py; app/core/config.py; tests/db/test_demo_mode.py; docs/DATA.md; docs/DECISIONS.md
- Reviewers: data-security-reviewer
- Risk: Touches non-negotiable 4's surface; must never expose non-synthetic drafts. If owner rejects, staging demo needs a signed-in reviewer preview instead.

#### DATA-13 - Owner: apply batch C (0010) and delta grant audit

- What: Owner applies 0010 to dev, staging and later prod via the same script; reviewer agent does a short read-only delta check of jobs/ai_usage grants and the reserve function; owner confirms worker credential variable is set only on the server.
- Acceptance: _schema_migrations lists 0010; anon/authenticated have no table grants on jobs or ai_usage; make test-db zero skips recorded in STATUS.md.
- Wave: 8 · Step: 13 · Needed by: ten-user-trial · Executor: mixed · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: AI-4, DATA-11, DATA-4, AUTH-15, I18N-8, OPS-6, TRIAL-5
- Touches: STATUS.md
- Reviewers: data-security-reviewer, human
- Risk: Low.

### Merged into other tasks

- DATA-1 -> PUB-2
- DATA-2 -> QA-5
- DATA-3 -> PUB-2
- DATA-5 -> CONSENT-4
- DATA-6 -> AUTH-15
- DATA-7 -> AI-4
- DATA-9 -> RULES-4

## Rules engines: eligibility, timeline, cost, per-exam rule functions

Area: `rules-engines`

Verified: three pure engines exist with 93 unit tests (44/26/23) and are wired to GET /eligibility, POST /timeline and the HTML screens. They are integer-age, all-of-subjects, category-blind, driven by five flat claim fields. Missing: DOB/reference-date checks, any-of groups, category thresholds, year-of-passing, cycle/jurisdiction, surfaced rule version, any per-exam module (0 of 8-10). Audit errors fixed: vacuous 'meets' is JSON-only (HTML already shows an honest empty state); YAML needs a new dependency (use stdlib JSON); rule_versions DB table is not required by any gate (approval recorded in git; table deferred); RULES-6 exceeded 3 sessions (split); RULES-8 split API vs page. Plan: freeze contract, two primitive sessions, NEET template, then up to 7 parallel exam sessions.

### Already done

- Three-outcome eligibility engine; does_not_meet > insufficient_information > meets; unknown input never becomes rejection; builders minimum_age, maximum_age, minimum_marks_percentage, required_subjects, domicile_in (case-insensitive) - F:\the competetion project\app\rules\eligibility.py (read in full, 286 lines); 44 test functions in tests/unit/test_eligibility.py (counted)
- Timeline engine: overlap validated not clamped, unknown duration -> total None, empty stages -> None, parallel activities excluded, expand_attempts rejects <1 attempts and negative durations - F:\the competetion project\app\rules\timeline.py lines 103-176; 26 tests in tests/unit/test_timeline.py; plus 9 in test_api_timeline.py and 6 in test_web_timeline_page.py
- Cost engine already supports a LIST of itemised FeeComponent with missing -> total None and stale flag; potential assistance never subtracted - F:\the competetion project\app\rules\cost.py (sum_verified_charges, compute_cost_summary, net_to_arrange); 23 tests in tests/unit/test_cost.py
- Comparison assembly: trust-label mapping, published/synthetic gating incl. expenses hint, urlsplit URL guard, per-request assumption override - F:\the competetion project\app\planning\comparison.py (trust_label_for_claim, _safe_source_url, field_value_for, assemble_cost_breakdown, assemble_cost_summary); 39 tests in tests/unit/test_comparison.py
- GET /eligibility builds criteria from published-only claims (5 flat fields), resolves source authority/url/date/trust label per criterion; reviewer-draft regression test exists - F:\the competetion project\app\api\eligibility.py (_criteria_from_claims line 159 filters status==published); tests/db/test_api_eligibility.py (draft-criterion and no-criteria fixtures)
- Synthetic-sourced claims cannot be published at all (DB trigger), so eligibility can never compute from a synthetic source even though _criteria_from_claims does not check source_type - F:\the competetion project\db\migrations\0001_init.sql lines 73-93 (forbid_publishing_synthetic_claims trigger)
- Requirements HTML screen already shows an honest empty state ('No published eligibility requirements yet for this pathway') instead of a meets badge when no criteria exist; overall badge wording is 'You meet the published requirements' - F:\the competetion project\app\web\templates\requirements.html lines 67-96; app/web/templates/_trust_badge.html lines 51-63
- Requirements and Timeline HTML screens reuse the same engine code paths; hand-parsed age/marks avoid raw 422s - F:\the competetion project\app\web\pages.py (requirements_page calls check_eligibility; _int_or_none/_float_or_none; compute_timeline import)
- Unverified draft eligibility research exists for 8 of the 9 named exams (JEE Main, NEET-UG, GUJCET, CUET-UG, CLAT, NDA, SSC CGL, IBPS PO) plus extras (JEE Advanced, CDS, AFCAT, CAT, CMAT, NATA, ICAR AIEEA) and 11 foreign-country drafts; no GPSC draft - F:\the competetion project\docs\content-drafts\ (listed; grep for gpsc/upsc returned nothing)

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| Age is an integer 'current age'; no DOB vs reference-date criterion (NEET 17 by 31 Dec; NDA born-between; SSC/IBPS 'as on' date). EligibilityInput.as_of exists but no criterion reads it. No leap-year (29 Feb) handling or tests anywhere. | Build pack s7 Quality gates (cut-off dates, leap-year birthdays); STATUS.md NEET section item 2 | launch-blocker |
| required_subjects is all-of only; no any-of groups. Flat comma-string claim value cannot express groups; Claim model value type is str\|int\|float\|bool\|None although the DB column is jsonb, so structured values need a model widening. | Build pack s6 Eligibility; STATUS.md NEET section item 2; app/data/models.py line 70 | launch-blocker |
| No per-exam rule function for any of the 8-10 exams; only generic builders and a synthetic NEET-style test fixture. | Build pack s2 Exams row; s9 Step 7 content track (5 exams) | phase1-required |
| rule_version is a hardcoded 'v1' default on Criterion, never set, never returned by GET /eligibility. No rule_versions/rule_test_cases tables (migrations 0001-0003 only). | Build pack s6 Tables; s6 'reviewed, versioned and cite their source'; s7 gate 'rule version' | phase1-required |
| No cycle or jurisdiction on rules or eligibility output; no guard against applying a past-cycle rule. No pathway->exam link exists (pathways has only name/description). | Build pack s6 'jurisdiction and academic cycle'; s7 gate 'cycle and jurisdiction'; DECISIONS 2026-09-21; db/migrations/0001_init.sql lines 38-44 | phase1-required |
| Category-dependent thresholds and age relaxations unsupported; EligibilityInput.category is unused. Unknown category must never produce a rejection against the general threshold. | Build pack s6 three outcomes; s6 consent | phase1-required |
| No criteria for qualification level / year of passing / appearing status, and no 'not checked here' declaration for gender, marital status, nationality, medical standards. | Build pack s2 Exams row; s6 Eligibility | phase1-required |
| JSON GET /eligibility returns overall 'meets' for a pathway with no published eligibility claims (documented as vacuous in the module docstring). The HTML Requirements screen already guards this; the public JSON route and any future client (AI fact cards, saved plans) do not. | CLAUDE.md non-negotiable 1; build pack s6 'meets the checked criteria'; app/api/eligibility.py docstring lines 15-21 | phase1-required |
| GET /eligibility input/claim robustness: no range validation (negative age, marks <0 or >100 accepted); int()/float() on a malformed published claim value raises an unhandled 500 on a public route; as_of uses date.today() in server timezone (UTC VM) rather than IST, wrong by a day at cut-off boundaries. | Build pack s7 gates 'boundaries, missing inputs, cut-off dates'; s7 contracts 'date and time conventions' | phase1-required |
| Overall outcome takes no account of evidence freshness: a criterion backed by a needs_rechecking claim still yields an unqualified overall 'You meet the published requirements' badge. | Build pack s7 contracts 'evidence states and stale-data behaviour' | phase1-nice |
| Eligibility API/UI has no DOB, category, year-of-passing inputs; results not labelled with rule version/cycle/jurisdiction. | Build pack s7 Contracts before parallel work; s7 eligibility gates | phase1-required |
| Cost assembly layer passes one pre-summed verified_charges claim (engine itself already supports itemised components); confirmed_assistance always empty; living-expense estimate and user assumption are one merged figure; money is float with no precision/rounding contract or rounding tests. | Build pack s6 Cost; s7 gates 'rounding'; s7 contracts 'money precision' | phase1-nice |
| Timeline stages are typed by hand; nothing seeds stages from published pathway claims, so time cannot be compared per pathway or cite sources; weeks-only output; compute_timeline (and therefore POST /timeline and the HTML form, which have no ge=0 validation) accepts negative durations - only expand_attempts rejects them. | Build pack s6 Timeline; s2 one journey; s7 calculators 'zero values, boundaries' | phase1-required |
| Two divergent _safe_source_url implementations (startswith in api/eligibility.py line 99 vs urlsplit in planning/comparison.py line 100). | STATUS.md security review finding | phase1-nice |
| No single command/report for the 'critical rule test cases pass' gate; Makefile has no test-rules target and CI runs only tests/unit and tests/db. | Build pack s12 'Before admitting 100 users' | phase1-required |
| rule_versions / rule_test_cases as DB tables; per-tier freshness SLA engine; GPSC and the 'one on demand' exam; computed eligibility for foreign pathways and per-state admission rules. | Build pack s6 Tables; DATA.md tiers; s2 Exams row; DECISIONS 2026-09-21 | defer |

### Owner decisions

- How to ask for age: full date of birth per request (not stored) versus birth month/year only - blocks: RULES-1, RULES-2, RULES-8, RULES-16 - recommended default: Full DOB as a per-request, never-stored, never-logged input; integer age kept as a fallback that yields insufficient_information whenever the rule is a date cut-off. No DOB added to student_profiles in Phase 1.
- Which exams must have computed eligibility at each gate, given widened scope and unchanged ceilings - blocks: RULES-6, RULES-15, RULES-7, RULES-14 - recommended default: Staging: NEET-UG, JEE Main, GUJCET. Before real users: add CUET-UG, CLAT (five total). Before ten-user trial: NDA, SSC CGL, IBPS PO if their claims are verified, else hidden. GPSC, tenth exam, foreign and per-state rules shown as cited facts only, not computed.
- Rules as code modules bound to claim values (reviewed by pull request) versus data-only rules in the database - blocks: RULES-1, RULES-4, RULES-11, RULES-18 - recommended default: Code modules reading thresholds from published claims; approval metadata and case tables as JSON in git; no rule_versions table for the pilot (record the deviation from build pack s6 in DECISIONS.md).
- What a student sees when a pathway has no verified eligibility rules - blocks: RULES-4, RULES-8, RULES-16 - recommended default: Keep the existing 'No published eligibility requirements yet for this pathway' wording plus an official-source link when one exists; JSON API returns insufficient_information with no_verified_rules=true, never 'meets'.
- Category-based relaxations: ask for category or show both general and relaxed thresholds - blocks: RULES-3, RULES-7, RULES-15, RULES-16 - recommended default: Guests are not asked; evaluate the general rule, and where a relaxation could change a failure return insufficient_information with 'a relaxation may apply - check the source'. Category input only for consented signed-in users after the consent workflow is human-reviewed.
- Who is the named human checker of rule case tables - blocks: RULES-12 - recommended default: The second content reviewer already required for critical publishing; the owner covers until named, but never the person who verified the underlying claim.

### Tasks

#### RULES-1 - Freeze rules contract v2 (design note + task card, no code)

- What: Write the contract in docs/DATA.md 'Rules' section and a task card: EligibilityInput v2 (date_of_birth, category, year_of_passing, qualification_level, appearing), RuleSet shape (exam_key, cycle, jurisdiction, rule_version, not_checked), JSON claim value shapes for any-of groups and reference dates, pathway->rule link via a published 'rule_key' claim, empty-rules outcome, IST as_of, integer-rupee money, weeks durations, stale-evidence qualifier.
- Acceptance: Contract merged; lists every new field, claim JSON shape, unknown/error behaviour, the per-exam module and JSON case-table template; data-security-reviewer confirms no new personal field is stored or logged; content-pipeline lead acknowledges shapes.
- Wave: 0 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.5
- Depends on: none
- Touches: docs/DATA.md; tasks/BCI-007.md; docs/DECISIONS.md
- Reviewers: data-security-reviewer, human

#### RULES-2 - Date-based age criteria with leap-year handling

- What: Add pure helper age_on(dob, ref_date) and criteria minimum_age_on_date, maximum_age_on_date, born_between(earliest, latest), each with optional per-category relaxation years. Missing DOB, or missing category when relaxations exist and the general rule fails, gives insufficient_information. Keep integer minimum_age/maximum_age for backward compatibility. New file so RULES-3 can run concurrently.
- Acceptance: Table tests: 29 Feb DOB on leap and non-leap reference years, birthday on and one day either side of cut-off, 16-year-old who turns 17 by 31 Dec, unknown DOB, unknown category with relaxations; lint, typecheck, test-unit green.
- Wave: 1 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-1
- Touches: app/rules/criteria_dates.py; app/rules/eligibility.py (EligibilityInput fields only); tests/unit/test_criteria_dates.py
- Reviewers: none

#### RULES-3 - Any-of subject groups, category thresholds, qualification/year-of-passing criteria

- What: Add subject_groups (all-of list of any-of sets), minimum_marks_by_category, passed_or_appearing_in_years, minimum_qualification_level, and a NotChecked declaration for conditions deliberately not evaluated (medical, nationality, gender, marital). Widen Claim.value to accept list/dict JSON and make field_value_for degrade non-scalar values safely. New file; does not edit eligibility.py.
- Acceptance: Tests: Biology-or-Biotechnology meets with either, fails with neither, unknown with empty subjects; unknown category never rejects; year-of-passing boundaries; structured Claim value round-trips; existing 39 comparison tests still pass.
- Wave: 1 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-1
- Touches: app/rules/criteria_extra.py; app/data/models.py; tests/unit/test_criteria_extra.py; tests/unit/test_models.py
- Reviewers: none

#### RULES-4 - RuleSet, auto-discovering registry, cycle/jurisdiction guard and honest empty result

- What: Add app/rules/ruleset.py: RuleSet (exam_key, cycle, cycle_end, jurisdiction, rule_version, reviewed_by, reviewed_on); evaluate_ruleset() returns outcome plus version, cycle, jurisdiction, not_checked, no_verified_rules, cycle_stale, evidence_stale. Empty criteria never reports bare meets. Registry discovers app/rules/exams/*.py via pkgutil; unreviewed modules are excluded when APP_ENV is production.
- Acceptance: Tests: empty ruleset sets no_verified_rules and outcome insufficient_information; result always carries version/cycle/jurisdiction; as_of past cycle_end sets cycle_stale; duplicate exam_key+cycle rejected; unreviewed module hidden in production mode.
- Wave: 2 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-2, RULES-3
- Touches: app/rules/ruleset.py; app/rules/exams/__init__.py; app/rules/__init__.py; tests/unit/test_ruleset.py
- Reviewers: data-security-reviewer

#### RULES-5 - Reference exam module: NEET-UG template bound to claim values

- What: Build the template every other exam copies: app/rules/exams/neet_ug.py builds a RuleSet from published claim values passed in (never literal facts), plus a stdlib-JSON case table (input, expected outcome, reason, source pointer) and a shared parametrised loader test. Test thresholds labelled synthetic. Absent claim means criterion omitted and listed as not verified.
- Acceptance: >=12 table cases incl. DOB cut-off, any-of biology, unknowns, stale cycle; module contains no literal fact values (grep check in test); loader test auto-runs any cases/*.json file without edits.
- Wave: 3 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-4
- Touches: app/rules/exams/neet_ug.py; tests/unit/rules/__init__.py; tests/unit/rules/test_exam_cases.py; tests/unit/rules/cases/neet_ug.json
- Reviewers: none

#### RULES-6 - Per-exam modules fan-out A: JEE Main, GUJCET

- What: Two independent parallel sessions, one exam each, copying the NEET template: one module plus one JSON case table, reading that exam's content draft for shape only, never values. JEE Main needs passed_or_appearing_in_years; GUJCET needs PCM/PCB any-of groups and Gujarat jurisdiction.
- Acceptance: Each exam: >=10 table cases covering boundary, unknown, cycle, jurisdiction; no literal facts in module; no shared file edited; full unit suite green after each merge.
- Wave: 4 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: RULES-5
- Touches: app/rules/exams/jee_main.py; app/rules/exams/gujcet.py; tests/unit/rules/cases/jee_main.json; tests/unit/rules/cases/gujcet.json
- Reviewers: none

#### RULES-7 - Per-exam modules fan-out C: NDA, SSC CGL, IBPS PO

- What: Three independent parallel sessions. NDA: born_between window, Class 12 appearing concession, gender/marital/medical as not_checked. SSC CGL and IBPS PO: age window as-on date with category relaxations, degree by cut-off date. Modules ship with reviewed_by empty so the registry hides them publicly until claims are primary-source verified.
- Acceptance: Each exam >=10 table cases incl. relaxation with unknown category -> insufficient_information; one 29 Feb DOB case per age-window exam; suite green; unreviewed modules absent in production-mode registry test.
- Wave: 4 · Step: 10 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 3 · Human hours: 0
- Depends on: RULES-5
- Touches: app/rules/exams/nda.py; app/rules/exams/ssc_cgl.py; app/rules/exams/ibps_po.py; tests/unit/rules/cases/nda.json; tests/unit/rules/cases/ssc_cgl.json; tests/unit/rules/cases/ibps_po.json
- Reviewers: none

#### RULES-8 - Wire RuleSets into GET /eligibility (JSON API only)

- What: Replace _criteria_from_claims with registry lookup via the pathway's published rule_key claim, falling back to generic builders. Accept date_of_birth, category, year_of_passing with range validation; malformed claim value degrades to omitted criterion, never 500. Return rule_version, cycle, jurisdiction, not_checked, no_verified_rules, stale flags. IST as_of. Reuse comparison._safe_source_url and delete the local copy.
- Acceptance: tests/db eligibility tests pass incl. reviewer-draft regression; new tests: DOB input, empty rules never 'meets', unpublished rule_key ignored, negative age/marks>100 rejected cleanly, malformed claim no 500; no DOB in logs; guest/A/B/reviewer matrix rerun.
- Wave: 4 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-5, SEC-5
- Touches: app/api/eligibility.py; app/planning/comparison.py (export _safe_source_url); tests/db/test_api_eligibility.py
- Reviewers: data-security-reviewer

#### RULES-9 - Timeline seeding from published stage claims plus input hardening

- What: Add pure stages_from_claims(claims, sources, as_of) in app/planning/timeline_assembly.py using field_value_for gating (unpublished -> duration None). Reject negative durations and overlaps in compute_timeline and map to 400 / friendly page error. Add weeks -> 'about N years M months' helper with documented rounding. Prefill /timeline/view when pathway_id is given.
- Acceptance: Tests: draft stage claim yields unknown duration and total None; negative duration raises in engine, 400 in API, friendly message on page; helper cases 0, 51, 52, 53, 260 weeks; prefilled page stays zero-JS.
- Wave: 4 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: RULES-1, UI-7, UI-2
- Touches: app/planning/timeline_assembly.py; app/rules/timeline.py; app/api/timeline.py; app/web/pages.py; app/web/templates/timeline_calculator.html; tests/unit/test_timeline_assembly.py; tests/unit/test_timeline.py; tests/unit/test_api_timeline.py
- Reviewers: ux-qa-reviewer

#### RULES-10 - Cost: itemised components in assembly, separate estimate and user-assumption lines, integer rupees

- What: Let assemble_cost_summary pass multiple published fee_component:* claims to the existing sum_verified_charges (fallback to single verified_charges); split estimated living expenses from the user-edited assumption in CostSummary; move arithmetic to integer rupees per RULES-1 with explicit rounding tests. confirmed_assistance stays a per-request input, never stored.
- Acceptance: Tests: one missing component -> total None; rounding cases (paise inputs, large sums) exact; potential assistance never changes net; existing compare JSON/HTML tests pass with the separate figures distinct.
- Wave: 1 · Step: 7 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: RULES-1
- Touches: app/rules/cost.py; app/planning/comparison.py; tests/unit/test_cost.py; tests/unit/test_comparison.py
- Reviewers: ux-qa-reviewer

#### RULES-11 - 'Critical rule cases' gate command and git-recorded rule approval (no migration)

- What: Add make test-rules running tests/unit/rules only and printing a per-exam table (exam, cycle, rule_version, cases passed, reviewed_by, reviewed_on); fail on any miss or on a registered-public exam lacking review metadata. Add the step to CI. Approval lives in each case-table JSON header, changed by reviewed pull request - no DB table.
- Acceptance: make test-rules prints per-exam counts and exits non-zero on a failing case or missing review metadata for a public exam; CI job runs it; CLAUDE.md verified-commands list updated.
- Wave: 4 · Step: 13 · Needed by: real-users-gate · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-5
- Touches: Makefile; .github/workflows/ci.yml; tests/unit/rules/report.py; CLAUDE.md
- Reviewers: none

#### RULES-12 - Human review of each exam's rule case table against the verified source

- What: A named content reviewer (not the person who verified the underlying claims) reads each exam's case table, rendered by make test-rules, beside the official notification, confirms or corrects expected outcomes, and fills reviewed_by/reviewed_on in the JSON header via pull request. About 40 minutes per exam; exposed exams first, the rest before the ten-user trial.
- Acceptance: Every publicly registered exam has reviewer name and date in its case-table header; corrected cases have a linked commit; make test-rules green; unreviewed exams stay hidden in production.
- Wave: 5 · Step: 10 · Needed by: real-users-gate · Executor: human-reviewer · Model tier: none · Dev sessions: 0 · Human hours: 5.5
- Depends on: RULES-6, RULES-15, RULES-11, CONTENT-1
- Touches: tests/unit/rules/cases/*.json
- Reviewers: human

#### RULES-13 - Calibration fixtures and seeded property sweeps for the engines

- What: Add labelled-invalid fixtures for reviewer calibration (stale cycle, rule with missing source, unknown-turned-rejection) and a seeded stdlib-random sweep: random DOB/ref-date pairs vs a reference age implementation; stage lists never yield a total when any duration is None; net never changes with potential assistance.
- Acceptance: Sweeps run in under 5 seconds inside test-unit with a fixed seed; invalid fixtures live under tests/fixtures/invalid and are clearly labelled; no new dependency added.
- Wave: 3 · Step: 13 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-4
- Touches: tests/unit/test_engine_properties.py; tests/fixtures/invalid/
- Reviewers: none

#### RULES-14 - GPSC Class 1-2, on-demand tenth exam, foreign-pathway computed rules

- What: GPSC has no content draft; the tenth exam is undefined (drafts exist for JEE Advanced, CDS, AFCAT, CAT, CMAT, NATA, ICAR AIEEA); foreign pathways (11 country drafts) and per-state rules are better shown as cited requirement claims with not_checked than computed. Build only if trial feedback demands, one session each, same template.
- Acceptance: Same per-exam acceptance as RULES-6 if built; otherwise a docs/DECISIONS.md entry recording the deferral and the 8-exam count against the 8-10 target.
- Wave: 4 · Step: 16 · Needed by: deferrable · Executor: dev-agent · Model tier: standard · Dev sessions: 3 · Human hours: 1.5
- Depends on: RULES-5, SCOPE-1
- Touches: app/rules/exams/gpsc.py; tests/unit/rules/cases/gpsc.json; docs/DECISIONS.md
- Reviewers: human

#### RULES-15 - Per-exam modules fan-out B: CUET-UG, CLAT

- What: Two independent parallel sessions copying the NEET template. CLAT needs minimum_marks_by_category with unknown category never rejecting; CUET-UG has minimal central criteria with university-specific rules declared not_checked. Completes the Step 7 five-exam target with RULES-5 and RULES-6.
- Acceptance: Each exam >=10 table cases incl. category unknown and not_checked listing; no literal facts; no shared file edited; suite green after each merge.
- Wave: 4 · Step: 7 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: RULES-5
- Touches: app/rules/exams/cuet_ug.py; app/rules/exams/clat.py; tests/unit/rules/cases/cuet_ug.json; tests/unit/rules/cases/clat.json
- Reviewers: none

#### RULES-16 - Requirements screen: DOB input, cycle/version label, 'not checked here' list, stale qualifier

- What: Update requirements_page and requirements.html to the RULES-8 response: date-of-birth field replacing integer age (kept as fallback), cycle and jurisdiction label, rule version in the evidence line, 'not checked here' list, no_verified_rules and cycle_stale/evidence_stale messages. DOB is per-request only, never stored, never logged, not echoed into links.
- Acceptance: tests/db/test_web_pages.py cases for DOB input, empty-rules wording, cycle label, stale qualifier, not-checked list; malformed DOB gives friendly in-page message; 360 px and keyboard check by ux-qa-reviewer; DOB absent from logs and URLs of outbound links.
- Wave: 5 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: RULES-8, UI-2
- Touches: app/web/pages.py; app/web/templates/requirements.html; app/web/templates/_trust_badge.html; tests/db/test_web_pages.py
- Reviewers: data-security-reviewer, ux-qa-reviewer

#### RULES-17 - Owner answers the six rules decisions (or accepts defaults)

- What: Owner reads the ownerDecisions list for this area and records answers or 'default accepted' in docs/DECISIONS.md before RULES-1 is merged, especially DOB input form, exam list per gate, and category handling for guests.
- Acceptance: One dated DECISIONS.md entry covering all six decisions; RULES-1 contract cites it.
- Wave: 0 · Step: cross · Needed by: staging-demo · Executor: owner · Model tier: none · Dev sessions: 0 · Human hours: 0.5
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: human

#### RULES-18 - rule_versions table in the database (deferred)

- What: Only if the owner wants approvals queryable in the reviewer console: additive migration for rule_versions (exam_key, cycle, jurisdiction, rule_version, code_ref, reviewer, approved_at), reviewer-write/public-read RLS, RLS matrix test. rule_test_cases stays in git regardless.
- Acceptance: Migration applies on a fresh DB; guest/A/B/reviewer RLS matrix test passes; otherwise a DECISIONS.md entry records that git-recorded approval replaces the build pack's table for the pilot.
- Wave: 5 · Step: 9 · Needed by: deferrable · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.5
- Depends on: RULES-11
- Touches: db/migrations/0004_rule_versions.sql (or next free number); tests/db/test_rule_versions_rls.py
- Reviewers: data-security-reviewer

## Student-facing screens and navigation

Area: `ui-student-screens`

Verified against the repo. Four zero-JS screens exist (Explore, Compare, Requirements, standalone Timeline) in one 438-line app/web/pages.py over six templates that all extend base.html. Missing: landing and quick start, four-destination nav and utility menu, career card, detail page, cost-assumption editing in the HTML compare view, pathway-linked timeline, student browser session and account pages, My Plan, Ask shell, Report an issue, why-am-I-seeing-this, What changed. The original audit's parallel wave was not actually conflict-free (five tasks edited compare.html/_trust_badge.html). Corrected: UI-1 now pre-wires per-owner stub partials into existing templates so wave-2 tasks touch only their own files; UI-7 and UI-14 were split; next migration is 0004.

### Already done

- Career explorer screen GET /explore: careers with pathways, zero-JS checkbox form to compare. Note: it does not import _trust_badge.html and has no search/filter. - F:\the competetion project\app\web\pages.py line 77 explore_page; F:\the competetion project\app\web\templates\explore.html (97 lines)
- Comparison screen GET /compare/view: 2-3 pathways, friendly handling of malformed/duplicate ids, wrong count and DB outage; reuses assemble_comparisons. Confirmed it accepts ONLY pathway_id (no expenses override parameter). - F:\the competetion project\app\web\pages.py lines 144-202; F:\the competetion project\app\web\templates\compare.html
- Requirements screen GET /requirements/view with eligibility outcome badge beside trust badge and evidence line. - F:\the competetion project\app\web\pages.py line 205; F:\the competetion project\app\web\templates\requirements.html line 2 imports
- Standalone timeline calculator GET/POST /timeline/view, stateless, six unit tests. - F:\the competetion project\app\web\pages.py lines 354-438; F:\the competetion project\tests\unit\test_web_timeline_page.py (6 tests)
- Trust-label component: four macros trust_badge(label), evidence_line(source_authority, source_url, verification_date, label=none), eligibility_outcome_badge(outcome, overall=false), field_value(fv, money=false). No applicable-cycle parameter, no report link. - F:\the competetion project\app\web\templates\_trust_badge.html lines 5, 29, 51, 73
- Design tokens and component CSS in one compiled stylesheet, no web fonts. - F:\the competetion project\app\web\styles\input.css; F:\the competetion project\app\static\css\app.css; F:\the competetion project\app\web\templates\base.html line 9
- Reusable JSON APIs: explore, compare (with expenses override), eligibility, timeline, auth, plans, claims. - F:\the competetion project\app\main.py lines 34-43; F:\the competetion project\app\api\
- Playwright e2e smoke exists: 6 tests (explore, compare, requirements, timeline, reviewer sign-in, reviewer queue). STATUS.md lines 326 and 387 saying no e2e are stale. - F:\the competetion project\tests\e2e\test_smoke.py lines 124-297; commit 2db356e
- Reviewer cookie session (httponly, samesite=lax, path-scoped, POST sign-out that deletes the cookie) usable as the pattern for a student session. - F:\the competetion project\app\web\reviewer_pages.py lines 64-126, 180-200
- A design mockup artifact exists and is recorded in STATUS.md (source for copy and layout). - F:\the competetion project\STATUS.md lines 226-233

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No four-destination navigation and no utility menu; base.html header has only the logo and a Timeline calculator link. Reviewer templates also extend base.html, so a student nav must not leak into /reviewer pages. | Build pack s5 Navigation; app/web/templates/base.html lines 12-19 | phase1-required |
| No landing page ('Find your next step', three starting choices); '/' redirects to /explore (pages.py line 72). | Build pack s5 First visit | phase1-required |
| Quick start (four questions, one at a time, skippable) and the 'three routes worth comparing' first result do not exist. | Build pack s5 Objective; docs/UI.md Quick start; Step 6 | phase1-required |
| 'Why am I seeing this' and 'change a preference' absent; 'change a preference' is a usability pass criterion. | docs/UI.md lines 29-31 and Usability task criteria | phase1-required |
| Career card content does not exist; careers table has only name and nco_anchor. | Build pack s5 Career card; db/migrations/0001_init.sql line 31 | phase1-required |
| Exam or programme detail screen does not exist; no detail route, no exams/programmes/institutions tables (only sources, careers, pathways, claims, student_profiles, reviewers, saved_plans). | Build pack s2 seven screens, s6 | phase1-required |
| Cost-assumption editing missing from the HTML compare view: compare_page takes only pathway_id. Step 15 tester task 'change a cost assumption and explain the result'. | Build pack s12 Step 15; app/web/pages.py lines 144-202 | launch-blocker |
| Timeline not pathway-linked; required/optional/user-assumption stages not distinguished; no 'Revise this scenario'. | Build pack s5 Timeline and cost; docs/UI.md Timeline & cost | phase1-required |
| My Plan screen missing; no student browser session (bearer only); no sign-in/sign-up HTML pages; no 'Save as an option'. Step 15 tester task 'save a plan and find the next action'. | Build pack s5 Navigation, s12 Step 15 | launch-blocker |
| Student shared-device sign-out absent (only /reviewer/sign-out exists). Step 15 tester task. | Build pack s12 Step 15; s5 Difficult states | launch-blocker |
| saved_plans has no next-actions or current-decision fields (columns: estimated_additional_expenses, notes only). | Build pack s5 Navigation; db/migrations/0002_saved_plans.sql lines 18-29 | phase1-required |
| Ask BCION contextual shell missing; no AI-enabled flag exists in app/core/config.py; no AI-unavailable state. Step 15 tester task 'ask a question outside coverage and notice the limitation'. | Build pack s5 Navigation, Difficult states, Step 11 | phase1-required |
| 'Report an issue' missing from every fact; no feedback table or endpoint. | Build pack s5 Trust labels; tasks/BCI-006.md | phase1-required |
| Evidence line omits 'applicable cycle'; evidence_line macro has no cycle parameter and claims has no cycle column. | Build pack s5 Trust labels; _trust_badge.html line 29 | phase1-required |
| Guest server session (7-day, 'not saved to an account' indicator) does not exist. If quick start is stateless and plans are account-only, only the indicator text is needed for the pilot. | docs/UI.md Guest sessions; Build pack Step 8 | phase1-nice |
| 'What changed' list missing; no data path under current RLS. Required by no section 12 gate. | docs/UI.md What changed surface | defer |
| Compare omits funding, work realities, alternatives, and met/not-met entry requirements. | Build pack s5 Comparison | phase1-nice |
| Explore has no search or filter, so the 'career in mind' starting choice has no direct landing (acceptable at 20-30 careers with an anchor list; Hindi search is Step 12). | Build pack s5 First visit; app/api/explore.py | phase1-nice |
| Permission-denied, generic 404/500 and empty-state student pages are not designed (only per-page friendly errors). | Build pack s5 Difficult states; Step 12 'every error state' | phase1-nice |
| Reminder opt-in component (in the frozen component set) does not exist. | docs/UI.md Component set | defer |
| Saved destination has no screen or table. | Build pack s5 Navigation | defer |
| Footer hard-coded to 'Synthetic pilot data unless...'; must become flag-driven before real content. | CLAUDE.md synthetic labelling; base.html lines 26-31 | phase1-required |

### Owner decisions

- Quick-start answers: server guest session or stateless URL parameters? - blocks: UI-3, UI-4 - recommended default: Stateless query parameters (non-personal categories only). No guest-session table for the pilot; show 'not saved to an account' text for signed-out users.
- Saved: separate destination or merged into My Plan? - blocks: UI-1 nav, UI-9, UI-16 - recommended default: Merge; nav still shows four items with Saved pointing at My Plan's saved section. UI-16 deferred.
- Detail screen: own exams/programmes tables or one claims-driven template? - blocks: UI-5 - recommended default: One claims-driven template; data area adds entity tables only if the Step 10 import needs them.
- May UI-8 be built before the consent gate is reviewed? - blocks: UI-8, UI-9, UI-18 - recommended default: Yes, behind a config flag defaulting to off, seeded synthetic accounts only on staging; never enabled on a public host until a person has reviewed the consent workflow.
- Where do suggestion tags live? - blocks: UI-4 - recommended default: As published claims on pathways so they pass maker-checker; matching is plain code.
- Is 'What changed' required for the pilot? - blocks: UI-12 - recommended default: Defer; no section 12 gate needs it. Build only if published content actually changes during the trial.
- Usability round 1 guest-only before account screens? - blocks: UI-14, UI-15 timing - recommended default: Yes, as the build pack says; run after UI-1..UI-7 and UI-14.

### Tasks

#### UI-1 - Component-first: app shell, nav, pre-wired stub partials, frozen macro signatures

- What: Rewrite base.html: four-destination nav, utility-menu slot, session-state slot, footer block, a block letting reviewer pages hide student nav. Create per-owner stub partials that render nothing (_report.html, _ask.html, _why.html, _save.html) plus _nav.html and _components.html, and wire their calls into compare/requirements/explore/_trust_badge NOW. Add optional cycle=none to evidence_line. Document signatures in docs/UI.md.
- Acceptance: All six existing templates render; existing web, reviewer-console and e2e tests pass (run by lead). Nav works at 375px zero-JS; /reviewer pages show no student nav. Stub macros called from existing templates. Signatures documented; app.css rebuilt once.
- Wave: 2 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 2 · Human hours: 0.5
- Depends on: DESIGN-1, DESIGN-2, I18N-1
- Touches: app/web/templates/base.html; app/web/templates/_nav.html; app/web/templates/_components.html; app/web/templates/_report.html; app/web/templates/_ask.html; app/web/templates/_why.html; app/web/templates/_save.html; app/web/templates/_trust_badge.html; app/web/templates/compare.html; app/web/templates/requirements.html; app/web/templates/explore.html; app/web/templates/reviewer_queue.html; app/web/templates/reviewer_sign_in.html; app/web/styles/input.css; app/static/css/app.css; docs/UI.md; tests/db/test_web_pages.py
- Reviewers: ux-qa-reviewer
- Risk: Every later task depends on these signatures; late changes force rework across screens.

#### UI-2 - Split pages.py into per-screen modules behind an aggregator

- What: Mechanical refactor. Move helpers and the templates object to app/web/common.py; one module per screen. app/web/pages.py stays as a thin aggregator that includes sub-routers and re-exports _db_client_or_none (tests import it from app.web.pages), so main.py and tests stay untouched. New screens register by one-line append in pages.py.
- Acceptance: Routes unchanged; no test file edited; full suite, ruff and mypy pass (lead runs them). pages.py contains only includes and re-exports.
- Wave: 0 · Step: cross · Needed by: staging-demo · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: none
- Touches: app/web/pages.py; app/web/common.py; app/web/explore_pages.py; app/web/compare_pages.py; app/web/requirements_pages.py; app/web/timeline_pages.py
- Reviewers: none
- Risk: Must merge before any screen task branches. Runs concurrently with UI-1 (disjoint files).

#### UI-3 - Landing page and stateless quick start

- What: Replace '/' redirect with 'Find your next step' and three starting choices ('career in mind' links to Explore's career anchor list). Add /start one-question-per-page GET flow, four questions, each skippable, answers as non-personal query params, ending at /start/results. No account wall, no marks/income/phone fields.
- Acceptance: Guest completes or skips all four questions zero-JS; no cookie or localStorage written; Back preserves answers; e2e covers skip and full paths; the old test asserting '/' redirect is updated.
- Wave: 3 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: UI-1, UI-2
- Touches: app/web/start_pages.py; app/web/pages.py; app/web/explore_pages.py; app/web/templates/home.html; app/web/templates/start_question.html; tests/unit/test_web_start.py; tests/e2e/test_start.py
- Reviewers: ux-qa-reviewer
- Risk: Option wording must avoid assessment or label framing.

#### UI-4 - Suggestion rule and 'why am I seeing this'

- What: Pure function app/planning/suggest.py mapping quick-start answers to up to three pathways by tag matching over published records; returns reasons, influencing preferences, unknowns and a change-preferences link. Budget never removes options; no salary/prestige ranking. Render on /start/results and fill the _why.html macro body.
- Acceptance: Unit tests: deterministic; budget removes nothing; no-match returns broader alternatives; each result lists reasons. Results page links back to edit answers. No AI call. Without tag data falls back honestly to Explore.
- Wave: 4 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: UI-3
- Touches: app/planning/suggest.py; app/web/start_pages.py; app/web/templates/start_results.html; app/web/templates/_why.html; tests/unit/test_suggest.py
- Reviewers: ux-qa-reviewer, ai-evaluator
- Risk: No tag data means no real relevance; never fake it.

#### UI-5 - Career card and pathway/programme detail page

- What: GET /pathways/{id}/view using one claims-driven detail template. Career card sections and programme/exam facts render only from published claims via field_value; missing sections show 'Not available'. Links to Requirements, Timeline, Compare. The detail link on Explore/Compare is a slot pre-wired by UI-1 in _components.html.
- Acceptance: Live DB test proves draft and synthetic-unapproved claims never render; malformed id gets friendly message; every fact shows badge, source, date (and cycle when supplied).
- Wave: 3 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0.5
- Depends on: UI-1, UI-2
- Touches: app/web/detail_pages.py; app/web/pages.py; app/web/templates/detail.html; tests/db/test_web_detail.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: Publication-integrity surface; must reuse the existing published-only assembly, not re-implement it.

#### UI-6 - Cost-assumption editing on Compare

- What: Add a GET form on compare.html for estimated additional expenses, parsed with a safe float helper and passed to assemble_comparisons' existing override. Label as 'Your assumption', one line explaining the recalculated total, explicit 'no data yet' notes for funding, work realities, alternatives.
- Acceptance: Changing the value updates net-to-arrange via URL; verified charges unchanged; user figure never carries an Estimate/verified badge; negative or garbled input degrades gracefully; web test and e2e step added in new files.
- Wave: 3 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: UI-1, UI-2
- Touches: app/web/compare_pages.py; app/web/templates/compare.html; tests/db/test_web_compare_assumption.py; tests/e2e/test_compare_assumption.py
- Reviewers: ux-qa-reviewer
- Risk: Sole wave-2 owner of compare.html body; a user figure must never look verified.

#### UI-7 - Timeline: stage kinds and 'Revise this scenario' (no data dependency)

- What: On the existing calculator, visually distinguish required, optional and user-assumption stages (text plus icon), add 'Revise this scenario' for an extra attempt (never a failure badge), and show pathway name context when pathway_id is given. Standalone mode kept. Zero JS.
- Acceptance: Three stage kinds distinguishable without colour; revise adds an attempt row and recomputes; existing six unit tests still pass plus new ones; total unknown when any duration missing.
- Wave: 3 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: UI-1, UI-2
- Touches: app/web/timeline_pages.py; app/web/templates/timeline_calculator.html; tests/unit/test_web_timeline_page.py
- Reviewers: ux-qa-reviewer
- Risk: Low.

#### UI-11 - Ask BCION contextual shell (AI-off first)

- What: Fill the _ask.html macro body (already called from cost card, pathway and eligibility line by UI-1) with fixed-prompt links. GET /ask?template=&pathway_id= renders an answer page; with AI disabled shows 'You can still compare routes and use the calculators' plus retrieved published records. No free-text input. Document the answer-slot contract.
- Acceptance: With the AI flag false every entry point returns 200 with fallback and cited records; unknown template id gets friendly error; no free-text field exists; contract documented in docs/UI.md for the AI area.
- Wave: 10 · Step: 11 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: UI-1, UI-2, AI-7, AI-2
- Touches: app/web/ask_pages.py; app/web/pages.py; app/web/templates/ask.html; app/web/templates/_ask.html; tests/unit/test_web_ask.py
- Reviewers: ai-evaluator, ux-qa-reviewer
- Risk: The 'outside coverage' tester task needs the AI area; shell alone shows only the AI-off state.

#### UI-13 - Utility menu pages and flag-driven footer

- What: Static privacy and help pages (pilot limits, what is stored, how to delete, report link), account page (sign out, export/delete entry points), generic friendly 404/permission-denied page. Footer synthetic label driven by a fixtures flag. Privacy text supplied by owner, not invented by the agent.
- Acceptance: All utility links resolve; owner has reviewed privacy text; footer test covers fixtures-on and fixtures-off; permission-denied page exposes no other user's data.
- Wave: 5 · Step: 8 · Needed by: real-users-gate · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 1.5
- Depends on: UI-1, UI-2, AUTH-9
- Touches: app/web/utility_pages.py; app/web/pages.py; app/web/templates/privacy.html; app/web/templates/help.html; app/web/templates/account.html; app/web/templates/error.html; app/web/templates/base.html; app/core/config.py; tests/unit/test_web_utility.py
- Reviewers: human
- Risk: Touches base.html footer after UI-1: run after wave 2 merges or as the only base.html editor.

#### UI-15 - Owner phone walk-through and component-set freeze

- What: Owner clicks the staging guest journey on a real phone, compares with the mockup artifact, confirms the owner decisions, and the freeze is recorded in docs/DECISIONS.md. Change requests become task cards.
- Acceptance: Dated DECISIONS.md entry with owner sign-off; change requests filed as tasks/BCI-xxx.md.
- Wave: 6 · Step: 7 · Needed by: staging-demo · Executor: owner · Model tier: none · Dev sessions: 0 · Human hours: 1.5
- Depends on: QA-7, DEPLOY-7, DATA-10
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: Skipping lets component churn continue.

#### UI-16 - Separate Saved destination

- What: saved_items table with own-row RLS, /saved page, save toggles. Only if the owner rejects merging Saved into My Plan.
- Acceptance: Cross-user RLS tests pass; zero-JS save/unsave; nav points to /saved.
- Wave: 6 · Step: 8 · Needed by: deferrable · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0.25
- Depends on: AUTH-6, AUTH-14
- Touches: db/migrations/00NN_saved_items.sql; app/api/saved.py; app/web/saved_pages.py; app/web/templates/saved.html; tests/db/test_web_saved.py
- Reviewers: data-security-reviewer
- Risk: Over-engineering for the pilot.

#### UI-19 - Usability round 1 fix round

- What: Turn round-1 findings (task-completion failures only, not taste) into at most two bounded fix sessions on copy, labels and layout, within the frozen component set.
- Acceptance: Each failed task criterion has a fix or a logged reason in STATUS.md; suite still green.
- Wave: 9 · Step: 7 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 1
- Depends on: UI-15, TRIAL-9
- Touches: app/web/templates/*; app/web/styles/input.css; app/static/css/app.css
- Reviewers: ux-qa-reviewer
- Risk: Scope creep; only task-criteria failures qualify.

### Merged into other tasks

- UI-8 -> AUTH-3
- UI-9 -> AUTH-6
- UI-10 -> OPS-6
- UI-12 -> AUTH-13
- UI-14 -> QA-7
- UI-17 -> RULES-9
- UI-18 -> QA-10

## Auth, browser sessions, guest sessions, saved and versioned plans, export and deletion

Area: `auth-sessions-plans`

The "done" claims all check out: JSON auth and plans API, own-row RLS, cascade deletes, and the reviewer-only cookie session. A Playwright harness already exists locally, which the audit missed.

All the listed gaps are real. Nothing is browser-usable for students: no student or guest session, My Plan, versions, next actions, export, deletion, sign-out, rate limiting or Origin check.

Four changes cut cost and risk:
- Keep the JSON API Bearer-only; cookies live only in the web layer.
- Drop refresh tokens for the pilot.
- Delete accounts with a narrow SECURITY DEFINER function, not a service-key script.
- Build the guest lane first so staging needs no sign-in.

Totals: 16 planned dev sessions, 1 contingency, 1 deferrable; about 4 human hours.

### Already done

- POST /auth/sign-up and /auth/sign-in over Supabase Auth. Provider status propagated (429), no-enumeration 401, fresh client per call closed in finally. Shared authenticate() returns the full Session (expires_in available). - F:\the competetion project\app\api\auth.py (sign_up, authenticate, sign_in); 9 test functions counted in tests/db/test_api_auth.py. Note: email-confirmation case is signalled by raising HTTPException(status_code=202) - works but is unusual; HTML flow must handle it explicitly.
- Guest-to-account migration at JSON level only: client-supplied pending_plan saved as first plan, best effort, failure logged by ids only (no notes/figures). - app/api/auth.py _migrate_pending_plan; module docstring lines 14-28 states no server guest session exists.
- Saved plans CRUD (POST/GET/PATCH/DELETE /plans) with 404/409/422 mapping; RLS is sole ownership enforcement; cross-user delete and reviewer-vs-plans regression tests exist. - app/api/plans.py; 13 test functions in tests/db/test_api_plans.py; docs/DECISIONS.md 2026-09-19 'M3 auth surface security-reviewed'.
- saved_plans table: own-row RLS (using + with check), unique(student_id, pathway_id), updated_at trigger, cascade from auth.users and pathways. - db/migrations/0002_saved_plans.sql (header says plan_versions deliberately deferred).
- Header-only auth dependencies (get_db_client, require_auth, AuthedSession) with per-request close; no service role anywhere under app/. - app/api/deps.py; grep for service_role under app/ hits only a docstring in app/db/client.py.
- Reviewer-only cookie session pattern: httponly, samesite=lax, secure in production, max_age = Session.expires_in, path=/reviewer, stale cookie cleared with redirect, POST sign-out. It calls API route functions directly with an AuthedSession rather than changing deps.py - the precedent the student session should copy. - app/web/reviewer_pages.py; 10 test functions in tests/db/test_reviewer_console.py. Caveat: sign-out only deletes the cookie; the access JWT stays valid until expiry (inherent to Supabase JWTs).
- student_profiles, reviewers and saved_plans all cascade on auth.users delete, so removing the auth row removes all student data with no extra code. - db/migrations/0001_init.sql lines 98-115; 0002_saved_plans.sql line 20.
- Student templates exist only for explore, compare, requirements, timeline; none for sign-in, sign-up, account or My Plan. - app/web/templates/: _trust_badge, base, compare, explore, requirements, reviewer_queue, reviewer_sign_in, timeline_calculator.
- Playwright e2e harness already exists locally (real uvicorn subprocess + browser, reuses tests/db fixtures, 6 smoke tests incl. reviewer cookie sign-in). Test users are created via admin.create_user with the test-only service-role key, so tests do not consume the sign-up email rate limit. - tests/e2e/conftest.py, tests/e2e/test_smoke.py (6 tests), tests/db/conftest.py lines 126-190; commit 2db356e. CI still has test-db and test-e2e commented out (.github/workflows/ci.yml lines 5-6, 46-47).

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No student browser session: pages.py and /plans read only the Authorization header; no student sign-in/sign-up pages; no 'session ended' handling. | Build pack s9 Step 8 'Managed auth, sessions'; app/web/reviewer_pages.py docstring | launch-blocker |
| No anonymous server-side guest session (no table, token, 7-day expiry, 'not saved to an account' label, purge). pending_plan path implicitly pushes clients to local storage, which the spec forbids. | Build pack s3 'Guest plans', s6 'Guest sessions'; docs/UI.md lines 55-58 | launch-blocker |
| No My Plan screen, no 'Save this route' control on Compare/Timeline/Requirements, no failed-save state. This is the last step of the core journey (save next actions), so the guest journey on staging is incomplete without it. | CLAUDE.md mission; docs/PRODUCT.md line 29; build pack s5 difficult states; s12 tester task | launch-blocker |
| No next-actions logic or data and no current-decision flag on a plan. | Build pack s2 'save next actions'; docs/PRODUCT.md My Plan; s12 'save a plan and find the next action' | launch-blocker |
| No student sign-out, no Cache-Control: no-store on plan/account pages, no shared-device verification. | Build pack s5 'Shared device'; s12 'log out safely on a shared device'; SECURITY.md Privacy gate | launch-blocker |
| Guest-to-account migration not wired to any UI or server guest session (JSON body only); no confirm step to stop a sibling's guest plans being imported on a shared phone. | Build pack s6 'account creation migrates it' | phase1-required |
| No student data export route or access-matrix 'export' test. | Build pack Step 8; SECURITY.md access matrix + Privacy gate | phase1-required |
| No account deletion (only per-plan delete). auth.users removal needs privilege the request path does not have; needs a reviewed narrow mechanism. | Build pack s6 'deletion within 30 days'; SECURITY.md access model | phase1-required |
| No app-level rate limiting on /auth/* or (future) web sign-in and guest-session creation; no Origin/Referer check on cookie-authenticated form POSTs (reviewer routes included - samesite=lax only). | Task scope 'rate limiting on auth'; SECURITY.md 'No known critical/high' | phase1-required |
| plan_versions table and version-on-edit missing (only updated_at). | Build pack s6 Tables; Step 8 'saved and versioned plans' | phase1-required |
| Plan input validation gaps found in code: PATCH /plans drops None values so notes/expenses can never be cleared; no length cap on notes; no bounds (negative/huge) on estimated_additional_expenses; plans.py docstring names a non-existent require_user_client. | app/api/plans.py lines 47-56, 128; SECURITY.md Calculators/boundaries gate | phase1-required |
| Supabase Auth dashboard settings undocumented and undecided: JWT expiry, email confirmation, minimum password length (SignUpRequest.password has no constraint), 'allow new sign-ups' toggle, auth rate limits. No forgotten-password path (not even a runbook line). | Build pack s12 'no repeated unexplained save failure'; STATUS.md consent warning; PRODUCT.md return visits weeks 2-4 | phase1-required |
| E2E coverage for save, next action, sign-out, back-button missing (harness exists; flows do not). test-db and test-e2e are not run in CI. | Build pack s12 Step 15 tester tasks; .github/workflows/ci.yml | phase1-required |
| 'What changed' list under My Plan / affected-plans flagging on claim supersession. | docs/UI.md lines 72-73; build pack s5, s6 Publishing | phase1-nice |
| 'Saved' destination (careers, programmes, sources to revisit) - fourth nav item in the spec, nothing exists. Missed by the audit. | Build pack s5 Navigation; docs/PRODUCT.md line 30 | defer |
| student_profiles has a table and RLS but no API or UI writes it (quick-start answers are not persisted). Missed by the audit. For the pilot, not collecting it is the data-minimising choice; export must still include it if rows exist. | Build pack s6 Identity tables; docs/UI.md Quick start | defer |
| reminders table and WhatsApp opt-in attached to plans. | Build pack s6 Tables; Step 13 calls it optional | defer |
| Parent family summary generated from a plan. | Build pack s5 'Other people in Lite' | defer |

### Owner decisions

- Build the server-side guest session now, or demo with stateless guests? - blocks: AUTH-4, AUTH-6, staging-demo - recommended default: Build now. Saving next actions is the final step of the guest journey, and usability round 1 is guest-only. Guest plans hold pathway id plus one number, no free text.
- Student session length: refresh-token cookie or access-token only? - blocks: AUTH-2, AUTH-16 - recommended default: Access token only for phase 1. Set JWT expiry to 4 hours in the dashboard. Expiry shows 'session ended, sign in again' with the draft kept. Revisit refresh tokens at expand-100 if testers complain.
- Account deletion mechanism: narrow SECURITY DEFINER delete_my_account() (immediate, no service key on the VM) or a request table plus owner-run script with the service key? - blocks: AUTH-10 - recommended default: Definer function, with mandatory human sign-off of its text. It is immediate, costs one session, and keeps the service key off the VM. Fall back to the script only if the reviewer rejects it.
- Is student sign-up open, flagged, or invite-only during the pilot? - blocks: AUTH-3, AUTH-8, AUTH-16 - recommended default: Invite-only: Supabase 'allow new sign-ups' off, app SIGNUP_ENABLED=false, owner creates adult tester accounts. Enable only after the consent workflow is reviewed by a person.
- Supabase email confirmation on or off? - blocks: AUTH-3 (202 path), AUTH-16 - recommended default: Off while invite-only (owner-created accounts are pre-confirmed). Revisit when public sign-up opens; free-tier email limits would block a classroom.
- Forgotten password during the trial: build a reset flow or handle manually? - blocks: AUTH-16 - recommended default: Manual: the owner resets via the dashboard, documented in the runbook. No reset flow in phase 1.
- Who allocates migration numbers and BCI card ids across parallel areas? - blocks: AUTH-4, 5, 7, 10, 15 - recommended default: The integrator session owns the sequence. This area's numbers 0004-0008 are provisional and renamed at merge time; a migration is never edited after it has been applied.
- Are reminders/WhatsApp, the Saved destination, profile capture and the parent summary in phase 1? - blocks: nothing in this area - recommended default: Defer all four. No section-12 gate needs them.

### Tasks

#### AUTH-1 - Freeze session, guest and plan-store contract (design only)

- What: Write task card + docs/ARCHITECTURE.md section: student/guest cookie names, flags, paths; JSON API stays Bearer-only, web layer owns cookies; no refresh token in phase 1; Origin-check rule; guest_sessions/guest_plans RPC signatures; plan_actions + is_current schema; PlanStore interface (guest vs account) used by My Plan; migration merge rules; export JSON shape; delete_my_account() design; SIGNUP_ENABLED flag and consent hook signature; provisional migration numbers.
- Acceptance: Owner approves card. Schemas, RPC signatures, error shapes and flag names listed. Consent area confirms hook suffices. Integrator confirms migration numbers and BCI card ids do not collide with other areas.
- Wave: 0 · Step: 8 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.5
- Depends on: none
- Touches: tasks/BCI-007.md (provisional id); docs/ARCHITECTURE.md; docs/DECISIONS.md
- Reviewers: data-security-reviewer, human
- Risk: Wrong contract causes rework across parallel lanes.

#### AUTH-2 - Student cookie session in the web layer

- What: Create app/web/session.py by generalising reviewer_pages' pattern: cookie bcion_student_session (httponly, samesite=lax, secure in prod, path=/, max_age=expires_in), get_student_session dependency yielding AuthedSession or None, redirect helper with 'your session ended' notice, no_store response helper. Do NOT change app/api/deps.py; JSON API stays header-only. Reviewer cookie untouched.
- Acceptance: Valid cookie yields AuthedSession; absent, expired or garbage cookie yields None and clears cookie. /plans JSON still rejects cookie-only requests (test). Reviewer suite unchanged. Cookie tests cover guest, A, B, reviewer.
- Wave: 2 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0
- Depends on: AUTH-1, SEC-2
- Touches: app/web/session.py; tests/db/test_student_session.py
- Reviewers: data-security-reviewer
- Risk: Access token cannot be revoked before expiry; mitigated by short JWT expiry (AUTH-16) and httponly.

#### AUTH-3 - Student sign-in, sign-up (flagged off) and sign-out pages

- What: Zero-JS Jinja forms at /sign-in, /sign-up, POST /sign-out in app/web/account_pages.py calling auth.authenticate / sign_up logic. Styled messages for 401, 429, 202. /sign-up returns a 'pilot is invite-only' page unless SIGNUP_ENABLED is true, and calls the consent hook stub. Sign-out clears student and guest cookies. no-store on all account pages. Nav links in base.html.
- Acceptance: Browser can sign in and out; after sign-out /my-plan redirects and carries no-store. With flag off, /sign-up creates no account (test). 429 and 202 render styled. Works at 360px without JS.
- Wave: 3 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: UI-1, UI-2, AUTH-2, CONSENT-1
- Touches: app/web/account_pages.py; app/web/templates/sign_in.html; app/web/templates/sign_up.html; app/web/templates/base.html; app/core/config.py; app/main.py; tests/db/test_account_pages.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: JSON POST /auth/sign-up is still ungated; consent area or AUTH-8 must put it behind the same flag.

#### AUTH-4 - Guest server session: migration, hashed token, 7-day expiry

- What: Migration (provisional 0004): guest_sessions(id, token_hash, created_at, expires_at) and guest_plans(session_id, pathway_id, estimated_additional_expenses) - no notes or free text. RLS deny-all; access only via SECURITY DEFINER RPCs (pinned search_path) keyed by token: create, save, list, delete. Expired rows filtered on read and purged opportunistically on create. app/web/guest_session.py sets 256-bit random cookie, 7-day max_age.
- Acceptance: Guest saves and lists by cookie; other token sees nothing; expired returns empty; token stored as SHA-256; max 10 plans per session; only existing pathway ids accepted. test-db covers guest X vs Y, student vs guest rows, direct table access denied.
- Wave: 1 · Step: 8 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 2 · Human hours: 0.25
- Depends on: AUTH-1
- Touches: db/migrations/0004_guest_sessions.sql; app/web/guest_session.py; tests/db/conftest.py (skip guard for new migration); tests/db/test_guest_session.py
- Reviewers: data-security-reviewer
- Risk: Definer functions are a deliberate RLS bypass; an input bug leaks one guest's plans to another.

#### AUTH-5 - Next actions, current-decision flag and plan input validation

- What: Migration (provisional 0005): saved_plans.is_current with partial unique index per student; plan_actions(plan_id, action_key, done, done_at) own-row RLS via parent. app/planning/actions.py derives up to three next actions by ordinary code from the pathway's published requirement claims (none -> 'not verified yet'). Extend plans.py: mark current, tick action, allow clearing notes/expenses, cap notes length, bound expenses, fix docstring.
- Acceptance: Actions derive only from published claims; draft or synthetic-unpublished never appear. One is_current per student enforced in DB. B cannot read or tick A's actions. PATCH can null a field. Negative or absurd expenses and over-long notes return 422.
- Wave: 1 · Step: 8 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: AUTH-1
- Touches: db/migrations/0005_plan_actions.sql; app/api/plans.py; app/planning/actions.py; tests/unit/test_plan_actions.py; tests/db/test_api_plans.py
- Reviewers: data-security-reviewer
- Risk: With no real published content, actions list is mostly 'not verified yet' on staging; needs labelled synthetic fixtures for the demo.

#### AUTH-6 - My Plan screen and Save controls (guest mode first)

- What: /my-plan page: current decision, next three actions, saved alternatives, remove. 'Save this route' POST forms on Compare, Timeline and Requirements. Uses the PlanStore interface with the guest-session backend; 'Not saved to an account' banner. Failed save keeps the draft visible and never shows 'Saved'. no-store on /my-plan. Zero JS.
- Acceptance: Guest saves from Compare and sees it on /my-plan at 360px and desktop. Forced RPC failure shows draft plus error, no 'Saved' text. Response has Cache-Control: no-store. ux-qa-reviewer walkthrough passes.
- Wave: 4 · Step: 8 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: AUTH-3, AUTH-4, AUTH-5, UI-1, SEC-2
- Touches: app/web/plan_pages.py; app/planning/plan_store.py; app/web/templates/my_plan.html; app/web/templates/compare.html; app/web/templates/timeline_calculator.html; app/web/templates/requirements.html; app/main.py; tests/db/test_plan_pages.py
- Reviewers: ux-qa-reviewer
- Risk: Template merge conflicts with the UI lane.

#### AUTH-7 - Guest-to-account migration in the HTML flow

- What: Add definer RPC migrate_guest_plans(token) (new migration, provisional 0006) that copies guest_plans into saved_plans for auth.uid(), keeps the account row on duplicate pathway, deletes the guest session. Sign-in/sign-up pages show 'Import these N saved routes?' with an explicit checkbox; on success clear guest cookie. JSON pending_plan path left as is.
- Acceptance: Guest with 2 plans signs in with box ticked: both appear, guest rows gone, cookie cleared. Unticked: nothing imported, guest session deleted. Failure never blocks sign-in; logged by ids only. B cannot migrate using A's session id, only a token.
- Wave: 6 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.1
- Depends on: AUTH-3, AUTH-4, AUTH-14
- Touches: db/migrations/0006_guest_migration.sql; app/web/account_pages.py; app/web/templates/sign_in.html; app/web/templates/sign_up.html; tests/db/test_guest_migration.py
- Reviewers: data-security-reviewer
- Risk: Shared-phone token replay: a sibling's guest plans imported into the wrong account - hence explicit confirmation.

#### AUTH-9 - Student data export

- What: GET /account/export (JSON download) plus /account page with button, in app/web/account_pages.py. Assembles profile (if any), saved plans, actions, versions and consent rows if those tables exist, using only the student's RLS-scoped client. no-store; payload never logged.
- Acceptance: A's export holds only A's rows; signed-out request redirects; reviewer export has no student rows; guest gets nothing. Access-matrix 'export' column covered in test-db.
- Wave: 4 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: AUTH-3, AUTH-5
- Touches: app/web/account_pages.py; app/web/templates/account.html; tests/db/test_account_export.py
- Reviewers: data-security-reviewer
- Risk: Low.

#### AUTH-10 - Account deletion via narrow definer function

- What: Migration (provisional 0007): delete_my_account() SECURITY DEFINER, no parameters, pinned search_path, deletes auth.users where id = auth.uid() (cascades profile, plans, actions, versions), execute granted to authenticated only. POST /account/delete requires password re-entry via authenticate(), calls RPC, clears cookies, shows confirmation. Runbook line for manual owner deletion as fallback.
- Acceptance: After delete, all A's rows gone and sign-in fails. B's data untouched. Anon call fails. Reviewer calling it deletes only self. Wrong password blocks deletion. Human reviewer signs off the function text.
- Wave: 5 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.5
- Depends on: AUTH-9
- Touches: db/migrations/0007_delete_my_account.sql; app/web/account_pages.py; app/web/templates/account.html; tests/db/test_account_deletion.py; docs/SECURITY.md
- Reviewers: data-security-reviewer, human
- Risk: Privileged delete on auth schema. If review rejects it, fall back to request table plus owner-run script (2 sessions, service key on VM).

#### AUTH-12 - Independent security review and human sign-off of auth/session/plan surface

- What: Read-only data-security-reviewer pass over AUTH-2..10, 14: full matrix (guest, A, B, reviewer x read, write, delete, export), cookie flags, Origin check, every definer function, log PII, cache headers. Then a one-hour human sign-off, since model review never signs off child data.
- Acceptance: Written findings with zero open critical or high. Named person recorded in docs/DECISIONS.md. Any exception has owner, rationale, expiry.
- Wave: 7 · Step: cross · Needed by: real-users-gate · Executor: mixed · Model tier: strongest · Dev sessions: 1 · Human hours: 1.5
- Depends on: AUTH-7, SEC-2, AUTH-9, AUTH-10, AUTH-14
- Touches: docs/DECISIONS.md; STATUS.md
- Reviewers: data-security-reviewer, human
- Risk: Findings trigger AUTH-18.

#### AUTH-13 - 'What changed' list under My Plan

- What: For each saved plan list published-claim supersessions on its pathway since the plan's updated_at: field, old value, new value, date, source. Read-only, from claims.superseded_by.
- Acceptance: Superseding a synthetic test claim shows the change on /my-plan for a plan saved earlier. Draft claims never appear.
- Wave: 5 · Step: 8 · Needed by: deferrable · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: AUTH-6
- Touches: app/planning/changes.py; app/web/templates/my_plan.html; tests/db/test_what_changed.py
- Reviewers: ux-qa-reviewer
- Risk: Little value until real content churns.

#### AUTH-14 - My Plan in signed-in mode

- What: Add the account backend of PlanStore: /my-plan and Save forms use the student cookie session and call plans.py functions directly (reviewer-console pattern). Adds edit assumption/notes, mark current, tick action, delete. Expired session during save shows 'session ended, sign in again' with the draft kept visible.
- Acceptance: Student saves, edits, marks current, ticks action, deletes from browser. B never sees A's plans via pages. Expired cookie on save gives explained state, not a 500. Duplicate save shows friendly 409 text.
- Wave: 5 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: AUTH-3, AUTH-6
- Touches: app/planning/plan_store.py; app/web/plan_pages.py; app/web/templates/my_plan.html; tests/db/test_plan_pages.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: Low; pattern is proven by reviewer console.

#### AUTH-15 - plan_versions with trigger snapshots

- What: Migration (provisional 0008): plan_versions(plan_id, version_no, snapshot jsonb, created_at) written by trigger on saved_plans insert/update; own-row select RLS through parent, no update/delete policy. Add versions to export. No diff UI.
- Acceptance: PATCH creates version n+1; history cannot be updated or deleted by the student; B cannot read A's versions; cascade on plan delete; export includes versions.
- Wave: 6 · Step: 8 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.1
- Depends on: DATA-4, AUTH-5, AUTH-9
- Touches: db/migrations/0008_plan_versions.sql; app/web/account_pages.py; tests/db/test_plan_versions.py; tests/db/test_account_export.py
- Reviewers: data-security-reviewer
- Risk: No section-12 gate needs it; first candidate to slip if time is short.

#### AUTH-17 - Human shared-phone check on a real Android device

- What: On staging with a real low-end Android phone: save as guest, close and reopen the browser, sign in, sign out, press back, open /my-plan, check browser history and tab previews for plan data. Record results against the Privacy gate.
- Acceptance: Checklist filled in STATUS.md: no plan data visible after sign-out via back, reopen, or history; guest label visible; any failure filed as a task.
- Wave: 7 · Step: 8 · Needed by: real-users-gate · Executor: human-reviewer · Model tier: none · Dev sessions: 0 · Human hours: 0.5
- Depends on: AUTH-14, AUTH-7, DEPLOY-7
- Touches: STATUS.md
- Reviewers: human
- Risk: bfcache behaviour varies by browser; automated tests alone will not catch it.

#### AUTH-18 - Contingency: fix session for review findings

- What: One bounded session reserved to fix critical or high findings from AUTH-12 or AUTH-17, then re-run the affected test-db and e2e suites. Skip if there are none.
- Acceptance: Every critical/high finding closed with a test that would have caught it; reviewer re-check passes.
- Wave: 8 · Step: cross · Needed by: real-users-gate · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.25
- Depends on: AUTH-12, AUTH-17
- Touches: files named in the findings
- Reviewers: data-security-reviewer, human
- Risk: Two failed fixes of the same finding -> stop and diagnose per CLAUDE.md.

### Merged into other tasks

- AUTH-8 -> SEC-2
- AUTH-11 -> QA-10
- AUTH-16 -> CONSENT-5

## Hindi, translation keys, locale formatting and search

Area: `i18n-hindi-search`

Verified: nothing in this area is built. All 8 templates (the reviewer ones extend base.html too), the pages.py messages and the domain-layer messages in app/rules are hardcoded English. `<html lang="en">` is fixed. There is no language switch, catalogue, search route or Hindi column. Money uses Western grouping at exactly two sites; dates and weeks print raw. The only hook is `student_profiles.language default 'en'`. Do first: a shared Jinja environment with `t()`, the formatters and a frozen key contract (I18N-1/2), then extraction of the existing templates (I18N-3) with a CI string-lint, before other areas build new screens. Then: Hindi draft, message codes for eligibility/timeline text, human review behind a prod flag, FTS + synonyms, Hindi e2e.

### Already done

- There is a `language` column on student_profiles (default 'en', no check constraint) and `language: str = "en"` on the Pydantic model. Nothing reads or writes it for rendering. - F:\the competetion project\db\migrations\0001_init.sql line 103 (table student_profiles); F:\the competetion project\app\data\models.py line 129
- Templates are server-rendered Jinja, but there are TWO separate Jinja2Templates instances, one in pages.py and one in reviewer_pages.py. Both reviewer templates extend base.html, so a `t()` global has to be registered on both or moved to one shared module. - F:\the competetion project\app\web\pages.py line 33; F:\the competetion project\app\web\reviewer_pages.py line 60; reviewer_queue.html and reviewer_sign_in.html line 1 (`{% extends "base.html" %}`)
- No web fonts are downloaded. There is one compiled stylesheet, so Devanagari must come from a system-font fallback stack. - F:\the competetion project\app\web\templates\base.html lines 7-9; app\web\styles\input.css (no font-family stack for Devanagari)
- Money formatting exists at exactly two sites, both the rupee sign plus `{:,.0f}` with Western grouping. An existing page test asserts '85,000', which is identical under Indian grouping, so the swap is safe. - F:\the competetion project\app\web\templates\_trust_badge.html line 90; compare.html line 89; tests\db\test_web_pages.py line 169
- Explore is a zero-JS list, and the only JS is a selection counter with a hardcoded English string. The API has `GET /careers` only, with no query parameter and no search. - F:\the competetion project\app\web\templates\explore.html lines 79-95; F:\the competetion project\app\api\explore.py lines 39-42
- A Playwright smoke suite, its live_server conftest and a `make test-e2e` target exist. The e2e step in CI is commented out, and STATUS.md line 387 still says 'No e2e test', which is stale against commit 2db356e. - F:\the competetion project\tests\e2e\test_smoke.py; tests\e2e\conftest.py; Makefile lines 25-26; .github\workflows\ci.yml lines 46-47
- careers and pathways are world-readable (`select using (true)`) and have no draft/published status; only claims carry status. Search over careers/pathways therefore exposes nothing that Explore does not already expose. - F:\the competetion project\db\migrations\0001_init.sql lines 148-153, 158-159

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| There are no translation keys. Strings are hardcoded in base.html, explore.html, compare.html, requirements.html, timeline_calculator.html, _trust_badge.html, the two reviewer templates, pages.py (_DB_UNAVAILABLE_MESSAGE at line 39, the invalid-pathway message at line 278) and the inline JS counter at explore.html line 86. | Build pack s9 Step 6 ('translation keys'); s7 contracts before parallel work | launch-blocker |
| User-visible English is generated inside domain code. app/rules/eligibility.py builds criterion explanations as f-strings (lines 118-282). app/rules/timeline.py raises ValueError messages that pages.py shows as-is (pages.py lines 414-427). Its attempt labels are built in English at line 179. Template extraction cannot translate any of these. They need message codes and params. | Build pack s2 line 25 (critical content in both languages); s5 line 88 (eligibility uncertain: name the missing requirement) | phase1-required |
| There is no Hindi catalogue, and `<html lang>` is hardcoded to 'en' (base.html line 2). | Build pack s2 line 25; docs/PRODUCT.md line 43 | phase1-required |
| There is no language switch. The spec wants language visible immediately on first visit and in the utility menu. | Build pack s5 lines 72, 74; docs/PRODUCT.md line 32 | phase1-required |
| There is no locale-aware formatting. Money uses Western grouping. verification_date and review_due_date print as raw ISO strings (_trust_badge.html line 46). Durations print as a bare '{{ total_weeks }} weeks' (timeline_calculator.html line 22). | Build pack s9 Step 12; s7 contracts | phase1-required |
| Careers and pathways have no Hindi names or descriptions (single name/description columns), and there is no fallback rule. No career/pathway editor exists anywhere, the reviewer console included, so Hindi labels must arrive through the content import/seed path. | Build pack s2 line 25; s12 'Built means' | phase1-required |
| There is no search at all: no tsvector, no synonym table, no route, no search box and no 'No matching result' state. | Build pack s4 line 58; docs/ARCHITECTURE.md line 17; s5 line 88; docs/UI.md line 66 | phase1-required |
| Roman-script Hindi input is not accepted anywhere. | Build pack s2 line 25; docs/PRODUCT.md line 43 | phase1-required |
| Hindi text expansion and the Devanagari font stack are untested at 360 px and 200% zoom. No :lang(hi) rules exist in input.css. | Build pack s7 Quality gates UI line 124 | phase1-required |
| No human Hindi review has happened and no reviewer is named. The build pack starts Hindi copy review at Step 7. | Build pack s9 Step 7 row (line 164); s12 'Built means' line 220 | phase1-required |
| There is no mechanism to keep unreviewed Hindi away from real users. A machine-draft Hindi trust label or consent text shown to a real minor would be unreviewed critical content. | Build pack s2 line 25 'Critical content reviewed in both'; CLAUDE.md non-negotiables (consent workflow reviewed by a person) | phase1-required |
| There is no Hindi-preferring participant path for usability round 1. It needs a draft Hindi UI on staging. | Build pack s5 line 90; docs/UI.md line 97 | phase1-required |
| The e2e step in CI is commented out, so a Hindi e2e would run only locally until the QA area enables it. | Build pack s7 Quality gates; .github/workflows/ci.yml lines 46-47 | phase1-nice |
| The reviewer console body text is English-only. Its base.html chrome is translated automatically. | No spec requirement. Reviewers are staff. | defer |
| Gujarati UI strings. | Build pack s2 line 25 (conditional); weakened by the 2026-09-21 all-India decision | defer |

### Owner decisions

- Who is the named human Hindi reviewer (a fluent reader, not a dev agent)? - blocks: I18N-6, I18N-10, I18N-11, I18N-16, and turning Hindi on in production - recommended default: The second content reviewer, or a Hindi-medium teacher from the pilot school, at about 7-8 hours in total. Until the sign-off exists, HINDI_UI_ENABLED stays false in prod and Hindi is shown on staging only, labelled as a draft translation.
- Catalogue mechanism: plain JSON plus `t()`, or Babel/gettext? - blocks: I18N-1 and every new screen in every area - recommended default: Plain JSON plus `t()`. It needs no dependency and no compile step, and the files are easy to diff. Record the choice in DECISIONS.md.
- What is the default language, and should the browser language be auto-detected? - blocks: I18N-1, I18N-4 - recommended default: English by default with an always-visible header switch, and the choice kept in a non-personal `lang` cookie. Do not sniff Accept-Language: Indian phones mostly send en-IN or en-US even for Hindi-preferring users, and dropping it keeps public caching keyed on one cookie.
- May unreviewed machine-draft Hindi be shown to real users? - blocks: I18N-4 flag default, I18N-11 timing relative to the ten-user trial - recommended default: No. Use staging and usability rounds only. Prod Hindi turns on after the I18N-11 critical-key sign-off. If the reviewer slips, the first ten users get English only and the reason is recorded honestly.
- What is the scope of Hindi catalogue content? - blocks: I18N-7, I18N-11 (reviewer hours) - recommended default: Translate career and pathway names and descriptions, plus all UI and critical wording. Keep institution, exam and programme proper names, source titles and URLs as the authority publishes them. Numbers, dates and rules are never translated and are only formatted.
- Which number style is used? - blocks: I18N-2 - recommended default: Indian grouping (1,00,000) with Latin digits in both locales, and no Devanagari digits. Add a lakh/लाख short form later only if usability testing asks for it.
- Is Gujarati UI needed after the all-India scope change? - blocks: I18N-14 only - recommended default: No. Defer it until a confirmed Gujarati-medium cohort exists.

### Tasks

#### I18N-1 - i18n mechanism, shared Jinja env and frozen key contract

- What: Create app/web/templating.py with the single Jinja2Templates instance. pages.py and reviewer_pages.py import it, replacing their two separate instances. Add app/i18n with flat en.json/hi.json and `t(key, **vars)` as a Jinja global. The locale resolver order is `lang` cookie -> 'en', with an allowlist of en|hi. Hindi falls back to English per key. Record the key naming, placeholder and fallback rules in docs/DECISIONS.md.
- Acceptance: Unit tests cover resolver precedence, the allowlist, missing-key fallback, en/hi key parity, and that both routers share one environment. lint, typecheck and test-unit pass. The DECISIONS entry is written. No template text is changed.
- Wave: 1 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: DESIGN-2, UI-2
- Touches: app/web/templating.py; app/i18n/__init__.py; app/i18n/en.json; app/i18n/hi.json; app/web/pages.py (line 33 import only); app/web/reviewer_pages.py (line 60 import only); docs/DECISIONS.md; tests/unit/test_i18n.py
- Reviewers: ux-qa-reviewer
- Risk: The lang value must be allow-listed and must never reach a file path. The cookie carries no personal data.

#### I18N-2 - Locale-aware formatting helpers

- What: Add pure functions in app/i18n/formatting.py, registered as Jinja filters in app/web/templating.py. format_inr gives Indian 1,00,000 grouping with a rupee sign and no decimals. format_number and format_date (ISO date/str -> '21 Sep 2026' / '21 सितंबर 2026') complete the set, with format_duration_weeks (weeks -> weeks plus approximate years/months wording via catalogue keys). Both locales use Latin digits.
- Acceptance: Table-driven unit tests cover 0, negative, 99,999 / 1,00,000 / 1,00,00,000, None -> the 'not available' key, a leap-day date, an ISO-string input, and both locales. No new dependency is added.
- Wave: 2 · Step: 12 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: I18N-1
- Touches: app/i18n/formatting.py; app/web/templating.py (filter registration); app/i18n/en.json; app/i18n/hi.json; tests/unit/test_formatting.py
- Reviewers: none
- Risk: Display rounding must not diverge from the net_to_arrange arithmetic.

#### I18N-3 - Extract strings from the existing templates and add a string-lint

- What: Replace the hardcoded strings with `t()` keys in base.html, explore.html, compare.html, requirements.html, timeline_calculator.html, _trust_badge.html and the two pages.py messages (lines 39 and 278). Swap the two `{:,.0f}` sites, the raw verification_date and the '{{ total_weeks }} weeks' output to filters. Set `<html lang="{{ lang }}">`. Pass the JS counter string through data attributes. Add the template string-lint test.
- Acceptance: With lang=en the rendered English is unchanged. tests/db/test_web_pages.py, tests/unit/test_web_timeline_page.py and the e2e smoke test pass unmodified. The lint test fails on any bare alphabetic text node in student templates (allowlist: the brand name, and the reviewer_* templates exempt).
- Wave: 3 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: I18N-1, I18N-2, UI-1
- Touches: app/web/templates/base.html; app/web/templates/explore.html; app/web/templates/compare.html; app/web/templates/requirements.html; app/web/templates/timeline_calculator.html; app/web/templates/_trust_badge.html; app/web/pages.py; app/i18n/en.json; app/i18n/hi.json; tests/unit/test_template_strings.py
- Reviewers: ux-qa-reviewer
- Risk: Merge conflicts with parallel UI work. Trust-label wording is a Step 15 gate item and must not drift during extraction.

#### I18N-4 - Language switch visible on first visit, with a prod flag

- What: Add a header control in base.html, 'English | हिन्दी', as plain links to `GET /lang?set=hi&next=<relative path>`. It sets the `lang` cookie and redirects, with zero JS and 44 px targets. Add the settings flag HINDI_UI_ENABLED in app/core/config.py: true on dev/staging, false in prod until I18N-11 sign-off. When it is off the switch is hidden and the resolver forces en.
- Acceptance: Tests show the switch re-renders the same page in hi. `next` values that are absolute, `//host` or backslash forms are rejected. An invalid lang is ignored. The flag when off hides the switch and ignores the cookie. The cookie is samesite=lax, and secure outside dev.
- Wave: 4 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: I18N-3
- Touches: app/web/pages.py; app/web/templates/base.html; app/core/config.py; app/i18n/en.json; tests/unit/test_lang_switch.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: Open redirect through `next`.

#### I18N-5 - Draft the Hindi catalogue (machine draft, labelled unreviewed)

- What: Fill hi.json for all keys with plain Class-8-readable Hindi. Keep exam and institution names and everyday loanwords (fees, course, scholarship) as they are. Add a meta key 'draft - not human reviewed'. Write scripts/export_i18n_review.py to produce a review CSV with key, en, hi, context and a critical flag.
- Acceptance: All keys in hi.json are non-empty. A placeholder parity test passes. A banned-phrase test (guarantee, suitability, rank claims, in both scripts) passes. The CSV is generated in docs/content-drafts/.
- Wave: 4 · Step: 7 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: I18N-3
- Touches: app/i18n/hi.json; scripts/export_i18n_review.py; docs/content-drafts/hindi-ui-review.csv; tests/unit/test_i18n.py
- Reviewers: human
- Risk: Over-formal Sanskritised Hindi hurts comprehension of verified-vs-estimated. The standard tier is used, not cheap, to cut the human correction hours.

#### I18N-6 - Name the Hindi reviewer and fix the critical-key list

- What: The owner names one fluent Hindi reader, a teacher or the second content reviewer. The owner confirms the critical list: trust labels, cost-category labels, the three eligibility outcomes and criterion messages, consent/safeguarding copy, difficult-state and error messages, the AI-unavailable and not-verified messages, and the closing prompt. Do this in week 1.
- Acceptance: The reviewer's role and the critical-key list are recorded in docs/DECISIONS.md with no personal contact details in the repo. No student data is shared with the reviewer.
- Wave: 0 · Step: 7 · Needed by: ten-user-trial · Executor: owner · Model tier: none · Dev sessions: 0 · Human hours: 1
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: none
- Risk: Without a named person the 'Built means' Hindi criterion cannot be met, and prod Hindi stays switched off.

#### I18N-7 - Hindi label columns for careers/pathways, with fallback

- What: Migration: add nullable name_hi and description_hi to careers and pathways; the existing RLS covers them. app/api/explore.py and the pages.py Explore/Compare/Requirements queries select them. A helper picks `_hi` when lang=hi and the value is non-null, and otherwise English. No editor exists, so values load through the content import/seed path. State the rule that `_hi` columns hold labels only and never facts.
- Acceptance: The migration applies on a fresh DB. `make test-db` is green, RLS suite included. lang=hi shows name_hi when present and falls back when null. A student or guest cannot write `_hi` columns. API responses are unchanged for lang=en.
- Wave: 4 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.25
- Depends on: I18N-3
- Touches: db/migrations/00NN_hindi_labels.sql (0004 if first in queue); app/api/explore.py; app/web/pages.py; app/data/models.py; tests/db/test_hindi_content.py
- Reviewers: data-security-reviewer
- Risk: `_hi` labels bypass maker-checker, which is safe only for names and descriptions.

#### I18N-8 - Search schema: FTS column, trigram index, synonym table

- What: Migration: enable pg_trgm in the Supabase `extensions` schema. Add a generated search_tsv column ('simple' config) over name, description, name_hi and description_hi on careers and pathways, with GIN indexes. Add a search_synonyms(term, canonical, script) table that everyone can select and only reviewers can write. Add `search_catalogue(q text)` as SECURITY INVOKER with a fixed search_path and execute granted to anon and authenticated.
- Acceptance: The fresh-migration test passes. Guest, student and reviewer can all execute search_catalogue, and the rows returned equal what the careers/pathways select policies expose. A student cannot write synonyms. A test asserts the function is not SECURITY DEFINER. `make test-db` is green.
- Wave: 5 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.25
- Depends on: I18N-7
- Touches: db/migrations/00NN_search.sql; tests/db/test_search_rls.py
- Reviewers: data-security-reviewer
- Risk: A SECURITY DEFINER shortcut would bypass RLS on future status-bearing tables. 'simple' config means no stemming, so synonyms and trigram similarity must carry recall.

#### I18N-9 - Search route, Explore search box and no-result state

- What: Add `GET /search?q=` (JSON) and a `q` parameter on /explore. Normalise the query (NFC, lowercase, trim, cap at 80 characters), expand tokens through search_synonyms, then call search_catalogue via rpc. It accepts Devanagari, Roman-script Hindi and English. The no-match state shows broader suggestions and a full-list link. It is a zero-JS GET form, and all strings go through `t()`.
- Acceptance: 'doctor', 'daktar' and 'डॉक्टर' return the same synthetic career. Empty and oversized q are handled. SQL-meta characters are harmless. The no-match state renders in both locales. The raw q is not written to logs.
- Wave: 6 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: I18N-8, I18N-3
- Touches: app/api/search.py; app/main.py (router include); app/web/pages.py; app/web/templates/explore.html; app/i18n/en.json; app/i18n/hi.json; tests/db/test_api_search.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: Free-text queries from minors may contain personal text and must stay out of logs.

#### I18N-10 - Seed and review the synonym list

- What: A dev agent drafts 150-300 rows covering the career families, major exams and study-abroad terms: Hindi, common Hinglish spellings (daktar, vakil/wakeel, injiniyar), abbreviations (CA, MBBS, IAS) and frequent misspellings. The Hindi reviewer prunes wrong mappings. An idempotent seed script loads them as the reviewer role. Synonyms map vocabulary only.
- Acceptance: The seed CSV is committed and re-running the script makes no changes. Reviewer sign-off is noted in DECISIONS.md. A 20-query bilingual test set (at least 8 Roman-script Hindi) finds the expected career in the top 3 for at least 18 of 20.
- Wave: 6 · Step: 12 · Needed by: ten-user-trial · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 2
- Depends on: I18N-8, I18N-6
- Touches: db/seeds/search_synonyms.csv; scripts/seed_synonyms.py; tests/db/test_search_queries.py
- Reviewers: human
- Risk: A wrong mapping misleads silently, so the list needs human pruning.

#### I18N-11 - Human Hindi review of critical keys and labels

- What: The named reviewer works through the review CSV with critical keys first: trust labels, eligibility outcomes and messages, cost labels, consent/safeguarding copy, difficult states and AI fallbacks. They then cover the remaining UI keys and name_hi/description_hi for the pilot careers and pathways. A dev agent applies the corrections, sets the catalogue meta to 'reviewed <date> by <role>', and the owner may then set HINDI_UI_ENABLED in prod.
- Acceptance: Every critical key is marked reviewed, with date and role, in the CSV. hi.json is updated and the parity test passes. There is a DECISIONS.md entry. Unreviewed non-critical keys are listed in docs/KNOWN_ISSUES.md with an owner. The prod flag is flipped only after this.
- Wave: 5 · Step: 12 · Needed by: ten-user-trial · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 4
- Depends on: I18N-5, I18N-6, I18N-7, I18N-15
- Touches: app/i18n/hi.json; docs/content-drafts/hindi-ui-review.csv; docs/DECISIONS.md; docs/KNOWN_ISSUES.md
- Reviewers: human
- Risk: Reviewer availability is the critical path for Hindi in prod. English-only prod remains a valid fallback for the first ten users if it slips.

#### I18N-12 - Hindi expansion and font-stack pass, with a Hindi e2e

- What: Extend the Tailwind font-sans stack with Noto Sans, Noto Sans Devanagari and system fallbacks, with no download. Add a `:lang(hi)` line-height bump in input.css. Add a Playwright run of explore -> compare -> requirements -> timeline with the lang cookie set to hi, at 360x740 plus one 200% zoom check. It asserts no horizontal scroll, no clipped badges or buttons, and html lang='hi'. Fix any overflow found.
- Acceptance: `make test-e2e` passes the Hindi journey locally with scrollWidth <= innerWidth on every screen. Screenshots are attached to the task card. The ux-qa-reviewer finds no truncated Hindi label.
- Wave: 7 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: I18N-4, I18N-5, A11Y-6
- Touches: app/web/styles/input.css; tailwind.config.js (fontFamily.sans); tests/e2e/test_hindi_journey.py; app/web/templates/* (overflow fixes only)
- Reviewers: ux-qa-reviewer
- Risk: Low-end Android may lack a good Devanagari system font, and matra clipping can occur at tight line-heights.

#### I18N-13 - New-screen key compliance sweep

- What: After other areas land quick start, My Plan, programme detail, consent, Ask BCION and the difficult states, run the string-lint across all student templates. Extract any stragglers, add the missing Hindi drafts, and regenerate the review CSV delta listing keys added since the I18N-11 sign-off.
- Acceptance: The lint covers every student template and passes. The hi.json parity test passes. The delta CSV lists only keys added since the last review.
- Wave: 11 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: I18N-3, I18N-5, UI-3, UI-4, UI-5, UI-11, UI-13, AUTH-3, AUTH-14, AI-7, OPS-6, A11Y-3, SCOPE-6, SCOPE-7
- Touches: app/web/templates/*; app/i18n/en.json; app/i18n/hi.json; docs/content-drafts/hindi-ui-review.csv
- Reviewers: ux-qa-reviewer
- Risk: This grows if other areas ignore the I18N-1 contract. The lint in test-unit keeps it near zero.

#### I18N-14 - Reviewer console body translation and Gujarati strings (deferred)

- What: Translate the reviewer_sign_in and reviewer_queue body text and add gu.json. No s12 gate needs either. The I18N-1 mechanism accepts a new locale file with one allowlist change.
- Acceptance: Not scheduled. If activated, the gu.json parity test passes and the switch shows a third option.
- Wave: 4 · Step: 12 · Needed by: deferrable · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 4
- Depends on: I18N-3
- Touches: app/i18n/gu.json; app/web/templates/reviewer_queue.html; app/web/templates/reviewer_sign_in.html
- Reviewers: human
- Risk: None if deferred.

#### I18N-15 - Message codes for eligibility and timeline domain text

- What: Add a `code` and `params` to each criterion result in app/rules/eligibility.py. The English `explanation` stays for API compatibility. Give the timeline ValueErrors and the attempt label a code and params too. requirements.html and timeline_calculator.html render `t(code, **params)`, falling back to the English text. Add the en and hi keys. Arithmetic and outcomes do not change.
- Acceptance: The existing eligibility and timeline unit tests pass unmodified. New tests show every criterion branch emits a code that exists in en.json and hi.json. At lang=hi the requirements and timeline pages show no English criterion sentence for coded messages.
- Wave: 4 · Step: 7 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: I18N-3
- Touches: app/rules/eligibility.py; app/rules/timeline.py; app/web/pages.py; app/web/templates/requirements.html; app/web/templates/timeline_calculator.html; app/i18n/en.json; app/i18n/hi.json; tests/unit/test_eligibility.py; tests/unit/test_timeline.py; tests/unit/test_message_codes.py
- Reviewers: ux-qa-reviewer
- Risk: New criteria added by other areas without codes fall back to English silently, so the code-coverage test must enumerate the builders.

#### I18N-16 - Delta Hindi review for late keys

- What: The reviewer checks the I18N-13 delta CSV, critical keys first, covering consent, Ask BCION and My Plan copy that landed after the main review. A dev agent applies the corrections and updates the catalogue meta date.
- Acceptance: No critical key in hi.json lacks a reviewed mark in the CSV. DECISIONS.md is updated. The KNOWN_ISSUES list of unreviewed non-critical keys is current.
- Wave: 12 · Step: 12 · Needed by: ten-user-trial · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 1.5
- Depends on: I18N-11, I18N-13
- Touches: app/i18n/hi.json; docs/content-drafts/hindi-ui-review.csv; docs/DECISIONS.md; docs/KNOWN_ISSUES.md
- Reviewers: human
- Risk: Copy changes after this pass reopen it, so enforce the freeze.

## Accessibility, difficult states and public-only PWA caching

Area: `a11y-states-pwa`

The audit was mostly accurate. Every page is server-rendered and the journey works with zero JS. Badges and alerts pair a glyph with text, reduced motion is global, and touch targets are 44 px. A six-test Playwright smoke suite exists, but CI does not run it. Nothing has been rendered at 360 px or 200% zoom, run through axe, or checked by keyboard or screen reader. base.html has no skip link or nav label. No template uses role=alert, aria-live or aria-describedby. app/main.py has no exception handlers or middleware, so 404/500 return raw JSON and nothing sets Cache-Control. /explore has no DB-down fallback. Students have no sign-out; reviewers do. app/static holds only css/app.css, so no service worker exists. I recommend shipping none.

### Already done

- Global prefers-reduced-motion override (animation, transition, scroll-behavior) - app/web/styles/input.css lines 8-15 (confirmed)
- Meaning is never by colour alone. Trust badges, eligibility badges, reviewer status badges and alerts each carry an aria-hidden glyph in markup plus text. - app/web/templates/_trust_badge.html; reviewer_queue.html lines 15-16, 49, 53; explore.html lines 10-13; input.css .trust-badge/.eligibility-badge/.status-badge/.alert (confirmed)
- Touch targets of 44 px or more on buttons, inputs and checkbox rows - input.css .btn-primary/.btn-secondary py-2.5, .input py-2.5, .field-input py-3; explore.html line 35 min-h-11; timeline_calculator.html line 87 min-h-11 (confirmed by class, not rendered)
- Form fields have explicit label for/id (student and reviewer forms); html lang=en; viewport meta; sr-only note on new-tab links; reviewer action buttons have descriptive aria-labels - requirements.html lines 32-60; reviewer_sign_in.html (labels + autocomplete); reviewer_queue.html lines 90-105; base.html lines 2,5; _trust_badge.html line 44
- Compare grid stacks on mobile (grid-cols-1, md:grid-cols-2/3); reviewer queue is stacked cards, not a table. Confirmed by class only, never rendered. - compare.html line 22; reviewer_queue.html lines 27-30; tasks/BCI-006.md lines 142,156
- Core journey works with zero JS. The only script is an inline progressive-enhancement selection cap in explore.html. No external font or script requests. - explore.html lines 73-95; base.html lines 7-9; app/static contains only css/app.css
- Partial difficult states. Empty states exist. Malformed, duplicate or wrong-count pathway ids get a friendly alert. DB-unconfigured degrades on compare and requirements ONLY. Unparsable numbers are treated as not provided. Timeline overlap errors are shown in-page. Reviewer action failures show alert--error. - app/web/pages.py lines 39-69, 164-188, 257-287, 414-427; explore.html lines 9-13, 20-21; reviewer_queue.html lines 15-23
- Reviewer console has a POST sign-out that deletes the path-scoped cookie - app/web/reviewer_pages.py lines 62-67, 126, 199-200; reviewer_queue.html line 9
- Neutral-token contrast fixed after measuring ~4.4:1 - tasks/BCI-006.md line 122; STATUS.md line 51
- Playwright-for-Python smoke suite (6 tests, live uvicorn fixture) exists and is installed via pyproject. It sets no viewport and has no axe check. It skips without Supabase env and is NOT run in CI. - tests/e2e/conftest.py; tests/e2e/test_smoke.py lines 124-297; pyproject.toml line 22; .github/workflows/ci.yml lines 46-48 (commented out); Makefile lines 25-26
- No service worker, manifest, localStorage/sessionStorage or Cache API usage anywhere in app/, templates and static included - Grep over app/ (excluding compiled app.css) returned no matches for serviceWorker, manifest, localStorage, sessionStorage or Cache-Control; app/static contains only css/app.css

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No rendered verification at 360 px, 320 px reflow, desktop or 200% zoom. Horizontal scroll is unchecked and header nav wrapping is untested. | Build pack s7 Quality gates (UI); Step 12; tasks/BCI-006.md line 156 | phase1-required |
| No automated axe check. The existing e2e job is commented out in ci.yml, so any a11y suite would not run in CI until test-qa-infra enables it. | Step 12; .github/workflows/ci.yml lines 46-48 | phase1-required |
| base.html has no skip link, no main id and no nav aria-label. No template has role=alert or role=status. Explore's #selection-count is updated by JS without aria-live. Disabled checkboxes beyond 3 give no explanation. Focus visibility on plain links is unverified. | Build pack s7 Quality gates: keyboard order, screen-reader spot tests | phase1-required |
| Field hints and errors are not linked to inputs (no aria-describedby or aria-invalid) on requirements, timeline and reviewer sign-in. Reviewer alerts lack role too. The previous audit listed this gap with no task; it is now A11Y-14. | Build pack s7 Quality gates: screen-reader spot tests, every error state | phase1-nice |
| No global styled 404/403/500 HTML pages. app/main.py registers no exception handlers. /explore uses get_db_client directly, so DB-unconfigured yields a raw 500. Any PostgREST runtime error on compare or requirements is also unhandled. | Build pack s5 Difficult states; s5 Design deliverables; s7 'every error state' | phase1-required |
| No student-facing permission-denied state | Build pack s5 Difficult states: Permission denied | phase1-required |
| No save-failed component or contract. No My Plan UI exists to host it, and the Step 15 gate is 'no repeated unexplained save failure'. | Build pack s5 Save failed; s12 Step 15 gates | phase1-required |
| No AI-unavailable or budget-exhausted state | Build pack s5 AI unavailable; s12 'application works with AI disabled' | phase1-required |
| Weak connection: no connection status, no slow-submit indication, no page-weight budget test | Build pack s5 Weak connection | phase1-required |
| Shared device: no student sign-out or signed-in indicator, because no student browser session exists at all (students are API bearer-token only). No Cache-Control on any HTML, reviewer pages included, so the back button or bfcache can re-show the reviewer queue after sign-out. /requirements/view carries age, marks and domicile in the URL. | Build pack s5 Shared device; s6 Guest sessions; s7 Privacy 'logout and cache behaviour'; s12 Step 15 task 'log out safely on a shared device' | launch-blocker |
| No public-only caching policy defined or tested. No recorded decision on whether a service worker ships. | Step 12 'public-only PWA caching'; s5 'Public content cached selectively' | phase1-required |
| Offline deadline with last-checked date plus online confirmation. Only relevant if a service worker ships. | Build pack s5 Difficult states, last sentence | defer |
| Information-changed state is only a per-field 'Needs rechecking' badge. There is no page-level what-changed or affected-plans banner. | Build pack s5 Information changed; docs/UI.md 'What changed surface' | phase1-required |
| No-matching-result state is not designed (search does not exist yet). The copy contract goes in A11Y-1; implementation belongs to the search area. | Build pack s5 No matching result | phase1-nice |
| No human screen-reader, keyboard or real-phone walkthrough has been performed | Build pack s7 Quality gates; s12 'Built means: mobile and accessibility checks done' | phase1-required |
| Hindi text expansion unchecked. html lang is hard-coded to 'en' in base.html. | Build pack s7 Quality gates: Hindi text expansion | phase1-required |
| Inline <script> in explore.html will break under a strict CSP (script-src 'self') if the security area adds one. It must move to app/static/js and be covered by the no-client-persistence guard. | Build pack s5 Weak connection (JS optional); SECURITY hardening | phase1-nice |
| Guest-session-expired and session-timeout state (7-day guest expiry, reviewer cookie expiry mid-action) has no designed message | Build pack s5 'guest session expires'; s6 Guest sessions | phase1-nice |

### Owner decisions

- OD-1: Ship a service worker or installable PWA in the pilot, or satisfy 'public-only caching' with HTTP Cache-Control alone? - blocks: A11Y-1 (records it), A11Y-5, A11Y-13 - recommended default: No service worker in Phase 1. Use HTTP cache headers only (A11Y-4), with a guard test (A11Y-5). The build pack allows server-rendered templates. No section-12 gate needs offline.
- OD-2: Who performs the human screen-reader and real-phone spot check? - blocks: A11Y-11 - recommended default: The owner, using their own Android phone with TalkBack and NVDA on the Windows PC, following the agent-written checklist (about 3 h), combined with usability round 2's shared-phone participant.
- OD-3: axe failure threshold - blocks: A11Y-6 - recommended default: Fail on serious and critical. Log moderate and minor to KNOWN_ISSUES without failing the build.
- OD-4: Public cache lifetime for anonymous catalogue pages - blocks: A11Y-1, A11Y-4 - recommended default: Cache-Control: public, max-age=60, must-revalidate, with no CDN. Everything else is no-store. Corrections become visible within a minute with no purge mechanism.
- OD-5: Approve English difficult-state copy before Hindi translation - blocks: A11Y-1 sign-off; i18n area - recommended default: Use build-pack sentences verbatim where they are given. The agent drafts the rest, and the owner approves in one 30-minute review.
- OD-6: /requirements/view keeps age, marks and domicile in GET query strings (shareable, but persists in shared-device history). Accept this, or switch to POST? - blocks: A11Y-4 route classification; privacy/security area - recommended default: Switch the personal-input submit to POST (as the timeline form already does) and keep only pathway_id in the URL. Until the owner area does that, mark the route no-store. It is a small change.

### Tasks

#### A11Y-1 - Freeze difficult-states and cache-class contract

- What: Docs only. Extend the docs/UI.md 'Difficult states' table. For the 8 states plus loading, empty, stale, session-expired, 404, 403 and 500, give exact English copy (build-pack sentences verbatim), alert variant, ARIA role, HTTP status, partial or macro name, and a string key for i18n. Add the Cache-Control classes (static, public-anonymous, no-store) to docs/SECURITY.md. Record the OD-1 no-service-worker decision and OD-4 in DECISIONS.md.
- Acceptance: UI.md table covers all 15 states with copy, role, status, macro name and i18n key. SECURITY.md has the cache-class table per route family. One DECISIONS.md entry covers OD-1 and OD-4. No code changed. Owner approval recorded.
- Wave: 1 · Step: 12 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: DESIGN-2
- Touches: docs/UI.md; docs/SECURITY.md; docs/DECISIONS.md; tasks/BCI-0xx.md (next free card number, assigned by lead)
- Reviewers: ux-qa-reviewer, human
- Risk: Copy drift for Hindi. Keep strings short and keyed.

#### A11Y-2 - State macros + base.html landmarks (student templates)

- What: Create app/web/templates/_states.html macros per the A11Y-1 contract: alert with role=alert/status, empty, changed banner, save-failed, ai-unavailable, permission-denied, session-expired. In base.html add a skip link, main id=main, nav aria-label and focus-visible link style. Move the explore inline script to app/static/js/explore-select.js and add aria-live=polite to #selection-count. Replace inline alerts in the 4 student templates.
- Acceptance: Skip link is the first focusable element. Error alerts carry role=alert and info alerts role=status. explore.html has no inline script. TestClient tests assert these. make css is re-run. tests/db/test_web_pages.py and tests/unit/test_web_timeline_page.py pass, run in-session.
- Wave: 3 · Step: 12 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-1, UI-1
- Touches: app/web/templates/_states.html; app/web/templates/base.html; app/web/templates/explore.html; app/web/templates/compare.html; app/web/templates/requirements.html; app/web/templates/timeline_calculator.html; app/static/js/explore-select.js; app/web/styles/input.css; app/static/css/app.css; tests/db/test_web_pages.py; tests/unit/test_web_timeline_page.py
- Reviewers: ux-qa-reviewer
- Risk: Merge conflicts on base.html and the compiled app.css.

#### A11Y-3 - Global HTML error pages (404/403/500) + explore DB-down fallback

- What: Add app/web/errors.py with exception handlers, registered in create_app. They render error.html for non-API browser requests (path in the HTML route set and Accept text/html) and leave JSON API error shapes untouched. Switch /explore to _db_client_or_none with the same degraded alert. 403 copy explains the boundary and never echoes ids. Error pages are no-store.
- Acceptance: An unknown URL, a forced 500 and a 403 each return a styled page with the correct status and a link to /explore. No stack trace or id appears in the body. Existing API tests are unchanged and pass. /explore with Supabase unconfigured returns 200 with the alert. New tests cover each case.
- Wave: 4 · Step: 12 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-2, A11Y-4, UI-2
- Touches: app/main.py; app/web/errors.py; app/web/templates/error.html; app/web/pages.py; tests/unit/test_error_pages.py; tests/db/test_web_pages.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: The handler could alter API JSON contracts. Guard it by route prefix list, not by Accept alone.

#### A11Y-4 - Cache-Control middleware and shared-device hygiene

- What: New app/web/cache_policy.py middleware, no-store by default. Public short max-age applies only to anonymous GETs on an allow-list (/explore, /compare/view, /timeline/view GET) with no Cookie or Authorization header. /static gets a long max-age. /reviewer/*, /auth, /plans, /requirements/view with personal params and all POST responses get no-store. Reviewer sign-out adds Clear-Site-Data: "cache". Add an e2e test that Back after reviewer sign-out does not show the queue.
- Acceptance: Unit tests assert the header class for every route family, for guest and reviewer. Authenticated or cookie-bearing HTML is always no-store. e2e back-button test passes. tests/db/test_reviewer_console.py and the cross-user tests are re-run in-session and pass.
- Wave: 2 · Step: 12 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-1
- Touches: app/web/cache_policy.py; app/main.py; app/web/reviewer_pages.py; tests/unit/test_cache_policy.py; tests/e2e/test_shared_device.py
- Reviewers: data-security-reviewer
- Risk: A missed route could be cached publicly. Mitigated by default no-store plus an explicit allow-list.

#### A11Y-5 - Guard test: no service worker or client-side persistence

- What: Add a unit test that scans app/web/templates and app/static (excluding the compiled css) and fails on serviceWorker, sw.js, caches., localStorage, sessionStorage or indexedDB. It implements the OD-1 default already recorded by A11Y-1.
- Acceptance: The test runs in make test-unit and passes on the current tree. It fails when a planted temp fixture string is scanned (proven with tmp_path, not by editing templates).
- Wave: 2 · Step: 12 · Needed by: real-users-gate · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-1
- Touches: tests/unit/test_no_client_persistence.py
- Reviewers: data-security-reviewer
- Risk: Low.

#### A11Y-6 - Viewport, zoom and axe matrix in Playwright

- What: Add tests/e2e/test_a11y.py, parametrised over a page list (tests/e2e/pages.py) covering student and reviewer pages plus error and empty variants. Run at 360x740, 320x640, 1280x800 and 640 px wide at DPR 2 (the 200% proxy). Assert scrollWidth <= clientWidth. Run a vendored axe.min.js via page.evaluate (CSP-proof) and fail on serious or critical. Add one reduced-motion emulation check. Session 2 fixes the findings.
- Acceptance: make test-e2e runs the matrix against a live project, with zero serious or critical axe violations and no horizontal overflow. axe lives under tests/e2e/vendor only. STATUS.md records exactly what ran and the e2e correction.
- Wave: 6 · Step: 12 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: A11Y-2, QA-7, UI-1
- Touches: tests/e2e/test_a11y.py; tests/e2e/pages.py; tests/e2e/vendor/axe.min.js; app/web/styles/input.css; app/static/css/app.css; STATUS.md
- Reviewers: ux-qa-reviewer
- Risk: The suite skips silently without Supabase env. A skip must never be reported as a pass.

#### A11Y-7 - Keyboard-order and focus e2e

- What: Add a Playwright test that tabs through Explore -> Compare -> Requirements -> Timeline and through reviewer sign-in -> queue. The skip link comes first, the order follows the DOM, and every focused element shows a visible indicator (coarse check: outline or box-shadow is not none). There must be no trap, and the journey must be completable with Tab, Space and Enter. Fix link focus styles if missing.
- Acceptance: Test passes in make test-e2e, run in-session. Focus indicator is present on links, buttons, inputs and checkboxes. The selection-limit message is exposed via the aria-live region.
- Wave: 4 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-2
- Touches: tests/e2e/test_keyboard.py; app/web/styles/input.css; app/static/css/app.css
- Reviewers: ux-qa-reviewer
- Risk: Brittle computed-style assertions. Keep them coarse.

#### A11Y-8 - Weak-connection treatment + page-weight budget

- What: Add app/static/js/net-status.js, an external file that makes no network calls. It shows an offline banner with role=status, worded 'You appear to be offline', driven by navigator.onLine and the online/offline events. It marks the submit button as 'Working...' on submit. Include it from base.html with defer. Add a unit test for the page-weight budget: gzip of rendered explore HTML plus app.css under 60 KB.
- Acceptance: With JS off, behaviour is unchanged. A Playwright set_offline toggle shows the banner, and submit shows the pending state. The budget test runs in make test-unit. The A11Y-5 guard still passes.
- Wave: 4 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-2, A11Y-5
- Touches: app/static/js/net-status.js; app/web/templates/base.html; tests/unit/test_page_weight.py; tests/e2e/test_net_status.py
- Reviewers: ux-qa-reviewer
- Risk: navigator.onLine is unreliable, so the copy must hedge.

#### A11Y-9 - Verify difficult states on feature screens (save-failed, 403, AI-unavailable, changed-info, student sign-out)

- What: Feature areas wire their own states from the A11Y-1 contract and the A11Y-2 macros. This task adds the forced-failure tests. Mocked DB error on plan save: draft kept and no 'Saved' string. Mocked provider outage or budget exhaustion: exact build-pack sentence plus links. Student B on student A's plan URL: 403 page with no ids. Changed-info banner on My Plan. Student sign-out then Back shows nothing. Fix the gaps found.
- Acceptance: One test per state passes, run in-session. A grep test proves that no success string appears on failure paths. The shared-device sign-out e2e passes for a student session.
- Wave: 12 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 2 · Human hours: 0
- Depends on: A11Y-2, A11Y-3, A11Y-4, A11Y-6, QA-10, AUTH-14, AI-7
- Touches: tests/db/test_web_states.py; tests/e2e/test_shared_device.py; app/web/templates/_states.html; app/web/pages.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: Blocked if the feature screens slip. It is a verification pass by design, to limit the coupling.

#### A11Y-11 - Human screen-reader, keyboard and real-phone spot check

- What: The agent writes a 15-item checklist with exact TalkBack and NVDA gestures in docs/a11y-spot-check.md (one cheap session). The owner or a tester then walks the core journey on private staging three ways: TalkBack on a low-end Android phone, keyboard-only with NVDA on Windows, and 200% browser zoom. Include shared-device sign-out. Log findings with severities.
- Acceptance: The checklist is completed and committed with no student data. Each blocker or high finding has a task card. Sign-off, with name and date, is recorded in the release checklist.
- Wave: 7 · Step: 12 · Needed by: ten-user-trial · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 3
- Depends on: A11Y-6, A11Y-7, A11Y-8, DEPLOY-7
- Touches: docs/a11y-spot-check.md; docs/KNOWN_ISSUES.md; docs/RELEASE_CHECKLIST.md
- Reviewers: human
- Risk: The owner may be unfamiliar with screen readers. The checklist must give the gestures.

#### A11Y-12 - Fix round from human spot check + final gate run

- What: One bounded session fixing only the blocker and high findings from A11Y-11. Re-run the full a11y e2e matrix and update STATUS.md with exactly which checks ran.
- Acceptance: All A11Y-11 blocker and high items are closed, or carry an owner-approved exception with a named owner and expiry. make test-e2e is green, run in that session. STATUS.md is updated.
- Wave: 8 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: A11Y-11
- Touches: app/web/templates/ (only files named in A11Y-11 findings); app/web/styles/input.css; app/static/css/app.css; STATUS.md
- Reviewers: ux-qa-reviewer
- Risk: Scope creep. Cap it at blocker and high items.

#### A11Y-13 - Offline service-worker cache of public catalogue (optional)

- What: Do this only if the pilot shows real offline need and the owner reverses OD-1. The service worker caches only anonymous catalogue pages and static assets. Offline deadlines show a last-checked date and require online confirmation before consequential action. The A11Y-5 guard is relaxed to an allow-list.
- Acceptance: The service-worker scope excludes every authenticated path. A test proves that no response to a request with Cookie or Authorization enters Cache Storage. Offline deadline pages show the last-checked date.
- Wave: 3 · Step: 12 · Needed by: deferrable · Executor: dev-agent · Model tier: strongest · Dev sessions: 2 · Human hours: 0
- Depends on: A11Y-4, A11Y-5
- Touches: app/static/sw.js; app/web/templates/base.html; tests/e2e/test_sw_cache.py; tests/unit/test_no_client_persistence.py; docs/DECISIONS.md
- Reviewers: data-security-reviewer
- Risk: Stale verified facts served offline would conflict with the trust model.

#### A11Y-14 - Reviewer templates + form hint/error association

- What: Apply the _states.html macros to reviewer_queue.html and reviewer_sign_in.html, with role=alert on errors. Add aria-describedby linking the field hints on requirements.html and timeline_calculator.html. Add aria-invalid plus describedby for reviewer sign-in and timeline errors where a field is identifiable. Switch the reviewer sign-in labels to .field-label for consistency.
- Acceptance: TestClient tests assert that describedby ids resolve to existing elements and that reviewer alerts carry roles. tests/db/test_reviewer_console.py and test_web_pages.py pass, run in-session. No CSS changes are needed beyond existing classes.
- Wave: 4 · Step: 12 · Needed by: ten-user-trial · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: A11Y-2
- Touches: app/web/templates/reviewer_queue.html; app/web/templates/reviewer_sign_in.html; app/web/templates/requirements.html; app/web/templates/timeline_calculator.html; tests/db/test_reviewer_console.py; tests/db/test_web_pages.py
- Reviewers: ux-qa-reviewer
- Risk: Low. Conflicts are possible with the reviewer-console feature work.

### Merged into other tasks

- A11Y-10 -> I18N-12

## Design deliverables and materials for parents, teachers and support staff

Area: `design-ux-deliverables`

The audit is mostly right. Tokens, badges, buttons, alerts, inputs and four Jinja macros exist. There is no frozen contract, copy-rules file, journeys, test script, usability round or stakeholder materials. Main corrections: Playwright e2e already exists (tests/e2e/test_smoke.py), so the never-done 360px and 200%-zoom check becomes a new task, DESIGN-17. DESIGN-4 was oversized and is split, adding DESIGN-18. DESIGN-1 and DESIGN-2 both edited docs/UI.md and could not run concurrently; DESIGN-2 now writes only docs/COPY.md. The banned-phrase lint must strip Jinja comments, because two templates contain "guarantee" in comments. The gallery gate setting is settings.app_env. Before parallel screen work: DESIGN-1, 2, 3, 4. Everything else can trail.

### Already done

- Design tokens: warm-white, charcoal, accent and AA-adjusted neutral colours. Noto plus system-ui font stack with no web-font download. Tailwind content glob is ./app/web/templates/**/*.html, so new template files are picked up. - F:\the competetion project\tailwind.config.js (lines 10-54)
- Component classes: .trust-badge with 5 variants, .eligibility-badge, .card, .status-badge, .btn-primary, .btn-secondary, .alert (caution/neutral/error), .field-label, .field-input, .field-hint and a global prefers-reduced-motion rule. The legacy .input class is also present. - F:\the competetion project\app\web\styles\input.css (lines 8, 30-161). The .input class is used only in reviewer_sign_in.html lines 25 and 36. .field-input is used 9 times in requirements.html and timeline_calculator.html.
- Shared macros trust_badge, evidence_line, eligibility_outcome_badge and field_value. Each uses icon plus text, never colour alone. A value with label not_available is never rendered. There is no applicable-cycle parameter and no report-issue slot. - F:\the competetion project\app\web\templates\_trust_badge.html
- Base layout: header with a brand link to /explore and a single 'Timeline calculator' link, footer with the synthetic-data disclaimer, one compiled stylesheet. No four-destination nav, no utility menu, no guest 'not saved to an account' indicator and no sign-out. - F:\the competetion project\app\web\templates\base.html
- UI spec covering trust labels, comparison field order, the difficult-states table, stakeholder views, the component list, usability rounds and six task criteria. Its heading says the component set was 'frozen at Step 7 / M2', which is not true. - F:\the competetion project\docs\UI.md (line 88 heading; lines 94-102 rounds)
- Copy rules exist only as a short use/never list in a product doc. A grep of app/ found no banned phrases in rendered template text. The word 'guarantee' appears in Jinja comments in two templates and in an AI-module docstring. - F:\the competetion project\docs\PRODUCT.md lines 18-21; app\web\templates\explore.html line 29; app\web\templates\_trust_badge.html line 77; app\ai\grounding.py
- Student page templates explore, compare, requirements and timeline_calculator exist, plus reviewer_sign_in and reviewer_queue. Page routes are /, /explore, /compare/view, /requirements/view and /timeline/view (GET and POST). - F:\the competetion project\app\web\pages.py lines 72-369; Glob of app/web/templates/*.html
- Playwright e2e smoke tests exist: a live_server fixture and an explore-to-compare real-browser test. Requirements and Timeline tests were un-skipped in commit 2db356e. The audit and STATUS.md 'Not claimed' section missed this. No viewport or zoom assertions exist yet. - F:\the competetion project\tests\e2e\test_smoke.py; tests\e2e\conftest.py; git log 2db356e
- A design mockup artifact is reported: seven phone screens, desktop compare, reviewer console and a difficult-states sheet, under a 'not verified facts' ribbon. No person has reviewed it and it is not frozen. I did not open it because network access is forbidden in this run. - F:\the competetion project\STATUS.md lines 226-237
- ux-qa-reviewer and data-security-reviewer agents are defined. ux-qa-reviewer has already found real UI defects, all fixed. - F:\the competetion project\.claude\agents\ux-qa-reviewer.md; .claude\agents\data-security-reviewer.md; STATUS.md lines 34-54; tasks\BCI-006.md lines 120-147

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| The component set is not frozen. UI.md line 88 claims it was, but STATUS.md says the mockup is 'not a frozen component set'. No inventory maps each component to a class or macro. Two input styles coexist: .input (reviewer_sign_in.html only) and .field-input. | Build pack s5 Design deliverables; s7 Contracts before parallel work; docs/UI.md Component set | launch-blocker |
| Several components are missing: reminder opt-in, 'what changed' list, comparison section as a reusable macro, career card (four questions plus reality check), a 'why am I seeing this' block, and the contextual 'Ask BCION' canned-prompt entry point (in the UI.md component set; the first audit missed it). The source label lacks 'applicable cycle' and 'Report an issue'. | Build pack s5 Trust labels, Career card, Design deliverables; docs/UI.md Component set; tasks/BCI-006.md line 134 | phase1-required |
| The navigation shell does not match the spec. There are no Explore / Compare / My Plan / Saved destinations, no utility menu (account, language, privacy, help, what changed), no guest 'not saved to an account' indicator and no shared-device sign-out control. My Plan and Saved routes do not exist yet, so the nav must handle unbuilt destinations. | Build pack s5 Navigation, Difficult states (shared device); docs/UI.md Guest sessions | phase1-required |
| Error, loading, empty, stale-data, permission, failed-save, AI-unavailable and weak-connection states have no shared pattern or fixed copy in the repo. | Build pack s5 Difficult states; s7 Contracts before parallel work | launch-blocker |
| There is no copy-rules document and no automated guard against banned phrases. With app/ai now present, canned prompts and AI templates also need the guard. | Build pack s5 Emotional progression; CLAUDE.md non-negotiables | launch-blocker |
| The three end-to-end journeys (undecided, goal-focused, alternative-seeking) and the teacher demonstration journey are not written anywhere. | Build pack s5 Design deliverables; s9 Step 4 design track | phase1-required |
| No low-fidelity flows exist. The mockup and the built screens have superseded them. | Build pack s5 Design deliverables | defer |
| The clickable prototype has not been reviewed by a person. docs/UI.md says round 1 runs on a prototype before the engines are built. The build pack says on staging, guest only. The engines are already built, so the round-1 vehicle is undecided. | Build pack s3 Usability testing; s5 Design deliverables; docs/UI.md Usability rounds | phase1-required |
| There is no moderated test script, scoring sheet or participant/parent information note. | Build pack s5 Design deliverables; s9 Step 15 'Moderator script'; docs/UI.md task criteria | phase1-required |
| Usability round 1 has not been run. It needs 5-8 participants including a shared-phone user, a Hindi-preferring user, a parent and a teacher. | Build pack s9 inserted round 1; tasks/BCI-006.md lines 167-170 | phase1-required |
| There is no student-approved family summary: no content spec, no student controls and no printable form. The mandatory consent-screen sentence (the parent consents to the account, the student controls the summary) is also missing. The sentence is gate-critical because it sits in the consent workflow; the rest is not. | Build pack s5 Other people in Lite; s6 Consent | phase1-nice |
| There is no teacher session guide, demonstration journey, printable prompts or referral route. | Build pack s5 Other people in Lite; s13 school-channel measurement | phase1-nice |
| The support-staff authorised case summary format is not defined. It needs four fields and must never be a model-generated label. | Build pack s5 Other people in Lite; s9 Step 8 support queue | phase1-required |
| No Hindi versions of critical microcopy or stakeholder materials exist. There is no translation-key convention, and templates and macros hard-code English strings, including _trust_badge.html. | Build pack s9 Step 6 translation keys; Step 7 'Hindi copy review begins'; Built-means 'English and Hindi critical content reviewed' | phase1-required |
| A mobile-viewport (360px) and 200%-zoom visual check of components and screens has never been rendered and looked at. Playwright exists, but tests/e2e has no viewport or zoom check. The first audit listed this gap but gave it no task. | Build pack s7 Quality gates UI; Built-means 'mobile and accessibility checks done'; tasks/BCI-006.md lines 156-159 | phase1-required |
| Components assume rupees. field_value(money=true) hard-codes the rupee sign. There is no pattern for foreign-currency costs or visa / another-country requirements after the 2026-09-21 scope widening. | docs/DECISIONS.md 2026-09-21; build pack s5 Timeline and cost | phase1-nice |

### Owner decisions

- Round-1 prototype vehicle: staging app, mockup artifact, or both. docs/UI.md says prototype; the build pack says staging; the engines are already built. - blocks: DESIGN-6, DESIGN-9 - recommended default: Both. Use the staging app for every built guest screen. Use the artifact only for unbuilt screens (quick start, My Plan, Ask BCION, family summary). Where they differ, the built app wins.
- Accept component set freeze v1 now (before round 1), with only additive changes allowed afterwards - blocks: DESIGN-4, DESIGN-18 and all parallel ui-student-screens work - recommended default: Yes. Freeze v1 from what is in input.css and _trust_badge.html plus the named missing items. Round-1 changes become v1.1.
- May real minors take part in round 1? - blocks: DESIGN-8 - recommended default: Only as guests with a parent present and the information sheet handed over. No account, no names, no recording. If that cannot be arranged, use adults and 18+ students.
- Family summary form: student-controlled print/share page, or a parent login - blocks: DESIGN-12, DESIGN-13 - recommended default: An on-demand print/share page controlled by the student. No parent account of any kind in the pilot. Build the page (DESIGN-13) only after the ten-user trial.
- Is a school or teacher channel used for the ten-user trial, or only at expansion? - blocks: neededBy of DESIGN-14 - recommended default: Expansion only. The teacher pack stays at expand-100 and is dropped if expansion also recruits outside schools.
- Named Hindi reviewer and named referral/support contact - blocks: DESIGN-14, DESIGN-15 - recommended default: The second content reviewer (or the owner, if fluent) reviews Hindi. The owner is the referral contact until a staff member is named. The helpline number is verified by the safeguarding area and never drafted by an agent.
- Are foreign-currency and visa-requirement display patterns part of component contract v1? - blocks: DESIGN-1 scope; DESIGN-18 source label and cost display - recommended default: Out of v1. Show foreign costs as the source-currency amount plus an 'Estimate'-labelled rupee conversion using the existing field_value pattern. Add dedicated components only if round 1 shows confusion.

### Tasks

#### DESIGN-1 - Freeze component and state contract v1 in docs/UI.md

- What: Docs-only. Add an inventory table mapping every build-pack component to a class or macro name and file, each marked exists or missing. Rows: cards, source label (with cycle and report slot), inputs, alerts, comparison section, reminder opt-in, what-changed list, career card, why-seeing-this, Ask BCION entry, nav shell. Declare .field-input canonical. Add a state-pattern table. Correct the false 'frozen at Step 7' heading. State whether foreign-currency and visa slots are in v1.
- Acceptance: docs/UI.md has a component table (name, file, status) and a state-pattern table. The heading reads 'frozen v1, <date>'. DECISIONS.md has a dated freeze entry with an additive-only rule. No code changed.
- Wave: 0 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: strongest · Dev sessions: 1 · Human hours: 0.5
- Depends on: none
- Touches: docs/UI.md; docs/DECISIONS.md
- Reviewers: ux-qa-reviewer, human
- Risk: Freezing before round 1 means later change. Mitigate with a v1 tag and additive-only amendments (v1.1 after round 1).

#### DESIGN-2 - Copy rules, fixed microcopy deck and translation-key convention (docs/COPY.md only)

- What: Create docs/COPY.md. Include a banned-pattern list as a machine-readable fenced block of regexes, precise enough not to flag ordinary words, plus approved phrasing. Fix exact English strings and keys for the five trust labels, three eligibility outcomes, every difficult state, the guest-session notice, the closing compare prompt and the 'not verified' answer. Set reading level and tone, and the key scheme screen.component.purpose. Do not edit docs/UI.md.
- Acceptance: COPY.md exists. Every row of the UI.md difficult-states table has one fixed string and key. Existing strings in _trust_badge.html match the deck verbatim. The banned block parses as one regex per line.
- Wave: 0 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: none
- Touches: docs/COPY.md
- Reviewers: ux-qa-reviewer, human
- Risk: Over-broad banned regexes (for example bare 'guarantee') create false positives in the lint. Write patterns as phrases.

#### DESIGN-3 - Banned-phrase lint test over templates and AI prompt text

- What: Add tests/unit/test_copy_rules.py. It loads the banned regex block from docs/COPY.md and strips Jinja comments ({# ... #}) and HTML comments. It fails on any match in app/web/templates/**/*.html, or in any prompt or template string files under app/ai. It must not scan Python docstrings. It runs under the existing make test-unit target, so no Makefile change is needed.
- Acceptance: A banned phrase seeded in a tmp_path template fails the test. Current templates pass, although explore.html and _trust_badge.html contain 'guarantee' inside Jinja comments. It runs in under 2 seconds with no DB.
- Wave: 1 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 0
- Depends on: DESIGN-2
- Touches: tests/unit/test_copy_rules.py
- Reviewers: none
- Risk: A static scan cannot see strings built in Python (pages.py error messages). Add app/web/*.py string literals to the scan, or note the limit.

#### DESIGN-5 - Write the three end-to-end journeys plus the teacher demonstration journey

- What: Create docs/design/journeys.md. Write the undecided, goal-focused and alternative-seeking journeys step by step. Map each step to a real route (/explore, /compare/view, /requirements/view, /timeline/view) or an unbuilt screen (quick start, My Plan, Ask BCION), the component used, the difficult state it can hit and the synthetic fixture needed. Mark one journey as the teacher demonstration journey. It doubles as the Playwright scenario and moderator task source.
- Acceptance: Three journeys exist. Every step names a route, component and copy key. Unbuilt screens are flagged. Personas are fictional and contain no real personal data. At least one journey includes a foreign pathway or marks it out of scope.
- Wave: 0 · Step: 4 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: none
- Touches: docs/design/journeys.md
- Reviewers: human
- Risk: Low. Copy keys referenced before DESIGN-2 lands are reconciled at merge.

#### DESIGN-6 - Owner reviews the mockup artifact and picks the round-1 vehicle

- What: Owner opens the design artifact (link in STATUS.md) on a phone. Walk the seven screens against docs/UI.md, covering trust labels, three cost amounts, no score or label language and the difficult-states sheet. List disagreements and decide the round-1 vehicle. Can start on day 1. Disagreements found before DESIGN-1 merges go into v1; later ones go into v1.1. A later dev session records the note.
- Acceptance: A dated DECISIONS.md note: mockup accepted or amended (with list), and the round-1 vehicle chosen. The STATUS.md design-mockup section no longer says 'not reviewed by a person'.
- Wave: 0 · Step: 7 · Needed by: staging-demo · Executor: owner · Model tier: none · Dev sessions: 0 · Human hours: 1.5
- Depends on: none
- Touches: docs/DECISIONS.md; STATUS.md
- Reviewers: human
- Risk: If the mockup diverges from built screens, participants would test two designs. The note must say which one wins.

#### DESIGN-11 - Support-staff authorised case summary format (spec and copy)

- What: Write docs/design/case-summary.md. Define the four fields (decision faced, options considered, constraints volunteered, unresolved questions), who writes each, the student authorisation wording, the staff-only visibility rule, the permission-denied copy and minimal-data hints on free text. There is no model-generated label, score or AI summarisation. Copy keys live in this file's own section to avoid COPY.md write conflicts.
- Acceptance: The spec lists fields, authors, authorisation wording and visibility. data-security-reviewer confirms no field or hint invites category, income or health data. Strings pass the banned-phrase lint rules.
- Wave: 1 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: DESIGN-2
- Touches: docs/design/case-summary.md
- Reviewers: data-security-reviewer, human
- Risk: Free-text fields can collect sensitive data. Length caps and hints are required in the spec.

#### DESIGN-12 - Family summary spec and the consent-screen sentence

- What: Write docs/design/family-summary.md. It has four sections: options explored, time and cost assumptions with trust labels kept, questions to discuss, and a suggested next conversation. The student ticks what is included. Output is an on-demand print or share page, with no parent account. Include the exact English consent-screen sentence (the parent consents to the account, the student controls the summary) and a draft Hindi version flagged for human review.
- Acceptance: The spec states that there is no parent login, estimates stay labelled, and unawarded assistance is never subtracted. The consent sentence (EN plus draft HI) is delivered to the consent area. Copy keys are listed in the file.
- Wave: 1 · Step: 8 · Needed by: real-users-gate · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0.5
- Depends on: DESIGN-2
- Touches: docs/design/family-summary.md
- Reviewers: data-security-reviewer, human
- Risk: Only the consent sentence is gate-critical. The rest rides along cheaply.

#### DESIGN-14 - Teacher pack: session guide, printable prompts and referral route

- What: Create docs/materials/teacher-pack.md as one printable document. It contains a 40-minute classroom session guide built on the demonstration journey, 8-10 discussion prompts that follow the copy rules, and a referral-route box with an owner-supplied contact. The helpline is left as 'verify at launch' and never invented. No analytics and no student lists.
- Acceptance: The pack prints on 2-3 A4 pages. Prompts pass the banned-phrase patterns. The referral box holds a placeholder or owner-supplied contact. No invented phone numbers.
- Wave: 1 · Step: 15 · Needed by: expand-100 · Executor: dev-agent · Model tier: cheap · Dev sessions: 1 · Human hours: 1
- Depends on: DESIGN-2, DESIGN-5
- Touches: docs/materials/teacher-pack.md
- Reviewers: human
- Risk: It is only needed if a school channel is used. Treat it as deferrable if the ten-user trial and expansion recruit outside schools.

#### DESIGN-15 - Hindi draft and human review of critical microcopy and stakeholder materials

- What: A dev agent drafts Hindi for the COPY.md critical keys (trust labels, eligibility outcomes, difficult states, guest notice, consent sentence), the family-summary headings and the teacher pack. A named human Hindi reviewer corrects meaning, tone and text length, and notes Hinglish or Roman variants where parents are likely to read them. Record the reviewer and date per string group.
- Acceptance: Every critical key has a Hindi value with a reviewer name and date. No critical string ships machine-only. Strings likely to overflow at 360px are flagged to ui-student-screens.
- Wave: 2 · Step: 12 · Needed by: ten-user-trial · Executor: mixed · Model tier: standard · Dev sessions: 1 · Human hours: 3
- Depends on: DESIGN-2, DESIGN-12, I18N-6
- Touches: docs/COPY.md
- Reviewers: human
- Risk: Machine-only translation of the trust labels would breach Built-means 'English and Hindi critical content reviewed'.

#### DESIGN-16 - Round 2 alongside the ten-user trial: script delta and scoring

- What: Mark the round-2 and Step-15 delta in the usability script (signed-in tasks: save a plan, find the next action, shared-device sign-out, out-of-coverage question). After the trial, compute the same per-criterion counts as round 1 from de-identified sheets and write a comparison for the go/no-go inputs.
- Acceptance: Round-2 scoring uses identical criteria. Counts for '8 of 10 complete the journey' and '8 of 10 distinguish estimate from verified' come from sheets, not impressions.
- Wave: 15 · Step: 15 · Needed by: ten-user-trial · Executor: mixed · Model tier: cheap · Dev sessions: 1 · Human hours: 2
- Depends on: TRIAL-2, TRIAL-9, TRIAL-11
- Touches: docs/research/usability-script.md; docs/research/round2-findings.md
- Reviewers: human
- Risk: Low.

#### DESIGN-18 - Content component macros: comparison section, career card, why-seeing-this, what-changed, reminder opt-in, Ask BCION entry, extended source label

- What: Add macros to _components.html: comparison_section, career_card skeleton (four questions plus reality check), why_seeing_this, what_changed_list, reminder_opt_in and ask_bcion_entry (canned prompts only, hidden when AI is off). Extend evidence_line with optional applicable_cycle and report_issue_url parameters, which render nothing when none. Show each in the gallery with synthetic labels. Edit input.css and base.html only as an append.
- Acceptance: The gallery shows every macro at 360px and desktop. Existing callers of evidence_line and field_value are unchanged and their tests pass. No report link renders without a URL. ux-qa-reviewer pass recorded.
- Wave: 3 · Step: 6 · Needed by: staging-demo · Executor: dev-agent · Model tier: standard · Dev sessions: 1 · Human hours: 0
- Depends on: UI-1
- Touches: app/web/templates/_components.html; app/web/templates/_trust_badge.html; app/web/templates/components_gallery.html; app/web/styles/input.css; app/static/css/app.css
- Reviewers: ux-qa-reviewer
- Risk: It can run in parallel with screen sessions that touch only their own page templates. It must not run concurrently with another input.css writer.

### Merged into other tasks

- DESIGN-4 -> UI-1
- DESIGN-7 -> TRIAL-2
- DESIGN-8 -> TRIAL-1
- DESIGN-9 -> TRIAL-8
- DESIGN-10 -> TRIAL-9
- DESIGN-13 -> CONSENT-16
- DESIGN-17 -> A11Y-6
