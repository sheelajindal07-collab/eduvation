# BCION Lite — build pack

One consolidated plan for the 10–100 user pilot, replacing the four separate Lite documents (CTO plan, interface brief, execution blueprint, build guide) and the annexes that reviewed them. It is a proof of concept that precedes the national DPR's Phase −1; its budget is thousands of rupees a month plus development time. Nothing in the crore-level DPR applies to it. Where this pack and the DPR describe the same mechanic, the DPR has been aligned to this pack.

Mirrors the "Lite build pack" tab of the [BCION DPR and White Paper](https://claude.ai/artifact/6VmrbGfAfpvmueTUFzUqXa) living doc — that tab is the source of truth; re-sync this file if it changes.

## 1. Purpose and fit

Lite is Phase −2 of the national plan. It produces what Phase 0 asks for anyway: the technical spike (Tier-0 engines plus retrieval with server-controlled citations on a small verified dataset), a working demo for sponsor and state talks, the claims schema, and the first measurements for the DPR's hypothesis table (section 13 here). The first proof is simple: can 100 people obtain useful, sourced, understandable plans, and can a small team keep those plans accurate.

## 2. Scope

**Users.** 100 registered, about 10 concurrently active, load-tested at 25 sessions. Adult testers on synthetic profiles first; real Class 10–12 students only after the consent and safeguarding workflow is built and reviewed by a person.

**One journey.** Explore → compare up to three pathways → calculate time and cost → see requirements → save next actions. Seven screens (quick start, career explorer, pathway comparison, timeline and cost calculator, exam or programme detail, my action plan, Ask BCION) plus a reviewer console.

| Coverage item | Ceiling | Chosen around |
| --- | --- | --- |
| Career families | 20–30 | What the first 100 users actually ask about |
| Exams | 8–10: JEE Main, NEET-UG, GUJCET, CUET-UG, CLAT, NDA, SSC CGL, IBPS PO, GPSC Class 1–2, plus one on demand | A rule function with test cases per exam |
| Programme records | 50–100 with sourced fees, seats and admission route | Government institutions in the pilot state first, plus NIRF top-50 nationally |
| Scholarships | 10–20 | State schemes plus NSP and PM Vidyalaxmi |
| Admission rules | One state, in detail | Gujarat if confirmed: Gujarat board, GUJCET, ACPC, ACPUGMEC, GCAS; verify current names and rules |
| Languages | English and Hindi; Roman-script Hindi accepted as input | Critical content reviewed in both; Gujarati UI strings only if the cohort is Gujarati-medium |

First vertical slice: three careers, two exams, five programmes as unmistakably synthetic fixtures. Synthetic records never appear as verified facts.

**Left out.** Mock tests, social features, native apps, inbound WhatsApp bot, voice, lender integrations, psychometric scoring, autonomous web research, counselling service, national coverage, paid rankings.

## 3. Decisions taken from the four source documents

| Question | Decision | Reason |
| --- | --- | --- |
| Stack | FastAPI, Supabase (Mumbai), Mumbai VPS, n8n off the request path | The builder's familiar stack; runs the worker natively; no new provider. One flip condition in section 4 |
| Timeline | 12 weeks, two tracks, 16 steps | Software alone is 6–8 weeks; content, consent and usability rounds are the long pole |
| WhatsApp | One opt-in deadline-reminder template, no inbound bot | Students do not read email; the Cloud API is already in use |
| Content | Starts week 1 alongside Step 1; imported at Step 10 | Curating 50–100 sourced records and 5–10 rule functions takes longer than the code |
| Usability testing | Round 1 on staging after Step 7 (guest only); round 2 with the ten-user trial | The comparison screen must be tested by people before it is live |
| Consent and safeguarding | Built and reviewed by a person at Step 8 (week 4–6); a launch gate | "Design at M3, review later" never got built |
| Outcome measure | Five-item pre/post decision-quality instrument at sign-up and week 4 | Technical acceptance proves the software runs, not that it helps |
| Guest plans | Anonymous server session, random token, no personal fields, 7-day expiry | Local storage on a shared phone leaks a sibling's plan |
| Residency | "India-only" is a statement about the data-flow map, not the database region | Model processing and monitoring vendors sit outside India |
| Distress | Keyword rule returns the national tele-mental-health helpline (verify the current number at launch) and flags a named staff member within 24 h | No counselling is promised that does not exist |
| Development cost | Stated, not hidden | "Not a crore" must not read as "free" |

## 4. Stack

| Component | Lite implementation | Note |
| --- | --- | --- |
| Application | FastAPI monolith with separate modules for data, rules, planning and AI | One deployment; no microservices |
| Front end | Server-rendered templates or a light PWA served by the same app; Tailwind with the section-5 component set | No separate front-end framework unless already in daily use |
| Database, auth, storage | Supabase (Mumbai): Postgres, Auth, Storage, row-level security; separate staging and production projects | The app connects as a restricted role and passes the user's token to Postgres on every request; RLS tested on every exposed table, view, function and bucket |
| Background worker | One process on the Mumbai VPS reading a Postgres jobs table with leases, bounded retries and idempotency keys | No Redis, no broker |
| Workflow glue | n8n on the VPS: reviewer notifications, review-due reminders, scheduled source checks | Never on the request path |
| Reminders | One WhatsApp Cloud API template, opt-in, deadline only | Paise per message; no inbound handling |
| Runtime AI | Google Gemini API (owner-confirmed 2026-09-19) behind a provider-agnostic adapter; model — flash vs pro — open until M5; restricted key; per-account and global spend caps; 15-second timeout; AI_ENABLED off by default | No GPU, no multi-vendor gateway |
| Search | Postgres full-text plus a Hindi–Hinglish–English synonym table | Enough for a curated catalogue |
| Tests | pytest, Playwright for Python, accessibility checks, SQL policy tests against local Supabase | ruff and mypy for lint and types |
| Hosting and CI | Docker on the VPS; staging container behind a basic-auth gate; GitHub Actions with a protected production environment holding the deploy key | Or an owner-run deploy script |
| Monitoring | Error tracking, uptime check, structured logs without personal data | Vendor region recorded in section 8 |
| Not bought | Kubernetes, Redis, Kafka, Elasticsearch, graph or vector database, GPU, memory platform, agent orchestration, Vercel | |

**One flip condition.** If the owner intends Claude Code, not himself, to remain the maintainer of the front end and wants per-pull-request preview deployments, the build guide may be used verbatim with Next.js and Vercel (Mumbai region selected; plan and retention verified). Decide in Step 0, record it in docs/DECISIONS.md, do not revisit.

## 5. Interface brief

**Objective.** Within five minutes a student understands their options and knows their next useful action. The first result after quick start is three routes worth comparing, each with "why am I seeing this".

**Emotional progression.** Uncertainty → exploration → comparison → provisional decision → action → review. Never assessment → score → label. Use "Explore this route", "Save as an option", "You can change this later". Never "Your perfect career", "You are 92% suitable", "You must choose science".

**Navigation.** Four destinations: Explore (discover careers and routes), Compare (two or three shortlisted pathways), My Plan (current decision, next three actions, saved alternatives, what changed), Saved (careers, programmes, sources). Account, language, privacy and help in a utility menu. Ask BCION is contextual: fixed prompt templates on a cost card ("Explain these costs"), a pathway ("What changes if I take a gap year?"), an eligibility line ("Explain this requirement"); no blank chat box, no floating button.

**First visit.** Headline "Find your next step". Three starting choices: exploring my options; career in mind; need an alternative plan. Language visible immediately; no carousel, video or account wall. Quick start asks one question at a time: studying now; what to decide; interests; what matters most (affordable, near home, start work sooner, keep options open, a particular interest, not sure yet), with skip where not essential. No marks, income, category, phone or parent details upfront; a field is requested when a calculation needs it, with the reason. Account creation only to save or sync.

**Career card.** What would I do; how could I enter; what should I investigate; why am I seeing this. A reality-check section: common misunderstandings, hard parts, what to try before committing, routes worth comparing. No ranking by prestige, salary alone or family income; a limited budget reveals support and alternatives, never silently removes ambitious options.

**Comparison, the central screen.** Pathways, not career titles. Fields: entry requirements (met, not met, still unknown); main stages; time as a range with assumptions; total cost as verified charges plus separated estimates; funding as confirmed versus potential; location; work realities; alternatives if plans change; evidence with sources, dates and missing information. Desktop: side-by-side columns. Mobile: stacked sections or a pathway switch keeping the same field in view; no sideways-scrolling table. Closing prompt: "Which option would you like to investigate further?"

**Timeline and cost.** Editable milestones with required stages, optional stages and user assumptions distinguished; an unsuccessful attempt offers "Revise this scenario", never a failure badge. Three separate amounts: verified charges, estimated additional expenses, potential assistance not yet awarded; assumptions editable without re-entering the profile; no single impressive total.

**Trust labels, per field.** Checked against official source; Institution-reported; Estimate; Needs rechecking; Not available. Each consequential fact shows source authority, applicable cycle, verification date, official link and "Report an issue". A whole college never gets one green badge. Every recommendation shows why it appeared, which preferences influenced it, what remains unknown, how to change the preferences.

**Other people in Lite.** Parent: a student-approved family summary (options explored, time and cost assumptions, questions to discuss, a suggested next conversation); the consent screen states that the parent consents to the account and the student controls what the summary shows. Teacher: session guide, demonstration journey, printable prompts, referral route; no analytics dashboard. Support staff: only the authorised case summary (decision faced, options considered, constraints volunteered, unresolved questions). Institutions, coaching, lenders, employers: no student-facing controls.

**Visual direction.** Warm white background, deep charcoal text, one deep-blue accent, teal or green for positive states with text and icon, amber with explanation, red sparingly; Noto Sans with system-font fallback; generous spacing, short sections, one primary action per screen; 44–48 px touch targets; meaning never by colour alone; reduced-motion respected. No glass effects, giant gradients, decorative dashboards, stock graduation imagery, animated mascot.

**Difficult states, designed first.** AI unavailable or budget exhausted: "You can still compare routes and use the calculators." Eligibility uncertain: name the missing requirement. Information changed: say what changed and which saved plans may be affected; a "What changed" list under My Plan. No matching result: broader searches and alternatives. Save failed: keep the draft visible, never say "Saved". Weak connection: lightweight content and visible status. Shared device: easy sign-out, nothing sensitive persists, guest session expires. Permission denied: explain the boundary without exposing another user's data. Public content cached selectively; an offline deadline shows its last-checked date and needs online confirmation before consequential action.

**Design deliverables.** Three end-to-end journeys (undecided, goal-focused, alternative-seeking); low-fidelity quick start, explore, compare, plan; a clickable prototype with test-labelled content; a component set (cards, source labels, inputs, alerts, comparison sections, reminder opt-in, "what changed" list); error, loading, empty, stale-data and permission states; a moderated test script. Usability rounds of 5–8 participants including a shared-phone user, a Hindi-preferring user, a parent and a teacher; score task completion, not whether it "looks good".

## 6. Data and rules contracts

**Tables.** Identity: profiles, consents, access_grants. Careers: careers, pathways, pathway_stages, pathway_transitions. Opportunities: exams, exam_cycles, institutions, programmes, scholarships. Rules: rule_versions, rule_test_cases. Evidence: sources, source_versions, claims, review_events. Student work: saved_plans, plan_versions, reminders. Operations: jobs, feedback, audit_events, ai_usage. Typed columns for dates, amounts, durations and identifiers; JSON only for genuinely variable structures. Pathways are relational stages and transitions, not a graph database.

**Every critical claim carries.** Entity and field; value and unit; jurisdiction and academic cycle; source URL and document version; source publication date; checked and verified timestamps; review due date; reviewer and status; superseded claim ID. "Last fetched today" is never displayed as "verified today". A changed source is not automatically a changed rule.

**Eligibility returns three outcomes.** Meets the checked criteria; does not meet the checked criteria; insufficient information, review required. An unknown domicile rule or missing subject requirement never becomes a rejection. Rule functions are reviewed, versioned and cite their source; no visual rule editor in the pilot.

**Timeline.** Remaining education, optional preparation, user-chosen attempts, training or internship, parallel activities, backup transitions; durations are not blindly added because preparation, applications and internships overlap.

**Cost.** Official fees, estimated living expenses, user assumptions, confirmed assistance and potential assistance kept separate; an unawarded scholarship is never subtracted.

**Publishing.** Source entered → document captured → draft extracted → reviewer checks → published version → affected plans flagged. AI may draft, never publish. Critical rules and deadlines need a second authorised reviewer; the author cannot approve their own claim, enforced in the database. Approval binds to the exact source version and draft; editing invalidates approval; publish atomically with an audit event; corrections invalidate public caches and flag saved plans. Manual document intake first; crawlers only where repeated manual work justifies them. The fetcher allow-lists domains, validates redirects, blocks private-network addresses and limits document size.

**Guest sessions.** Anonymous server session with a random token, no personal fields, 7-day expiry, shown as "not saved to an account"; account creation migrates it. Nothing sensitive in service-worker or shared caches.

**Consent and safeguarding.** Public tools need no consent (no personal data). Under-18 accounts need verifiable parental consent through a DigiLocker-issued guardian token or a school-mediated route; no identity documents, caste certificates or counselling histories collected. Separate revocable consents for marks, category or income, parent summary, contacting an institution. Withdrawal freezes the account; deletion within 30 days. At 18, consent is re-obtained from the student. Support-queue and distress content is visible only to staff. Distress keyword rule as in section 3.

**AI request pipeline.** Validate input → enforce identity, rate and budget limits → retrieve only approved applicable records → compute facts with domain functions → generate a bounded explanation → validate schema and referenced record IDs against what was actually retrieved → render server-owned fact cards and citation URLs. The answer object carries explanation, referenced record IDs, missing information, assumptions and next actions. Missing or stale critical information yields uncertainty, not prose. Documents are untrusted data. The model has no secrets, no vault access, no SQL. No autonomous loops, no live browsing, no expensive-model retry cascade; unsupported questions return clarification or a support request.

## 7. Operating rules for Claude Code

**Three separate systems.** Development agents (write, inspect and test code; on demand in Claude Code); runtime AI (explains approved information to students; bounded API requests); background jobs (source checks, reminders; scheduled deterministic jobs). Development agents are never deployed inside the student application. A Claude Code subscription does not pay for the application's inference.

**Memory in files, not chats.** CLAUDE.md at 60–100 lines: mission, non-negotiables, verified commands, links. docs/STATUS.md under 400 words: step, exact commit, blockers, next task. docs/PRODUCT.md, ARCHITECTURE.md, UI.md, DATA.md, SECURITY.md scoped to their topics. docs/DECISIONS.md: dated decisions with reasons and superseded status. docs/KNOWN_ISSUES.md, RUNBOOK.md, RELEASE_CHECKLIST.md. tasks/BCI-xxx.md: one task contract each. The DPR is linked, not imported. Session close records changes, tests actually run, known failures, commit state and one exact next task; never "all tests pass" for one suite; never secrets, raw student data or unverified conclusions. Conflict order: latest approved task → accepted architecture decision → code and tests as evidence; if specification and code conflict, report it.

**Agents.** The main session is lead implementer and integrator. Three specialists, each with trigger, exclusions, tools, input contract, checklist, stop conditions and evidence-based output: data-security reviewer (schema, grants, RLS, publication, cross-user access, privacy; read and test only); UX/QA reviewer (completed journeys, mobile and desktop states, keyboard, source labels, save failures; isolated test accounts); AI evaluator, added only at the first runtime AI feature (grounding, refusal, cost, latency; capped budget; no student data). Definitions under .claude/agents/ in syntax the installed version supports. Default concurrency: lead plus one specialist; two implementers only with a fixed contract, disjoint files and separate worktrees; never parallel edits to a migration, lockfile or shared schema. Calibrate each reviewer on labelled invalid fixtures (a cross-user access flaw, a missing source, a stale deadline, a misleading status) kept out of deployment. No marketplace plugins, no orchestration server, no CEO or architect agents. If agent execution is unavailable, do the review sequentially and say so.

**Token and time rules.** One bounded outcome per task. Read STATUS and targeted files, not the repository; rg with generated output excluded. Targeted tests while iterating, full suite before merge. Short summaries and paths; no reprinting saved files. Deterministic tools for formatting, arithmetic, linting, migrations, tests. Fresh session after a clean handoff. Strongest model for architecture, security and hard failures; standard model for ordinary implementation; cheap models only for verified low-risk work. Two failed fixes of one failure → reproduce and diagnose. Track cost per accepted slice, failed-fix cycles, escaped defects and time to a tested feature.

**Contracts before parallel work.** Request and response schemas and error shapes; money precision, duration units, currency, date and time conventions; the three eligibility outcomes; evidence states and stale-data behaviour; guest and signed-in authorisation; loading, empty, permission-denied, failed-save and AI-unavailable states.

**Quality gates.** Calculators: zero values, boundaries, missing inputs, overlapping durations, rounding, leap-year birthdays. Eligibility: cycle and jurisdiction, unknowns, cut-off dates, rule version. Access: guest, student A, student B, reviewer across read, write, delete, export and storage; never tested only as database owner. Publication: separate maker and checker, exact draft approval, invalidation on edit, concurrent publication, supersession. AI: wrong source IDs, unsupported claims, stale evidence, prompt injection, timeout, overspend, no key, provider outage. Privacy: PII-free logs, logout and cache behaviour, authorised export and deletion. UI: 360 px mobile, desktop, 200% zoom, keyboard order, screen-reader spot tests, Hindi text expansion, every error state. Operations: fresh migration, staging deploy, monitoring alert, backup restore into a separate target, 25-session load test without live model calls. AI unit tests use mocked responses; a capped live evaluation of 30+ questions (10+ in Hindi or Roman-script Hindi; supported, ambiguous, unsupported, stale, injection, source mismatch, API failure) runs before release. No known critical or high security issue ships; lower-severity exceptions carry a named owner, rationale and expiry; model review alone never signs off child data or production security.

**Hooks.** Narrow deterministic checks only (format changed files, warn on secret-like additions, flag prohibited tool actions), tested on harmless fixtures; never the sole enforcement boundary; never disable permission checks globally. Real package commands for lint, typecheck, unit, database, browser and build tests, verified before agents are told to use them; no success via `|| true`, disabled assertions or skipped suites.

**Deployment.** Feature branch on synthetic data → pull request runs checks without production secrets → preview against staging only, callbacks and origins restricted → reviewer findings resolved, checks rerun → owner approves the exact release commit and migration plan → protected GitHub Actions environment (or owner-run script) applies additive migrations and releases to the production container → smoke tests → monitor; disable AI or revert if needed. Schema changes are append-only migration files; expand/contract so the previous release still runs; forward fixes over reversed destructive migrations; any restore carries a declared data-loss window. No production credential in the everyday Claude Code environment. No synthetic records in production; no real data in staging.

**Spend controls.** Four ledgers: development agents, application inference, hosting and monitoring, human verification and support. Runtime AI reserves an allowance per request atomically, limits input and output tokens, records actual usage and degrades to deterministic tools at the cap; provider caps plus an application kill switch; alerts at thresholds; no retry cascade.

**Ask versus proceed.** Routine work within an approved step proceeds; equivalent low-risk component choices follow the approved stack; credentials are configured by the owner privately; paid plans, new services and plugin permissions need approval; unknown fees, rules and deadlines are marked unknown and routed to a reviewer; destructive database actions and production releases stop for exact-target approval; a failed gate is reported, never claimed complete; real minor accounts stay disabled until the consent policy is reviewed.

**Completion report after every step.** Step; status (complete, blocked, partial); implemented; verified with exact commands and results; not verified; owner action only where necessary; Git state; next permitted step. "Looks good", "production-ready" and "tests should pass" are not evidence.

## 8. Data-flow map

| Flow | Where it runs or is stored | Personal data | Control |
| --- | --- | --- | --- |
| Database, authentication, file storage | Supabase, Mumbai | Yes | RLS, restricted role, field-level encryption for optional sensitive fields |
| Application and worker | Hostinger VPS, Mumbai | In transit and memory | No personal data in logs; containers isolated; staging separate |
| Database and storage backups | Supabase-managed; Mumbai (ap-south-1) — provisioned and confirmed 2026-09-19 | Yes | Daily backups; point-in-time recovery if a day's loss is unacceptable; object storage covered |
| Runtime AI requests | Google Gemini API, outside India (Google's global infrastructure; no India-only guarantee) | No: PII redacted; retrieved records and stated interests and constraints only | Provider terms reviewed for retention and training; restricted key; spending cap |
| Error tracking and uptime | Monitoring vendor; region recorded at sign-up | No: payloads scrubbed; no session replay | Region and retention in docs/SECURITY.md |
| WhatsApp reminders | Meta Cloud API | Phone number, first name, a deadline | Opt-in only; template carries nothing else |
| Transactional email, if used | Provider; region recorded | Email address | Domain verified; delivery tested |
| Development agents | Owner's machine, Claude Code | Never | Synthetic fixtures and staging keys only |

Real personal data of a minor does not enter the system until every row has a confirmed region and the owner has accepted the map in writing. "India-only" is a statement about this table, not about the database region.

## 9. Master schedule: 16 steps, 12 weeks, two tracks

The build guide's 16 steps are the executable sequence. Each step is one paste into Claude Code, authorises only its own work, and ends with the completion report and an owner check before the next.

| Step | Deliverable | Milestone | Week | Content and design track alongside |
| --- | --- | --- | --- | --- |
| 0 Prepare | Tools installed; the five owner decisions (state and cohort, fact authors and approvers, three spend ceilings, release approver, residency policy) plus the stack decision | — | 0 | |
| 1 Memory and rules | CLAUDE.md, STATUS, scoped docs, task index, .gitignore, .env.example | M0 | 1 | Career-family list, exam list, source register; editor onboarded |
| 2 Scaffold and tests | Runnable shell, real lint, typecheck, unit, browser, build commands; CI without production secrets | M0 | 1 | |
| 3 Agent team | Two read-and-test-only reviewers, calibrated | M0 | 1 | |
| 4 Data foundation | Migrations, typed access, seeds, RLS as migrations, test-db with guest/A/B/reviewer cases, rebuild from scratch | M1 | 2 | Design: three journeys, low-fidelity flows |
| 5 Private staging | Staging Supabase project and container behind a gate; health checks; AI disabled | M1 | 2 | |
| 6 UI system and Explore | Tokens, components, quick start, Explore against the development database; translation keys | M1 | 2–3 | Second reviewer onboarded; 25 career families drafted |
| 7 Compare and calculators | Compare up to three; pure domain functions for cost, timeline, eligibility; assumption editing | M2 | 4–5 | Rule functions and test cases for 5 exams; Hindi copy review begins |
| Inserted: usability round 1 | Five people, guest only, on staging; section-5 task criteria | M2 | 5 | |
| 8 Sign-in, plans, consent | Managed auth, sessions, guest migration, saved and versioned plans, export and deletion, consent gate and safeguarding workflow, distress rule, support queue | M3 | 4–6 | Consent workflow reviewed by a person |
| 9 Publishing console | Draft → submitted → approved → superseded; author cannot approve own claim; approval bound to draft; corrections invalidate caches | M4 | 6–7 | 50+ programme records ready to enter it |
| 10 Real pilot dataset | Import template, source register, exception report, coverage and freshness summary; human approval for critical records | M4 | 7–8 | Two human reviewers; nothing published unapproved |
| 11 Bounded AI | Provider adapter, pipeline, fact cards, budget reservation, mocked tests, 30-question live evaluation, AI-off journey | M5 | 7–8 | Contextual prompts; 10+ Hindi cases |
| 12 Hindi, accessibility, difficult states | Locale-aware formatting, Hindi search, 200% zoom, keyboard, screen reader, every error state, public-only PWA caching | M6 | 8 | Content freeze |
| 13 Operational safety and release review | Redacted logs, error tracking, uptime, feedback triage, jobs table and worker, optional WhatsApp template, release checklist, runbook, restore drill, 25-session load test | M6 | 8–9 | |
| 14 Production deployment | Owner approves the exact commit; protected deploy; smoke checks; pause and kill-switch documented | M6 | 9 | |
| 15 Ten-person trial | Moderator script, de-identified feedback, go/no-go report; usability round 2; outcome instrument | Acceptance | 9–10 | |
| 16 Expand to 100 | Batches 10 → 25 → 50 → 100 on observed metrics; operational checks; scope fixed | Expansion | 11–12 | Outcome instrument per batch |

**Progress (as of 19 Sep 2026).** Steps 1–3 (M0) are complete and verified: CLAUDE.md, STATUS.md, scoped docs and the task index are in place; the app boots and serves `/healthz` and `/docs`; `make lint`, `make typecheck` and `make test-unit` all pass for real; the two-reviewer agent team is configured. Step 4, Data foundation (M1), is in progress: schema and RLS policies are written as a migration (`db/migrations/0001_init.sql`) with an RLS-aware client, and `tests/db/test_rls.py` has 9 real guest/student-A/student-B/reviewer access-matrix test cases — they currently skip with a printed reason because no live database was connected yet. A Supabase project now exists (Mumbai, `ap-south-1`); applying the migration and wiring `.env` is the one remaining step to turn those 9 skips into passes. Steps 5–16 have not started.

A narrow staging demonstration can exist within days; it is not the pilot. 100-user access follows acceptance, not a date.

## 10. Substitutions when using the build guide's prompts

The build guide's prompts assume Next.js. On the pinned stack, replace as follows before pasting.

| Guide text | Replace with |
| --- | --- |
| Next.js, TypeScript, Tailwind, Vitest, Playwright; Vercel as provisional host | FastAPI (Python), server-rendered templates or a light PWA, Tailwind, pytest, Playwright for Python; Mumbai VPS with Docker as host |
| pnpm, Node.js LTS, lockfile | uv or pip-tools with a pinned lockfile; supported Python version |
| pnpm dev, lint, typecheck, test:unit, test:e2e, test:db, build | make dev, make lint (ruff), make typecheck (mypy), make test-unit (pytest), make test-e2e (Playwright), make test-db (policy tests against local Supabase), make build (Docker image) |
| NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY | SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_JWT_SECRET (server-only); no browser-exposed privileged key under any name |
| Vercel project; preview URLs; auth callbacks per environment | Staging container behind basic auth at its own hostname; production container at the pilot hostname; callbacks allow-listed per hostname |
| Scheduled serverless runner | One worker process on the VPS |
| Transactional email for reminders | Optional WhatsApp Cloud API template; email only if the account flow needs it |
| Protected CI deployment via the hosting plan | GitHub Actions protected environment holding the deploy key, owner approval required; or an owner-run script |
| "Do not buy n8n" | n8n already runs; notifications and reminders only |

## 11. Budget

| Item | Allowance |
| --- | --- |
| Application hosting and worker (existing VPS) | ₹0–4,000 per month |
| Supabase project, backups, storage | ₹2,500–6,000 per month |
| AI usage at Hindi-adjusted volumes (2,500–5,000 English-equivalent answers per month) | ₹1,000–5,000 per month |
| WhatsApp templates, monitoring, email, miscellaneous | ₹500–2,500 per month |
| **Operating subtotal** | **₹4,000–17,500 per month**, an unquoted planning range until current quotes including staging, backups and tax are obtained |
| Development, if hired: one senior full-stack engineer, 12 weeks | ₹6–14 lakh one-time |
| Editor and second reviewer honoraria, 12 weeks | ₹1.5–3 lakh one-time |
| Part-time product designer, weeks 1–3 and 7–9 | ₹1–2.5 lakh one-time |
| Part-time QA and security review | ₹0.5–1.5 lakh one-time |

If built in-house, the one-time lines become the builder's own time; state that opportunity cost rather than showing zero. No self-hosted GPU. Price the model's input and output tokens separately with the chosen provider's current rates; add retries and evaluation traffic.

## 12. Gates

**Before admitting 100 users.** Student A cannot read or change Student B's records; critical rule test cases pass; every published critical field has reviewed evidence; unsupported questions produce an honest fallback; corrections invalidate cached answers; a backup has actually been restored; the application works with AI disabled; spending limits and alerts have been tested; a named person owns source review and corrections; consent and safeguarding workflow reviewed by someone other than its author; the outcome instrument piloted on the first ten users; the distress rule tested in Hindi and Hinglish.

**Step 15 gates, approved before testing.** No critical data or security failure; at least 8 of 10 complete the core journey without intervention; at least 8 of 10 correctly distinguish estimated from verified cost; no repeated unexplained save failure. Tester tasks: explore without signing in; find two plausible routes and compare; change a cost assumption and explain the result; identify verified versus estimated; open an official source; save a plan and find the next action; log out safely on a shared device; ask a question outside coverage and notice the limitation. Small-sample gates, not impact claims.

**Expansion checks per batch.** Failed logins and saves; critical source freshness; pending reviews; AI fallback rate; usage budget; backup status; reviewer hours per record; support requests per 100 users. Pause if data integrity, privacy, spend or support capacity breaches its agreed limit.

**"Built" means.** Reproducible repository with pinned dependencies and reviewed migrations; guest exploration, comparison, calculators and saved plans working; field-level evidence status with real sources and no disguised synthetic content; account isolation tested beyond the UI; two authorised people for critical publishing with no bypass; English and Hindi critical content reviewed; mobile and accessibility checks done; AI grounded, budgeted, interruptible and optional; separate staging and production with protected release authority; monitoring, support owner, restore and recovery verified; real-data and minor-account approvals completed; ten-user results recorded honestly and expansion justified by evidence.

## 13. What Lite measures for the DPR

| Measurement | DPR section | Assumption it tests |
| --- | --- | --- |
| Share of interactions served without a model call | 9 | Tier 0 at 65–70% |
| Support and escalation requests per 100 users per month | 19 | Tier-3 referral rate 1–1.5% per year |
| Editor hours per verified programme record and per exam rule | 24, 26 | Data-operations headcount |
| AI cost per Hindi answer | 9 | ₹10–15 per MAU per year |
| Pre/post decision quality: can name three pathways, total cost of first choice, next deadline, a backup, one scholarship they are eligible for | 29 | 15-point uplift target |
| Whether one school lets 30 Class 10–12 students use it under parental consent | 12, 23 | School channel and consent design |
| Return visits in weeks 2–4 after sign-up | 12 | 30% monthly activity |
| Whether institution stewards maintain self-declared profiles when asked | 15, 24 | Steward model |

## 14. Step 1 prompt, ready to paste on the pinned stack

Complete Step 0 first. Save this pack as `docs/BUILD_PACK.md` in the project folder, open a terminal there, run `claude`, and paste:

```
You are the lead engineer for BCION Lite, a 10–100-user career decision pilot.
Read docs/BUILD_PACK.md once for the sequence. Execute Step 1 only. Do not
write another plan.

Stack is fixed: FastAPI monolith (Python) with data, rules, planning and AI
modules; server-rendered templates or a light PWA with Tailwind; Supabase
(Mumbai) for Postgres, Auth and Storage with row-level security; a Postgres
jobs table with one worker process on the Mumbai VPS; n8n off the request
path; one hosted AI provider behind an adapter, disabled by default; pytest,
Playwright for Python, ruff, mypy; Docker on the VPS; GitHub Actions with a
protected production environment. Do not propose Next.js, Vercel or any
replacement.

Inspect the directory, Git status, installed tools and any existing
instructions. Preserve unrelated user changes. If new, initialise Git
locally. Do not create a remote, push, buy a service or deploy.

Create concise project memory:
- CLAUDE.md: scope, non-negotiables, real commands once established, file
  routing. 60–100 lines. Do not import this pack or the DPR.
- docs/STATUS.md: step, blockers, next task, last verified state; under 400 words.
- docs/PRODUCT.md: one-state 10–100-user scope and the excluded features.
- docs/ARCHITECTURE.md: the fixed stack, module boundaries, data flow.
- docs/UI.md: Explore / Compare / My Plan / Saved; calm mobile-first design;
  per-field trust labels; difficult states.
- docs/DATA.md: typed facts, claim evidence fields, three-outcome eligibility,
  guest session rule.
- docs/SECURITY.md: roles, RLS, local/staging/production separation, data-flow
  map with regions, no production credential in this workspace.
- docs/DECISIONS.md and docs/KNOWN_ISSUES.md.
- tasks/INDEX.md: ordered checklist of the 16 steps.

Mark unapproved provider and privacy assumptions. No real student records.
Create .gitignore and .env.example with names and placeholders only:
SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_JWT_SECRET, APP_ENV,
AI_ENABLED, AI_PROVIDER_KEY. Ignore secrets, build output, local database
state, raw private data and temporary test artefacts. Never write secrets
to logs or memory.

End with the completion report: STEP, STATUS, IMPLEMENTED, VERIFIED (exact
commands and results), NOT VERIFIED, OWNER ACTION, GIT, NEXT.
```

**Owner check after Step 1.** A short CLAUDE.md exists; STATUS names Step 2 as next; nothing was purchased or deployed; the exclusions are explicit; the stack in ARCHITECTURE.md is the pinned one.

## 15. Daily prompts

**Resume a new session.** Read CLAUDE.md, docs/STATUS.md, Git status and the current task. Do not reread the pack. Verify the recorded state against code and tests. State the next bounded task and any actual blocker, then execute the already-authorised task. Do not change stack, buy services or touch production.

**Next step.** Proceed to Step [N] only; the preceding acceptance gate is approved. Read that step and the scoped docs it names. Implement, verify, review, update STATUS, give the completion report. Do not expand scope.

**End a session.** Finish the current safe checkpoint. Update STATUS with step, branch and commit, files changed, tests actually run, remaining failures and one exact next task. Save meaningful decisions only. No transcript, no restated plan.

**Stop a debugging loop.** Stop speculative edits. Reproduce the smallest failing case, show the actual error, inspect the relevant code and configuration. State the evidence-supported cause, apply one bounded fix, rerun the failing test and the relevant regression checks. Do not rewrite architecture or weaken assertions to make tests pass.

**Release review.** Review the exact candidate commit against docs/RELEASE_CHECKLIST.md. Prioritise cross-user access, source integrity, secrets, migrations, recovery, AI failure and complete mobile journeys. Report reproducible findings and untested areas. No code changes or deployment until findings are triaged.

The owner's highest-value contribution is fast scope decisions, authoritative content review and timely acceptance testing. Planning is complete; the next artefact is a repository with Step 1 done.
