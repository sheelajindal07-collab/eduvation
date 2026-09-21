# Task inventory - Trust, content and AI

Generated 2026-09-21 by the planning workflow from verified area audits. DRAFT - task cards under tasks/ still need owner approval before work starts.

## Consent gate and safeguarding workflow (launch gate)

Area: `consent-safeguarding`

Audit confirmed in substance: nothing in this area is built. POST /auth/sign-up is a bare Supabase wrapper; no consents/invites/flags tables, no distress rule, no support queue, no student pages. Only protection is localhost-only hosting. Cheapest compliant Phase 1: a one-session sign-up kill switch now (unblocks guest-only staging), then an adult-only invite gate enforced in RLS via security-definer functions (no service-role key in the app), a deterministic distress rule, staff-only queue with a NEW safeguarding-staff role (content reviewers must not see flags), withdrawal freeze, and one non-author human review. Under-18 school-mediated flow, per-purpose consents, re-consent at 18, parent summary and DigiLocker wait. About 8 dev sessions and 8 human hours to the real-users gate.

**Already done**

- Consent and safeguarding requirements documented as a launch gate (verifiable guardian route, per-purpose revocable consent, named staff review, distress rule in Hindi/Hinglish/English, person-not-model sign-off) - Evidence: F:\the competetion project\docs\SECURITY.md lines 20-32 and 71-73 (verified); F:\the competetion project\docs\BCION-Lite-Build-Pack.md lines 13, 40, 44, 84, 108, 149, 166, 214, 220 (verified)
- Missing age/consent gate recorded as CRITICAL and a hard blocker on public exposure; interim invite-only/reviewer-approved gate named as acceptable - Evidence: F:\the competetion project\docs\DECISIONS.md lines 144-159 and 181 in the current working copy (the audit's 125-140/162-163 are stale because the file has uncommitted edits); F:\the competetion project\STATUS.md lines 242-263 and 337-341 (verified)
- Sign-up route docstring states it deliberately enforces no age check; SignUpRequest has only email, password, pending_plan - Evidence: F:\the competetion project\app\api\auth.py lines 5-9 and 61-64 (verified). Also lines 164-173: when Supabase email confirmation is on, sign-up returns 202 with NO session - this constrains where invite redemption can happen
- student_profiles minimised (class, interests, language, broad location; no DOB/marks/category/income); RLS strictly own-row, no reviewer override - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 99-107 and 174-177 (verified)
- PII-free logging pattern (opaque ids only, free text excluded) exists and is reusable for distress flags - Evidence: F:\the competetion project\app\api\auth.py lines 102-133 (verified)
- Reviewer cookie session scoped to /reviewer exists and can host a staff page; authorisation is delegated to RLS (a signed-in non-reviewer sees an empty queue) - Evidence: F:\the competetion project\app\web\reviewer_pages.py lines 59-67, 77, 204-224 (opened and verified). NOTE: only one role exists - reviewers table + is_reviewer() (0001_init.sql lines 113-122); there is no separate safeguarding-staff role
- Security-definer role-check pattern (is_reviewer()) exists and is the template for is_admitted()/is_safeguarding_staff() - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 118-122
- Test fixtures already create throwaway users with a test-only service-role key that the app itself never loads - the path for creating admitted/un-admitted test accounts - Evidence: F:\the competetion project\tests\db\conftest.py lines 10, 29-38, 126-181
- Exposure is limited only by network reachability: localhost:8010, no nginx site; next migration number in this repo is 0004 - Evidence: F:\the competetion project\STATUS.md line 334; F:\the competetion project\db\migrations contains 0001-0003 only

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| Sign-up has no age, invite or consent gate and no kill switch; nothing in code or DB disables a minor's account. FastAPI-only gating is bypassable: Supabase Auth sign-up is callable directly with the publishable key, and that alone would put a minor's email into auth.users | CLAUDE.md non-negotiables; SECURITY.md lines 20-22; build pack s2 line 13, s3 line 40, Step 8; DECISIONS.md M3 review finding 1 | launch-blocker |
| No consents table, no account admission/status, no invites, no audit of who consented to what wording and when (grep of app/, db/, tests/ for consent\|invite\|birth\|minor finds only the auth.py docstring) | Build pack s6 Tables line 94 and Consent line 108; DATA.md line 14 | launch-blocker |
| No written consent/safeguarding design for a person to review; no docs/CONSENT.md; no named safeguarding staff member; no named non-author reviewer | Build pack Step 8 gate; s12 line 214; SECURITY.md lines 28-29, 72-73 | launch-blocker |
| No safeguarding-staff role distinct from content reviewers. The only role is reviewers/is_reviewer(); Step 10 brings in outside content reviewers, who must not see distress or support content ('visible only to staff') | Build pack s6 line 108 (support-queue and distress content visible only to staff) | phase1-required |
| No distress keyword rule anywhere in app/; no helpline response; helpline number unverified. saved_plans.notes (0002 line 26) is a stored free-text field today and is unscreened | Build pack s3 line 44; s6 line 108; s12 line 214; SECURITY.md lines 30-32 | phase1-required |
| No staff-only support queue, no flags table, no 24-hour notification to a named staff member | Build pack s3 line 44, s6 line 108, Step 8 | phase1-required |
| No withdrawal action (freeze), no consent revocation, no 30-day deletion marker or runbook | Build pack s6 line 108 | phase1-required |
| No student-facing HTML sign-up/account page or student cookie session exists (student auth is Bearer-header JSON only), so consent wording, refusal message, helpline card and withdraw button have no screen to live on yet | STATUS.md lines 73-75; build pack Step 8 | phase1-required |
| No verifiable guardian consent route for under-18 accounts (school-mediated or DigiLocker) | Build pack s6 line 108; SECURITY.md lines 23-25; s13 line 231 | phase1-nice |
| No separate revocable per-purpose consents (marks/category/income, parent summary, contacting an institution); none of those fields/features exist today so there is nothing to consent to yet | Build pack s6 line 108; SECURITY.md lines 26-27 | phase1-nice |
| No re-consent at 18 | Build pack s6 line 108 | defer |
| No student-approved parent family summary or consent-screen wording about parent vs student control | Build pack s5 line 84; PRODUCT.md lines 50-51 | defer |
| No authorised case summary for support staff | Build pack s5 line 84 | defer |
| No DigiLocker guardian token integration | Build pack s6 line 108 | defer |

**Owner decisions**

- Interim gate versus full under-18 flow for Phase 1 - Blocks: CONSENT-2 onward; the public-domain/nginx request - Recommended default: Interim gate: adult-only, invite-only, MINOR_ACCOUNTS_ENABLED=false, SIGNUP_ENABLED=false until CONSENT-10 signs off. Guest tools stay open (no personal data). Minors admitted only at Step 16 via the school-mediated route.
- Does the ten-user trial (Step 15) include real minors? - Blocks: Whether CONSENT-11 and CONSENT-13 move from expand-100 to ten-user-trial - Recommended default: No. Build pack line 13 says adult testers on synthetic profiles first. Use 18+ first-year students, parents, teachers. Saves about 2 dev sessions, 4 human hours and a school agreement before first users. Start the school conversation now anyway; it is calendar-bound.
- Who is the named safeguarding staff member receiving distress flags within 24 h? - Blocks: CONSENT-4 staff seeding; CONSENT-7 notification target; CONSENT-10 - Recommended default: The owner for the pilot, with a named backup who checks /reviewer/support daily when the owner is away. Content reviewers are NOT given this role.
- Who is the non-author human reviewer of the consent workflow? - Blocks: CONSENT-10, the real-users gate - Recommended default: A teacher or school counsellor contact, or one of the two Step 10 content reviewers. Not the owner if the owner approved the design text; if unavoidable, record the limitation in the sign-off. Name the person this week - it is the long pole.
- Supabase Auth sign-up setting: disable open sign-ups, or keep enabled with email confirmation and rely on the RLS admission gate? - Blocks: CONSENT-4; the sign-up path shape in CONSENT-5 and auth-sessions-plans - Recommended default: Keep enabled with email confirmation required; enforce admission via redeem_invite()/is_admitted() in RLS so a bypass account can store nothing, and keep the service-role key out of the app. Accept the residual that a bypass leaves an email in auth.users; owner purges un-admitted accounts weekly. CONSENT-2 evaluates a Supabase before-user-created hook as a free hardening step (owner to verify availability on the plan).
- What age evidence is acceptable for adults, and what is stored? - Blocks: CONSENT-5 - Recommended default: Self-declared birth year checked at sign-up plus a personally issued single-use invite. Store only adult_attested_at and wording version, not the birth year. No identity documents.
- Which helpline number is displayed? - Blocks: CONSENT-8 - Recommended default: The national tele-mental-health helpline (Tele-MANAS). Owner verifies against the official government page on the day, stores it as an env value, records source URL and date. If unset the card says the number is being verified - never a guessed number.

**Tasks**

### CONSENT-1 - Sign-up kill switch (immediate stopgap)

- What: Add config SIGNUP_ENABLED (default false; fail closed if unset or unparsable). When false, POST /auth/sign-up returns 403 with a kind 'pilot sign-up is by invitation, not open yet' message before any Supabase call. Sign-in is unaffected. Lets guest-only private staging and usability round 1 proceed without waiting for the full gate.
- Acceptance: Unit tests: flag absent or false gives 403 and the Supabase client is never constructed; true preserves current behaviour. .env.example lists the variable name only. make lint, typecheck, test-unit run green in-session.
- Step: 8 (wave 0)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: app/core/config.py, app/api/auth.py, .env.example, tests/unit/test_signup_switch.py, tests/db/test_api_auth.py
- Reviewers: data-security-reviewer

### CONSENT-2 - Owner: pick the interim gate mode and name the safeguarding people

- What: Owner records in docs/DECISIONS.md: (a) interim mode = adult-only, invite-only, minors disabled; (b) named staff member receiving distress flags within 24 h plus a backup; (c) named non-author human reviewer of the consent workflow; (d) whether the ten-user trial includes real minors (default no); (e) Supabase sign-up setting choice (see ownerDecisions).
- Acceptance: Dated DECISIONS.md entry names two real people (flag recipient, reviewer), the gate mode, trial cohort and Supabase setting choice. Contact details kept outside the repo.
- Step: 8 (wave 0)
- Needed by: real-users-gate
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 1
- Depends on: none
- Touches: docs/DECISIONS.md, STATUS.md
- Reviewers: human

### CONSENT-3 - Write the consent and safeguarding design doc (contract freeze)

- What: Author docs/CONSENT.md: account states (none, active_adult, frozen, deletion_due; later pending_guardian, active_minor), invite redemption sequence given Supabase email confirmation returns no session at sign-up, security-definer function contract (invite_is_valid, redeem_invite, is_admitted, is_safeguarding_staff, withdraw_account), data stored (adult attestation + wording version, NOT birth year for adults), distress behaviour, staff-only visibility, withdrawal/30-day deletion, later minor route.
- Acceptance: Doc exists; every build pack s6 consent sentence mapped to a state or rule and marked Phase 1 or later; table/function signatures listed for CONSENT-3; anon-key bypass analysed; no secrets or real personal data.
- Step: 8 (wave 1)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: CONSENT-2, AUTH-1
- Touches: docs/CONSENT.md, docs/SECURITY.md
- Reviewers: data-security-reviewer, human

### CONSENT-4 - Migration 0004: admission, consents, invites, safeguarding staff and flags, fail-closed RLS

- What: Add account_status, consents (append-only), pilot_invites (hashed code, expiry, used_by), safeguarding_staff, safeguarding_flags (category and ids only, no text). Security-definer functions: invite_is_valid, redeem_invite (only way to become admitted; users cannot write account_status directly), is_admitted, is_safeguarding_staff, withdraw_account. Add is_admitted() to write policies of saved_plans and student_profiles. Update conftest fixtures to create admitted users.
- Acceptance: make test-db (not as DB owner) proves: un-admitted or frozen user cannot write saved_plans/student_profiles; user cannot self-insert account_status or reuse/forge an invite; students AND content reviewers read zero rows of flags, invites, others' consents; full guest/A/B/reviewer matrix rerun green.
- Step: 8 (wave 2)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0.5
- Depends on: DATA-12, CONSENT-3
- Touches: db/migrations/0004_consent_gate.sql, db/migrations/README.md, tests/db/conftest.py, tests/db/test_consent_gate.py, docs/DATA.md
- Reviewers: data-security-reviewer
- Risk: Every existing db test user becomes un-admitted; fix fixtures, not policies

### CONSENT-5 - Owner: set Supabase Auth sign-up settings and the invite hand-out procedure

- What: In the Supabase dashboard (and staging project when it exists) apply the CONSENT-1 choice: email confirmation required at minimum; optionally disable open sign-ups or add a before-user-created hook per docs/CONSENT.md. Decide how invite codes reach adult testers (personally, one code per person). Seed the safeguarding_staff row for the named person.
- Acceptance: A direct Supabase Auth sign-up with the publishable key is rejected, or yields an account that RLS leaves unable to store anything (owner runs the provided check script). Setting names, not values, recorded in DECISIONS.md.
- Step: 8 (wave 3)
- Needed by: real-users-gate
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 1
- Depends on: AUTH-1, CONSENT-2, CONSENT-4
- Touches: docs/DECISIONS.md
- Reviewers: human

### CONSENT-6 - Interim gate in the API: invite code, 18+ attestation, terms consent, minors refused

- What: POST /auth/sign-up requires invite code, birth year and accepted wording version. Under-18 year or invalid invite is refused before any Supabase call; birth year is not stored. Add MINOR_ACCOUNTS_ENABLED (default false, fail closed). Call redeem_invite RPC when a session exists; add POST /auth/redeem-invite for the email-confirmation path after first sign-in. Add scripts/mint_invites.py (prints codes once, stores hashes).
- Acceptance: Tests: missing/invalid/used invite gives 403; under-18 refused and sign_up never called; valid adult gets active status plus consent row; confirmation path admits on redeem; flag absent keeps minors disabled; cross-user matrix rerun; logs contain no birth year, email or code.
- Step: 8 (wave 3)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-4, CONSENT-1
- Touches: app/api/auth.py, app/core/config.py, app/consent/__init__.py, app/consent/gate.py, scripts/mint_invites.py, .env.example, tests/unit/test_consent_gate.py, tests/db/test_api_auth.py
- Reviewers: data-security-reviewer, ux-qa-reviewer

### CONSENT-7 - Distress keyword rule (English, Hindi, Hinglish) with helpline response

- What: Pure deterministic app/safeguarding/distress.py, no AI: Unicode-normalise, handle Devanagari and Roman variants, match a reviewed phrase list in a data file, return category only. Helpline number from config (unset means show 'number being verified', never invented). Hook into saved_plans notes on POST/PATCH /plans and sign-up pending_plan; response carries a helpline block and a flag row is written. Export check_distress() for Ask BCION.
- Acceptance: Labelled synthetic fixture of 30+ phrases (10 per language plus negatives like 'deadline') passes; a match returns the helpline block and creates a flag with category and ids only; message text never logged or copied into the flag; plan save still succeeds.
- Step: 8 (wave 3)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-4
- Touches: app/safeguarding/__init__.py, app/safeguarding/distress.py, app/safeguarding/keywords.yaml, app/web/templates/_helpline_card.html, app/api/plans.py, app/api/auth.py, app/core/config.py, tests/unit/test_distress.py, tests/db/test_distress_flag.py
- Reviewers: data-security-reviewer, ux-qa-reviewer, human

### CONSENT-8 - Staff-only safeguarding queue, deletion-due list and 24-hour notification

- What: Add /reviewer/support in a new router file reusing get_reviewer_session. Lists safeguarding_flags (time, opaque user id, category, status), acknowledge action, highlights flags older than 24 h, and lists frozen accounts with deletion days remaining. Visibility enforced by is_safeguarding_staff() RLS, not is_reviewer(). Notification: off-request-path webhook carrying flag id only; fallback is a daily manual check.
- Acceptance: db tests: guest, students A/B and a content reviewer get redirect/empty and zero rows; safeguarding staff can list and acknowledge; notification payload has no free text, email or user id; overdue highlight unit-tested.
- Step: 8 (wave 3)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-4, PUB-5
- Touches: app/web/support_pages.py, app/web/templates/reviewer_support.html, app/safeguarding/notify.py, app/main.py, tests/db/test_support_queue.py, tests/unit/test_flag_overdue.py
- Reviewers: data-security-reviewer, ux-qa-reviewer

### CONSENT-9 - Human\: review the Hindi/Hinglish phrase list and verify the helpline number

- What: A fluent Hindi speaker (not the dev agent) reviews and extends keywords.yaml for real student phrasing in Devanagari and Roman script, then types at least 10 Hindi and 10 Hinglish test phrases on staging. Owner verifies the national tele-mental-health helpline number against the official government source that day and sets the env value.
- Acceptance: Signed-off phrase list committed; test-session result with misses fixed or listed recorded in DECISIONS.md; helpline source URL, verification date and verifier recorded; re-verified on launch day.
- Step: 8 (wave 5)
- Needed by: real-users-gate
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 2.5
- Depends on: CONSENT-7, DEPLOY-7, CONTENT-1
- Touches: app/safeguarding/keywords.yaml, docs/DECISIONS.md
- Reviewers: human

### CONSENT-10 - Withdraw consent: freeze account, revoke consents, mark deletion due, 30-day runbook

- What: POST /account/withdraw (Bearer auth) calls withdraw_account(): status frozen, consents revoked_at set, deletion_due_at = now + 30 days; RLS then blocks all writes. Own router file. Pilot deletion is a staff runbook (owner deletes the auth user in the dashboard, cascades verified) driven by the CONSENT-7 due list, not a job.
- Acceptance: db tests: after withdrawal the user cannot write plans or profile, can still read own data, another user unaffected, action is idempotent. docs/RUNBOOK-deletion.md exists and names the cascade tables.
- Step: 8 (wave 3)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-4
- Touches: app/api/account.py, app/main.py, docs/RUNBOOK-deletion.md, tests/db/test_withdrawal.py
- Reviewers: data-security-reviewer

### CONSENT-11 - Human gate review of the interim consent and safeguarding workflow by a non-author

- What: Named reviewer from CONSENT-1 reads docs/CONSENT.md and walks staging as a would-be minor, an invited adult, a direct-to-Supabase bypass attempt (owner-assisted), a withdrawing user and a distress phrase; checks the staff queue and that content reviewers cannot see it; confirms minors disabled in code, RLS and Supabase settings; explicitly accepts or rejects the self-declared-age residual risk.
- Acceptance: Dated DECISIONS.md sign-off by a named non-author listing what was tested, findings and disposition. Critical/high findings closed first. No public domain or real-user invite before this entry exists.
- Step: 8 (wave 6)
- Needed by: real-users-gate
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 3
- Depends on: CONSENT-5, CONSENT-6, CONSENT-8, CONSENT-9, CONSENT-10, DEPLOY-7, AUTH-3
- Touches: docs/DECISIONS.md, STATUS.md
- Reviewers: human

### CONSENT-12 - Under-18 route: school-mediated guardian consent with staff enablement

- What: New migration adds birth_year and guardian-verification columns (school, date, verifier; no documents). School coordinator collects signed guardian forms (template in docs/, forms stay with the school). Safeguarding staff mark a minor invite guardian_consent_verified; only then does redeem_invite yield active_minor. Requires MINOR_ACCOUNTS_ENABLED=true. Split: session 1 migration + RLS tests, session 2 staff page + form template.
- Acceptance: Tests: minor invite without staff verification cannot activate; with it activates and a consent row records route and verifier; flag off blocks everything; cross-user matrix rerun. Consent form reviewed for plain English and Hindi.
- Step: 16 (wave 7)
- Needed by: expand-100
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 1
- Depends on: CONSENT-6, CONSENT-11, TRIAL-14
- Touches: db/migrations/00NN_minor_consent.sql, app/consent/minor_route.py, app/web/support_pages.py, app/web/templates/reviewer_minor_consent.html, docs/guardian-consent-form.md, tests/db/test_minor_route.py
- Reviewers: data-security-reviewer, ux-qa-reviewer, human

### CONSENT-13 - Per-purpose revocable consents UI

- What: Settings page listing each purpose (saving marks/category/income, parent summary, contacting an institution) with separate grant/revoke writing append-only consents rows; server-side checks refuse a purpose-gated field without active consent. Build only purposes whose feature exists. Skip entirely if no such field or feature ships in the pilot.
- Acceptance: db tests: revoking a purpose blocks the dependent write/read on the next request and leaves other purposes untouched; history append-only; page works without JavaScript on mobile.
- Step: 16 (wave 4)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-4, CONSENT-6, AUTH-3
- Touches: app/api/consents.py, app/web/templates/consents.html, tests/db/test_consents.py
- Reviewers: data-security-reviewer, ux-qa-reviewer

### CONSENT-14 - Human review and owner sign-off before enabling real minor accounts

- What: Non-author reviewer re-reviews the under-18 flow end to end with the school coordinator's actual process. Owner confirms in writing that the data-flow map is accepted with every row's region confirmed. Only then does the owner set MINOR_ACCOUNTS_ENABLED in the environment.
- Acceptance: DECISIONS.md entry records reviewer name, date, findings closed and the owner's written data-flow-map acceptance. Flag change recorded by variable name only.
- Step: 16 (wave 8)
- Needed by: expand-100
- Executor: mixed
- Model tier: none
- Dev sessions: 0
- Human hours: 3
- Depends on: CONSENT-12, SEC-8
- Touches: docs/DECISIONS.md, docs/SECURITY.md, STATUS.md
- Reviewers: human

### CONSENT-15 - Re-consent at 18 (minimal manual version)

- What: Staff-queue query lists active_minor accounts whose birth year implies turning 18 in the pilot window; staff trigger a re-consent prompt at next sign-in; account frozen if not completed within 30 days. A 12-week pilot sees a handful of cases at most.
- Acceptance: Unit tests cover the turning-18 selection; prompt records a new consent row with granted_by_role=student; procedure documented in docs/CONSENT.md.
- Step: 16 (wave 8)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: CONSENT-12
- Touches: app/consent/reconsent.py, app/web/support_pages.py, tests/unit/test_reconsent.py
- Reviewers: data-security-reviewer

### CONSENT-16 - Student-approved parent family summary and support-staff case summary

- What: Printable family summary generated deterministically from a saved plan; the student chooses what it shows under the parent-summary consent purpose. Authorised case summary view for support staff. No section 12 gate requires either. Split: session 1 family summary, session 2 case summary.
- Acceptance: Summary renders only fields the student ticked; revoking consent disables the share link; staff see the case summary only when authorised.
- Step: 16 (wave 7)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 2
- Human hours: 0
- Depends on: CONSENT-13, UI-1, DESIGN-12, DESIGN-11, AUTH-14, AUTH-15
- Touches: app/web/templates/family_summary.html, app/api/summary.py, tests/db/test_family_summary.py
- Reviewers: ux-qa-reviewer, data-security-reviewer

### CONSENT-17 - Record DigiLocker guardian token route as deferred

- What: DigiLocker partner onboarding cannot be obtained quickly for a 100-user pilot. The school-mediated route satisfies the spec's 'or'. Owner records this as a national-phase item; fold into the CONSENT-1 DECISIONS.md entry. No code.
- Acceptance: DECISIONS.md records the deferral and rationale.
- Step: cross (wave 0)
- Needed by: deferrable
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 0.25
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: human

## Publishing console and maker-checker completion

Area: `publishing-console`

Verified: the maker-checker core (0003 trigger, claims JSON API, zero-JS reviewer console, 12+13+10 live tests) exists as claimed. The audit under-stated the bypasses: a reviewer JWT against PostgREST can self-approve today (insert with created_by NULL, or rewrite created_by while in_review), can flip a source's source_type from synthetic to official, and one reviewer alone can supersede (unpublish) any fact pointing at any claim. Everything else in the audit's gap list is confirmed missing. Corrected plan: 16 tasks, ~17 dev sessions on the required path, two serialised migrations (0004, 0005) authored back-to-back and applied once by the owner, then three to four parallel lanes after a cheap router split.

**Already done**

- DB-enforced workflow: insert must be draft; draft<->in_review->published only; publish requires non-null reviewed_by that is not equal to created_by; published content frozen (value, source_id, verification_date, verifier, entity, field, created_by, extracted_by); only published->superseded; superseded final; service_role exempt. CAVEAT verified in code: the equality check is NULL-unsafe and created_by is not frozen before publication (see gaps). - Evidence: F:\the competetion project\db\migrations\0003_maker_checker.sql lines 58-136
- Synthetic-sourced claims cannot be published (trigger reads sources.source_type at publish time); claims table has source_id, verification_date, verifier, review_due_date, superseded_by, extracted_by, created_by, reviewed_by and a never-written approved_draft_version text column - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 50-93
- Claims JSON API: POST /claims (always draft, created_by from JWT, verifier!='ai', extracted_by Literal), /submit, /approve (reviewed_by from JWT), /reject (no reason), /supersede (any new_claim_id, no validation), GET /claims (default draft+in_review, no paging); single Postgres-error mapper - Evidence: F:\the competetion project\app\api\claims.py (254 lines, read in full)
- Reviewer console: /reviewer/sign-in, /sign-out, /queue, POST /claims/{id}/submit|approve|reject; cookie httponly, samesite=lax, secure only in production, path-scoped; CSRF defence is SameSite=Lax only (no token). Queue shows raw entity_id and source_id UUIDs, no source link. - Evidence: F:\the competetion project\app\web\reviewer_pages.py lines 147-264; F:\the competetion project\app\web\templates\reviewer_queue.html lines 63-105
- Live tests exist: 12 trigger tests, 13 API tests, 10 console tests (grep count confirmed; not run in this session) - Evidence: F:\the competetion project\tests\db\test_maker_checker.py, test_api_claims.py, test_reviewer_console.py
- Playwright e2e harness already exists and already has two reviewer-console smoke tests (sign-in reaches queue; queue shows a seeded draft). CI job for test-e2e and test-db is still commented out. - Evidence: F:\the competetion project\tests\e2e\test_smoke.py lines 286-297; F:\the competetion project\.github\workflows\ci.yml lines 5-6, 47
- Student-side 'Needs rechecking' label is already computed from review-due/staleness and rendered in the trust badge (so PUB-8 only needs the reviewer-side view) - Evidence: F:\the competetion project\app\planning\comparison.py lines 45-69; F:\the competetion project\app\web\templates\_trust_badge.html lines 18-43
- No application-level cache of public facts (only settings lru_cache); no Cache-Control headers set anywhere - Evidence: Grep lru_cache|cache-control over F:\the competetion project\app: only app/core/config.py and a comment in app/db/client.py
- Migration runner exists (scripts/apply_migrations.py with _schema_migrations tracking), so the owner does not have to paste SQL by hand - Evidence: F:\the competetion project\db\migrations\README.md; F:\the competetion project\scripts\apply_migrations.py
- BCI-005 card lists remaining M4 scope honestly - Evidence: F:\the competetion project\tasks\BCI-005.md

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| Self-approval is bypassable today by one reviewer using their JWT directly against PostgREST: (1) insert a draft with created_by NULL, then publish with reviewed_by = self - the trigger test 'new.reviewed_by = new.created_by' evaluates to NULL and does not raise, and the RLS check 'reviewed_by is distinct from created_by' is true; (2) created_by is only frozen once published, so it can be rewritten to NULL/another uid while draft or in_review, even in the approving UPDATE. created_by/reviewed_by are not forced to auth.uid() and created_by is nullable. | CLAUDE.md non-negotiable 'maker-checker, enforced server-side'; build pack s6 Publishing 'author cannot approve their own claim, enforced in the database'; s12 Built means 'two authorised people ... with no bypass'; 0003 lines 51-56, 110-118 | launch-blocker |
| Approval not bound to the exact draft: approved_draft_version never written or checked; in_review content is editable (in_review->in_review allowed) and value/source can change inside the approving UPDATE | Build pack s6 Publishing 'Approval binds to the exact source version and draft; editing invalidates approval'; s7 Quality gates Publication; docs/DATA.md Publishing workflow step 3 | launch-blocker |
| No source_versions table or document capture; sources rows are fully mutable by any reviewer (policy 'for all'), including official_url AND source_type - a reviewer can flip a synthetic source to 'official' and then publish its claims, defeating the synthetic-never-published trigger; official_url can change under published claims | Build pack s6 Tables (source_versions), Publishing 'Source entered -> document captured'; CLAUDE.md 'Synthetic fixtures ... NEVER published'; 0001_init.sql lines 76-93, 145-146 | launch-blocker |
| Supersede has no maker-checker and no validation: any single reviewer can remove a published fact from public results; superseded_by may point at any claim (draft, different entity/field, even unrelated), so a 'correction' can silently delete a fact with no reviewed replacement | Build pack Step 9 'approved -> superseded'; s7 Quality gates 'supersession'; s12 'no bypass'; app/api/claims.py lines 108-114, 225-235 | phase1-required |
| No review_events and no audit_events tables; publish is a bare UPDATE with no audit record; rejection has no reason | Build pack s6 Tables and Publishing 'publish atomically with an audit event' | phase1-required |
| No claim create/edit form and no source entry form in the console; no draft-edit route in the API; queue shows raw UUIDs with no source link or document | Build pack Step 9; s6 Publishing 'reviewer checks'; s2 reviewer console | phase1-required |
| No supersede/correction UI and no published-claims list in the console | Build pack Step 9; s7 Quality gates 'supersession' | phase1-required |
| Corrections do not flag affected saved plans (saved_plans has only pathway_id, no flag column, strict own-row RLS so a reviewer cannot write it without a definer function) | Build pack s6 Publishing 'flag saved plans'; docs/DATA.md step 4; db/migrations/0002_saved_plans.sql | phase1-required |
| Second authorised reviewer for critical rules and deadlines: no tier column on claims, no 'authorised for critical' flag on reviewers | Build pack s6 Publishing; s12 Built means 'two authorised people for critical publishing'; docs/DATA.md Freshness tiers | phase1-required |
| Claims lack unit/currency, jurisdiction, academic cycle, source publication date, and separate checked vs verified timestamps; material now that scope is all-India plus foreign pathways | Build pack s6 'Every critical claim carries'; docs/DECISIONS.md 2026-09-21 scope entry | phase1-required |
| No reviewer-side review-due/overdue view or pending-review counts; review_due_date is free input with no tier default (student-side stale label already exists) | docs/DATA.md Freshness tiers; build pack s12 expansion checks 'critical source freshness; pending reviews' | phase1-required |
| Publication quality-gate tests missing: NULL/rewritten created_by, invalidation on edit, concurrent publication, Storage access for guest/A/B/reviewer | Build pack s7 Quality gates Publication and Access | phase1-required |
| Console CSRF defence is SameSite=Lax only; adding multipart upload and supersede forms widens what a same-site attacker could trigger; cookie not Secure outside app_env=production (staging must set it) | app/web/reviewer_pages.py lines 180-192; build pack s7 'No known critical or high security issue ships' | phase1-nice |
| No explicit rule pinning 'public fact responses are not cached' (no cache today, no header, no test) | Build pack Step 9 and s12 'corrections invalidate cached answers' | phase1-required |
| careers and pathways rows (public names/descriptions) are reviewer-writable with no review step; out of this area's core but a publication-integrity hole to hand to data-foundation | 0001_init.sql lines 148-154; CLAUDE.md 'Unapproved facts never reach public results' | phase1-nice |
| No pagination/filtering on GET /claims or the queue | tasks/BCI-005.md 'Not done yet' | phase1-nice |
| CI does not run test-db or test-e2e (commented out), so publication regressions are caught only by the lead running the suite locally | .github/workflows/ci.yml lines 5-6, 47; build pack s7 | phase1-nice |
| Fetcher with domain allow-list, redirect validation, private-network block, size limit | Build pack s6 Publishing last sentence ('Manual document intake first'); docs/DATA.md Source allowlist | defer |

**Owner decisions**

- Meaning of 'second authorised reviewer for critical rules and deadlines' in a small pilot: (a) maker plus one distinct checker flagged critical-authorised, or (b) maker plus two distinct checkers (three people) - Blocks: PUB-1, PUB-2, PUB-15, PUB-11 - Recommended default: (a). Record (b) as a national-platform requirement; the tier column and flag allow adding it later without rework.
- Who the two named content reviewers are, and who owns source review and corrections (s12 gate needs a named person) - Blocks: PUB-11, PUB-12 and all real publication - Recommended default: Owner as maker plus one paid subject reviewer as critical-authorised checker for the dry run; add a second paid reviewer before bulk entry so absence does not deadlock maker-checker.
- Review-due cadence per freshness tier (DATA.md only says short/per cycle/annual) - Blocks: PUB-6 default date, PUB-8 - Recommended default: Tier 1: 14 days in-cycle; Tier 2: 180 days or next cycle start; Tier 3: 365 days. Editable per claim.
- Document capture formats and size cap - Blocks: PUB-2 bucket policy, PUB-4 - Recommended default: PDF, PNG/JPEG screenshot or saved HTML; 15 MB cap; private Supabase Storage bucket; served only by short-lived signed URL as attachment.
- Migration queue: may this area take 0004 and 0005 back-to-back, other areas sequenced after - Blocks: PUB-2, PUB-15 and every other area's schema work - Recommended default: Yes. Publishing takes 0004 and 0005 now (they close live bypasses); consent takes 0006; data-foundation entity tables 0007. One migration author at a time, numbers assigned by the lead.
- Does superseding (unpublishing) a fact need a second person, or is requiring an already-published, same-field replacement enough - Blocks: PUB-1, PUB-15 - Recommended default: Require a published same-entity/field replacement (which itself passed maker-checker); allow a single-reviewer emergency 'withdraw' only with a mandatory reason and audit event.
- Should flagged plans trigger a student notification or only a banner on next visit - Blocks: Nothing in this area (plans area) - Recommended default: Banner only for the pilot; no outbound message to minors.

**Tasks**

### PUB-1 - Freeze the publishing contract (task card + DECISIONS entry)

- What: Write the task card fixing: source_versions shape, claim content-hash field list, tier column and 'critical-authorised' reviewer flag, review_events/audit_events columns, new claim columns (unit, jurisdiction, academic_cycle, source_published_on, checked_at), supersede rules, saved_plans flag columns, bucket name/path convention, function signatures publish_claim/supersede_claim, review-due JSON shape. No code.
- Acceptance: Card lists every new column/table, hash inputs, all state transitions incl. edit-invalidates-approval and supersede preconditions, route list; owner decisions recorded in docs/DECISIONS.md; content-pipeline confirms import template field names match.
- Step: 9 (wave 1)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: SCOPE-2
- Touches: tasks/BCI-007.md (or next number assigned by lead), docs/DECISIONS.md, docs/DATA.md
- Reviewers: data-security-reviewer

### PUB-2 - Migration 0004: identity enforcement, approval binding, source versions, claim columns, bucket

- What: Append-only 0004: created_by NOT NULL-safe and forced to auth.uid() on insert, frozen afterwards; reviewed_by forced to auth.uid() on publish; NULL-safe self-approval check; content hash computed in trigger, content edit while in_review returns claim to draft, publish writes approved_draft_version; immutable source_versions; sources.source_type and official_url frozen once referenced by a published claim; new claim columns + tier; reviewers.critical_authorised; private storage bucket and storage.objects policies.
- Acceptance: New tests prove: insert with NULL or spoofed created_by rejected; created_by rewrite rejected; value change inside approving UPDATE rejected; in_review edit drops to draft; source_type flip on a used source rejected; source_version immutable; fresh rebuild 0001..0004 works; schema-version marker returns 4.
- Step: 9 (wave 4)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0
- Depends on: CONSENT-4, PUB-1, SCOPE-3
- Touches: db/migrations/0004_publishing_evidence.sql, tests/db/test_maker_checker.py, tests/db/conftest.py, db/migrations/README.md
- Reviewers: data-security-reviewer
- Risk: Existing fixtures seed published claims via service_role; keep the exemption. Existing rows with NULL created_by need a backfill rule before adding constraints.

### PUB-3 - Migration 0005: review/audit events, atomic publish and supersede functions, plan flag

- What: Split out of PUB-2/PUB-5. Append-only 0005: review_events and audit_events (insert-only, reviewer-readable), saved_plans.needs_review + flagged_at + flagged_reason, publish_claim(claim_id, expected_hash) and supersede_claim(old_id, new_id) functions doing status change + events in one transaction; supersede requires the new claim to be published and same entity/field, critical tier requires critical_authorised checker; flags plans, returns a count only.
- Acceptance: DB tests: stale hash raises; two concurrent publish calls yield one publish and one audit row; supersede with draft or mismatched replacement rejected; events not updatable/deletable by reviewers; plan flagged for student A, invisible to B, function returns only a count; marker returns 5.
- Step: 9 (wave 5)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0
- Depends on: PUB-2
- Touches: db/migrations/0005_publish_functions.sql, tests/db/test_maker_checker.py, tests/db/test_rls.py
- Reviewers: data-security-reviewer
- Risk: security definer functions cross into the student vault; must re-check is_reviewer() and auth.uid() and write only the flag columns

### PUB-4 - Owner applies 0004 and 0005 to staging (then production) and confirms the bucket

- What: Owner runs scripts/apply_migrations.py (or SQL editor) for 0004 and 0005 on the staging Supabase project, confirms the source-documents bucket is private, then a lead session runs make test-db and records the result. Repeat on the production project before real content.
- Acceptance: maker_checker_schema_version() returns 5 on staging; bucket not public; full make test-db green with zero skips, result recorded in STATUS.md.
- Step: 9 (wave 6)
- Needed by: real-users-gate
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 1
- Depends on: PUB-2, PUB-3
- Touches: STATUS.md
- Reviewers: human

### PUB-5 - Split reviewer_pages.py into a package so console lanes are file-disjoint

- What: New. Mechanical refactor with no behaviour change: app/web/reviewer/ package with auth.py (session, sign-in/out), queue.py (queue + submit/approve/reject), and empty sources.py, claims_forms.py, published.py, due.py routers registered in app/main.py. Split tests/db/test_reviewer_console.py fixtures into a shared helper. Can run immediately, before PUB-1.
- Acceptance: All 10 existing console tests and the two e2e reviewer smoke tests still pass unchanged in behaviour; ruff and mypy clean; no route path changes.
- Step: 9 (wave 0)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: app/web/reviewer_pages.py, app/web/reviewer/__init__.py, app/web/reviewer/auth.py, app/web/reviewer/queue.py, app/main.py, tests/db/test_reviewer_console.py
- Reviewers: none

### PUB-6 - Sources and source-version API with document upload

- What: Routes: POST/GET /sources, POST /sources/{id}/versions (multipart PDF/PNG/JPEG/HTML snapshot, 15 MB cap, content-type allow-list, sha256 server-side, stored via the reviewer's own scoped client), GET short-lived signed URL served as attachment. http/https-only URL validation. source_type 'synthetic' not selectable from this API.
- Acceptance: Live tests: reviewer creates source+version and fetches document; guest, student A, student B denied on write and document fetch (API and direct Storage); oversize and wrong-type rejected; duplicate sha256 detected.
- Step: 9 (wave 7)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: PUB-4
- Touches: app/api/sources.py, app/main.py, tests/db/test_api_sources.py
- Reviewers: data-security-reviewer

### PUB-7 - Claims API completion (app layer only)

- What: PATCH /claims/{id} (draft only); reject requires a reason; approve calls publish_claim RPC with the hash the reviewer saw (409 on stale); supersede calls supersede_claim RPC and returns flagged-plan count; new claim fields in request/response models; status/entity/tier filters and limit/offset on GET /claims. SQL lives in PUB-15, not here.
- Acceptance: Live tests: stale-hash approve is 409; reject without reason 422; supersede returns count and rejects unpublished replacement with a clear 400; paging works; existing 13 API tests updated and green.
- Step: 9 (wave 7)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: PUB-4
- Touches: app/api/claims.py, tests/db/test_api_claims.py
- Reviewers: data-security-reviewer

### PUB-8 - Console: source entry and claim create/edit forms

- What: Zero-JS forms: new source, add source version (file upload), new claim (entity picker by name, field from a fixed list, typed value + unit, jurisdiction, cycle, tier, review-due default from tier), edit draft. Calls claims.py/sources.py functions directly; same error-redirect pattern; hidden per-session CSRF token on all POST forms.
- Acceptance: A reviewer can enter a source, upload a document, create, edit and submit a draft entirely in the browser at 360 px; validation errors shown inline; new tests in tests/db/test_reviewer_forms.py.
- Step: 9 (wave 8)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 2
- Human hours: 0
- Depends on: PUB-6, PUB-7, PUB-5, SCOPE-13
- Touches: app/web/reviewer/sources.py, app/web/reviewer/claims_forms.py, app/web/templates/reviewer_source_form.html, app/web/templates/reviewer_claim_form.html, tests/db/test_reviewer_forms.py
- Reviewers: ux-qa-reviewer

### PUB-9 - Console: claim review detail, published list, supersede/correct flow

- What: Claim detail page: human-readable entity, value+unit, source authority, link to captured document, review history, approve (carries seen hash) and reject-with-reason. Published tab with search and paging. 'Correct this fact' flow: prefilled new draft; after a different reviewer publishes it, supersede the old claim and show the flagged-plan count.
- Acceptance: Reviewer sees the source document beside the value before approving; rejection reason visible to the author; correction ends with old superseded, new published, count shown; self-approval and stale-hash show styled errors.
- Step: 9 (wave 8)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 2
- Human hours: 0
- Depends on: PUB-7, PUB-5
- Touches: app/web/reviewer/queue.py, app/web/reviewer/published.py, app/web/templates/reviewer_claim_detail.html, app/web/templates/reviewer_published.html, app/web/templates/reviewer_queue.html, tests/db/test_reviewer_review_flow.py
- Reviewers: ux-qa-reviewer, data-security-reviewer

### PUB-10 - Console: review-due and overdue view

- What: /reviewer/due page and queue counters: published claims overdue or due within 14 days grouped by tier, plus pending-review count; one reviewer-only read-only JSON endpoint for the n8n reminder. Student-side stale label already exists and is not touched.
- Acceptance: Seeded overdue critical claim appears first; counts match a direct SQL check; endpoint denies guest/student and returns no student data.
- Step: 9 (wave 7)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: PUB-4, PUB-5
- Touches: app/web/reviewer/due.py, app/web/templates/reviewer_due.html, tests/db/test_reviewer_due.py
- Reviewers: ux-qa-reviewer

### PUB-12 - Independent publication-integrity review, fix round and human sign-off

- What: Read-and-test-only data-security-reviewer pass over 0004/0005, sources.py, claims.py, console: direct-PostgREST bypass attempts with a reviewer JWT (NULL/rewritten created_by, source_type flip, in-UPDATE edits, direct RPC calls), event immutability, Storage as guest/A/B/reviewer, upload abuse, CSRF on forms. One fix session. Owner or named human reads the findings and signs off.
- Acceptance: Written findings with reproductions; zero open critical/high; every fix has a regression test; full suite run recorded in STATUS.md; human sign-off line dated in docs/DECISIONS.md.
- Step: 9 (wave 9)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: strongest
- Dev sessions: 2
- Human hours: 1
- Depends on: PUB-8, PUB-9, A11Y-4
- Touches: tests/db/test_maker_checker.py, tests/db/test_api_sources.py, docs/KNOWN_ISSUES.md, docs/DECISIONS.md, STATUS.md
- Reviewers: data-security-reviewer, human

### PUB-13 - Owner names reviewers and authorises the critical-tier checker

- What: Owner names at least two content reviewers, creates their accounts, inserts them into reviewers via SQL (table has no API policy by design), marks who is critical_authorised, and confirms tier cadence numbers. Naming can happen now; the flag needs PUB-3.
- Acceptance: Two distinct reviewer accounts sign in to /reviewer on staging; at least one other than the usual maker is critical-authorised; cadence numbers written in docs/DATA.md; named owner of source review recorded.
- Step: 9 (wave 7)
- Needed by: real-users-gate
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 2
- Depends on: PUB-4, CONTENT-1
- Touches: docs/DATA.md, docs/DECISIONS.md
- Reviewers: human

### PUB-14 - Two-reviewer dry run on five real records

- What: The two named reviewers push five real facts (one critical deadline, one fee, one eligibility rule, one foreign-pathway fact, one correction of a deliberately wrong value) through capture, draft, review, publish, supersede, timing each. One fix session for findings.
- Acceptance: All five published with document attached; correction flagged a test plan; minutes per record recorded; usability blockers fixed or logged with an owner.
- Step: 9 (wave 10)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: standard
- Dev sessions: 1
- Human hours: 4
- Depends on: PUB-12, PUB-13, DEPLOY-7
- Touches: app/web/templates/reviewer_claim_form.html, app/web/templates/reviewer_claim_detail.html, STATUS.md
- Reviewers: human, ux-qa-reviewer

### PUB-15 - Extend Playwright e2e to the full reviewer flow

- What: Harness and two reviewer smoke tests already exist in tests/e2e/test_smoke.py. Add one spec: reviewer A creates source+draft and submits, self-approve shows error, reviewer B approves, fact appears on /compare/view with correct badge, correction replaces it. Synthetic-labelled fixtures cannot be published, so seed an 'official'-typed test source with cleanup.
- Acceptance: make test-e2e runs the new spec green locally with cleanup and no real data; result recorded in STATUS.md (CI e2e job is still commented out and is owned by the CI area).
- Step: 9 (wave 9)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: PUB-9
- Touches: tests/e2e/test_reviewer_flow.py, tests/e2e/conftest.py
- Reviewers: ux-qa-reviewer

### PUB-16 - Source fetcher with allow-list (deferred)

- What: Only if repeated manual intake justifies it: worker job fetching allow-listed domains, validating redirects, blocking private-network addresses, capping size, storing a new unreviewed source_version. Not required by any s12 gate; the spec says manual intake first.
- Acceptance: Not scheduled. If built: SSRF tests (private IP, redirect to private IP, oversize) pass and a fetched version never changes a published claim.
- Step: 9 (wave 8)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0
- Depends on: PUB-6, CONTENT-4, OPS-14
- Touches: app/worker/fetcher.py, tests/unit/test_fetcher.py
- Reviewers: data-security-reviewer

**Merged into other tasks**

- PUB-11 -> A11Y-4

## Content pipeline and the real pilot dataset

Area: `content-pipeline`

Maker-checker (DB trigger, claims API, reviewer console) exists; nothing from Step 10 does, and zero real content is published. 119 drafts (about 2,620 fact rows) share one 5-column table, so table parsing is plain code. Values are prose and Fact labels are free text, though, so mapping rows to the app's typed fields needs a human-confirmed step. Most rows map to no field the app consumes. The schema models only Career/Pathway, and no draft covers career families, pathway stages or programme fees. The human lane is the critical path: name two reviewers, write an editor handbook, freeze a CSV contract, verify a small trial subset (about 125 claims, about 45 human hours), approve in source-grouped batches. Section-2 numbers are ceilings, not floors.

**Already done**

- Maker-checker enforced in the DB plus claims API: create is always draft, submit/approve/reject/supersede exist, created_by comes from the caller, verifier 'ai' is rejected, extracted_by is human|ai - Evidence: F:\the competetion project\app\api\claims.py (routes at lines 138-239, verifier validator near line 100); F:\the competetion project\db\migrations\0003_maker_checker.sql (enforce_claims_workflow trigger, tightened claims_update_reviewers policy); tests/db/test_maker_checker.py and tests/db/test_api_claims.py exist (not run)
- Synthetic-source claims can never be published (DB trigger); source_type enum is official|institution_self_declared|synthetic - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 16-17 and 76-93 (opened)
- A reviewer RLS session can write sources, careers, pathways and insert claims, so an importer can run under a reviewer's own session with no service key - Evidence: db/migrations/0001_init.sql policies sources_write_reviewers, careers_write_reviewers, pathways_write_reviewers, claims_insert_reviewers (lines 144-165)
- Reviewer console UI: sign-in, sign-out, a flat queue of draft and in_review claims, per-claim submit/approve/reject - Evidence: F:\the competetion project\app\web\reviewer_pages.py lines 147-255 (opened); templates reviewer_queue.html and reviewer_sign_in.html; tests/db/test_reviewer_console.py
- Dangerous URL schemes are blocked when an evidence link is rendered - Evidence: docs/DECISIONS.md 2026-09-20 entry (field_value_for in app/planning/comparison.py; _safe_source_url in app/api/eligibility.py)
- Claims model, trust-label mapping, freshness tiers and the source-allowlist principle are documented; trust labels are implemented with a single 180-day SLA - Evidence: F:\the competetion project\docs\DATA.md; app/planning/comparison.py line 29 (DEFAULT_FRESHNESS_SLA_DAYS = 180) and lines 32-62
- Synthetic fixtures are clearly labelled - Evidence: F:\the competetion project\tests\fixtures\synthetic_data.py (not opened; name and STATUS.md only)
- 119 draft research files plus INDEX.md (120 files). 64 state files: 32 admission-rules and 32 institutions-scholarships. 12 foreign: 11 countries and 1 comparison summary. 10 scholarship-* files plus nmmss, aicte, nsp and 3 state scholarship files. 6 NIRF. About 17 exam files. 116 carry STATUS: DRAFT front-matter; gujarat-institutions, gujcet-eligibility and neet-ug-eligibility do not. 454 tables use the header 'Fact | Value | Source | Access date | Confidence'; 3 use a 'Source URL / Confidence note' variant and 1 has a modified Value header. About 2,619 fact rows: roughly 1,536 High, 502 Medium, 220 Low, 336 Not verified. - Evidence: ls and grep tallies over F:\the competetion project\docs\content-drafts; sampled state-admission-rules-kerala.md, state-institutions-scholarships-bihar.md, foreign-pathway-uk.md, nirf-top-engineering-institutions.md, ibps-po-eligibility.md
- Claim fields the app consumes on entity_type 'Pathway': minimum_age, maximum_age, minimum_marks_percentage, required_subjects and domicile_states (both comma-separated strings), plus the cost fields. The claims API accepts scalar values only (str|int|float|bool|None). - Evidence: app/api/eligibility.py lines 1-20; app/api/claims.py lines 83 and 122; app/api/compare.py line 174 (.eq entity_type Pathway)
- Scope decision recorded: all-India plus foreign pathways, numeric ceilings unchanged, phasing still open - Evidence: docs/DECISIONS.md 2026-09-21 entry; build pack section 2 table

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| No import template or contract. There is no content/ directory at all. | Build pack s9 Step 10 | launch-blocker |
| No importer. scripts/ holds only apply_migrations.py, so the only path is one POST /claims per fact. | Build pack s9 Step 10; s6 Publishing | launch-blocker |
| Draft rows are prose, not typed field values. Fact labels are free text, values are sentences, and many Source cells are prose such as 'Same official notification' or 'secondary aggregator'. Nothing maps a draft row to entity, field and typed value. Only a small share of the roughly 2,619 rows maps to any field the app consumes. | Build pack s9 Step 10 (import template); s6 'Every critical claim carries' | launch-blocker |
| Zero real published content. Every pathway is synthetic-sourced, so a guest on staging sees only 'Not available'. | Build pack s12 'Built means'; s12 Step 15 tasks 'identify verified versus estimated' and 'open an official source' | launch-blocker |
| Two named human reviewers and a named corrections owner are not assigned. | Build pack s9 Step 0 and Step 10; s12 gate 'a named person owns source review and corrections' | launch-blocker |
| No career-family list, no pathway or stage content, and no programme fee or seat records in any draft. NIRF drafts are ranking lists. State institution drafts cover one institution each, often with fees or seats 'not found'. | Build pack s2 ceilings; s9 Steps 1, 6 and 9 content track | launch-blocker |
| No editor handbook or onboarding: no written procedure for what counts as official, browsing from the homepage, review_due per tier, handling conflicts, or how to issue a correction. | Build pack s9 Step 1 track 'editor onboarded' and Step 6 'second reviewer onboarded'; s12 corrections owner | phase1-required |
| Partial publication gives a false 'meets'. /eligibility builds criteria only from published claims and returns 'meets' when none exist. Publishing minimum_age without required_subjects would tell a student they meet criteria that were never checked. A per-pathway completeness rule is needed before any eligibility claim goes public. | Build pack s6 Eligibility 'unknown rule never becomes a rejection' (mirror case); app/api/eligibility.py docstring | launch-blocker |
| No source register. The sources table has no unique key on URL, no publication date, version or hash, and no allow-list of official domains. Source rows are not under maker-checker: one reviewer can write a URL. | Build pack s9 Step 1 and Step 10; DATA.md 'Source allowlist' | phase1-required |
| No exception report. | Build pack s9 Step 10 | phase1-required |
| No coverage and freshness summary. | Build pack s9 Step 10; s12 expansion checks | phase1-required |
| The schema models only careers, pathways, sources and claims. There are no exams, exam_cycles, institutions, programmes, scholarships, source_versions or review_events tables. Claims lack unit, jurisdiction, cycle, source publication date, tier and rejection reason. The claims table has no batch or import key, so an importer cannot be idempotent without a new column or a heuristic. | Build pack s6 Tables and 'Every critical claim carries' | phase1-required |
| Freshness uses a single 180-day SLA, not per-tier SLAs. Tier-1 'days' cadence is not representable. | DATA.md Freshness tiers | phase1-nice |
| Exam drafts are 2026-cycle. JEE Main 2027 and NEET 2027 bulletins are due during the build, and claims carry no cycle label. | DATA.md tier 1; STATUS NEET notes | phase1-required |
| Rules-engine mismatches block honest NEET publication (DOB-cutoff age rule; Biology OR Biotechnology). | STATUS 'Content drafts - NEET' item 2 | phase1-required |
| The reviewer queue is a flat list that shows entity_id and source_id as raw UUIDs, with no source URL, entity name, grouping or filter. A checker cannot verify a claim from the console alone. | Build pack s9 Step 9; s12 'reviewer hours per record' | phase1-required |
| Hindi review of critical content is not possible yet: pathways.name and description are single-language columns, and no Hindi reviewer is named. | Build pack s2 Languages; s12 'English and Hindi critical content reviewed' | phase1-required |
| Pathway name and description are plain columns outside maker-checker. One reviewer can publish editorial text alone. | CLAUDE.md non-negotiable 'unapproved facts never reach public results' | phase1-required |
| The owner's email address appears in the 'Researcher' line of 116 draft files. The extractor must not propagate it. Scrub it before the repo is shared with reviewers. | CLAUDE.md minimisation and no personal data in repo memory | phase1-nice |
| INDEX.md is stale: NDA and IBPS are listed as having no file though both exist, and most of the batch is shown as in-progress. | docs/content-drafts/INDEX.md own rule | phase1-nice |
| Document capture (archived copy plus hash) and an allow-listed fetcher are not built. | Build pack s6 Publishing | defer |
| Verifying all 32 state profile pairs and all 11 foreign countries inside the pilot. | Build pack s2; DECISIONS 2026-09-21 | defer |

**Owner decisions**

- Who are the editor (maker), second reviewer (checker), corrections owner and Hindi content reviewer? - Blocks: CONTENT-9 onward; s12 gate 'a named person owns source review and corrections' - Recommended default: Owner is editor and corrections owner now. One trusted adult (teacher or counsellor) fluent in Hindi is second reviewer and Hindi reviewer, on a small honorarium. Replaceable later without a code change.
- Phase the widened scope inside the unchanged ceilings? - Blocks: CONTENT-5, CONTENT-12, CONTENT-16 - Recommended default: Yes. Trial: 6 families, about 12 pathways, 3 exams (JEE Main, NEET-UG, plus CUET-UG or GUJCET by cohort), 10-12 programmes, 5 scholarships, and 1 foreign country (UK, the best-sourced draft, from GOV.UK) as a read-only pathway. State profiles only for testers' home states. Treat section-2 numbers as maximums, not targets.
- May an AI-researched row be imported without a human first checking it in the sheet? - Blocks: CONTENT-6 design - Recommended default: No. checked_by is mandatory, so two humans touch every published fact. An AI may only propose the field mapping and value; the proposal is marked unchecked.
- Publish 2026-cycle exam rules before the 2027 bulletins exist? - Blocks: CONTENT-10, CONTENT-11 - Recommended default: Yes, with an explicit '2026 cycle' label and review_due set to the expected bulletin date. Never roll figures forward.
- Publish partial eligibility sets? - Blocks: CONTENT-2, CONTENT-6, CONTENT-8 - Recommended default: No. A pathway's eligibility claims publish as a complete documented set or not at all. NEET eligibility stays unpublished until the rules engine handles DOB cutoffs and OR-subjects. Cost and other fields may still publish.
- Reviewer honoraria budget - Blocks: CONTENT-10, CONTENT-12 - Recommended default: Commit about 50 hours now (waves 0-1, Hindi review, cycle recheck). Release a further 60 hours only after wave-0 timing and the trial demand log. This stays well under the build pack's Rs 1.5-3 lakh line.
- Does the editor run the importer CLI, or need a web upload page? - Blocks: CONTENT-19 - Recommended default: CLI, run by the owner as editor on his own machine with his own reviewer sign-in. Build the upload page only if a non-technical editor is appointed.

**Tasks**

### CONTENT-1 - Owner: name editor, second reviewer, corrections owner, Hindi reviewer; confirm trial subset

- What: Owner names an editor (maker), a second reviewer (checker), a corrections owner and the person who reviews Hindi content. Records them in docs/DECISIONS.md. Creates reviewer accounts himself via the Supabase dashboard and the reviewers table. Approves the trial subset default.
- Acceptance: Two distinct named people recorded in docs/DECISIONS.md; both can sign in at /reviewer/sign-in on staging; subset approved in writing.
- Step: 10 (wave 0)
- Needed by: staging-demo
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 2
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: human

### CONTENT-2 - Freeze the import contract: CSV templates and closed field vocabulary

- What: Write docs/CONTENT-IMPORT.md, content/templates/claims_import.csv and content/templates/sources_register.csv. Columns: entity_type, natural keys, field (closed vocabulary), scalar value (lists comma-separated, matching eligibility.py), unit, jurisdiction, cycle, tier, source_key, section ref, verbatim quote, checked_by, checked_on, draft_file#row. Define the review_due rule per tier and the per-pathway eligibility completeness set.
- Acceptance: Every field in eligibility.py and comparison.py is in the vocabulary with its type; 5 JEE Main rows validate by hand; the doc states that rows without checked_by and a status column are rejected.
- Step: 10 (wave 2)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: SCOPE-2, RULES-1, PUB-1
- Touches: docs/CONTENT-IMPORT.md, content/templates/claims_import.csv, content/templates/sources_register.csv
- Reviewers: data-security-reviewer, human

### CONTENT-3 - Offline draft extractor, exception report and inventory

- What: Pure-Python parser of the markdown tables in docs/content-drafts. Writes content/staging/candidates.csv with file, section heading, row number, fact, value, source text, extracted http(s) URLs and confidence bucket. Writes exceptions.csv with reason codes. No DB, network or AI. Drops the Researcher/email line. Writes docs/content-drafts/INVENTORY.md; does not overwrite the hand-kept INDEX.md.
- Acceptance: Runs on all 119 files; per-file row counts total about 2,600; the 3 header variants and the 3 files lacking front-matter are handled in unit tests; every non-High or URL-less row has a reason; no email address appears in output.
- Step: 10 (wave 0)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: scripts/content/__init__.py, scripts/content/extract_drafts.py, tests/unit/test_extract_drafts.py, content/staging/, docs/content-drafts/INVENTORY.md
- Reviewers: data-security-reviewer

### CONTENT-4 - Source register and official-domain allow-list checker

- What: Build content/sources_register.csv for the trial subset from candidates.csv URLs: source_key, authority, URL, source_type, document title, publication date, cycle, retrieved date, optional sha256 of a human-downloaded file. Add scripts/content/check_sources.py to reject non-http(s) schemes, non-allow-listed domains and aggregator domains. Allow-list goes in content/allowed_domains.txt, approved by the editor.
- Acceptance: Unit tests fail javascript:, data:, Wikipedia or Careers360, and unlisted-domain rows; the register covers every source_key in trial_subset.csv; the allow-list is signed off by the editor.
- Step: 10 (wave 3)
- Needed by: staging-demo
- Executor: mixed
- Model tier: cheap
- Dev sessions: 1
- Human hours: 1.5
- Depends on: CONTENT-2, CONTENT-3
- Touches: content/sources_register.csv, content/allowed_domains.txt, scripts/content/check_sources.py, tests/unit/test_check_sources.py
- Reviewers: data-security-reviewer, human

### CONTENT-5 - Curate trial subset: map draft rows to typed fields, list what must be sourced fresh

- What: Agent builds content/curation/trial_subset.csv in contract format from High-confidence candidates. It proposes the entity and field mapping and a typed value per row, marked as an unchecked AI proposal with checked_by left blank. Career families, pathway names and stages, and programme fees and seats are not in any draft, so the agent lists official pages and the editor sources them. No DB writes.
- Acceptance: About 100-130 rows; every row has a source_key plus quote, or an 'editor to source' marker; no value without a source; each pathway's eligibility set is complete or wholly excluded; owner or editor accepts the list.
- Step: 10 (wave 3)
- Needed by: staging-demo
- Executor: mixed
- Model tier: standard
- Dev sessions: 1
- Human hours: 3
- Depends on: CONTENT-1, CONTENT-2, CONTENT-3
- Touches: content/curation/trial_subset.csv
- Reviewers: human

### CONTENT-6 - Importer: checked CSV in, draft claims out, never published

- What: scripts/content/import_claims.py plus a validation module. Validates against the contract, runs check_sources, and upserts sources and entities by natural key. Inserts claims with status=draft, extracted_by='ai' and verifier=checked_by. Deterministic import_key for idempotency. Dry-run is the default. A human runs it under their own reviewer sign-in (publishable key plus RLS); no service key, and no credentials handled by agents.
- Acceptance: test-db proves: all rows are draft; a rerun inserts zero; rows with a status column, a synthetic source, an 'ai' verifier or blank checked_by are rejected; an incomplete eligibility set is rejected; the importer account cannot approve its own rows; a guest sees none.
- Step: 10 (wave 4)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0.5
- Depends on: CONTENT-2, SCOPE-3
- Touches: scripts/content/import_claims.py, scripts/content/validation.py, tests/db/test_content_import.py, tests/unit/test_import_validation.py, Makefile
- Reviewers: data-security-reviewer

### CONTENT-7 - Per-source review packets for the second reviewer

- What: Read-only script that produces one printable checklist per source per batch: official URL, section refs, verbatim quotes, proposed values, entity names, claim ids and tick boxes. It compensates for the console queue showing only UUIDs, so the checker opens one document and clears 10-20 claims in one sitting.
- Acceptance: For a test batch, packets cover 100 percent of in_review claims grouped by source; no DB writes; no student data.
- Step: 10 (wave 5)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: CONTENT-6
- Touches: scripts/content/review_packets.py, tests/unit/test_review_packets.py
- Reviewers: ux-qa-reviewer

### CONTENT-8 - Coverage, freshness and publication-integrity report

- What: scripts/content/coverage_report.py, read-only under a reviewer session. Reports counts per entity type and status against section-2 ceilings, 'Not available' fields per published pathway, review-due in 14 and 30 days, stale by tier, pending-review age, and claims per reviewer-hour. The integrity section fails on a published claim with a synthetic, non-http or non-allow-listed source, an unnamed verifier, created_by = reviewed_by, or an incomplete eligibility set.
- Acceptance: Renders markdown plus CSV; exits non-zero on a seeded violating fixture in test-db; figures match a hand count on the wave-0 batch.
- Step: 10 (wave 5)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0.5
- Depends on: CONTENT-6
- Touches: scripts/content/coverage_report.py, tests/db/test_coverage_report.py, Makefile
- Reviewers: data-security-reviewer

### CONTENT-9 - Human wave 0: staging seed, one family end to end, timed

- What: Editor verifies about 25 claims for engineering (JEE Main route, 2 pathways, 2 programmes, 1 scholarship) by browsing from official homepages. Fills checked_by, runs the importer on staging and submits. Second reviewer approves from the packets. Record minutes per claim for both roles and re-plan wave 1 from the result.
- Acceptance: Staging Compare shows real trust-labelled fields with working official links for at least 2 pathways; the integrity check passes; minutes per claim are recorded in STATUS.md.
- Step: 10 (wave 6)
- Needed by: staging-demo
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 8
- Depends on: CONTENT-1, CONTENT-4, CONTENT-5, CONTENT-6, CONTENT-7, CONTENT-15, DATA-10, DEPLOY-7, TRIAL-7
- Touches: content/curation/trial_subset.csv, STATUS.md
- Reviewers: human

### CONTENT-10 - Human wave 1: full ten-user-trial subset verified and published

- What: Editor verifies the remaining roughly 100 trial claims in source-grouped batches of 20-30. Second reviewer approves each batch within 48 hours. Exceptions stay unpublished and show as 'Not available'. Estimated 15 min per claim for the editor (many rows need fresh sourcing) and 5 min for the checker; adjust from wave-0 timing.
- Acceptance: Coverage report shows 6 families, about 12 pathways, 3 exams, 10 or more programmes and 5 scholarships published; the integrity check passes; zero published claims without a distinct second reviewer.
- Step: 10 (wave 11)
- Needed by: ten-user-trial
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 34
- Depends on: CONTENT-8, CONTENT-9, PUB-14, QA-12
- Touches: content/curation/
- Reviewers: human

### CONTENT-11 - Cycle-roll recheck for tier-1 exam claims

- What: When the JEE Main 2027 and NEET 2027 bulletins appear, the editor rechecks tier-1 claims and supersedes changed ones via new claims. Until then, 2026 claims publish only with an explicit cycle label in the value or field and review_due set to the expected bulletin window.
- Acceptance: Every published exam claim shows its cycle; every changed rule has a superseding claim approved by the second reviewer.
- Step: 10 (wave 12)
- Needed by: ten-user-trial
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 4
- Depends on: CONTENT-10
- Touches: content/curation/
- Reviewers: human

### CONTENT-12 - Wave 2: demand-driven growth during trial and first batches

- What: Agent prepares the next curation sheets (cheap tier) for entities testers actually searched for or asked about. Editors verify in the same batch rhythm. Section-2 figures are ceilings, not targets, so stop when demand is covered. Expect roughly 150-250 further claims.
- Acceptance: Every entity added traces to a logged tester or user need; pending-review age stays under 7 days; reviewer hours per record are reported per batch; no ceiling is exceeded.
- Step: 16 (wave 12)
- Needed by: expand-100
- Executor: mixed
- Model tier: cheap
- Dev sessions: 2
- Human hours: 60
- Depends on: CONTENT-10
- Touches: content/curation/
- Reviewers: human

### CONTENT-15 - Editor and checker handbook, including the corrections procedure

- What: Write docs/CONTENT-HANDBOOK.md: what counts as an official source, always navigating from the official homepage, quote capture, tier and review_due rules, the eligibility completeness rule, handling conflicting sources, the forbidden-wording list (no ranks, suitability or guarantees), a checker checklist, how to reject, how to supersede a published claim, the corrections owner's response time, and batch time-logging.
- Acceptance: Editor and second reviewer each read it and complete one dry-run claim on staging; the owner signs off the corrections procedure.
- Step: 10 (wave 3)
- Needed by: staging-demo
- Executor: mixed
- Model tier: standard
- Dev sessions: 1
- Human hours: 2
- Depends on: CONTENT-2
- Touches: docs/CONTENT-HANDBOOK.md
- Reviewers: human

### CONTENT-17 - Hindi review of trial-subset critical content

- What: The named Hindi reviewer checks Hindi renderings of published entity names, pathway descriptions, field labels and units for the trial subset against the English approved values. Numbers and source links must be identical in both languages.
- Acceptance: A signed checklist covers every published trial entity; zero numeric or link differences between the en and hi renderings.
- Step: 12 (wave 12)
- Needed by: ten-user-trial
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 5
- Depends on: CONTENT-10, I18N-7, CONTENT-1
- Touches: content/curation/
- Reviewers: human

### CONTENT-18 - Scrub researcher email from drafts and fix INDEX.md once

- What: Mechanical edit: replace the 'session run for \<email>' line in 116 draft files with 'automated agent', and correct the stale INDEX.md rows (NDA, IBPS, scholarships, NIRF, states, foreign) using INVENTORY.md.
- Acceptance: A grep for the email over docs/content-drafts returns zero matches; INDEX.md lists every existing file as done; no table content changed (the diff is limited to those lines).
- Step: cross (wave 1)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: CONTENT-3, SCOPE-1
- Touches: docs/content-drafts/*.md, docs/content-drafts/INDEX.md
- Reviewers: data-security-reviewer

### CONTENT-19 - Reviewer-console CSV upload page (only if the editor cannot run a CLI)

- What: A /reviewer/import route and reviewer_import.html that reuse the importer's validation module: upload the contract CSV, show a dry-run report, confirm, and insert drafts under the signed-in reviewer session. Skip it while the owner acts as editor.
- Acceptance: Same rejection tests as CONTENT-6, run via the web route; CSRF and file-size limits applied; a non-reviewer gets no insert.
- Step: 10 (wave 5)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0.5
- Depends on: CONTENT-6, PUB-5
- Touches: app/web/reviewer_pages.py, app/web/templates/reviewer_import.html, tests/db/test_reviewer_console.py
- Reviewers: data-security-reviewer, ux-qa-reviewer

**Merged into other tasks**

- CONTENT-13 -> PUB-16
- CONTENT-14 -> SCOPE-3
- CONTENT-16 -> SCOPE-11

## All-India admission rules and foreign pathways: design and phasing

Area: `scope-widening`

Audit core confirmed: the 2026-09-21 widening has no schema, model or UI support. Claims lack jurisdiction, cycle and currency; pathways/sources lack jurisdiction; the rupee sign is hardcoded in TWO templates. Main corrections: the proposed trial set relied on drafts that do not exist (no state-admission-rules files for Gujarat, Maharashtra, Tamil Nadu, Karnataka); the reviewer console cannot create claims, sources or pathways, so "enter via console" is impossible today; migrations are applied with scripts/apply_migrations.py, not the SQL editor; INDEX/summary staleness details were slightly off. Recommendation stands: one additive migration, currency-safe display without FX, derived coverage, and a 4-state + 2-country verified trial set with everything else "not verified yet" by design.

**Already done**

- Owner decision to widen scope recorded; ceilings explicitly unchanged; phasing left open - Evidence: F:\the competetion project\docs\DECISIONS.md second entry dated 2026-09-21 ('Pilot scope widened'); STATUS.md 'Needs your input' item 3 (lines 343-349) marks the ceilings/phasing follow-up as not yet answered
- A newer 2026-09-21 DECISIONS entry lifts the agent concurrency ceiling but keeps guardrails: disjoint files in separate worktrees, never parallel edits to a migration or shared schema, lead verifies and merges - Evidence: F:\the competetion project\docs\DECISIONS.md top entry (lines 8-26)
- Generic claims provenance table exists (entity_type, entity_id, field, jsonb value, source_id, verification_date, verifier, status, review_due_date, superseded_by, extracted_by) with no jurisdiction, cycle, unit or currency column - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 50-67
- Published-claim content-freeze trigger enumerates frozen columns explicitly (value, source_id, verification_date, verifier, entity_type, entity_id, field, created_by, extracted_by); new columns must be added to it - Evidence: F:\the competetion project\db\migrations\0003_maker_checker.sql lines 84-97
- Domicile criterion exists, case/whitespace-insensitive string match, None gives insufficient_information, but any unmatched string gives does_not_meet; fed by a comma-separated 'domicile_states' claim; input is free text - Evidence: app/rules/eligibility.py lines 243-286; app/api/eligibility.py lines 175-178; app/web/templates/requirements.html lines 54-60
- Cost engine and comparison assembly operate on currency-less numbers - Evidence: app/rules/cost.py; app/planning/comparison.py lines 189-280; grep for 'currency|jurisdiction|academic_cycle' across app/, db/ and docs/DATA.md returns no schema or model hits
- not_available trust label and rendering path exist and can carry 'not verified by design' - Evidence: app/planning/comparison.py lines 46-66 and 143
- Draft unverified research: 32 state-admission-rules files and 11 foreign-pathway country files (no USA). The 4 states WITHOUT an admission-rules profile are Gujarat, Maharashtra, Tamil Nadu and Karnataka; Gujarat has gujcet-eligibility/institutions/scholarships drafts, Maharashtra and Tamil Nadu have only institution + scholarship drafts - Evidence: Directory listing of F:\the competetion project\docs\content-drafts (120 files); INDEX.md lines 112-119 say the state batch excluded Gujarat, Maharashtra, Tamil Nadu
- Migration runner exists: owner runs a direct-Postgres script, not the dashboard SQL editor - Evidence: F:\the competetion project\scripts\apply_migrations.py docstring
- In-memory models have ad-hoc state hints only (Exam.state_specific, Institution.state, Scholarship.state); only sources, careers, pathways, claims, student_profiles, reviewers, saved_plans tables exist - Evidence: app/data/models.py lines 95-118; grep 'create table' in db/migrations
- Playwright e2e smoke tests exist (the task prompt's 'no Playwright e2e' is stale) - Evidence: tests/e2e/test_smoke.py; commits 84b1a1e and 2db356e

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| Claims have no jurisdiction and no academic cycle; with 36 states/UTs a quota claim for one state is indistinguishable from another's | Build pack line 96 'Every critical claim carries ... jurisdiction and academic cycle'; line 124 eligibility gate 'cycle and jurisdiction'; DECISIONS 2026-09-21 | launch-blocker |
| No currency/unit on claims. Rupee sign is hardcoded in TWO places: _trust_badge.html line 90 (every money field) and compare.html line 89 (net_to_arrange). A foreign fee would display as INR and be summed with INR | Build pack line 96 'value and unit'; section 2 Foreign pathways row | launch-blocker |
| Pathways have no jurisdiction; compare.py builds claims_by_field as a dict keyed by field per pathway (lines 192-194) so a second state's claim on the same pathway silently overwrites the first (row-order dependent). Explore has no filter of any kind | Build pack section 2; app/api/compare.py lines 190-197; app/api/explore.py | phase1-required |
| Sources have no jurisdiction; source_type enum is only official / institution_self_declared / synthetic; no written standard for what counts as official for a non-Indian or state source | db/migrations/0001_init.sql line 16; build pack section 2 Foreign pathways row; CLAUDE.md non-negotiable 2 | phase1-required |
| No content-entry path at all: the reviewer console has only sign-in, queue, submit, approve, reject; claims can be created only via raw POST /claims JSON; there is NO route, script or seed that creates sources, careers or pathways. Human verification cannot 'enter via the console' today | app/web/reviewer_pages.py routes (lines 147-255); grep for table("sources"\|"pathways"\|"careers") shows select only; build pack Step 10 'Import template, source register' | phase1-required |
| No field vocabulary for visa/entry requirements and no decision whether they are display-only or rule criteria | Build pack section 2 Foreign pathways row; section 6 Eligibility | phase1-required |
| No coverage notion: an uncovered state/country shows nothing rather than an explicit 'not verified yet'; AI pipeline (not built) will need the same signal for the Step 15 tester task 'ask a question outside coverage and notice the limitation' | CLAUDE.md non-negotiable 1; build pack line 216 | phase1-required |
| Domicile input is free text; naming variants or typos yield a confident does_not_meet, contradicting the module's own promise | Build pack section 6 unknown domicile never becomes rejection; app/rules/eligibility.py lines 243-286 | phase1-required |
| Trial-state drafts are incomplete: no admission-rules profile draft for Gujarat (GUJCET draft partly covers), Maharashtra, Tamil Nadu or Karnataka - the most likely trial states | docs/content-drafts listing; INDEX.md lines 112-119 | phase1-required |
| saved_plans.estimated_additional_expenses is a bare numeric; a saved estimate on a foreign pathway has no currency of its own | db/migrations/0002_saved_plans.sql line 25 | phase1-nice |
| Phasing inside unchanged ceilings is an unanswered owner question | DECISIONS 2026-09-21; STATUS.md lines 343-349 | phase1-required |
| Docs stale: docs/DATA.md has no jurisdiction/currency/unit; INDEX.md foreign table still says 'in-progress' with no files and mentions US, its batch note lists 8 countries while 11 files exist; comparison summary says only 3 country files exist; build pack section 7 concurrency text superseded | docs/content-drafts/INDEX.md lines 63-67, 98-102; foreign-pathways-comparison-summary.md lines 35-49 | phase1-nice |
| INR conversion of foreign costs (FX rate as a provenanced fact) | foreign-pathways-comparison-summary.md line 84 | defer |
| Verified coverage of all 36 states/UTs and all 11 countries; per-state counselling schedules, category lists, cutoffs | DECISIONS 2026-09-21 item 1 | defer |
| Foreign eligibility as executable rule functions | Build pack section 6; section 2 rule-function ceiling | defer |

**Owner decisions**

- Phasing: are all 36 states/UTs and all foreign countries required verified for the ten-user trial, or phased within existing ceilings? - Blocks: SCOPE-9 volume and the 12-week schedule; does not block SCOPE-2..7, 13 - Recommended default: Phase. Schema is any-state/any-country capable from day one; the trial verifies at most 4 states + national exams and 2 countries; everything else renders 'not verified yet' by design and widens in Step 16 batches.
- Which states form the trial set? - Blocks: SCOPE-14, SCOPE-9 - Recommended default: Gujarat and Delhi NCT, plus up to 2 states where the ten trial participants live; if unknown, Maharashtra and Tamil Nadu. Note Gujarat, Maharashtra and Tamil Nadu need a new admission-rules draft (SCOPE-14); Delhi NCT already has one.
- Which countries form the trial set? - Blocks: SCOPE-9 - Recommended default: UK and Canada (drafts exist; official government sources are clear). USA not in the trial set and no draft commissioned unless trial users ask.
- Do the numeric ceilings change (20-30 career families, 50-100 programme records, 12 weeks)? - Blocks: Content-track planning; reviewer honoraria - Recommended default: Unchanged. Foreign routes count inside the pathway budget (2 countries x 2-3 routes); state admission rules are claims on jurisdiction-tagged routes, not new programme records.
- Show foreign costs in INR, original currency, or both? - Blocks: SCOPE-4 display; SCOPE-12 - Recommended default: Original currency only, labelled, never summed with INR, never converted. Revisit after usability round 1.
- What counts as an 'official' source for a foreign or state fact, and who verifies it? - Blocks: SCOPE-8, SCOPE-9 - Recommended default: Destination government's immigration/education domain or the institution's own domain only; state counselling body's prospectus PDF for state rules; aggregators and marketing portals are leads. Same two named reviewers; visa facts 90-day review-due.
- Are foreign visa/entry requirements evaluated by the eligibility engine or displayed only? - Blocks: SCOPE-7 scope - Recommended default: Display-only verified facts with trust badges. No meets/does-not-meet verdict on visa rules.
- Name the two content reviewers (maker and checker) - Blocks: SCOPE-8 sign-off and all of SCOPE-9 - Recommended default: Owner as one reviewer plus one paid subject reviewer engaged this week; the author of a claim never approves it.

**Tasks**

### SCOPE-1 - Owner: confirm phasing and the trial coverage set

- What: Owner answers the open DECISIONS question. Default if no answer in 2 days: phase within ceilings; verified trial set = Gujarat + Delhi NCT + up to 2 states where the ten trial participants actually live (fallback Maharashtra, Tamil Nadu) + national exams; UK and Canada; all else 'not verified yet'. No INR conversion. Lead records it.
- Acceptance: DECISIONS.md has a dated entry naming covered states, covered countries, ceilings status and the FX decision; STATUS.md 'Needs your input' item 3 closed.
- Step: cross (wave 0)
- Needed by: staging-demo
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 1
- Depends on: none
- Touches: docs/DECISIONS.md, STATUS.md
- Reviewers: human
- Risk: If the owner requires all 36 states verified for the trial, the human content track breaks the 12-week schedule regardless of agent count.

### SCOPE-2 - Design note + frozen contract: jurisdiction, cycle, currency, coverage

- What: Docs only. Freeze in docs/DATA.md + DECISIONS: jurisdiction codes ('IN', 'IN-GJ', 'GB'; ISO 3166), academic_cycle text format, ISO 4217 currency on money fields and the list of money fields, route-per-jurisdiction pathway modelling, deterministic rule when two published claims share a field, foreign display-only field vocabulary, derived-coverage rule, no-FX rule. Write task cards for SCOPE-3..7, 13.
- Acceptance: DATA.md documents every new column, code list, money-field list and foreign vocabulary; DECISIONS entry dated; task cards exist with numbers assigned by the lead; no code changed.
- Step: cross (wave 0)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: none
- Touches: docs/DATA.md, docs/DECISIONS.md, tasks/BCI-0xx.md (next free numbers, assigned by lead; BCI-001..006 used)
- Reviewers: data-security-reviewer, human
- Risk: Can start on the recommended defaults before SCOPE-1 is answered.

### SCOPE-3 - Migration: jurisdiction/cycle/currency columns + freeze-trigger update + models

- What: Append-only migration (0004, or next number the lead assigns): claims.jurisdiction text not null default 'IN', claims.academic_cycle text null, claims.currency char(3) null with uppercase check, pathways.jurisdiction, sources.jurisdiction, index claims(jurisdiction). Re-create the 0003 freeze function with the three new columns frozen. No unique index (breaks supersede ordering). Update Claim/Pathway/Source models, CreateClaimRequest, ClaimOut, row mappers. Owner applies with scripts/apply_migrations.py.
- Acceptance: make test-db green after owner applies; new tests prove a published claim's jurisdiction, currency and cycle cannot be edited; guest/A/B/reviewer matrix rerun; existing rows read 'IN'; fresh rebuild from 0001 works; ruff and mypy clean.
- Step: 4 (wave 3)
- Needed by: staging-demo
- Executor: mixed
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0.5
- Depends on: CONTENT-2, SCOPE-2
- Touches: db/migrations/0004_jurisdiction_currency.sql, app/data/models.py, app/api/claims.py, app/api/compare.py, app/api/eligibility.py, tests/db/test_maker_checker.py, tests/db/test_rls.py, tests/db/test_api_claims.py, tests/db/conftest.py, tests/unit/test_models.py
- Reviewers: data-security-reviewer
- Risk: Omitting the freeze-trigger update lets a published GBP fee be re-labelled INR in place - a maker-checker bypass.

### SCOPE-4 - Currency-safe cost engine and money display

- What: Carry currency on FieldValue/FeeComponent/AssistanceItem/CostSummary. Totals return None with a 'mixed currencies' reason when components differ; never convert. Replace BOTH hardcoded rupee signs (_trust_badge.html line 90, compare.html line 89) with one currency-aware formatter. Student estimate override and saved estimated_additional_expenses inherit the pathway's verified-charges currency and are labelled so.
- Acceptance: Unit tests: INR output unchanged; GBP claim renders with GBP code, never a rupee sign; mixed INR+GBP gives None total with visible reason; money claim with null currency renders not_available; grep finds no literal &#8377; outside the formatter.
- Step: 7 (wave 4)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-3, I18N-2
- Touches: app/rules/cost.py, app/planning/comparison.py, app/api/compare.py, app/web/templates/_trust_badge.html, app/web/templates/compare.html, tests/unit/test_cost.py, tests/unit/test_comparison.py, tests/db/test_api_explore_compare.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: Most safety-critical display task here: a foreign amount shown as rupees is a wrong published fact.

### SCOPE-5 - Canonical state/UT + country code list and domicile select

- What: Static module app/data/jurisdictions.py: 36 states/UTs with ISO 3166-2:IN codes and aliases, plus pilot countries. domicile_in matches on codes; unrecognised input gives insufficient_information, never does_not_meet. Replace the free-text domicile input with a zero-JS select. 'domicile_states' claim values accepted as codes or aliases. Eligibility result states the jurisdiction and cycle it was evaluated for when the claim has them.
- Acceptance: Unit tests: 'Delhi' and 'NCT of Delhi' resolve to IN-DL; unknown state returns insufficient_information; existing eligibility and e2e smoke tests pass; requirements page works without JavaScript at 360px.
- Step: 7 (wave 1)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-2, UI-2
- Touches: app/data/jurisdictions.py, app/rules/eligibility.py, app/api/eligibility.py, app/web/pages.py, app/web/templates/requirements.html, tests/unit/test_eligibility.py, tests/db/test_api_eligibility.py, tests/e2e/test_smoke.py
- Reviewers: ux-qa-reviewer
- Risk: Low; no migration; parallel with SCOPE-3.

### SCOPE-6 - Derived coverage and 'not verified yet for this state/country' states

- What: Coverage is derived: a jurisdiction is covered only if it has at least one published, non-synthetic claim. Explore gets a zero-JS jurisdiction filter (GET query) and India/abroad grouping using pathways.jurisdiction; Explore and Requirements show an explicit 'not verified yet for \<place>' panel instead of emptiness. Expose covered_jurisdictions() for the AI pipeline. No request-tracking link unless a feedback route already exists.
- Acceptance: Tests: guest selecting an uncovered state sees the panel and no draft data; signed-in reviewer sees no draft content on public pages; covered list changes only on publish; works at 360px and without JavaScript.
- Step: 6 (wave 4)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-3, SCOPE-5
- Touches: app/planning/coverage.py, app/web/pages.py, app/api/explore.py, app/web/templates/explore.html, app/web/templates/requirements.html, app/web/templates/_not_verified.html, tests/db/test_coverage.py, tests/db/test_web_pages.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: Deriving coverage from published claims avoids a second publication path that could drift from maker-checker.

### SCOPE-7 - Foreign pathway student display: 'Visa and entry' block

- What: Render the SCOPE-2 foreign vocabulary (visa_name, proof_of_funds, english_test, application_system, under_18_conditions, visa_fee) as display-only claims with trust badges in a new partial included from Compare and Requirements for pathways whose jurisdiction is not Indian. Add labelled synthetic foreign-pathway fixtures to the db test fixtures. No rule-engine criteria, no verdicts.
- Acceptance: With synthetic fixtures: foreign pathway shows the block, every field badge-labelled, missing fields show not_available, money fields use the SCOPE-4 formatter; Indian pathways unchanged; synthetic fixtures remain unpublishable.
- Step: 7 (wave 5)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-3, SCOPE-4
- Touches: app/api/compare.py, app/planning/comparison.py, app/web/pages.py, app/web/templates/_visa_entry.html, app/web/templates/compare.html, app/web/templates/requirements.html, tests/db/conftest.py, tests/db/test_web_pages.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: An eligibility verdict on visa rules would be guarantee-shaped; keep display-only.

### SCOPE-8 - Reviewer standard for non-Indian and state sources (one page)

- What: Agent drafts, owner and named reviewers agree: for foreign facts only the destination government's immigration/education domain or the institution's own domain is 'official'; British Council, Study-in-X portals and aggregators are leads only; record document version/date; visa facts get a 90-day review_due_date, fees per cycle; state counselling prospectus PDF outranks portals. One pathway per jurisdiction route.
- Acceptance: docs/DATA.md section exists with an allow-list of official domains for the trial set; both named reviewers' acceptance recorded in DECISIONS.md.
- Step: 10 (wave 1)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: cheap
- Dev sessions: 1
- Human hours: 2
- Depends on: SCOPE-1, CONTENT-1
- Touches: docs/DATA.md, docs/DECISIONS.md
- Reviewers: human
- Risk: Without it reviewers will approve aggregator-sourced visa facts that change within weeks. The UK draft's tuition range is British-Council-sourced and will be dropped under this rule.

### SCOPE-9 - Human verification of the trial coverage set from existing drafts

- What: Two reviewers work the verifier checklists in the chosen state and country drafts: open primary documents, confirm or drop each fact, enter with jurisdiction/cycle/currency through the content-entry path (import template or console form, owned by the content-pipeline area), second reviewer approves. Target 8-12 claims per state, 8-10 per country; Low-confidence rows are dropped, not guessed.
- Acceptance: Every published trial-set claim has an allow-listed source, verifier, date, jurisdiction and (if money) currency; none approved by its author; dropped facts listed in an exception note; derived coverage shows exactly the chosen set.
- Step: 10 (wave 11)
- Needed by: ten-user-trial
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 28
- Depends on: SCOPE-3, SCOPE-8, SCOPE-13, SCOPE-14, CONTENT-6, CONTENT-15, PUB-14
- Touches: (database content only)
- Reviewers: human
- Risk: Long pole of the area. About 50-70 claims plus source rows at roughly 20-25 minutes each across maker and checker. Reviewers can pre-verify offline against primary PDFs while code lands.

### SCOPE-11 - Expansion: widen verified coverage in batches (more states, countries 3-11)

- What: After Step 15 passes, add states/countries in batches chosen from trial feedback and the 10-25-50-100 cohort's home states, logging reviewer hours per record. Pure content work through the same entry path; no code.
- Acceptance: Each batch: reviewer-hours-per-record logged; freshness and pending-review counts within agreed limits before the next batch; DECISIONS ceilings respected or formally raised.
- Step: 16 (wave 13)
- Needed by: expand-100
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 40
- Depends on: CONTENT-12, SCOPE-9
- Touches: (database content only)
- Reviewers: human
- Risk: Every state added is recurring re-verification work each admission cycle.

### SCOPE-12 - INR conversion of foreign costs (deferred)

- What: Only if usability rounds show students cannot reason about foreign-currency figures: FX rate as its own provenanced claim (RBI reference rate, dated), shown as an estimate-labelled 'approx INR at rate of \<date>' line, never summed into verified charges.
- Acceptance: Converted figures always carry estimate label, rate, date and source; verified charges stay in original currency; unit tests cover stale-rate handling.
- Step: cross (wave 5)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 1
- Depends on: SCOPE-4
- Touches: app/rules/cost.py, app/planning/comparison.py, app/web/templates/_trust_badge.html
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: An FX rate goes stale daily; recurring verification burden for little pilot value.

### SCOPE-13 - Reviewer-side integrity: currency required on money fields, queue shows jurisdiction/cycle/currency, duplicate warning

- What: Server-side: POST /claims rejects (422) a money-field claim without currency and a non-money claim with one, using the SCOPE-2 money-field list. Reviewer queue shows jurisdiction, cycle and currency columns and warns when another published claim exists for the same entity+field. Split out of the original SCOPE-7.
- Acceptance: Tests: money claim without currency gets 422 and a styled console error; queue renders the three columns; duplicate-published warning appears; maker-checker and cross-user tests rerun green.
- Step: 9 (wave 4)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-3, PUB-5
- Touches: app/api/claims.py, app/web/reviewer_pages.py, app/web/templates/reviewer_queue.html, tests/db/test_api_claims.py, tests/db/test_reviewer_console.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: Publication-integrity control; must be enforced in the API, not only the form.

### SCOPE-14 - Draft admission-rules profiles for chosen trial states that lack one

- What: Only for trial states the owner picks that have no state-admission-rules draft (Gujarat, Maharashtra, Tamil Nadu, Karnataka): one research session producing DRAFT/NOT VERIFIED profiles in the existing file format with per-fact confidence, primary-source URLs and a verifier checklist. Nothing enters the database.
- Acceptance: One file per missing chosen state following the existing template and banner; every fact cites a primary-source URL or is marked Low; INDEX.md updated; no database writes.
- Step: 10 (wave 1)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: SCOPE-1
- Touches: docs/content-drafts/state-admission-rules-gujarat.md, docs/content-drafts/state-admission-rules-maharashtra.md, docs/content-drafts/state-admission-rules-tamil-nadu.md, docs/content-drafts/INDEX.md
- Reviewers: human
- Risk: Skip entirely if the owner chooses only states with existing drafts.

**Merged into other tasks**

- SCOPE-10 -> CONTENT-18

## Bounded AI: Ask BCION

Area: `bounded-ai`

Verified: nothing of Step 11 exists. app/ai/ is docstring-only; Settings has provider, key, monthly cap and timeout but no AI_ENABLED, model or per-account cap; migrations 0001-0003 contain no ai_usage; no /ask route, template, evaluator agent, evals/ or AI tests. Corrections to the audit: a Playwright harness already exists (tests/e2e/test_smoke.py), docs/RUNBOOK.md does not exist, students have no browser session (only reviewers use cookies), DECISIONS line refs were stale, and "spending limits and alerts tested" is a section 12 gate. Whole pipeline builds against a FakeProvider in parallel with all other areas; only the live evaluation needs a key, staging and published records. The Ask screen must give a deterministic "not verified" answer even with AI off (Step 15 tester task).

**Already done**

- AI package placeholder: docstring only stating non-negotiables (no KB write, no vault, PII redaction, 15 s timeout, atomic reservation); no code - Evidence: F:\the competetion project\app\ai\__init__.py (10 lines, confirmed)
- Settings: ai_provider=gemini, gemini_api_key, ai_monthly_spend_cap_inr=5000, ai_request_timeout_seconds=15, ai_configured property (key presence only); Settings frozen and lru_cached - Evidence: F:\the competetion project\app\core\config.py lines 27, 36-39, 54-62 (confirmed)
- Env var names documented: AI_PROVIDER, GEMINI_API_KEY, AI_MONTHLY_SPEND_CAP_INR, AI_REQUEST_TIMEOUT_SECONDS - Evidence: F:\the competetion project\.env.example lines 26-30 (confirmed)
- /health reports ai_configured - Evidence: F:\the competetion project\app\api\health.py line 23 (confirmed); unit test in tests\unit\test_health.py
- Provider decision: Gemini, owner-confirmed; flash vs pro open until M5 - Evidence: F:\the competetion project\docs\DECISIONS.md entry '2026-09-19 -- AI provider: Google Gemini API (owner-confirmed)' now at line 495 (audit's 476-484 was stale); build pack line 57
- AI controls and AI quality gate written as policy; data-flow row for runtime AI - Evidence: F:\the competetion project\docs\SECURITY.md lines 39-44, 62, 81 (confirmed)
- UI contract: AI-unavailable/budget-exhausted copy and canned-prompt rule for Ask BCION entry points - Evidence: F:\the competetion project\docs\UI.md lines 63, 90 (confirmed)
- Reusable grounding helpers: field_value_for and _safe_source_url (published-only filtering, safe URL schemes); a second _safe_source_url exists in eligibility.py - Evidence: F:\the competetion project\app\planning\comparison.py lines 100, 131; app\api\eligibility.py line 84 (confirmed)
- claims.extracted_by ('human'|'ai') with DB check, API Literal validation, verifier-never-'ai' rule, and edit-invalidates-approval trigger covering extracted_by - Evidence: db\migrations\0001_init.sql lines 58-63; db\migrations\0003_maker_checker.sql line 92; app\api\claims.py lines 88-103; tests\db\test_api_claims.py line 108 (audit said 96)
- Playwright e2e harness exists with 6 smoke tests covering explore, compare, requirements, timeline and reviewer queue (audit and STATUS summary said no e2e) - Evidence: F:\the competetion project\tests\e2e\conftest.py, tests\e2e\test_smoke.py lines 124-297; commit 2db356e
- data-security-reviewer and ux-qa-reviewer agent definitions exist; ai-evaluator does not - Evidence: F:\the competetion project\.claude\agents\ (two files only, confirmed by glob)
- Parallel multi-agent workflows now allowed by decision (removes the old 'no agent swarm' rule); build pack s7 constraints on migrations/shared schema still apply - Evidence: F:\the competetion project\docs\DECISIONS.md line 8 (2026-09-21 entry, uncommitted working copy)

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| AI_ENABLED flag (off by default) and kill switch missing; ai_configured is key-presence only; no ai_model, token-limit or per-account cap settings | Build pack s4 Runtime AI row; s7 Spend controls; Step 5 'AI disabled' | phase1-required |
| No provider-agnostic adapter, Gemini implementation or fake provider | Build pack s4 Runtime AI row; Step 11 | phase1-required |
| ai_usage table absent from migrations 0001-0003; no atomic reservation, per-account or global cap enforcement, or actual-usage recording | Build pack s6 Tables; s7 Spend controls; SECURITY.md AI controls | phase1-required |
| No identity/rate limit step for AI requests; no app-level rate limiting anywhere (only Supabase 429 handling in app/api/auth.py); students have no browser session (cookies only in reviewer_pages.py), so account-only Ask BCION has no identity to key caps on yet | Build pack s6 AI request pipeline step 2 | phase1-required |
| No retrieval-of-approved-records module or domain-function fact computation for AI context | Build pack s6 AI request pipeline steps 3-4; CLAUDE.md non-negotiable 1 | phase1-required |
| No answer schema, referenced-ID validation, server-owned fact cards/citations or 'not verified' path | Build pack s6 AI request pipeline steps 5-7 | phase1-required |
| No PII redaction / outbound payload allow-list before the external call | SECURITY.md line 44; line 81 data-flow row | phase1-required |
| No forbidden-output guard (rank prediction, not suited, personality labels, guarantees) | CLAUDE.md non-negotiable 3 | phase1-required |
| No Ask BCION screen, fixed prompt templates, AI-unavailable state, or deterministic out-of-coverage answer; Step 15 tester task 'ask a question outside coverage and notice the limitation' has no surface at all | Build pack s2 screens; s12 Step 15 tester tasks; UI.md lines 63, 90 | phase1-required |
| No mocked AI unit tests for the s7 gate list | Build pack s7 Quality gates (AI) | phase1-required |
| No AI-off journey test ('the application works with AI disabled' is a section 12 gate) | Build pack Step 11; s12 Before admitting 100 users | phase1-required |
| No 30+ question live evaluation set or capped runner (10+ Hindi/Roman Hindi); no evals/ directory | Build pack s7 Quality gates; Step 11 | phase1-required |
| AI evaluator agent definition missing | Build pack s7 Agents | phase1-required |
| Provider terms not reviewed; restricted key and provider-side cap not configured; model not pinned | Build pack s4; SECURITY.md line 81; DECISIONS.md Gemini entry | phase1-required |
| Spend threshold alerts and AI fallback-rate metric absent; 'spending limits and alerts have been tested' is an explicit gate before 100 users (audit under-rated this as nice-to-have) | Build pack s7 Spend controls; s12 Before admitting 100 users; s12 Expansion checks | phase1-required |
| Distress-keyword rule not wired to the Ask free-text field (rule itself owned by safeguarding area; explicitly excluded from BCI-004) | Build pack s3 Distress row; s6 Consent and safeguarding; tasks/BCI-004.md line 47 | phase1-required |
| No person sign-off step for sending minors' text to an external provider (model review alone may not sign off child data) | Build pack s7 Quality gates last sentence; CLAUDE.md non-negotiable 4 | launch-blocker |
| docs/RUNBOOK.md does not exist, so the kill-switch procedure has nowhere to live | Build pack s7 Memory in files | phase1-nice |
| Env name mismatch: build pack line 275 says AI_PROVIDER_KEY, code uses GEMINI_API_KEY | Build pack line 275; .env.example | defer |
| Hindi answers while UI and fact-card labels are English only | Build pack Step 11 '10+ Hindi cases'; Step 12 | phase1-nice |
| AI-assisted claim extraction (extracted_by='ai' drafting) not built; required by no gate | Build pack s6 Publishing | defer |

**Owner decisions**

- Gemini model: flash vs pro - Blocks: AI-11 only; all other tasks are model-agnostic - Recommended default: Pin the current flash-class model via AI_MODEL; move to pro only if the 36-question evaluation fails grounding or Hindi quality after one fix round. Record measured cost per answer.
- Who may use Ask BCION: guests or signed-in accounts - Blocks: AI-1, AI-4 cap keys, AI-7 access - Recommended default: Live model answers for signed-in accounts only; guests get the same Ask page in deterministic mode (fact cards plus not-verified), so the Step 15 out-of-coverage task works for everyone. Revisit at Step 16.
- Cap values - Blocks: AI-2, AI-4 - Recommended default: Global Rs 1,000/month during the trial, 20 answers per account per day, about 600 input-record tokens and 400 output tokens, one request in flight per account.
- Free-text follow-up or fixed prompts only - Blocks: AI-7, injection and PII surface - Recommended default: Fixed prompt buttons plus one optional 200-character follow-up; no chat, no memory. If the distress rule is not delivered by the safeguarding area in time, ship fixed prompts only.
- Gemini paid vs free tier - Blocks: AI-10, data-flow acceptance - Recommended default: Paid tier with a provider budget cap, subject to the owner reading current terms; pilot volume spend is negligible.
- Hindi answer scope while the UI is English - Blocks: AI-9, AI-11, AI-16 - Recommended default: Accept Hindi/Roman Hindi input and answer in the asker's language; fact cards stay English until Step 12; a Hindi-preferring person reviews all Hindi eval answers.
- Is live AI required for the 10-user trial - Blocks: Critical-path placement of AI-10, 11, 12, 16, 17 - Recommended default: No. Ship the deterministic Ask page for the trial regardless; enable the model only if AI-17 is signed before the trial starts, otherwise run the trial with AI off and do the live evaluation before Step 16.

**Tasks**

### AI-1 - Freeze the AI contract (task card + schemas)

- What: Write the AI task card and an ARCHITECTURE.md AI section; add Pydantic-only app/ai/schemas.py: AskRequest (template_id, context pathway ids, optional follow-up <=200 chars, lang), Answer (explanation, referenced_record_ids, missing_information, assumptions, next_actions, status ok/not_verified/ai_unavailable/budget_exhausted/unsupported), Provider protocol signature, typed errors, settings names, account-vs-guest policy.
- Acceptance: Schemas import, mypy/ruff clean; card names one test per s7 AI gate case; DECISIONS.md entry records owner-decision defaults; no provider or DB code.
- Step: 11 (wave 0)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: none
- Touches: tasks/BCI-0xx-bounded-ai.md, app/ai/schemas.py, docs/ARCHITECTURE.md, docs/DECISIONS.md
- Reviewers: data-security-reviewer
- Risk: Loose contract forces rework in every later AI task

### AI-2 - AI_ENABLED flag, kill switch and AI settings

- What: Add ai_enabled (default False), ai_model, ai_max_input_tokens, ai_max_output_tokens, ai_per_account_daily_cap to Settings and .env.example (names only). Add ai_available property = ai_enabled AND key present. /health reports ai_enabled. Kill switch is env flip plus restart because Settings is lru_cached and frozen.
- Acceptance: Unit tests: defaults give ai_available False; key alone does not enable; /health shows both flags; existing test_health still passes.
- Step: 11 (wave 0)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: app/core/config.py, .env.example, app/api/health.py, tests/unit/test_health.py, tests/unit/test_config_ai.py
- Reviewers: none
- Risk: low; config.py is a shared file, merge early

### AI-3 - Provider adapter: protocol, FakeProvider, Gemini over httpx

- What: app/ai/provider.py Protocol generate(system, user, json_schema, max_tokens, timeout). Scripted FakeProvider. GeminiProvider via plain httpx REST, JSON response mode, hard 15 s timeout, zero retries, no model fallback, key never logged.
- Acceptance: httpx MockTransport tests: success, timeout, 429, 5xx, malformed JSON, missing key map to typed errors; exactly one request per call; no network in tests.
- Step: 11 (wave 1)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: AI-1, AI-2
- Touches: app/ai/provider.py, app/ai/gemini.py, app/ai/fake.py, tests/unit/test_ai_provider.py
- Reviewers: data-security-reviewer
- Risk: Gemini REST shape may have drifted; verified only in AI-11

### AI-4 - ai_usage migration and atomic budget reservation

- What: New migration (next number after 0003, assigned by the migration serialiser) creating ai_usage: account id, template_id, reserved/actual tokens and paise, status, created_at; no prompt text. SECURITY DEFINER reserve and settle functions enforcing per-account daily and global monthly caps in one transaction. RLS denies cross-user reads. Python wrapper app/ai/budget.py.
- Acceptance: make test-db: concurrent reservations never exceed global cap; per-account cap enforced; guest/student A/student B/reviewer matrix on ai_usage; cap hit returns budget_exhausted with no provider call.
- Step: 11 (wave 7)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0.5
- Depends on: AUTH-15, AI-1
- Touches: db/migrations/0004_ai_usage.sql (or next free number), app/ai/budget.py, tests/db/test_ai_usage.py
- Reviewers: data-security-reviewer
- Risk: Only AI task touching shared schema

### AI-5 - Retrieval of approved records and deterministic facts

- What: app/ai/retrieval.py: for given pathway ids fetch only published, non-synthetic claims, re-check status in code even with a reviewer-scoped client, flag stale, call existing app/rules cost/timeline/eligibility functions for numbers, emit compact records with server-assigned short ids. Reuse comparison.field_value_for and _safe_source_url. No student-table access.
- Acceptance: Tests: draft, in_review, superseded and synthetic claims never returned even with reviewer client; stale flagged; empty set gives not_verified; module imports nothing touching saved_plans or student_profiles.
- Step: 11 (wave 1)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: AI-1
- Touches: app/ai/retrieval.py, tests/unit/test_ai_retrieval.py, tests/db/test_ai_retrieval_live.py
- Reviewers: data-security-reviewer
- Risk: Unapproved claim leaking into a prompt

### AI-6 - Pipeline orchestration, prompt templates, validation, guards

- What: app/ai/pipeline.py: validate input and template allow-list, ai_available, reserve budget, retrieve, build prompt from fixed templates with records wrapped as untrusted data, outbound allow-list/PII scrub, provider call, schema validation, reject ids outside retrieved set, forbidden-phrase guard, settle usage. Every failure degrades to deterministic fact cards plus status. With AI off it still returns not_verified/fact cards.
- Acceptance: FakeProvider tests for every s7 case: wrong source id, unsupported claim, stale evidence, injection in record and user text, timeout, overspend, no key, outage, forbidden phrases; never raw model prose on failure; logs hold no user text.
- Step: 11 (wave 8)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0
- Depends on: AI-3, AI-4, AI-5
- Touches: app/ai/pipeline.py, app/ai/prompts.py, app/ai/guards.py, tests/unit/test_ai_pipeline.py, tests/fixtures/ai_pipeline/
- Reviewers: data-security-reviewer, ai-evaluator
- Risk: Core non-negotiable lives here

### AI-7 - Ask BCION route and screen

- What: POST /ask (JSON) and GET/POST /ask/view zero-JS page: fixed prompt buttons per context, optional 200-char follow-up, server-rendered fact cards with _trust_badge.html and citation links from retrieved records only, missing-info and assumptions lists, UI.md AI-unavailable copy. Register router in app/main.py. Works in deterministic mode when AI is off.
- Acceptance: Tests: citations come only from server records; model-text XSS probe escaped; AI off shows exact UI.md copy plus fact cards; out-of-coverage prompt shows not-verified limitation; access follows AI-1 policy.
- Step: 11 (wave 9)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: AI-6, AUTH-3
- Touches: app/api/ask.py, app/web/ask_pages.py, app/web/templates/ask.html, app/main.py, tests/unit/test_ask_api.py, tests/db/test_ask_view.py
- Reviewers: ux-qa-reviewer, data-security-reviewer
- Risk: app/main.py is a shared one-line touch

### AI-8 - AI-off journey regression

- What: Unit-level journey test plus one Playwright spec in the existing tests/e2e harness walking explore, compare, timeline, requirements (and save once that UI exists) with AI_ENABLED=false and with AI on but FakeProvider failing.
- Acceptance: Both modes pass with no key and no network; no journey page returns 5xx; difficult-state copy asserted; no dead Ask buttons.
- Step: 11 (wave 11)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: UI-11, AI-7
- Touches: tests/unit/test_ai_off_journey.py, tests/e2e/test_ai_off.py
- Reviewers: ux-qa-reviewer
- Risk: low

### AI-9 - AI evaluator agent definition and evaluation set

- What: Write .claude/agents/ai-evaluator.md (trigger, exclusions, read and run-eval tools only, input contract, checklist grounding/refusal/cost/latency, capped budget, no student data, stop conditions). Author evals/ask_bcion_questions.yaml: 36 questions, 12+ Hindi/Roman Hindi, covering supported, ambiguous, unsupported, stale, injection, source mismatch, API failure, including all-India and foreign out-of-coverage cases. Labelled invalid fixtures for calibration.
- Acceptance: Schema test validates the YAML; each category has 4+ cases; all content synthetic-labelled or keyed by record id placeholders; evaluator flags every seeded bad fixture in a dry run.
- Step: 11 (wave 4)
- Needed by: ten-user-trial
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: AI-1, DOCS-4
- Touches: .claude/agents/ai-evaluator.md, evals/ask_bcion_questions.yaml, tests/unit/test_eval_set_schema.py, tests/fixtures/ai_invalid/
- Reviewers: human
- Risk: Model-written Hindi may be unnatural; see AI-16

### AI-10 - Owner: provider terms, restricted key, provider-side cap

- What: Owner reads current Gemini API terms for retention and training on the chosen tier, records the finding in the SECURITY.md data-flow row and DECISIONS.md; creates a key restricted to the Generative Language API; sets a provider budget alert/quota near Rs 1,000; places the key in staging env only.
- Acceptance: Dated DECISIONS.md entry with tier and cap; key exists only in provider dashboard and server env; never in repo or any agent session.
- Step: 11 (wave 0)
- Needed by: ten-user-trial
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 1.5
- Depends on: none
- Touches: docs/SECURITY.md, docs/DECISIONS.md
- Reviewers: human
- Risk: Free tier may permit training on prompts

### AI-11 - Capped live evaluation runner and first run

- What: scripts/run_ai_eval.py runs the question set through the real pipeline against staging published data with a hard spend ceiling that aborts, writing per-question status, referenced ids, tokens, latency and cost to a JSON report. ai-evaluator scores grounding and refusal; owner reviews every failure. Flash model first.
- Acceptance: Committed report with no student data: 0 invented facts, 0 citations outside retrieved set, 0 forbidden phrases, all injection cases safe, p95 under 15 s, cost per answer recorded.
- Step: 11 (wave 9)
- Needed by: ten-user-trial
- Executor: mixed
- Model tier: standard
- Dev sessions: 1
- Human hours: 1
- Depends on: AI-6, AI-9, AI-10, CONTENT-9, DEPLOY-7
- Touches: scripts/run_ai_eval.py, evals/reports/, STATUS.md
- Reviewers: ai-evaluator, human
- Risk: Blocked by content and staging, not by code

### AI-12 - Fix round from evaluation and enable AI on staging

- What: One reserved session to fix prompt or guard failures from AI-11 and rerun failed categories; then owner flips AI_ENABLED=true on staging and performs one kill-switch drill. Production stays off until AI-17.
- Acceptance: Rerun report meets AI-11 criteria; drill recorded (flag off, journey works) in the ops runbook or DECISIONS.md.
- Step: 11 (wave 11)
- Needed by: ten-user-trial
- Executor: mixed
- Model tier: standard
- Dev sessions: 1
- Human hours: 0.5
- Depends on: AI-11, AI-16, OPS-7
- Touches: app/ai/prompts.py, app/ai/guards.py, evals/reports/
- Reviewers: ai-evaluator
- Risk: Two-failed-fixes rule; if flash cannot pass, escalate model choice to owner

### AI-13 - Spend and fallback metrics, threshold alert, tested

- What: scripts/ai_spend_report.py (month spend vs cap, fallback rate, requests per account, no content) and app/ai/alerts.py firing a once-per-threshold notice at 50/80/100 percent through the existing N8N_WEBHOOK_URL. No new migration, no reviewer page. Owner runs one test with a tiny cap to satisfy the section 12 gate.
- Acceptance: Seeded synthetic usage gives correct totals; each threshold notice fires exactly once in tests; owner-recorded cap-hit test on staging shows degrade to deterministic answer.
- Step: 16 (wave 9)
- Needed by: expand-100
- Executor: mixed
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0.5
- Depends on: AI-4, AI-6
- Touches: scripts/ai_spend_report.py, app/ai/alerts.py, tests/unit/test_ai_alerts.py, tests/db/test_ai_spend_report.py
- Reviewers: data-security-reviewer
- Risk: low

### AI-14 - AI-assisted claim extraction drafts (not scheduled)

- What: Optional reviewer tool drafting a candidate claim with extracted_by='ai'. Required by no section 12 gate; manual entry is adequate for the pilot's record counts.
- Acceptance: Not scheduled; if ever built, AI drafts reach published only through the existing maker-checker path.
- Step: cross (wave 2)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 2
- Human hours: 0
- Depends on: AI-3
- Touches: app/ai/extraction.py
- Reviewers: data-security-reviewer
- Risk: Over-engineering for the pilot

### AI-16 - Hindi-preferring person reviews Hindi questions and answers

- What: A Hindi-preferring person (not the owner-author if possible) checks the 12+ Hindi/Roman Hindi evaluation questions for naturalness before the run, then reads every Hindi answer in the AI-11 report for correctness, tone and forbidden claims.
- Acceptance: Signed note in the eval report: questions accepted or reworded; each Hindi answer marked pass/fail with reason.
- Step: 11 (wave 10)
- Needed by: ten-user-trial
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 2
- Depends on: AI-9, AI-11, I18N-6
- Touches: evals/reports/
- Reviewers: human
- Risk: Finding the person; schedule early

### AI-17 - Owner sign-off to enable AI for real users

- What: Owner reviews AI-11/12 reports, AI-10 terms finding, the outbound payload allow-list, and confirms consent gate and data-flow acceptance are complete; records a dated decision to enable AI (or run the trial with AI off, deterministic Ask only).
- Acceptance: DECISIONS.md entry naming the exact commit, model, caps and who approved; AI_ENABLED on production changed only after this entry.
- Step: 11 (wave 12)
- Needed by: ten-user-trial
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 0.5
- Depends on: AI-12, CONSENT-11, CONSENT-7, SEC-8
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: Model review alone may not sign off child data

**Merged into other tasks**

- AI-15 -> UI-11

## Cross-cutting security and privacy

Area: `security-privacy`

Verified against code: the access core is real (per-request RLS-scoped clients, no service role in app/, RLS on all seven tables, DB-level maker-checker, hardened /reviewer cookie, URL-scheme allowlist). The audit's gaps mostly hold, with corrections: CI does NOT run the db/RLS suite (ci.yml passes no Supabase env, so tests/db silently skips); APP_SECRET_KEY and SUPABASE_JWT_SECRET are read nowhere; explore.html has an inline script that a strict CSP breaks; the build pack file must not be edited; no Dockerfile or deploy/ exists. SEC-10 split into agent review plus a separate human sign-off; three tasks added (CI db wiring, human sign-off, VM log purge/bind check). 14 tasks, ~13 dev sessions (2 deferrable), ~9 human hours.

**Already done**

- Per-request, never-cached Supabase client using only the publishable key plus the caller's token; no service-role path in app code - Evidence: F:\the competetion project\app\db\client.py; F:\the competetion project\app\api\deps.py; Grep of app/ for SERVICE_ROLE / service_role returns nothing; .env.example marks SUPABASE_SERVICE_ROLE_KEY test-only and DATABASE_URL ops-only
- RLS enabled on sources, careers, pathways, claims, student_profiles, reviewers (no policy = deny) and saved_plans (own-row); is_reviewer() is security definer with pinned search_path - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 118-177; F:\the competetion project\db\migrations\0002_saved_plans.sql lines 55-58
- Synthetic-source publish block (trigger) and maker-checker state machine (trigger, security invoker, search_path pinned) plus tightened update policy; API sets created_by from the caller's own id - Evidence: F:\the competetion project\db\migrations\0001_init.sql lines 76-93; F:\the competetion project\db\migrations\0003_maker_checker.sql lines 58-136; F:\the competetion project\app\api\claims.py line 148
- Live access-matrix test files exist for guest/A/B/reviewer (not run by me; STATUS.md reports 239 passing locally). They run only where Supabase env vars are set - NOT in CI - Evidence: F:\the competetion project\tests\db\ (test_rls.py, test_client_isolation.py, test_api_plans.py, test_maker_checker.py, test_reviewer_console.py, test_web_pages.py, conftest.py lines 42-122 skip logic)
- Reviewer session cookie: httponly, samesite=lax, secure only when APP_ENV=production, path=/reviewer, max_age from Supabase expires_in, token re-validated with auth.get_user per request, stale cookie cleared - Evidence: F:\the competetion project\app\web\reviewer_pages.py lines 62-127, 178-194
- Frozen settings, env-only config, /docs disabled only when APP_ENV=production, AI timeout/cap names present - Evidence: F:\the competetion project\app\core\config.py; F:\the competetion project\app\main.py line 31
- .env files git-ignored; .env.example holds names only - Evidence: F:\the competetion project\.gitignore lines 14-17; F:\the competetion project\.env.example
- The single logging call site logs only opaque user_id and pathway_id (but with exc_info=True, see gaps); app/ai has no logging calls at all - Evidence: F:\the competetion project\app\api\auth.py lines 125-133; Grep of app/ for logger/logging
- Data-flow map drafted; Supabase DB/auth/storage confirmed Mumbai; build pack row records backups Mumbai and Gemini outside India (SECURITY.md copy of those two rows is staler than the build pack) - Evidence: F:\the competetion project\docs\SECURITY.md lines 75-90; F:\the competetion project\docs\BCION-Lite-Build-Pack.md lines 138-149
- data-security-reviewer agent defined read/test only with person-not-model sign-off rule; calibration described but never performed - Evidence: F:\the competetion project\.claude\agents\data-security-reviewer.md
- CI runs ruff, mypy and unit tests with no secrets; dependencies range-bounded; npm side has package-lock.json - Evidence: F:\the competetion project\.github\workflows\ci.yml; F:\the competetion project\pyproject.toml; F:\the competetion project\package-lock.json
- http/https-only scheme allowlist on evidence links and Jinja autoescape (per STATUS.md prior review; evidence link uses target=_blank rel=noopener) - Evidence: F:\the competetion project\STATUS.md lines 162-200; F:\the competetion project\app\web\templates\_trust_badge.html line 40

**Gaps**

| Gap | Spec ref | Severity |
|---|---|---|
| No security headers and no middleware at all (app/main.py registers none): no CSP, nosniff, frame-ancestors, Referrer-Policy, HSTS, Permissions-Policy, TrustedHost. explore.html lines 79-95 contain an inline \<script>, so a script-src 'self' CSP breaks it unless moved to a static file | Build pack s7 Quality gates; s10 'callbacks and origins restricted' | launch-blocker |
| No Cache-Control: no-store on authenticated/personal pages (reviewer queue now, My Plan later); logout/cache gate untested | Build pack s7 Privacy gate; s12 Step 15 task 'log out safely on a shared device' | launch-blocker |
| CSRF defence is SameSite=Lax only, on /reviewer only; no Origin/Referer check; no frozen posture for the student cookie session that auth-sessions-plans must build | docs/SECURITY.md Access model; build pack s7 Contracts 'guest and signed-in authorisation' | launch-blocker |
| No rate limiting in app or proxy; only Supabase Auth's own limits (429 passthrough) protect sign-in/sign-up; the AI layer has only an in-memory daily request count | Build pack s7 Spend controls 'no retry cascade'; s12 expansion checks 'failed logins' | phase1-required |
| No logging configuration, redaction filter or PII-free-log test; uvicorn/nginx access logs record full query strings; auth.py line 131 logs exc_info=True whose postgrest error text is unfiltered | Build pack s4 Monitoring; s7 Privacy gate 'PII-free logs'; s9 Step 13 'Redacted logs' | launch-blocker |
| Eligibility inputs (age, marks_percentage, subjects_studied, domicile_state) travel as GET query params on /requirements/view (requirements.html line 28 method=get; pages.py lines 205-214) and GET /eligibility - into access logs, shared-device history and Referer (evidence links are rel=noopener only, not noreferrer) | docs/DATA.md optional sensitive fields; build pack s8 row 2 | launch-blocker |
| POST /auth/sign-up returns detail=str(exc) for unstructured exceptions (auth.py line 162) | docs/SECURITY.md Quality gates | phase1-required |
| Nothing stops a staging/production boot with APP_ENV unset (cookie 'secure' off, /docs on) or Supabase unset. APP_SECRET_KEY (insecure default) and SUPABASE_JWT_SECRET are read nowhere in app/ - dead secret names that should be removed or actually used, not merely guarded | docs/SECURITY.md Standards; build pack s7 Deployment | phase1-required |
| No grants/exposure audit: no revoke in any migration; forbid_publishing_synthetic_claims() and touch_updated_at() have no pinned search_path; no catalogue test enumerating every table, view, function, bucket (grants state inferred, not queried) | Build pack s4 'RLS tested on every exposed table, view, function and bucket' | launch-blocker |
| CI never runs the access matrix: ci.yml invokes pytest tests/db but passes no SUPABASE_* env, so the whole module skips and the job is green; its header comment is also stale. 'Cross-user access tested every time auth/RLS/publication changes' is therefore enforced only by whoever remembers to run make test-db locally | CLAUDE.md non-negotiable (cross-user access tested every time); build pack s7 Hooks 'no success via skipped suites' | launch-blocker |
| Local db suite uses SUPABASE_SERVICE_ROLE_KEY against the single live Supabase project that is also the would-be production database; synthetic users and rows live in it | Build pack s7 Deployment 'No synthetic records in production; no production credential in the everyday environment' | launch-blocker |
| Storage buckets: none exist, and nothing asserts that or would guard a future one | Build pack s4 'and bucket'; s7 Access gate 'storage' | phase1-required |
| Field-level encryption for optional sensitive fields not implemented; those fields are not persisted today | Build pack s8 row 1 | defer |
| Data-flow map stale and unaccepted: SECURITY.md app row says 'VPS, Mumbai (once provisioned)' and backups 'region to confirm' while the app runs on an Oracle VM whose region DECISIONS.md never records; email (Supabase Auth confirmation mail already in use), monitoring, WhatsApp, n8n rows have no vendor/region; no written owner acceptance | Build pack s8 final rule; docs/SECURITY.md Data-flow map Rule | launch-blocker |
| No pinned Python lockfile (ranges only; CI does pip install -e .[dev]); no Dockerfile (make build is an echo); no dependency vulnerability audit | Build pack s10 lockfile row; s12 Built means 'pinned dependencies' | phase1-required |
| No secret scanning in CI; no secret-warning hook | Build pack s7 Hooks; CLAUDE.md 'no secrets in repo' | phase1-required |
| /reviewer/queue?error= renders any attacker-supplied text as a styled alert inside the authenticated console (autoescaped, so content spoofing not XSS) | docs/SECURITY.md Publishing security; s7 Quality gates | phase1-nice |
| data-security-reviewer never calibrated on labelled invalid fixtures although Step 3 is marked complete | Build pack s7 Agents; s9 Step 3 | phase1-required |
| No release security review, docs/KNOWN_ISSUES.md, docs/RELEASE_CHECKLIST.md, exception register or human sign-off record | Build pack s7 Quality gates last sentence; s9 Step 13; s12 Built means | launch-blocker |
| Reviewer sign-out only deletes the cookie; the Supabase access token stays valid until expiry (about an hour) | Build pack s7 Privacy gate 'logout' | phase1-nice |
| Existing VM logs already contain query-string eligibility inputs (synthetic so far); Makefile dev target binds 0.0.0.0 - the systemd unit's bind address on the VM is asserted in STATUS.md but not checkable from the repo | Build pack s8 row 2 | phase1-required |
| CERT-In incident-reporting awareness not written down | docs/SECURITY.md Standards (aspirational) | defer |

**Owner decisions**

- Persist optional sensitive fields (marks, category, income) or keep them request-only for the pilot? - Blocks: SEC-11; field-level-encryption wording in the data-flow map - Recommended default: Request-only, never stored, for the whole pilot; record under SEC-8; SEC-11 dropped.
- Keep the app on the Oracle VM (record its region) or move to a Mumbai VPS as the build pack states? - Blocks: SEC-8 acceptance and therefore any real minor's data - Recommended default: If the VM is in an Indian Oracle region (Mumbai/Hyderabad) keep it and update the map; otherwise use it for guest-only staging and admit no real account until moved or accepted in writing.
- Separate test/staging and production Supabase projects, and which one the service-role test suite and CI may touch - Blocks: SEC-12, SEC-10; 'no synthetic records in production' - Recommended default: Treat the current project as test/staging forever; create a fresh Mumbai project for production at Step 14; service-role key lives only in local test env and the CI secret for the test project.
- Name the human who signs off child data and production security (not the author) - Blocks: SEC-13 and every real user - Recommended default: Engage the build pack's budgeted part-time QA/security reviewer for one 4-hour slot in week 8-9; book now. Until named, work proceeds but nobody real is admitted.
- CSRF approach for zero-JS cookie sessions - Blocks: SEC-2 and student session design in auth-sessions-plans - Recommended default: Origin/Referer allow-list plus SameSite=Lax, no token store. Proceed unless the owner objects.
- Rate-limit thresholds - Blocks: SEC-3 tuning only - Recommended default: Sign-in/sign-up 5 per minute per IP burst 10; ask route 10 per minute; general 60 per minute burst 120; revisit after the ten-user trial because of school NAT.
- Approve free CI tools (pip-audit, gitleaks) and whether to add any secret-warning hook to Claude Code settings - Blocks: SEC-7 scan steps - Recommended default: Approve both CI tools (free, no new vendor receives data). Skip a Claude settings hook; CI scan plus optional pre-commit is enough for the pilot.
- Remove unused APP_SECRET_KEY and SUPABASE_JWT_SECRET names, or keep them for a planned use - Blocks: SEC-1 config guard wording - Recommended default: Remove both from config.py and .env.example unless auth-sessions-plans commits to local JWT verification or signed cookies; fewer secrets to hold.

**Tasks**

### SEC-1 - Security middleware: headers, no-store, trusted hosts, env guard

- What: Add one middleware module: CSP (self only, no inline), nosniff, frame-ancestors none, Referrer-Policy no-referrer, Permissions-Policy, HSTS in production, Cache-Control no-store on responses to cookie/bearer requests, TrustedHostMiddleware from ALLOWED_HOSTS. Move explore.html's inline script to app/static/js/explore.js. Fail startup when APP_ENV is staging/production and Supabase unset or APP_ENV invalid; remove unused APP_SECRET_KEY/SUPABASE_JWT_SECRET names or document why kept.
- Acceptance: Unit tests assert each header on /explore and /reviewer/sign-in, no-store on a cookie request, 400 on foreign Host, boot failure with APP_ENV=production and no Supabase config. Explore selection counter still works under CSP; existing web tests pass.
- Step: cross (wave 0)
- Needed by: staging-demo
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: app/core/security_middleware.py, app/main.py, app/core/config.py, .env.example, app/web/templates/explore.html, app/static/js/explore.js, tests/unit/test_security_headers.py
- Reviewers: data-security-reviewer
- Risk: CSP breaking templates; app/main.py is a shared merge point with SEC-4 and every new router.

### SEC-2 - CSRF contract for cookie sessions (Origin check + SameSite) and reviewer error codes

- What: Record the CSRF decision in docs/DECISIONS.md and implement a reusable dependency rejecting state-changing requests that carry a session cookie unless Origin (fallback Referer) matches ALLOWED_HOSTS; keep SameSite=Lax, httponly, secure. Apply to /reviewer POSTs; export for the student session. Also replace the free-text /reviewer/queue?error= with a fixed code-to-message map.
- Acceptance: Cross-origin cookie POST to /reviewer/claims/{id}/approve gets 403 and claim unchanged; same-origin succeeds; cookie POST with neither Origin nor Referer rejected; bearer JSON API unaffected; arbitrary ?error= text is not rendered.
- Step: 8 (wave 1)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0
- Depends on: SEC-1, PUB-5
- Touches: app/core/csrf.py, app/web/reviewer_pages.py, app/web/templates/reviewer_queue.html, docs/DECISIONS.md, docs/SECURITY.md, tests/unit/test_csrf.py, tests/db/test_reviewer_console.py
- Reviewers: data-security-reviewer
- Risk: Behind nginx a wrong forwarded host makes every POST fail; verify through the real proxy on staging.

### SEC-3 - Proxy rate limiting for auth and AI endpoints

- What: Write an nginx limit_req/limit_conn snippet (per-IP zones) for /auth/*, /reviewer/sign-in, /plans writes and the AI ask route, plus a friendly static 429 page. Document Supabase Auth's own limits as the second layer. No Redis, no in-app limiter. Owner includes it in the VM site file.
- Acceptance: nginx -t passes on the VM; a 30-request burst to /auth/sign-in from one IP yields 429s while /explore is unaffected; thresholds recorded in docs/SECURITY.md.
- Step: 13 (wave 0)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0.5
- Depends on: none
- Touches: deploy/nginx/ratelimit.conf (new directory), app/static/429.html, docs/SECURITY.md
- Reviewers: data-security-reviewer
- Risk: School/carrier NAT puts many students behind one IP; generous burst, tight only on sign-in.

### SEC-5 - Move eligibility inputs out of URLs

- What: Change the Requirements form to POST-and-render (no redirect carrying values), add a POST body variant of /eligibility and keep GET for pathway_id only. Add rel="noopener noreferrer" on evidence links. Update the web-page and e2e tests in the same session.
- Acceptance: No HTML or JSON route accepts age, marks_percentage, subjects_studied or domicile_state in a query string; eligibility tests pass via POST; template test asserts noreferrer; zero-JS still works.
- Step: 7 (wave 1)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: standard
- Dev sessions: 1
- Human hours: 0
- Depends on: UI-2
- Touches: app/web/pages.py, app/api/eligibility.py, app/web/templates/requirements.html, app/web/templates/_trust_badge.html, tests/db/test_api_eligibility.py, tests/db/test_web_pages.py, tests/e2e/test_smoke.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: Breaking the recently un-skipped e2e Requirements tests.

### SEC-6 - Grants and exposure hardening migration plus catalogue test

- What: Append-only migration: revoke non-select table privileges from anon on knowledge tables and everything on student_profiles, saved_plans, reviewers; revoke EXECUTE from PUBLIC on functions except is_reviewer and maker_checker_schema_version; pin search_path on forbid_publishing_synthetic_claims and touch_updated_at. Add a psycopg catalogue test (DATABASE_URL, skips with reason if unset) failing on any public table without RLS, non-security_invoker view, or bucket without policy.
- Acceptance: Migration applies cleanly after 0001-0003 on a fresh database; full db suite green as guest/A/B/reviewer; catalogue test fails when a scratch no-RLS table exists and passes when removed; zero buckets asserted.
- Step: 4 (wave 0)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: strongest
- Dev sessions: 1
- Human hours: 0.5
- Depends on: none
- Touches: db/migrations/0004_grants_hardening.sql (number allocated by lead), tests/db/test_exposure_catalogue.py, tests/db/conftest.py, docs/SECURITY.md
- Reviewers: data-security-reviewer
- Risk: Over-revoking breaks supabase-py calls; run the whole live suite before merge. Current grants state is inferred, so the first step is a read-only catalogue query.

### SEC-7 - Pinned lockfile, dependency audit and secret scan in CI

- What: Generate hashed Linux lockfiles with uv or pip-tools (runtime and dev), switch CI and make install to them, add pip-audit and gitleaks CI jobs failing on high findings, and an optional .pre-commit-config.yaml secret check. No .claude/settings.json change (owner-only configuration). Dockerfile consumes the lockfile when staging-deploy creates it.
- Acceptance: CI installs only from the lockfile with hash checking; pip-audit and secret-scan jobs green; a planted fake key on a scratch branch turns the scan red; make install uses the lockfile.
- Step: 2 (wave 0)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: cheap
- Dev sessions: 1
- Human hours: 0
- Depends on: none
- Touches: requirements.lock, requirements-dev.lock, Makefile, .github/workflows/ci.yml, .pre-commit-config.yaml, README.md
- Reviewers: data-security-reviewer
- Risk: psycopg[binary] and playwright wheels differ Windows vs Linux; generate for Linux/py3.11. Conflicts with SEC-12 on ci.yml - serialise.

### SEC-8 - Data-flow map: confirm every row and record written owner acceptance

- What: Owner confirms: Oracle VM region (or move), Supabase Auth email sender/region, monitoring vendor region and retention, Gemini retention/training terms, WhatsApp used or dropped, n8n location, and that marks/category/income are request-only. Dev agent updates docs/SECURITY.md only (the build pack mirrors the online doc and is not edited); owner signs a dated acceptance in docs/DECISIONS.md.
- Acceptance: Every SECURITY.md map row has vendor, confirmed region and date, or is struck as not used; DECISIONS.md holds a dated owner acceptance naming the map's commit; no row says 'to confirm' or 'once provisioned'.
- Step: cross (wave 2)
- Needed by: real-users-gate
- Executor: mixed
- Model tier: cheap
- Dev sessions: 1
- Human hours: 2
- Depends on: OPS-1, DEPLOY-2, AI-10
- Touches: docs/SECURITY.md, docs/DECISIONS.md
- Reviewers: human
- Risk: If the Oracle VM is outside India the application row breaks the residency statement; decide early.

### SEC-10 - Pre-release security review run on the staging release candidate

- What: data-security-reviewer runs the full access matrix (guest/A/B/reviewer x read/write/delete/export/storage), headers, CSRF, rate limit, log scan, grants catalogue, secret scan, AI boundary, consent gate, logout/cache. Findings go to docs/KNOWN_ISSUES.md with owner, rationale, expiry; fixes are routed to owning areas; second session re-verifies. Drafts the security section of docs/RELEASE_CHECKLIST.md.
- Acceptance: Zero open critical/high findings; every lower exception has owner, rationale, expiry; every command and result listed, none claimed without being run; checklist security section ready for a human signature.
- Step: 13 (wave 10)
- Needed by: real-users-gate
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0
- Depends on: SEC-1, SEC-2, SEC-3, OPS-2, SEC-5, SEC-6, SEC-7, SEC-8, QA-9, QA-5, SEC-14, QA-6, QA-16, CONSENT-11, AUTH-12, AUTH-10, PUB-12, OPS-15, DEPLOY-7
- Touches: docs/KNOWN_ISSUES.md, docs/RELEASE_CHECKLIST.md, STATUS.md
- Reviewers: data-security-reviewer
- Risk: Join point for all areas; late findings push the trial.

### SEC-11 - Field-level encryption for optional sensitive fields (only if persisted)

- What: Only if the owner decides marks, category or income are stored: app-layer AES-GCM envelope encryption (key from an env name, key id per row) in a separate own-row table, covered by deletion and export. Recommended default is request-only, which voids this task (recorded under SEC-8).
- Acceptance: If built: ciphertext only at rest verified by raw SQL read; student B and reviewer cannot read; delete removes the row; key never in repo. If not: DECISIONS.md records request-only.
- Step: 8 (wave 5)
- Needed by: deferrable
- Executor: dev-agent
- Model tier: strongest
- Dev sessions: 2
- Human hours: 0.5
- Depends on: SEC-6, CONSENT-13
- Touches: app/core/crypto.py, db/migrations/ (new, number allocated by lead), tests/db/test_sensitive_fields.py, docs/DATA.md, docs/DECISIONS.md
- Reviewers: data-security-reviewer, human
- Risk: Key loss equals data loss; over-engineering for a stateless-eligibility pilot.

### SEC-13 - Human security and child-data sign-off

- What: A named person who is not the author reads SEC-10's evidence, spot-checks the access matrix and consent gate on staging, and signs the security section of docs/RELEASE_CHECKLIST.md against the exact commit. Booked at project start; model review cannot substitute.
- Acceptance: Signed, dated entry naming reviewer, commit hash and any accepted exceptions with expiry; recorded in DECISIONS.md; no real user admitted before this exists.
- Step: 13 (wave 11)
- Needed by: real-users-gate
- Executor: human-reviewer
- Model tier: none
- Dev sessions: 0
- Human hours: 4
- Depends on: SEC-10
- Touches: docs/RELEASE_CHECKLIST.md, docs/DECISIONS.md
- Reviewers: human
- Risk: Finding a competent reviewer is the long pole; book in week 1.

### SEC-14 - Owner: purge pre-hardening VM logs and confirm bind address

- What: After SEC-4 and SEC-5 deploy, the owner rotates/purges existing journald and any nginx/uvicorn logs for eduvation.service on the Oracle VM (they hold query-string eligibility inputs), confirms the unit binds 127.0.0.1 only, and confirms no service-role key or DATABASE_URL sits in the VM's app environment.
- Acceptance: Owner records in STATUS.md the commands run and results: logs purged with date, bind address shown as 127.0.0.1:8010, app env lists no SERVICE_ROLE or DATABASE_URL names.
- Step: 13 (wave 5)
- Needed by: real-users-gate
- Executor: owner
- Model tier: none
- Dev sessions: 0
- Human hours: 0.5
- Depends on: OPS-2, SEC-5, DEPLOY-7
- Touches: STATUS.md
- Reviewers: human
- Risk: Other apps share the VM; purge only this service's logs.

**Merged into other tasks**

- SEC-4 -> OPS-2
- SEC-9 -> QA-9
- SEC-12 -> QA-5
