# BCION Lite - Development Plan to complete the app

Date: 2026-09-21. Status: PROPOSAL. Nothing here is approved until the owner approves task cards
(CLAUDE.md conflict order: approved task card > `docs/DECISIONS.md` > code/tests > anything else).
`STATUS.md` stays the source of truth for what is built. This file is the map of what is left.

Task ids (for example `UI-1`, `PUB-2`) are described once, in the inventory files. This plan only schedules them.

- [plan/inventory-1-product.md](plan/inventory-1-product.md) - product build, Hindi, accessibility, design
- [plan/inventory-2-trust-content.md](plan/inventory-2-trust-content.md) - consent, publishing, content, scope, AI, security
- [plan/inventory-3-platform-launch.md](plan/inventory-3-platform-launch.md) - platform, QA, launch, trial, docs

The ordered checklist of every task is [../tasks/INDEX.md](../tasks/INDEX.md) (DRAFT, not yet owner-approved).
The inventories are **lead-only reading**. Implementers never open them, this plan, the build pack or the DPR: they get a task card (section 8.6). The "Wave: N" field printed in the inventory is a dependency depth, **not** this plan's wave number. Ignore it.

Revision note (2026-09-21, second pass): this file was revised after six critic reviews (non-negotiables, parallelism, speed, cost, completeness, owner usability). The main changes: round 1 is adults only; no agent ever holds staging or production credentials; live keys leave the repo folder before any fan-out; migration ledger reordered so the publishing fix lands first; per-lane start conditions replace hard wave barriers; writer cap lowered from 8 to 6; the signed-in account stream became float work; owner hours and seat costs restated honestly.

---

## 0. Read this first

1. **Phase 1 = "Gated staging, journey complete, AI off".** The whole student journey works on a private staging site, in English, with **no real accounts and no open public site**. Staging has a hostname, but every page sits behind a shared basic-auth password, sign-ups are off in two places, and only moderated guest sessions use it.
2. At the end of Phase 1 the honest claim is **"ready for gate reviews"**, not "ready for users".
3. **How long:** about 22-27 working days from kickoff. With Day 1 = Tue 22 Sep 2026 that is an exit between about Wed 21 Oct and Wed 28 Oct 2026 (weekdays only; public holidays not removed). If your hours or the named people slip, expect 28-30 days. People set the end date (recruits, the checker, your apply steps), not agents.
4. **Cash cost:** about Rs 45,000-80,000 including GST. Almost all of it is dev-agent subscription seats, billed per calendar month (section 9 shows the seat arithmetic). Hosting is Rs 0-1,000. AI inference is Rs 0.
5. **Your time:** about 86-96 unpaid hours: about 58 h of decisions, applies, content and round-1 work, about 30 h of operating the agent sessions, and about 8 h of Phase 2 booking. That is 3.5-4 hours every working day, with a peak of about 4-4.5 hours on days 8-10 (first staging bring-up; section 10). It fits a fixed daily slot only if someone else moderates at least half of round 1 (TRIAL-1 names that person).
6. **Six waves (0 to 5).** At most **6** writing agents at once. Most waves use 3-5. Waves overlap: each lane starts when its own start condition is met, not when a wave "opens". **Section 8.8 is the one table to look at**: how many workflows run at once in each wave, how many agents each workflow needs, and what must always run alone.
7. **Only you can do this week, thing 1 (day 1):** approve the clean-up commit (DOCS-1), the day-1 `.claude/settings.json` deny rules that land with it, and the writer caps in section 8.3; install Docker and the Supabase CLI (QA-1); switch sign-ups OFF in the Supabase dashboard (CONSENT-18, 10 minutes); move the live Supabase keys out of the repo folder into an owner-only file that no agent terminal ever loads (SEC-15). No agent fan-out happens before SEC-15 is done. About a week later you rotate those keys (SEC-16), because earlier agent sessions could read them.
8. **Only you can do this week, thing 2 (days 1-3):** name the people - a second reviewer ("checker"), a safeguarding person, a non-author consent reviewer, a Hindi reviewer, and a round-1 moderator who is not you (CONTENT-1, CONSENT-2, I18N-6, TRIAL-1) - and start recruiting 5-8 **adult** round-1 testers. This is the longest pole in the plan.
9. **Only you can do this week, thing 3 (days 2-4):** record the VM facts (DEPLOY-1 + OPS-1) and answer the decisions in section 13. Section 13 has two lists. List (a) needs your **explicit yes**; nothing proceeds on silence. List (b) holds reversible technical choices where a **provisional** default applies after 24 hours, is labelled "PROVISIONAL - not owner-confirmed", and is never written into `docs/DECISIONS.md` as your decision.
10. Phases 2 and 3 (real-users gate, production, AI, Hindi, the ten-user trial, 100 users) are outlined in section 14. They are not scheduled in detail here.

### Words used

| Word | Plain meaning |
|---|---|
| Lead | The one Claude Code session you keep open on `main`. It is the only one that merges, and the only one that edits `STATUS.md`, `DECISIONS.md` and `CLAUDE.md`. |
| Implementer | A separate Claude Code session that does exactly one task card and then stops. |
| Lane | A queue of cards that touch the same files, done one after another by one implementer at a time. |
| Fan-out | Starting several lanes at once. |
| Worktree | A second copy of the repo folder on its own git branch, so two agents never edit the same files on disk. |
| Wave | A group of days in this plan (0 to 5). Not the "Wave: N" number printed in the inventory files. |
| Contract burst | One agent writing the shared definitions (`docs/CONTRACTS.md`) in one serial run, so every lane builds against the same names. |
| strongest / standard / cheap | The largest, middle and smallest model in the Claude Code model picker (`/model`). The lead records the actual model names in `docs/PARALLEL.md` (DOCS-4). |
| Local stack | A private copy of Supabase (database and sign-in) running in Docker on your PC. Tests use it; it holds no real data and no live keys. |
| RLS | Row-level security: database rules that decide which rows each signed-in person can read or change. |
| Definer function | A database function that runs with its owner's rights. Powerful, so each one gets a security review. |
| Freeze trigger | The database rule that stops a published fact from being edited in place. |
| Revert-to-prove | Temporarily remove a protection, watch its test fail, put it back. Proves the test can actually catch the fault. |
| No-skip mode | Tests fail loudly instead of quietly skipping when the database is missing. |
| Lockfile | A file pinning exact dependency versions. |
| Basic auth | One shared username and password that the web server asks for before showing any page. |
| Adversarial pass | A second security review whose only job is to try to break the change. |
| Apply | Running new migration files against a cloud database. Only you do this, from your own shell. |
| Card table | A one-page table the lead prepares per wave (task, owned files, forbidden files, tier, tests, migration number). Your approval of the table approves those cards. |
| Float work | Tasks that run only when a lane and a lead merge slot are free. They never block a wave or the Phase 1 exit; unfinished ones roll into Phase 2. |
| Content batch 0/1/2 | CONTENT-9, CONTENT-10, CONTENT-12 (the inventory calls these "human wave 0/1/2"). |

---

## 1. Assumptions

| # | Assumption | If wrong |
|---|---|---|
| A1 | **"First phase" means Phase 1 as defined above**: full journey on gated staging, AI off, English, one real content family as a labelled rehearsal. It needs no hosting spend, no AI key, no paid security signer. | See the alternative reading below. |
| A2 | Owner gives about 3.5-4 hours every working day (decisions plus operating the sessions), **and about 4-4.5 hours on days 8-10** (DEPLOY-7 first bring-up, DATA-10a and operating the sessions fall together; the content work is moved off those days - section 10), and turns round apply steps and sign-offs within 24 hours. Someone other than the owner moderates at least half of round 1. | Every day of owner delay adds about a day to the end date. Without a second moderator, add 2-3 days. |
| A3 | Docker Desktop (WSL2 backend) and the Supabase CLI work on the Windows dev machine (QA-1). | The free Supabase quota is already full (A11), so a "second free cloud test project" does not exist. Default fallback **(b)**: run the local stack on the Oracle VM over SSH, Rs 0, owner sets it up, agents reach it only through a localhost tunnel the owner opens. Option (a): repurpose the empty Singapore project as a tests-only project (synthetic data only); production then needs Supabase Pro from Phase 2, about Rs 2,100-2,500 per month plus GST. Either way the writer cap stays at 2 and the phase grows by 1-2 weeks. |
| A4 | Dev agents run on subscription seats, **billed per calendar month with no pro-rating**. Schedule: ONE seat for Waves 0-1; a second seat from Wave 2 only if measured rate limits block a lane for more than 30 minutes; ONE seat in the second billing month. Seat price assumed at about Rs 17,000-20,000 per month **before 18% GST**, at USD 1 = Rs 85 (rate assumed on 2026-09-21). **Not checked against a price list.** No third seat and no API overflow by default. | Replace with real bills in `docs/COSTS.md` by week 2. The owner checks the real seat price including GST before confirming D15. |
| A4a | The owner's current subscription counts as seat 1 and is **shown as a cost, not treated as sunk**. | If you treat it as sunk, subtract one seat from each month in ledger 1. |
| A4b | How many sessions one seat sustains per day is **unknown**. It is measured in Waves 0-1 (tokens and limit hits per session by tier) and recorded in `docs/COSTS.md`. | The seat schedule in A4 is re-derived from that measurement at the Wave 1 close. |
| A5 | If billed by API instead: about Rs 150 (cheap), Rs 500 (standard), Rs 1,500 (strongest) per session. **Assumed, not measured.** | Same as A4. |
| A6 | One dev session is about half a working day. **Lead throughput is the real limit**: verification and merge are serial, so the lead merges in batches (section 8.2) and the writer cap is tied to the lead's queue, not to how many lanes could run. | Calendar stretches in proportion. |
| A7 | Numeric ceilings are unchanged. The 2026-09-21 scope widening (all-India rules plus study-abroad) is handled by **schema and "not verified yet" states in Phase 1**, and by a phased verified set (up to 4 states, UK first then Canada) in Phase 2. Phasing is still an open owner question (SCOPE-1, section 13). | Full coverage would add 150+ reviewer hours per cycle. |
| A8 | Trial accounts are adults-only and invite-only through Step 15. Minors only at Step 16 by the school route. **Usability round 1 is adults only too (18+)**: no under-18 participant before CONSENT-11, and no minor in any study before CONSENT-14. | Minors earlier pulls CONSENT-12 and CONSENT-14 and a school agreement onto the critical path. |
| A9 | The existing Mumbai Supabase project becomes permanent STAGING. Production is a fresh project created in Phase 2 (DEPLOY-11). | - |
| A10 | The Oracle VM is acceptable for guest-only staging whatever its region. No real account is admitted until the region is recorded and accepted in writing (DEPLOY-1, SEC-8). | An Indian VPS adds about Rs 500-1,500 per month. |
| A11 | The free Supabase quota (2 projects) is already full: the Mumbai project plus an unused Singapore "project education" (inventory-3 DEPLOY-1/DEPLOY-11; DECISIONS 2026-09-19). Production (DEPLOY-11, Phase 2) needs the Singapore project confirmed empty and then paused or deleted by you, or Supabase Pro at about USD 25 per month. | Ledger 3 Phase 2 carries the Pro line as a possible cost. |
| A12 | GitHub Actions free minutes are enough. **Whether the repo is public or private is not recorded here - the owner states it in DEPLOY-1.** A private repo gets about 2,000 free minutes a month; the heavy jobs (local Supabase stack, Playwright, image build) are limited by the QA-5 rules in section 5. | If minutes run out, the DB and e2e jobs run on `main` only and the lead runs them locally for branches. |

**Alternative reading of "first phase".** If you mean the whole Lite pilot through Step 16, the three phases become checkpoints of one run: 241 tasks that are not dropped (229 of the original 248, plus 12 added by this plan), about 230-235 dev sessions, about 330 human hours, 12-14 calendar weeks. It is bounded by recruitment, about 62 reviewer hours of content checking, and the week-4 post-test. The order of work does not change, and none of the cuts in section 4 are restored. Whole-pilot cash is roughly Rs 1.75-3.6 lakh (the sum of the section 9 phase totals).

---

## 2. Where we are now

Source: `STATUS.md` (current). The build pack section 9 "Progress" paragraph is stale.

| Build pack step | State | Evidence or gap |
|---|---|---|
| 0-4 Foundation, schema, RLS, maker-checker, engines (M0-M4, BCI-001..006) | Done | 239 tests pass. Migrations 0001-0003 exist. |
| 5 Private staging | Partial | App runs on the Oracle VM on localhost only. No nginx site, no deploy script, no demo-mode, no seed. |
| 6 UI system, Explore, translation keys | Partial | Explore screen exists. No app shell, no component set in code, no translation keys (all strings hardcoded). |
| 7 Compare, calculators, five exams | Partial | Compare, requirements and timeline screens exist. No per-exam rule modules. Cost is one pre-summed float with a hard-coded rupee sign. |
| Usability round 1 | Not started | No recruits, no script, no Playwright guest journey. |
| 8 Sign-in, plans, consent | Partial and BLOCKED | Sign-up has **no age or consent gate**. Hard blocker before any exposure. No student cookie session, no guest save. |
| 9 Publishing console | Partial | Reviewer console exists. A self-approval bypass is open when `created_by` is NULL (`0003_maker_checker.sql`). |
| 10 Real dataset | Not started | No real content published. Drafts only. |
| 11 Bounded AI | Groundwork only | Adapter and safety layer groundwork (M5). No route, no budget table. Stays off in Phase 1. |
| 12 Hindi, accessibility, difficult states | Not started | English only. |
| 13 Operational safety | Not started | No PII-free logging, no backups, no runbook. |
| 14 Production | Not started | - |
| 15-16 Trial and expansion | Not started | - |

Repo facts checked for this plan: `db/migrations/` holds 0001-0003, so **0004 is the next number** *(written at plan creation; superseded within the hour — see the third-pass note below: `0004_guardian_consent.sql` was merged by a concurrent session, so this plan's own ledger now starts at **0006**, not 0004)*. `.claude/agents/` holds only `data-security-reviewer.md` and `ux-qa-reviewer.md`. `tasks/` holds BCI-001..006. Working tree has uncommitted `CLAUDE.md` and `docs/DECISIONS.md` edits plus `docs/plan/` (DOCS-1 clears this). Those edits already contain the owner's 2026-09-21 decision allowing parallel multi-agent work (section 8).

Checked on the second pass: the repo root holds a live `.env` (git-ignored, but readable by any agent with shell access) and there is no `.claude/settings.json` - hence SEC-15, SEC-16 and the deny rules that land with DOCS-1. `scripts/apply_migrations.py` applies **every** pending file with no upper bound - hence DATA-15. `_safe_source_url` exists in three copies (`app/planning/comparison.py`, `app/api/eligibility.py`, `app/web/reviewer_pages.py`). No `AI_ENABLED` setting exists in `app/` yet.

---

## 3. The 18 work areas

248 tasks came from the audits. 21 are tagged deferrable; **19** of those are dropped for the pilot (CONTENT-18 and CONSENT-17 are kept). This plan adds **12** tasks (listed under the table), so the total is **260**, of which 241 are not dropped. About 118 tasks are firm in Phase 1, plus 8 float tasks (section 4). (The draft `tasks/INDEX.md` still counts 11 added and 259 in total: SEC-16 was added on the third pass, and DOCS-3 adds it to the index.)
"Open" = all audit tasks in the area. "Dropped" = cut for the pilot. "(float)" = Phase 1 only if a lane and a lead merge slot are free. The lead finds a task's text with Grep on its id heading; nobody reads an inventory file whole.

| Area | State today | Open | Dropped | Phase 1 tasks | Inventory |
|---|---|---|---|---|---|
| DATA - schema, seed, owner applies | 0001-0003 applied | 6 | 0 | 3 + 1 new: DATA-12, 8, 10 (run as 10a, 10b, 10c), **DATA-15** | [1](plan/inventory-1-product.md) |
| RULES - eligibility, timeline, cost, exams | Engines exist, no exam modules | 18 | 2 | 12: RULES-1, 17, 2, 3, 4, 5, 6, 8, 9, 10, 11, 16 (RULES-15 moved to Phase 2) | [1](plan/inventory-1-product.md) |
| UI - student screens | 4 screens, no shell | 12 | 1 | 8: UI-1, 2, 3, 4, 5, 6, 7, 15 (UI-13 to Phase 2; UI-19 is float or the first Phase 2 task) | [1](plan/inventory-1-product.md) |
| AUTH - sessions, plans, export, deletion | Bearer JSON only | 15 | 1 | 4: AUTH-1, 4, 5, 6. Float: AUTH-2, 3, 14. Phase 2: AUTH-7, 9, 10 | [1](plan/inventory-1-product.md) |
| DESIGN - contracts, copy, journeys | Mockup only | 11 | 0 (2 shrunk) | 6: DESIGN-1, 2, 3, 5, 6, 18 | [1](plan/inventory-1-product.md) |
| I18N - keys, Hindi, search | None | 16 | 1 | 4: I18N-1, 2, 3, and I18N-6 (owner naming, day 3) | [1](plan/inventory-1-product.md) |
| A11Y - states, cache, checks | None | 13 | 1 | 4: A11Y-1, 2, 4, 5 (A11Y-3 to Phase 2) | [1](plan/inventory-1-product.md) |
| CONSENT - gate, safeguarding | **No gate. Blocker.** | 17 | 3 | 5 + 1 new: CONSENT-1 (**superseded, not built** — see Wave 0), 2, 3, 4, 17, **CONSENT-18** (dashboard sign-ups off). Float: CONSENT-6, **CONSENT-6b**, 7, 8, 10 | [2](plan/inventory-2-trust-content.md) |
| PUB - maker-checker, console | Console exists, bypass open | 15 | 1 | 6 + 1 new: PUB-1, 2, 3, 4, 5, PUB-13 split into **PUB-13a** (naming) and **PUB-13b** (accounts and authorisation on staging) | [2](plan/inventory-2-trust-content.md) |
| CONTENT - import, real dataset | Drafts only | 16 | 1 | 10 + 1 new: CONTENT-1, 2, 3, 4, 5, 6, **CONTENT-6b**, 7, 9, 15, 18 | [2](plan/inventory-2-trust-content.md) |
| SCOPE - states, countries, currency | Decision recorded, nothing built | 13 | 1 | 7: SCOPE-1, 2, 3, 4, 5, 6, 13 (+ SCOPE-8, 14 as a Phase 2 head start) | [2](plan/inventory-2-trust-content.md) |
| AI - bounded explanation | Groundwork | 16 | 1 | 1: AI-2 (the `AI_ENABLED` flag). AI-10 owner prep in weeks 2-3 | [2](plan/inventory-2-trust-content.md) |
| SEC - middleware, CSRF, grants, reviews | Not started | 11 | 1 | 5 + 2 new: SEC-1, 2, 5, 6, 7, **SEC-15**, **SEC-16** (SEC-3 to Phase 2) | [2](plan/inventory-2-trust-content.md) |
| OPS - logging, backups, runbook | Not started | 15 | 2 | 2: OPS-1, OPS-2 | [3](plan/inventory-3-platform-launch.md) |
| DEPLOY - staging, production | Localhost only | 15 | 1 | 10 + 1 new: DEPLOY-1, 2, 3, 4, 5, 6, 7, 9, 15, 17, **DEPLOY-18** | [3](plan/inventory-3-platform-launch.md) |
| QA - local stack, CI, e2e, matrix | 239 tests, silent skips possible | 11 | 0 | 9: QA-1, 2, 3, 4, 5, 6, 7, 9 (one session), 12 | [3](plan/inventory-3-platform-launch.md) |
| TRIAL - rounds, instrument, expansion | Not started | 19 | 1 | 7: TRIAL-1, 2, 3 (English draft), 7, 8, 9, 10 (TRIAL-4 to the end of Phase 2) | [3](plan/inventory-3-platform-launch.md) |
| DOCS - memory, cards, protocol | Stale STATUS, no cards index | 9 | 1 | 8: DOCS-1, 2, 3, 4, 5, 6, 12, 13 (DOCS-6 folded into the DOCS-4 session) | [3](plan/inventory-3-platform-launch.md) |

The Dropped column sums to 19.

**Tasks added by this plan (no inventory entry; DOCS-3 publishes them in `tasks/INDEX.md`):**

| Id | One-line card | Executor, size | Depends on | Blocks |
|---|---|---|---|---|
| CONSENT-18 | Owner: switch "Allow new users to sign up" off in the Supabase dashboard for the Mumbai project | owner, 0.2 h | - | DEPLOY-7 |
| SEC-15 | Owner: move the live Supabase credentials out of the repo tree into **one owner-only file outside the repo** (never a shell profile, never a user or system environment variable). The file is loaded only in a terminal the owner uses himself, never in a terminal where a Claude Code session runs. After QA-2 the repo `.env` holds local-stack values only | owner, 0.5 h | - | **Any fan-out** |
| SEC-16 | Owner: rotate the staging credentials. The Mumbai project's service-role key, JWT secret and DB password sat in the repo-root `.env`, readable by every earlier agent session and possibly present in transcripts. In the Supabase dashboard rotate the JWT secret (which re-issues the anon and service-role keys) and the database password. New values go only into the owner-only file and, at DEPLOY-7, into `/etc/eduvation/staging*.env`. Confirm the app env on the VM holds **no** service-role key (only the migrate env does). Update or stop the localhost app on the VM in the same sitting | owner, 0.5 h | QA-2 merged (no test run needs the live project any more) | DEPLOY-7, PUB-13b |
| DEPLOY-18 | Flags and wiring stub: every flag in the section 6.2 flag list (the AUTH-1 list; **provisional until the AUTH-1 yes**, a later change is a lead one-liner) added to `config.py` and `.env.example` with fail-closed defaults; an ordered `MIDDLEWARE = [...]` and router registry in `app/main.py` with **slot names frozen on the card from section 6.4**; a Makefile that includes `mk/*.mk`. **Fail closed:** each registry slot is marked required or optional; outside development the app refuses to start if a required module (security headers, CSRF/Origin check, cache policy, maintenance, logging) is absent or misnamed; a unit test asserts the middleware order and the refuse-to-start behaviour (every required module is merged before DEPLOY-7, the first non-development start). After it, lanes never edit `config.py`, `main.py` or the Makefile | dev-agent, **standard**, 1 session, in data-security review pass 1 | DOCS-1 merged; the 6.2 flag list. **Note:** `config.py` already carries the merged guardian-consent gate's own fields (`smtp_*`, `app_base_url`, `email_configured`) — DEPLOY-18 adds its registry alongside them, never overwrites | Wave 2 lanes |
| DATA-15 | `--through NNNN` argument for `scripts/apply_migrations.py`: refuses files numbered above the bound and prints what it skipped; unit test; data-security review | dev-agent, cheap, 1 session (migration conflict group) | - | DATA-10a, PUB-4 |
| CONTENT-6b | Importer DB half: upsert, `tests/db/test_content_import.py`, tier and `source_version` populated under the reviewer's own sign-in, stored content hash; **plus the read-only publication-integrity query as `make content-integrity`** (`mk/content.mk`; counts of published claims with `created_by = reviewed_by`, NULL `created_by`, or an unnamed or fixture verifier), with a DB test on the local stack that seeds one violating row of each kind and expects it counted (exit gate 3 uses it; CONTENT-8 extends it in Phase 2) | dev-agent, standard, 1 session (the second CONTENT-6 session, moved) | CONTENT-6, PUB-3 | CONTENT-7, CONTENT-9 import |
| CONSENT-6b | `sign_up.html` invite-code, 18+ attestation and terms fields, plus the HTML withdraw-consent button | dev-agent, standard, 1 session (float) | AUTH-3, CONSENT-6, CONSENT-10 | CONSENT-11, QA-10 |
| PUB-13b | Owner: create the checker's reviewer account on staging by dashboard invite, insert `reviewers` rows by SQL, set `critical_authorised`, record tier cadence in `docs/DATA.md`. Repeated for production in Phase 2 | owner, 1 h | PUB-4, PUB-13a | CONTENT-9 approval |
| QA-9b | ux-qa-reviewer calibration and the `ux-qa-reviewer.md` edit | dev-agent, strongest, 1 session, Phase 2 | QA-9 | A11Y-11 |
| DATA-14 | Owner: apply 0006..N to production with `--through`, run the grant and exposure audit (SEC-6 catalogue test) and a data-security review | owner, 1.5 h, Phase 2 | DEPLOY-11, DATA-11, DATA-13 | CONTENT-10 production import, PUB-13b on production, DEPLOY-12, DEPLOY-13 |
| UI-20 | Compare and detail sections the outcome instrument scores: potential assistance (published scholarship claims, never subtracted), backup or alternative routes, next key date with cycle and last-verified date, met / not met / unknown summary linking to Requirements | dev-agent, standard, 2 sessions, Phase 2 | DATA-4, SCOPE-4, AUTH-6 | TRIAL-11 |
| CONTENT-20 | Owner: declare the content freeze in DECISIONS before DEPLOY-12; only corrections after | owner, 0.25 h, Phase 2 | CONTENT-10 | DEPLOY-12 |

---

## 4. Phases and exit gates

### Phase 1 - Gated staging, journey complete, AI off

Two checkpoints inside it:

- **1A - Guest demo and usability round 1.** Explore, compare three, time and cost, requirements, save next actions as a guest. Private staging behind basic auth, sign-ups off, synthetic data with a permanent "sample data" ribbon. Five to eight **adults** test it. Round-1 testers are guests in moderated sessions, not users. No accounts are created and no identifying details are typed.
- **1B - Publication integrity and first real content.** The maker-checker bypass is closed. One career family goes through the hardened pipeline as a **timed, labelled rehearsal** (CONTENT-9). The signed-in surface (sign-in, signed-in My Plan, the consent gate code) is **float work**: it is built behind a fail-closed, adults-only, invite-only gate if lanes are free, and otherwise rolls into Phase 2 block P2-A.

**Phase 1 exit gate** (all must be true, recorded in `STATUS.md` by the lead after running the checks itself):

1. QA-6 cross-user access matrix is green **in CI** (QA-5) with no-skip mode on, and has rows for every table and policy added by **every migration merged in Phase 1** (the ledger plans 0006-0013).
2. RULES-11 critical rule cases pass for NEET-UG, JEE Main and GUJCET. (CUET-UG and CLAT move to Phase 2 with RULES-15, where their real values arrive.)
3. One CONTENT-9 family is published on staging with reviewed evidence, **only after PUB-4** closed the self-approval bypass, and timed in the editor-hours log (TRIAL-7). In addition: every CONTENT-9 published claim has `created_by` and `reviewed_by` belonging to two different named people recorded in DECISIONS; the checker is `critical_authorised`; the owner holds no second reviewer account; and the integrity query `make content-integrity` (built and tested on the local stack in CONTENT-6b: `created_by = reviewed_by`, NULL `created_by`, unnamed or fixture verifier) returns zero rows **when the owner runs it against staging from his own shell** and pastes the counts (section 10). No agent runs it on staging.
4. Honest fallbacks work: `no_verified_rules` (RULES-8) and "not verified yet for this state/country" (SCOPE-6).
5. The full journey works with AI off (the only mode in Phase 1), and `/readyz` reports `AI_ENABLED=false`.
6. Named people own source review and corrections (CONTENT-1). (TRIAL-4, the Step 15 thresholds, moves to the end of Phase 2; the build pack only requires it before testing, that is before TRIAL-11.)
7. Round 1 is scored on the six task criteria in `docs/UI.md` (Usability rounds) on the real app, with adult participants only. The weaker Class 8-12 evidence is recorded as a round-1 limitation in `round1-findings.md`.
8. The sample-data ribbon is permanent on staging. A test proves a synthetic row can never carry a verified badge, and demo mode cannot be switched on in a production environment. The QA-12 dry-run reports zero matches on the staging project, and zero published claims exist whose verifier or source is a fixture marker.
9. Dependencies are pinned (SEC-7). Every migration merged in Phase 1 was covered by a batch data-security review **before its owner apply**, and by a revert-to-prove run.
10. Supabase dashboard sign-ups are off, `SIGNUP_ENABLED=false`, `POST /auth/sign-up` returns closed with the env file as deployed, and staging logs carry no `age=` query strings.
11. Staging guest rows were purged after TRIAL-8 (count = 0 recorded), and no agent held staging credentials at any point after the first TRIAL-8 session.

**Float work (never blocks a wave close or this exit gate; unfinished cards roll into P2-A):** AUTH-2, AUTH-3, AUTH-14, CONSENT-6, CONSENT-6b, CONSENT-7, CONSENT-8, CONSENT-10, UI-19. CONSENT-4 (0013) is firm only if the CONSENT-3 human read is done by about day 14; otherwise it floats too. None of these is on the Phase 1 exit path. Each still carries its cross-user acceptance lines (section 5) whenever it is built.

**Not claimed at Phase 1 exit:** backup restored, spend alerts tested, consent workflow reviewed by a non-author, distress rule reviewed in Hindi and Hinglish, instrument piloted, separate production.

### Phase 2 - Real-users gate, production, AI, Hindi, trial dataset

Exit gate: every "real-users-gate" item in build pack section 12 passes once, on one release candidate, with human sign-offs (CONSENT-11, SEC-13, DATA-11, AI-17), then DEPLOY-12 and DEPLOY-13. See section 14.

### Phase 3 - Ten-user trial, expansion to 100, minors

Exit gate: build pack Step 15 gates (TRIAL-11, TRIAL-12), then per-batch checks for Step 16 (TRIAL-13). See section 14.

### Cuts and moves (with the risk of each)

| Tasks | Action | Risk accepted |
|---|---|---|
| A11Y-13, SCOPE-12, RULES-14, RULES-18, SEC-11, CONSENT-13, 15, 16, PUB-16, OPS-11, OPS-13, UI-16, AUTH-13, I18N-14, AI-14, CONTENT-19, DEPLOY-14, DOCS-10, TRIAL-15 (19 tasks) | Dropped for the pilot | No section 12 gate needs them. Several remove explicit build pack deliverables, so they are listed in **decision D16** (section 13) and need an owner-approved DECISIONS entry; until then the build pack still binds. |
| DEPLOY-14 and OPS-11 | Dropped - **deviation from the pinned stack** | Production release is an owner-run script from a protected `main` plus exact-SHA approval (DEPLOY-10, DEPLOY-12, DEPLOY-17), not a GitHub Actions protected environment; n8n is not deployed for the pilot. Both need an owner-approved DECISIONS entry (the lead drafts D13 and D16 together in DOCS-5; DEPLOY-2 only supplies the hosting facts as proposed lines) **before DEPLOY-13**. No other stack element changes. |
| AUTH-13 ("What changed" list) | Dropped; pilot substitute owned by AUTH-14 | AUTH-14 acceptance: a plan with `needs_review=true` shows the A11Y-1 changed-info state with `flagged_reason` and date, and a link to the affected field; guest plans likewise through AUTH-6 if flagged. A11Y-9 (Phase 2) verifies it. Recorded in D16. |
| DOCS-10 (hooks) | Dropped, **except** the file-access deny rules, which land **with DOCS-1 on day 1, before any fan-out** (DOCS-13 later adds only the implementer allowlist) | `.claude/settings.json` denies Read and Edit of the files that hold live values (`.env`, `.env.local`, the owner-only key file, `/etc/eduvation/**`) and the Bash patterns that would print them (section 8.7). `.env.example`, `.env.test.example` and the local-stack `.env.test` stay readable. Owner-approved. |
| I18N-14 (Gujarati strings half) | Dropped unless the cohort needs it | SCOPE-1 and TRIAL-1 acceptance: record the recruits' school medium; if a majority are Gujarati-medium, restore the Gujarati-strings half for Phase 3 (D16). |
| CONSENT-17 | **Kept** (0.25 h owner, zero cost) | Dropping the task that records the DigiLocker deferral would mean it is never recorded. |
| CONTENT-18 | **Kept**, and run before any outside reviewer receives files | Otherwise the owner's email reaches third parties. |
| RULES-15, AUTH-7, AUTH-9, AUTH-10, UI-13, SEC-3, A11Y-3, TRIAL-4, QA-9b | **Phase 2** (P2-A, TRIAL-4 at the end of Phase 2) | No Phase 1 exit item tests them. No real account exists until Phase 2. CUET and CLAT modules would be re-touched when real values arrive. The ribbon and footer stay in UI-1. |
| DESIGN-14 (teacher pack) | **Phase 3**, ready before the first school session (TRIAL-14) | Dropped only if expansion recruits outside schools (D16). |
| DESIGN-11, DESIGN-12 | Shrunk to one consent-screen sentence inside CONSENT-3 | Family and case summary specs missing if Phase 3 wants them. |
| All AI tasks except AI-2 (AI-1 included), I18N-4 **and** I18N-5, A11Y-6, DATA-4, PUB-6 to PUB-9 | Phase 2 | Round 1 gives weaker Hindi evidence (moderator translates; log it). The checker sees raw ids in the queue for one family. DATA-4 keeps `pathway_transitions` (UI-20 needs backup routes); only the stage tables are trimmed. |
| **OPS-6** ("Report a problem") | **Phase 2, not Phase 3** | TRIAL-11, QA-10, DATA-13 and I18N-13 depend on it. Costs one migration slot. |
| OPS-5, OPS-14 (jobs table, worker) | Phase 3, only if something enqueues work | None for the pilot. This is a build pack Step 13 deliverable, so it is in D16. |
| RULES-10, OPS-2, A11Y-4, SEC-5, SEC-2 | **Not deferred** - pulled into 1A | Deferring costs more in rework and logged personal data than it saves. |
| Gate reviews | Batched once in Phase 2 on one release candidate | A late finding forces rework. Mitigation: a data-security review of every migration batch **before its owner apply** in Phase 1 (section 8.6 review ledger). |

---

## 5. Phase 1 wave plan

Rules that apply to every wave:

- Every dev lane works in its own git worktree. Only the lead works on `main`.
- **Every wave closes on a full-suite run by the lead** (lint, mypy, unit, `test-db`, e2e). An implementer's "tests passed" is never accepted as proof.
- "Days" are working days from kickoff (Day 1 = Tue 22 Sep 2026). **A wave is not a barrier.** Each lane starts when its own start condition is met; the wave tables say which condition. People work runs alongside every wave.
- **Migration ledger (order is fixed; Phase 1). Numbers below are PROVISIONAL, not fixed** — this plan's starting number has already moved twice in one afternoon (0004→0005→0006) from migrations other sessions created against the live project while this plan was being written. **Re-verify with `ls db/migrations/` immediately before the migration lane's first session opens** (DATA-15/DATA-12's card) and shift again if anything new landed; do not trust this table blind. As of this pass: **0006 DATA-12, 0007 SCOPE-3, 0008 AUTH-4, 0009 AUTH-5, 0010 PUB-2, 0011 PUB-3, 0012 SEC-6, 0013 CONSENT-4.** Phase 2 continues with AUTH-7, AUTH-10, then the ten-user-trial group (DATA-4, I18N-7, I18N-8, AUTH-15, OPS-6, TRIAL-5, AI-4). Older numbers and file names printed on task texts are stale; DOCS-3 publishes this ledger.
  - "PUB-2 depends on CONSENT-4" is recorded as **ordering only** (the same treatment DATA-12 got): PUB-2 touches claims, sources and storage; CONSENT-4 touches account status, invites and saved-plan policies. The migration owner confirms on the PUB-2 card that it references no CONSENT-4 object; if it does, the old order (CONSENT-4 first) is restored.
  - The lead reserves the number on the card when the session opens. If a review forces a fix **after** a batch has been tagged for apply, the fix takes the next free number and later entries shift by one. Before the tag, the migration file is corrected in place and the local stack is reset.
- **The migration lane runs continuously from the day QA-3 lands. It has no wave gates** and must never idle. The wave tables show roughly where each migration falls.
- **Prep-session rule (2026-09-21, speed finding, section 8.8F):** for every multi-session migration card (SCOPE-3, AUTH-4, PUB-2, PUB-3, CONSENT-4), the acceptance-test scaffolding for that migration — the new `tests/db/access_matrix.py` rows, the docs pointer, the card's own test-module skeleton — is drafted ahead of time in a parallel non-DB lane (Rules or Docs-and-scripts, whichever is open), so the migration owner's own session covers only schema, RLS and revert-to-prove. This changes nothing in 6.4's one-open-migration rule or the 8.8 Table A caps; it only narrows what happens inside each session. Track in `docs/COSTS.md` whether this actually removes the card's second session — if it doesn't, the second session was real complexity, not scaffolding overhead, and the session count stands as planned.
- **Every migration PR ships its own cross-user rows** (guest / student A / student B / reviewer) in `tests/db/access_matrix.py`, in the same PR. After QA-6 merges, `access_matrix.py` is one of the migration lane's owned files. The lead does not merge a migration while the QA-6 table guard is red. There is no separate "matrix extension" task.
- **Owner applies are bounded and tagged.** The lead tags `staging-batch-A` (0006-0007), `-B` (0008-0009), `-C` (0010-0011), `-D` (0012-0013). The owner applies from the tag checkout with `apply_migrations.py --through NNNN` (DATA-15), so a later migration already on `main` can never reach staging early.
- **Staging hygiene.** After QA-2 merges, no test run targets the staging project except the owner-run QA-16 in Phase 2. From the first TRIAL-8 session no agent, including the lead, holds staging or production credentials or queries those databases (section 8.4).

### Wave 0 - Clean main, close the sign-up hole, publish the ids (days 1-2)

| Track | Agent role | Worktree | Task ids (in order) |
|---|---|---|---|
| Memory | Lead (cheap/standard) | no, on main | DOCS-1 (**includes the day-1 `.claude/settings.json` deny rules**, section 8.7) -> DOCS-3 (ledger, ids, card numbers) -> DOCS-2 with DOCS-5 (off the critical path, but done by day 3 because QA-9 needs DOCS-5; DOCS-5 is also the one place the lead drafts the D13 and D16 DECISIONS entries) |
| Stopgap | **SUPERSEDED, do not build** (third-pass note below) | - | ~~CONSENT-1~~ |

- **DOCS-1 also carries one CLAUDE.md line edit**, approved with the commit: "Implementers read only their task card, `implementer.md` and the one `docs/CONTRACTS.md` section named on the card. Do NOT open the build pack, the DPR, `docs/DEVELOPMENT-PLAN.md`, `docs/plan/*` or `docs/DECISIONS.md`; use the digest from DOCS-5." `CLAUDE.md` carries exactly one **lead-only** pointer to sections 8.8 and 6.4 of this plan (owner instruction 2026-09-21: Claude works to the deployment table) and never links `docs/plan/`; implementers are told not to open either. (This brings forward the part of DOCS-12 that matters for cost; the rest of DOCS-12 stays in Wave 2.)
- **DOCS-1 also lands the deny rules**, shown to you and approved with the same commit: a minimal `.claude/settings.json` whose `permissions.deny` covers Read and Edit of the live-value files and the Bash patterns that would print them (exact list in section 8.7). They exist **before the first worktree is cut**, not on days 3-4. DOCS-1 ends with a fast-forward merge into `main`, so every worktree contains both the parallel-work decision and the deny rules.
- DOCS-3 also **rewrites the cards that still name a shared file** so that "DEPLOY-18 is the last task to edit them" is true: SEC-7, PUB-5, SEC-1, DEPLOY-5, OPS-2, A11Y-4, DEPLOY-9, DEPLOY-15 and AI-2 ship their make targets as `mk/<task>.mk`, their middleware or router as a named registry module, and use the flag already in `config.py`; none of them lists `Makefile`, `app/main.py`, `app/core/config.py` or `.env.example` as an owned file. (SEC-7's `ci.yml` edit stays; `ci.yml` has its own order in 6.4.)
- DOCS-3 also publishes: the canonical task ids including the 12 added tasks (section 3; SEC-16 is not yet in the draft index); the 0006-0013 ledger; BCI card numbers from BCI-007 up; the **stale-name ledger** - `requirements.lock` (not `constraints.txt`), `RELEASE_CHECKLIST.md`, `SIGNUPS_ENABLED` -> `SIGNUP_ENABLED` (DEPLOY-9 adds only `MAINTENANCE_MODE`), `app/web/reviewer_pages.py` -> the specific `app/web/reviewer/*.py` file for each of I18N-1, SEC-2, A11Y-4, DEPLOY-15 and SCOPE-13, DATA-13's "batch C (0012)" title, and contract outputs moving into `docs/CONTRACTS.md`; the ci/Makefile order with QA-5 after DEPLOY-3; and the empty `docs/CONTRACTS.md` skeleton.
- DOCS-3 generates **per-task card stubs once** from the inventories (a small script, or Grep with `-A` on each id heading) with the corrected numbers applied, then marks `docs/plan/inventory-*.md` "ARCHIVED - lead-only; cards supersede". After that the lead fills cards with Grep on the id, never a whole-file Read.
- Sessions 1-3 run before `tasks/TEMPLATE.md` exists. For them, the pasted block in section 15 plus your typed "approved" **is** the task card; DOCS-3 back-fills them as BCI-007..009.
- **Owner actions due (spread over days 1-4 so no day passes 4 h; section 10 has the split):** approve DOCS-1, the day-1 deny rules and the writer caps; QA-1; **dashboard sign-ups off (CONSENT-18, 10 min) — belt-and-braces alongside the real gate below, not a substitute for it**; **SEC-15 - move live Supabase credentials out of the repo tree into an owner-only file outside the repo, never a shell profile (blocks any fan-out)**; DEPLOY-1 with OPS-1 in one sitting; SCOPE-1 (explicit yes needed), RULES-17 and DESIGN-6; CONSENT-17; start TRIAL-1 recruitment (adults only) and name a second moderator; give the CONSENT-2, CONTENT-1 and I18N-6 names (PUB-13a naming happens in the same sitting); open the TRIAL-7 hours log; **apply `0004_guardian_consent.sql` and provision a real email provider (third-pass note below) — this is now the actual sign-up/consent gate, not CONSENT-1**.
- **Until QA-2 lands, no agent runs `make test-db` or e2e at all - not even the lead.** The live keys are in no agent's environment; otherwise the DB run waits for the local stack (QA-2, about day 3). The lead still runs lint, mypy and unit tests itself.
- **Closing gate:** `git status` clean on `main` after the DOCS-1 fast-forward merge, stale worktrees removed **except the locked `wf_9b7797a4-e76-1` one (the "Held, not merged" student sign-up/save-plan UI named in `STATUS.md` - real uncommitted work, not scratch; needs its own bounded merge task, not yet carded - see the third-pass note)**; `.claude/settings.json` deny rules merged and approved; dashboard sign-ups off and a test sign-up refused; SEC-15 done: the repo-root `.env` is gone or holds no secret value (the lead can only check that the file is absent, because the deny rules stop it reading the file; otherwise you confirm it), and you confirm that the terminal you launch Claude Code from has no `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` or database-password variable set (you check, names only); ids and ledger published. (`STATUS.md` under 400 words by day 3.)

### Wave 1 - Protocol, contracts, mechanical splits, local test stack (days 1-4)

| Track | Agent role | Worktree | Start condition | Task ids (in order) |
|---|---|---|---|---|
| Protocol | Lead, **standard** (input limited to sections 6.4 and 8.2 of this plan) | no, on main | DOCS-3 done | DOCS-4 with DOCS-13 **and DOCS-6** (one session; it creates `docs/PARALLEL.md`, `docs/COSTS.md`, `implementer.md`, `migration-owner.md`). DOCS-13 also (a) fixes the stale trigger paths in `data-security-reviewer.md` (`app/db/`, `app/api/admin*` do not exist) and adds definer, grants and local-stack-only wording; (b) extends `.claude/settings.json` (its deny rules already landed with DOCS-1 on day 1) with an allowlist for the implementer tool set so lanes do not stop on prompts; it does not loosen any deny rule. **The owner approves every agent file and every settings change.** |
| Contract burst | ONE strongest-tier agent, strictly serial | yes | DOCS-1 committed, SEC-15 done. It may run **alongside** DOCS-4 because it touches only `docs/CONTRACTS.md` and `docs/CONSENT.md`, and the lead touches only `docs/PARALLEL.md`, `docs/COSTS.md` and `.claude/` | SCOPE-2 -> RULES-1 -> PUB-1 -> CONTENT-2 -> AUTH-1 -> CONSENT-3 (written with role placeholders and the D6 default; only its human read waits for the CONSENT-2 names) -> A11Y-1 (only after DESIGN-2 and DESIGN-1 are merged; A11Y-1 also takes the small `docs/UI.md` usability-wording fix that TRIAL-2 used to carry). Written as sections of `docs/CONTRACTS.md`. AI-1 is left for Phase 2. **Until D2 (SCOPE-1) has your explicit yes, SCOPE-2 freezes only the scope-neutral vocabulary**; SCOPE-2 and SCOPE-3 do not depend on which states or countries are chosen. |
| Design docs | Implementer, standard (strongest for DESIGN-1) | yes | DOCS-1 committed (DESIGN-2 is a new file, `docs/COPY.md`, and needs no PARALLEL.md) | DESIGN-2 -> DESIGN-1 -> DESIGN-5 -> TRIAL-2 (about day 3, so recruits and the Hindi reader get the consent sheet early) |
| Mechanical | Implementer, cheap (**standard for DEPLOY-18 and SEC-1**) | yes | DOCS-1 merged; the section 6.2 flag list and registry slot names copied onto the DEPLOY-18 card (provisional until the AUTH-1 yes) | DEPLOY-18 (in data-security pass 1: registry fails closed) -> SEC-7 -> UI-2 -> **SEC-1 -> DEPLOY-5** (neither has dependencies and neither touches `tests/db/**`) -> **PUB-5, start condition "QA-3 merged"** (about day 4-5): it edits `tests/db/test_reviewer_console.py` and needs a `test-db` run, so it must not overlap QA-3's exclusive window; it runs on the local stack. Its data-security pass is limited to proving the auth dependency is byte-equivalent and every reviewer route still requires it. All of these use the rewritten cards from DOCS-3 (`mk/*.mk`, registry modules; no shared-file edits after DEPLOY-18) |
| Tests | Test engineer, strongest | yes | QA-1 and DOCS-1 done (day 1-2). It does **not** wait for SEC-7: QA-2 ships its targets as `mk/testdb.mk` and lists its one config line in the completion report; the lead merges those after SEC-7 | QA-2 (2 sessions) -> QA-3. **QA-3 has an exclusive window on `tests/db/**` and `tests/e2e/**` (half a day): it is the first merge before any DB-touching branch is cut.** |
| Docs and scripts (cheap, **firm**, not optional) | cheap | yes | DOCS-4 merged | CONTENT-3 -> DESIGN-3 (after DESIGN-2) -> CONTENT-18 (after CONTENT-3 and SCOPE-1) |

- **QA-2 acceptance additions:** the target guard refuses any non-localhost URL; the migration lane gets its **own second local stack** (dedicated project id and ports, fixed in `supabase/config.toml`); local GoTrue auth rate limits are raised in `supabase/config.toml`; a measured run of 3 concurrent `pytest -n 2 tests/db` plus one e2e on the owner's machine is recorded, and the DB-lane cap after QA-3 is set from it (default 3). QA-2 also adds `make verify`: one summary line per suite (pass, fail, skip counts), full logs to a file, read only on failure.
- Cap: before DOCS-4/DOCS-13 merge, only the three lanes that need no `PARALLEL.md` (contract burst, DESIGN-2, QA-2) — **not four; the CONSENT-1 stopgap that used to fill a fourth slot here is superseded, not built.** After they merge and you approve the agent files: **burst + 4 (design docs, mechanical, tests, docs and scripts)**. The fourth lane is firm (the closing gate needs CONTENT-3 and the DESIGN-3 lint) and costs little: docs and unit tests only, no DB, no shared file. Until QA-3 merges the tests lane is the only DB-touching lane; PUB-5 is the first other DB-touching card and starts only after QA-3.
- **Owner actions due:** approve the agent files and the `.claude/settings.json` allowlist (the deny rules were approved on day 1); **SEC-16 - rotate the staging keys once QA-2 is merged** (section 3); give an **explicit yes** on AUTH-1 and PUB-1 (0.5 h each) and on CONSENT-3 once your non-author reviewer has read it; the other contracts (SCOPE-2, RULES-1, CONTENT-2, A11Y-1, DESIGN-1, DESIGN-2) proceed on merge and you object within 48 h; one 30-minute read-through of `docs/CONTRACTS.md`, which gates only SCOPE-3, PUB-2 and CONTENT-6; DEPLOY-17 (protect main) this week or next.
- **Closing gate:** the contract sections merged with **every conflict in the section 6.2 table settled**; explicit yes recorded for AUTH-1 and PUB-1; local stack green with strict no-skip mode (`BCION_REQUIRE_LIVE=1`); **no live key readable from any worktree or present in any agent terminal's environment (SEC-15 file outside the repo, deny rules in force since DOCS-1), and the QA-2 target guard refuses non-localhost URLs**; PUB-5 merged after QA-3; CONTENT-3 merged; DESIGN-3 lint running in CI; `docs/COSTS.md` exists with measured tokens and limit hits per session (A4b); QA-3 merged.

### Wave 2 - Foundations, first staging bring-up (days 3-9)

Each lane starts on its own condition; nothing here waits for a "wave open".

| Track | Agent role | Start condition | Task ids (in order) |
|---|---|---|---|
| Reviewer calibration (own lane; touches only `tests/calibration/`) | Test engineer, strongest | QA-2, DOCS-4, DOCS-5 done | **QA-9 (ONE session): data-security-reviewer only, 5-6 seeded-flaw SQL and RLS fixtures in `tests/calibration/` (shared later with RULES-13). The 0006-0007 batch review is not requested until this calibration run is recorded.** The ux-qa half is QA-9b in Phase 2. |
| Tests | Test engineer | QA-3 merged | QA-12 (sweep script; the owner runs `--apply` before DATA-10a) ; QA-6 (2 sessions, strongest; **branched only after DATA-12 merges**; written against `main` including 0006 and 0007: 7 tables + `app_settings` + any SCOPE-3 additions; first acceptance line = backfill rows for 0006 and 0007 if they merged first) -> QA-4 (writes `docs/TESTING.md` only; its `CLAUDE.md` and `STATUS.md` changes come back as proposed lines) -> QA-5 (after DEPLOY-3) |
| Memory (lead-only edits, on main) | Lead | QA-4 merged | **DOCS-12** (refresh `CLAUDE.md` links and verified commands), applying the proposed lines from QA-4 and RULES-11 in the same edit |
| Migration (continuous; DB-touching; own second local stack) | Migration owner: **strongest for SCOPE-3 and AUTH-4** (the two multi-session cards, 2026-09-21 speed change), standard for DATA-15, DATA-12, DATA-8, AUTH-5 | QA-3 merged; contract read-through done for SCOPE-3 | DATA-15 (unit-only, may run during the QA-3 window) -> DATA-12 (0006) -> SCOPE-3 (0007, 2 sessions) -> DATA-8 -> AUTH-4 (0008, 2 sessions; needs your yes on AUTH-1) -> AUTH-5 (0009) -> continues in Wave 3 |
| Shell | Shell lane (strongest for UI-1) | DESIGN-2, DESIGN-1 and UI-2 merged (about day 3-4) | I18N-1 (**does not touch the reviewer console**: its one reviewer-import line is taken off the card and the lead adds it when PUB-5 merges, so I18N-1 never meets PUB-5 on that file) -> I18N-2 (`format_money`, not `format_inr`) -> UI-1 (2 sessions; **includes the sample-data ribbon and the `_save.html` stub. UI-1 does not edit the four journey templates**: the three `{% include '_save.html' %}` lines move into A11Y-2, the first task of the Wave 3a window, so UI-1 never meets SEC-5 or SCOPE-5 on `requirements.html`) -> DESIGN-18 (**start condition: SEC-5 merged**, because both edit `_trust_badge.html` and the order is SEC-5 -> DESIGN-18; fills the `_ask.html` and `_why.html` stubs; defines `career_card`, `evidence_line` and the other macros) -> **ux-qa pass on UI-1 plus the DESIGN-18 gallery** -> the Wave 3a window starts once DESIGN-18, **SEC-5 and SCOPE-5** are all merged (about day 6-7) |
| Rules (unit only, no DB) | Implementer, standard; RULES-4 strongest | RULES-1 merged (does not wait for CONTENT-2, AUTH-1 or A11Y-1) | RULES-2 (adds `EligibilityInput` fields only; **lands before SEC-5**) ; RULES-3 (takes the `models.py` slot **before** SCOPE-3 starts; recorded in the ledger) -> RULES-4 -> RULES-5 -> RULES-6 (**one** implementer, both exams, 2 sessions) -> RULES-11 ; RULES-10 (2 sessions, **only after DATA-12 is merged**; introduces the `Money` value type and makes `safe_source_url` public - section 6.2) |
| Eligibility (**DB-touching**, serial file group) | Implementer, standard | QA-3, SEC-1 and RULES-2 merged. **It gets the first free DB-lane slot after QA-3**, because DESIGN-18 and the Wave 3a window wait for it | SEC-5 (edits `requirements.html` and `_trust_badge.html`) -> SCOPE-5 (edits `requirements.html`; also carries SCOPE-3's one-line mapper edit in `app/api/eligibility.py`). In Wave 2 this lane is the **only** writer of `requirements.html`; both must be merged before the Wave 3a window opens |
| Hardening | Implementer, standard/strongest | DOCS-4/13 merged (SEC-1 already ran in the Wave 1 slot) | OPS-2 ; SEC-2 (after SEC-1 and PUB-5) -> A11Y-5 (new unit test only; fills the gap) -> A11Y-4 (**start condition: DEPLOY-15 merged**, because both edit `app/web/reviewer/auth.py`; order in 6.4) |
| Deploy (scripts only; no DB, no single-writer file after DEPLOY-18) | Implementer, cheap/standard | DEPLOY-1 and SEC-7 done (DEPLOY-5 already ran in the Wave 1 slot) | DEPLOY-2 (edits `docs/SECURITY.md` and `docs/ARCHITECTURE.md` only; its hosting facts for `docs/DECISIONS.md` and `STATUS.md` come back as proposed lines that the lead applies at merge. It does **not** draft D13 or D16: the lead drafts both in DOCS-5) -> DEPLOY-3 -> DEPLOY-4 -> DEPLOY-15 (after SEC-1 **and SEC-2**, because both edit `app/web/reviewer/auth.py`) -> DEPLOY-9 (after OPS-2; adds only `MAINTENANCE_MODE`) -> DEPLOY-6 ; AI-2 (after DEPLOY-5; both touch `health.py`) |
| Docs and content prep (filler) | cheap/standard | CONTENT-2 merged for the content items | TRIAL-10 ; CONTENT-4, CONTENT-5, CONTENT-15 dev parts ; **CONTENT-6 session 1** (standard: `validation.py`, CSV contract checks, unit tests, **no DB writes**) |

- **Lead-only files stay lead-only.** QA-4, DEPLOY-2 and RULES-11 each list `CLAUDE.md`, `STATUS.md` or `docs/DECISIONS.md` in their inventory text. Their cards remove those files from the owned list: the implementer returns the proposed lines in its completion report and the lead applies them at merge (RULES-11's `CLAUDE.md` command line goes in with DOCS-12 if that is still open, otherwise as a lead one-liner). DOCS-12 itself is a lead edit (Memory track above). D13 and D16 have one drafting home: the lead, in DOCS-5.
- **SCOPE-3 is cut down** to the migration, `models.py`, `claims.py` and tests. Its two one-line mapper edits go to SCOPE-5 (`app/api/eligibility.py`) and SCOPE-4 (`app/api/compare.py`) as named acceptance lines, so the migration lane never blocks the eligibility lane. The card says so.
- **Card additions:** DEPLOY-15 - the app refuses to start outside development if an unknown `SIGNUP*`-like or legacy flag name is in the environment. DEPLOY-6 - `deploy.sh` refuses to deploy when the highest migration number in the release is greater than the highest filename in `_schema_migrations` on the target (read through `/readyz` or a read-only query). CONTENT-4 and CONTENT-6 - the four content checks (missing `checked_by`, missing verbatim quote, aggregator domain, incomplete eligibility set) are **ordinary code** in `scripts/content/validation.py` with unit tests, exposed as `make content-check`; there is no LLM "content-import-checker" agent. CONTENT-5 - the trial subset contains a deadline, a backup route and a scholarship per family. QA-5 - see below.
- **QA-5 card (written now, not left open):** three jobs (unit, local-stack DB, e2e) with no skipped suites; a job that rebuilds 0001..N on an empty local stack and **fails if the hash of any migration file already tagged for apply has changed** (additive-only check); `make css` runs before the e2e server starts; a path filter so docs-only changes skip the DB, e2e and image jobs; the image is built only on `main`; pip, Playwright browsers and Supabase images are cached; `concurrency: cancel-in-progress`. The lead pushes merge batches of 3-5 branches, not one push per branch.
- Cap: during the QA-3 half-day only unit and docs lanes run. After QA-3: **up to 3 DB-touching lanes** (tests, migration, eligibility; the number is set from the QA-2 measurement) plus unit, docs and deploy-script lanes, **6 writers in total**, and only while the lead's queue is under 4 green branches.
- **Owner actions due:** **SEC-16 key rotation if not done yet (must precede DEPLOY-7)**; human parts of CONTENT-4, CONTENT-5, CONTENT-15 on **days 5-7** (only after CONTENT-18 is merged), so they are finished before the bring-up; the **CONTENT-9 maker entry in the CSV, offline, moves to days 11-12** (Wave 3) - days 8-10 carry no content work; the Hindi speaker reads the TRIAL-2 consent sheet (days 5-7; blocks TRIAL-8); staging DNS record (day 7); **DEPLOY-7 first bring-up, days 8-10, budgeted at 4-6 h spread over the three days**, using the existing four screens plus the ribbon; chase the checker and the consent reviewer if not yet named (day 5 is the latest safe date).
- **DATA-10a (owner, end of Wave 2, about day 8-9): run the QA-12 `--apply` sweep, then `apply --through 0007` from the `staging-batch-A` tag, then the synthetic seed.** Only after (a) the data-security batch review of 0006-0007 has no open critical or high finding, (b) revert-to-prove is recorded for the DATA-12 policy and the SCOPE-3 freeze trigger (all earlier columns carried forward), and (c) the QA-6 matrix rows for their tables are green (in CI once QA-5 exists; until then run by the lead on the local stack).
- **Closing gate:** UI-1, DESIGN-18, I18N-1 and SCOPE-3 merged; CI runs three jobs with no skipped suites and a fresh-migration rebuild; the **matrix covers every table and policy added this wave, run by the lead**; QA-9 calibration recorded; one data-security pass over the wave's non-schema security code (SEC-1, SEC-2, SEC-5, OPS-2, A11Y-4, DEPLOY-15, DEPLOY-9); QA-12 dry-run reports zero matches on the staging project after the owner's sweep.

### Wave 3 - Exclusive template window, then screen fan-out (days 7-13)

**3a - while the existing templates are held (about 1 day). Start condition: DESIGN-18, SEC-5 and SCOPE-5 are all merged.** A late eligibility lane delays the window; it never edits `requirements.html` inside it.

| Track | Agent role | Task ids (in order) |
|---|---|---|
| Template window (no other merge touches `explore.html`, `compare.html`, `requirements.html`, `timeline_calculator.html`, `base.html`, `_trust_badge.html`) | Shell lane, then 3 short parallel sessions | A11Y-2 (**also adds the one `{% include '_save.html' %}` line to `compare.html`, `requirements.html` and `timeline_calculator.html`**; moved here from UI-1) -> I18N-3 **split by file**: the shell lane takes `base.html`, `_trust_badge.html` and the string-lint; three parallel cheap/standard sessions take `explore.html`, `compare.html`, and `requirements.html` with `timeline_calculator.html`, each writing only its own key prefix (sorted keys keep the catalogue merges line-disjoint). **The lint merges last, so it passes.** |
| New-file screens (safe during the window; they consume the DESIGN-18 macros) | 2 implementers, standard | UI-3 -> UI-4 (fills `_why.html` content only) ; UI-5 (2 sessions) |
| API work that touches no template | Implementer, strongest for RULES-8 | RULES-8 (after RULES-5, SEC-5, SCOPE-5, RULES-2; uses the public `safe_source_url` from RULES-10, so it no longer waits for SCOPE-4; data-security pass) ; RULES-9 session 1 (`timeline_assembly.py`, `rules/timeline.py`, `api/timeline.py`) |
| Guest save (new files only) | Implementer, standard | AUTH-6 (2 sessions), right after AUTH-5 and SEC-2: touches **only** `_save.html`, `my_plan.html`, `plan_pages.py`, `plan_store.py`. It is no longer last on any template. Its AUTH-3 dependency is dropped (guest first). |
| Migration (continuous) | Migration owner, strongest | PUB-2 (0010, 2 sessions, **failing reproduce test first**) -> PUB-3 (0011, 2 sessions) |
| Content | standard | CONTENT-4, CONTENT-5, CONTENT-15 dev parts continue |

**3b - after I18N-3 merges; one open task per template file:**

| Template lane | Task ids (in order) |
|---|---|
| `compare.html` and cost engine | UI-6 -> SCOPE-4 (limited to the no-cross-currency-sum guard, `format_money` display, the template, and SCOPE-3's one-line mapper edit in `app/api/compare.py`) |
| `timeline_calculator.html` | UI-7 -> RULES-9 session 2 |
| `requirements.html` | Full order across waves: SEC-5 -> SCOPE-5 (Wave 2, eligibility lane) -> A11Y-2 (with the `_save.html` include line) -> I18N-3 (Wave 3a window) -> SCOPE-6 -> RULES-16 (starts as soon as SCOPE-6 is done; RULES-8 is already in) |
| `_trust_badge.html` (shared partial, single writer) | SEC-5 -> DESIGN-18 (enforced by DESIGN-18's start condition "SEC-5 merged") -> I18N-3 -> SCOPE-4 -> RULES-16. The lead merges SCOPE-4's edit before RULES-16's. |
| E2E | QA-7 after the screens (UI-3, 4, 5, 6, 7) |

**AUTH-6 acceptance lines (its own test module; also in the closing gate):** guest B's cookie cannot read, tick or delete guest A's plan; a forged or expired token is rejected.

- Peak: **6 writers**, counting the migration and shell slots, and only while the lead's queue stays under 3 green branches. Read-only reviewers are extra.
- **DEPLOY-7 is owner-only on the VM** (started in Wave 2, days 8-10). The agent's part is limited to repo artefacts - nginx templates, env-file templates with variable names only, a checklist - and reading PII-free output you paste. No agent gets SSH access or reads `/etc/eduvation/*`. You type the secret values. Executor: owner; zero dev sessions on the VM.
- **Owner actions due, in order:** **CONTENT-9 maker entry, offline in the CSV (days 11-12, about 2 h a day; moved out of days 8-10)**; **DATA-10b = `apply --through 0009` from the `staging-batch-B` tag, in the same sitting as a `deploy.sh staging` redeploy** (guest save cannot work on staging without 0008 and 0009), only after the batch review of 0008-0009 (AUTH-4 and AUTH-5 RLS, hashed guest token) has no open critical or high finding, revert-to-prove is recorded for the AUTH-4/AUTH-5 RLS, and their matrix rows are green in CI - these are preconditions of the lead's notice, not an afterthought; UI-15 phone walk-through (needs QA-7, DEPLOY-7 and DATA-10b; **day 13-14, which keeps at least one full day of float after the day 8-10 bring-up** - if DEPLOY-7 overruns to day 11-12 it still does not move UI-15 or TRIAL-8); **PUB-4 = `apply --through 0011` from the `staging-batch-C` tag**, within 24 h of the adversarial review of 0010-0011 passing (about day 13-14); then **PUB-13b** (checker account, `reviewers` rows, `critical_authorised`).
- **DEPLOY-7 standing gate (holds from first bring-up and at every later deploy):** **SEC-16 done - the staging service-role key, JWT secret and DB password were rotated after QA-2 merged, the env files under `/etc/eduvation/` hold only the new values, and the app env holds no service-role key**; SEC-5, OPS-2, A11Y-4 and DEPLOY-9 deployed; dashboard sign-ups off; **`POST /auth/sign-up` returns closed with the env file as deployed**; **`/readyz` reports `AI_ENABLED=false`**; basic auth on; `/healthz` and `/readyz` exempt from basic auth; ribbon visible; pause drill and smoke test pass; logs show no `age=` strings; **the QA-12 dry-run reports zero matches on the staging project and zero published claims carry a fixture verifier or source**. You run `deploy.sh`, the smoke test and the applies from your own shell and paste PII-free output (counts, pass/fail, commit hash) to the lead.
- **Round-1 build is pinned.** After the last apply before TRIAL-8 the lead tags `round1-rc`; you deploy that tag. **No deploy and no apply to staging between the first and the last TRIAL-8 session.**
- **Closing gate:** QA-7 guest journey green in CI; staging passing the standing gate; one ux-qa pass; batch-B review done before DATA-10b; one data-security pass on RULES-8, AUTH-6 and CONTENT-6 session 1; the AUTH-6 cross-user lines green; **matrix covers every table and policy added this wave, run by the lead**.

### Wave 4 - Usability round 1 alongside the integrity chain (days 13-19)

| Track | Agent role | Worktree | Task ids (in order) |
|---|---|---|---|
| People | Moderator(s), participants, owner | - | TRIAL-8 (about days 15-18, 2-3 days, guest only, **adults only**, on the `round1-rc` tag) -> **owner purges `guest_sessions` and guest plan rows on staging and records count = 0** -> owner de-identifies notes -> TRIAL-9 |
| Migration (continuous) | Migration owner, strongest | yes | SEC-6 (0012) -> CONSENT-4 (0013, 2 sessions; **only after CONSENT-3 passed its human read**; if that read is late, CONSENT-4 rolls into P2-A and nothing in Phase 1 waits for it) |
| Content | standard / cheap | yes | **CONTENT-6b** (after PUB-3 merges: DB upsert, `tests/db/test_content_import.py`, tier and `source_version`, content hash, **and the read-only `make content-integrity` query with its local-stack DB test** - exit gate 3) -> CONTENT-7 (review packets print the database hash next to the hash on the checker's signed offline sheet) |
| Hardening | standard | yes | SCOPE-13 |
| Trial prep | standard | yes | TRIAL-3 (**English draft only**; the Hindi half moves to the end of Phase 2 with TRIAL-4) |
| **Float** (only when a lane and a lead merge slot are free) | Implementer, strongest for AUTH-2 | yes | Accounts, single stream: AUTH-2 -> AUTH-3 (flag off) -> AUTH-14. Consent (needs CONSENT-4): CONSENT-6 -> CONSENT-7 ; CONSENT-8 ; CONSENT-10 ; then CONSENT-6b |
| Content prep | Owner as maker, offline | - | CONTENT-9 maker entry **in the CSV and on the local stack only** (done on days 11-12, Wave 3; any remainder here) - no real record enters the staging database before PUB-4 **and** the end of TRIAL-8 |

- Cap: 4-5 writers.
- **PUB-2 and PUB-3 acceptance lines (both cards):** `tests/db/test_content_import.py` and the reviewer-console approve test stay green or are updated in the same PR; an imported draft can be submitted, approved by a second `critical_authorised` reviewer through `publish_claim`, and carries a `source_version` row. CONTENT-2 and PUB-1 state how a `source_version` is created in Phase 1 without PUB-6: the importer inserts it from the `sources_register` row (URL, document version, publication date, accessed date). If the console approve path cannot publish after 0010-0011, pull a slim PUB-7 forward.
- **Content-hash rule (PUB-1 and CONTENT-2 contracts; CONTENT-6b and CONTENT-7 acceptance):** the importer stores a content hash of (entity, field, value, currency, cycle, jurisdiction, source_key, quote) per row. Fast re-approval on production (D3) is allowed only when the database hash matches the hash on the checker's signed offline sheet. Any mismatch, or any row edited after `checked_by` was filled, gets full source re-verification. **Agents never fill `checked_by` or the quote columns**; `make content-check` flags agent-authored quotes.
- **Float-card acceptance lines (each in the card's own test module):** AUTH-2 and AUTH-14 - student B's cookie gets 403/404 on A's `/my-plan` items, and a reviewer cookie cannot open student pages; AUTH-14 also owns the `needs_review` changed-info banner (section 4). CONSENT-7 - the distress hook fails open to the helpline card, with a logged code and no 500, if the flag write fails (the table may not be on staging yet). QA-10 stays in Phase 2 as the browser-level repeat.
- **TRIAL-8 safety:** **Round 1 is adults only (18+): 18+ students or recent school-leavers, a parent, a teacher. No under-18 participant before CONSENT-11 (Phase 2), and no minor in any study before CONSENT-14.** TRIAL-1 recruitment profiles say the same. Moderators tell everyone not to type real identifying details. Sessions are guest-only. No recordings. UI-15, AUTH-6 **and UI-4** (the preference change) must be on the `round1-rc` build, because two of the six `docs/UI.md` criteria need them. The weaker Class 8-12 evidence is recorded as a limitation in `round1-findings.md`.
- **No agent on staging from here on.** From the first TRIAL-8 session no agent, including the lead, holds staging credentials or queries that database (section 8.4). "De-identify notes" covers the paper notes; the purge covers the database rows.
- **Owner actions due:** PUB-4 and PUB-13b if not already done (they must land before `round1-rc` is tagged, or wait until TRIAL-8 ends); moderate at most half of the TRIAL-8 sessions and observe two; purge guest rows and de-identify notes before any agent reads anything; **after TRIAL-8 ends: import the CONTENT-9 CSV on staging, the named checker approves, timed in the TRIAL-7 log; then you run `make content-integrity` against staging from your own shell and paste the three counts (all must be zero)**; **DATA-10c = `apply --through 0013` from the `staging-batch-D` tag** after its batch review; book the SEC-13 signer and send the TRIAL-14 letter this week at the latest (before the festival and school-holiday period).
- **Closing gate:** adversarial data-security pass on 0010-0011 done **before PUB-4**; every bypass test proven by revert (revert the policy, watch the test fail, restore it); **matrix covers every table and policy added this wave, run by the lead**, and runs in CI; PUB-4 applied and PUB-13b done; **staging guest rows purged, count = 0 recorded**; round 1 scored on the six `docs/UI.md` criteria; if any float auth card merged, its cross-user lines are green.

### Wave 5 - Close (days 19-23)

| Track | Agent role | Worktree | Task ids (in order) |
|---|---|---|---|
| People | Owner as maker + named checker | - | CONTENT-9 finishes: import to staging (after TRIAL-8 and the purge), the checker approves, publish, **timed** in the TRIAL-7 log; the owner then runs `make content-integrity` on staging and pastes the counts (exit gate 3). A labelled rehearsal (content batch 0); records are re-imported and re-approved on production in Phase 2 under the content-hash rule. |
| Float / first Phase 2 task | Implementer, standard | yes | UI-19 (2 sessions, round-1 fixes) and any unfinished float card from Wave 4. None of them is in the Wave 5 close. |
| Phase 2 head start (optional, cheap) | cheap/standard | yes | SCOPE-8, SCOPE-14. Paid offline pre-verification for CONTENT-10 and SCOPE-9 may start only when these two exist **and** CONTENT-9 has timed its first ten or so claims. |
| Exit | Lead | no | Exit verification against section 4; `STATUS.md` and `docs/COSTS.md` actuals. The lead verifies from the local stack, CI and the PII-free output you paste; it does not touch staging. |

- Cap: 2-3 writers.
- There is **no migration lane in Wave 5**. AUTH-7 and AUTH-10 are Phase 2 (P2-A); they reach staging with DATA-11. Staging ends Phase 1 on 0006-0013 (or 0006-0012 if CONSENT-4 floated).
- **Closing gate:** the Phase 1 exit gate in section 4.

### Calendar summary

Day 1 = Tue 22 Sep 2026. Weekdays only; public holidays (for example 2 Oct) are not removed, so each one adds a day.

| Wave | Days | Calendar (2026) | Writers (max) | Owner hours (rough, incl. operating the sessions) |
|---|---|---|---|---|
| 0 | 1-2 | 22-23 Sep | 1-2 (+ the three early lanes) | 8 |
| 1 | 1-4 | 22-25 Sep | burst + 4 | 12 |
| 2 | 3-9 | 24 Sep - 2 Oct | up to 6 (3 DB-touching) | 21 (SEC-16, the content human parts on days 5-7 and DEPLOY-7 are here; days 8-10 peak at about 4-4.5 h) |
| 3 | 7-13 | 30 Sep - 8 Oct | 6 | 18 (includes the CONTENT-9 maker entry on days 11-12) |
| 4 | 13-19 | 8-16 Oct | 4-5 | 21 (round 1 is about 7 of these with a second moderator) |
| 5 | 19-23 | 16-22 Oct | 2-3 | 8 |
| **Total** | **about 22-27 working days; exit between about 21 Oct and 28 Oct 2026** | | | **about 88, plus about 8 h of Phase 2 booking = about 96** |

The exit date is set by two things: round-1 recruit readiness (TRIAL-8 scoring) and the checker's CONTENT-9 turnaround. If adult recruits are not ready by day 15, 1B work continues and the exit slips to about day 27-30. Nothing else in the plan waits on them.

**Festival and holiday caution (dates from memory - check a calendar):** Navratri and Dussehra fall in mid-to-late October 2026 and Diwali in early November. That is exactly when TRIAL-8, the checker's CONTENT-9 sitting, and the Phase 2 reviewer work and TRIAL-14 school approach are due. Book TRIAL-8 slots and the checker's sitting **by date** in week 1, and send the TRIAL-14 letter before the holidays.

---

## 6. Parallelism map

### 6.1 Do these first - the unlockers

| Order | Task | What it unlocks |
|---|---|---|
| 1 | DOCS-1 | Clean main. Worktrees cannot see uncommitted edits. Commits the owner's 2026-09-21 parallel-work decision and the day-1 `.claude/settings.json` deny rules, then fast-forwards `main`. |
| 2 | CONSENT-18 (dashboard sign-ups off) + SEC-15 (live keys into an owner-only file outside the repo, never a shell profile) — **CONSENT-1 itself is superseded**, the real gate is merged already | Makes sure no agent can read a live key: the keys are in no agent's folder or environment, and until QA-2 the owner runs any `test-db` himself. SEC-15 blocks any fan-out. SEC-16 (rotation, after QA-2) covers the keys' earlier exposure. The dashboard toggle and the merged age/guardian-email gate (0004/0005) together close the sign-up hole; CONSENT-1's kill-switch would have been redundant. |
| 3 | DOCS-3 | Card numbers, migration ledger, stale-name ledger, card stubs. Seven tasks each assumed BCI-007; ten assumed 0006. |
| 4 | DOCS-4 with DOCS-13 and DOCS-6 | Ownership map, single-writer list, `implementer.md`, `migration-owner.md`, the settings allowlist (the deny rules landed in DOCS-1), cost file. The full caps apply only after this. |
| 5 | QA-1 -> QA-2 -> QA-3 | Agents verify migrations on a local stack. No silent skips. Concurrent test runs. Started on day 1-2, not after SEC-7. |
| 6 | DEPLOY-18 (standard, reviewed, fails closed), UI-2, PUB-5 (after QA-3) | Three short sessions: after them no lane edits `config.py`, `main.py` or the Makefile, and about 25 later tasks are file-disjoint. |
| 7 | SEC-7 | Lockfile before anyone adds a dependency or builds an image. |
| 8 | DESIGN-2 -> I18N-1 -> UI-1 -> DESIGN-18 | Strings written as keys once; shell, stub partials and content macros exist before any screen is built on them. |
| 9 | SCOPE-3 | First schema change that content, currency and coverage all sit on. |
| 10 | RULES-5 | Reference exam module; after it the exam modules fan out. |

### 6.2 Contracts to freeze first (one file: `docs/CONTRACTS.md`, 1,500-word cap)

| Contract | Owner task | Conflict the burst must settle |
|---|---|---|
| Money and currency | SCOPE-2 + RULES-1 | Original currency only, never converted, never summed across currencies. Integer amounts. `format_money(amount, currency)`. **Settled: RULES-10 introduces the `Money` value type (integer amount + ISO currency, default INR) in every component and total signature, so the type changes once. SCOPE-4 is limited to the no-cross-currency-sum guard, display and the template.** |
| Duration, dates, cycle, DOB | RULES-1, SCOPE-2 | DOB is per request, POST body only, never stored, logged or in a URL. IST is "today". |
| Three eligibility outcomes | RULES-1 | No verified rules -> `insufficient_information` + `no_verified_rules`. Message codes, not English. "Personal inputs are POST-only." |
| Evidence states, stale, sample label | PUB-1, DATA-12, SCOPE-2 | Per-tier review-due; `is_sample`; coverage "not verified yet". |
| Publishing evidence in Phase 1 | PUB-1, CONTENT-2 | Per-row content hash; how a `source_version` is created by the importer without PUB-6; fast re-approval only on a hash match (Wave 4). |
| Entity vocabulary | SCOPE-2 | Closed list now, even though tables arrive in DATA-4. States in one line how a backup or alternative route is represented (`pathway_transitions`, kept in DATA-4) so UI-20 has a source. |
| Error shape, sessions, guest state, flags | AUTH-1 | Quick-start answers are stateless query params; guest plans use the server session. Birth year not stored. One flag list: `SIGNUP_ENABLED`, `MAINTENANCE_MODE`, `AI_ENABLED`, `HINDI_UI_ENABLED`, `ALLOWED_HOSTS`, `MINOR_ACCOUNTS_ENABLED`, plus the demo-mode guard. DEPLOY-18 adds all of them to `config.py` with fail-closed defaults. `SIGNUPS_ENABLED` (with an S) is a stale name and must not exist anywhere. |
| Difficult states and cache class | A11Y-1 | `no-store` everywhere except `/static`. A11Y-4 owns it; SEC-1 drops its own no-store logic. |
| Keys and components | DESIGN-2, DESIGN-1 (docs); I18N-1, UI-1 (code) | Flat `screen.element` keys; stub partials `_report`, `_ask`, `_why`, `_save`, `_states`. |
| Rule approval lives in git JSON | RULES-1 | Deviation from build pack section 6 - DECISIONS entry. |
| Migration ledger, fixtures | DOCS-3, DOCS-4, QA-2/3/4 | Additive only; freeze-trigger column carry-forward; new table = new matrix row. |

After the gate, contract changes are additive only and need a DECISIONS line from the lead.

Where contract text lives: the inventory says the contract tasks write into `docs/DATA.md`, `docs/UI.md` and `docs/ARCHITECTURE.md`. This plan moves the contract text into `docs/CONTRACTS.md` (and `docs/CONSENT.md` for CONSENT-3). Each contract task appends only a **one-line pointer** to its section in the older doc. DESIGN-1 and A11Y-1 still edit `docs/UI.md` itself, in that order.

### 6.3 What can run in parallel (files are disjoint)

- Exam modules are file-disjoint, but Phase 1 runs RULES-6 as one implementer in one worktree (each extra worktree costs a lead merge cycle). RULES-15 and RULES-7 fan out in Phase 2.
- During the I18N-3 window: new-file screens UI-3, UI-4, UI-5; RULES-8 and RULES-9 session 1 (no template); AUTH-6 (new files only); the three per-file I18N-3 sessions.
- After I18N-3: one lane per template file.
- The Rules unit lane and the Deploy scripts lane never contend for the local stack, so they do not count against the DB-lane cap.
- Deploy scripts; content scripts (CONTENT-3, 4, 7, 15); docs cards; QA specs (QA-6, QA-7).
- Reviewer-console files after PUB-5. Consent modules after CONSENT-4.
- Read-only reviewers, alongside the next fan-out.
- All owner and people work, alongside everything.

### 6.4 What must NEVER run in parallel (conflict groups)

| Group | Rule |
|---|---|
| `db/migrations/*`, `apply_migrations.py`, `app/data/models.py`, `tests/db/access_matrix.py` (after QA-6), DATA.md schema section | One migration owner, on its own second local stack. One open migration. Order: DATA-15, then 0006-0013 as listed in section 5. RULES-3 takes its `models.py` slot before SCOPE-3 opens. Additive only. Only the owner applies to cloud projects, with `--through`. |
| Contract docs | One serial burst by one agent. Never two bursts. `docs/UI.md` order: DESIGN-1 -> A11Y-1 (A11Y-1 carries the usability-wording fix; TRIAL-2 no longer edits `docs/UI.md`). |
| Shell: `base.html`, `_components.html` | UI-1 -> DESIGN-18 -> A11Y-2 -> I18N-3 (shell part) -> AUTH-3 (float) -> the rest, one at a time. |
| `_trust_badge.html` | SEC-5 -> DESIGN-18 -> I18N-3 -> SCOPE-4 -> RULES-16. Enforced by a start condition: DESIGN-18 starts only after SEC-5 is merged. |
| `_why.html` | UI-1 stub -> DESIGN-18 macro -> UI-4 fills content only. |
| Journey templates | One open task per file. **UI-1 does not edit them.** `requirements.html`: SEC-5 -> SCOPE-5 -> A11Y-2 (adds the `_save.html` include line) -> I18N-3 -> SCOPE-6 -> RULES-16. `compare.html`: A11Y-2 (include line) -> I18N-3 -> UI-6 -> SCOPE-4. `timeline_calculator.html`: A11Y-2 (include line) -> I18N-3 -> UI-7 -> RULES-9 session 2. `explore.html`: SEC-1 -> A11Y-2 -> I18N-3 -> SCOPE-6. The Wave 3a exclusive window opens only when DESIGN-18, SEC-5 and SCOPE-5 are all merged. AUTH-6 never edits these files (A11Y-2 pre-wires the `_save.html` include; UI-1 ships the stub). |
| `tests/db/**` and `tests/e2e/**` during QA-3 | Exclusive window for QA-3 (half a day). DATA-12, SCOPE-3, SEC-5 **and PUB-5** branches are cut only after it merges (PUB-5 edits `tests/db/test_reviewer_console.py`; its start condition is "QA-3 merged", and SEC-1 and DEPLOY-5 take the mechanical slot before it). |
| `app/web/pages.py` | UI-2 alone first, then I18N-1, then per-screen modules only. |
| Eligibility engine and API | RULES-2 (input fields only) -> SEC-5 -> SCOPE-5 (with SCOPE-3's mapper line) -> RULES-8 (-> I18N-15 in Phase 2). SCOPE-3 itself does not touch `app/api/eligibility.py`. |
| Cost engine: `cost.py`, `comparison.py`, `api/compare.py` | DATA-12 -> RULES-10 (Money type; makes `safe_source_url` public) -> SCOPE-4 (with SCOPE-3's mapper line in `api/compare.py`) (-> SCOPE-7 in Phase 2). Money types change once. RULES-8 only imports from `comparison.py`. |
| `app/api/auth.py` | OPS-2 -> DEPLOY-9 -> CONSENT-6 -> CONSENT-7. (CONSENT-1 dropped, superseded — the merged guardian-consent gate already carries the age/guardian-email code on this exact file; OPS-2 is the first Phase-1 lane to touch it again.) |
| Plans and account surface | Single stream: AUTH-5 -> AUTH-6 -> AUTH-2 -> AUTH-3 -> AUTH-14 (float) -> in Phase 2: AUTH-9 -> UI-13 -> AUTH-7 -> AUTH-10; CONSENT-7's hook into `plans.py` lands after AUTH-5. |
| `claims.py`, reviewer console | PUB-5 alone first; then SCOPE-3 -> SCOPE-13 (-> PUB-7 in Phase 2). I18N-1 stays out of this group: its reviewer-import line is a lead one-liner at the PUB-5 merge. `app/web/reviewer/auth.py`: SEC-2 -> DEPLOY-15 -> A11Y-4. |
| Lockfiles, `pyproject.toml` | SEC-7 -> QA-3. One dependency slot at a time. |
| `ci.yml` | SEC-7 -> QA-2 -> DEPLOY-3 -> QA-5 -> RULES-11. (DESIGN-3 is `tests/unit/test_copy_rules.py`; it runs inside the existing unit job and needs **no** `ci.yml` edit, which is how it is in CI by the Wave 1 close.) (The graph listed QA-5 before DEPLOY-3, but QA-5 depends on DEPLOY-3; the dependency wins. Recorded in DOCS-3.) |
| `main.py`, `config.py`, `.env.example`, Makefile | **DEPLOY-18 is the last task to edit them.** After it, a lane ships its middleware or router as a named module the registry loads, its flag is already in `config.py`, and its make targets live in its own `mk/<task>.mk`. Middleware order and slot names are fixed in the registry and frozen on the DEPLOY-18 card: TrustedHost -> security headers (SEC-1) -> maintenance (DEPLOY-9) -> request id and logging (OPS-2) -> cache policy (A11Y-4) -> Origin check (SEC-2) -> usage events (TRIAL-16, optional, Phase 2). **The registry fails closed:** outside development the app refuses to start if a slot marked required (all but usage events) is absent or misnamed; a unit test asserts the order. DEPLOY-18 is standard tier and sits in data-security pass 1. The tasks scheduled after it that named these files in the inventory (SEC-7, PUB-5, SEC-1, DEPLOY-5, OPS-2, A11Y-4, DEPLOY-9, DEPLOY-15, AI-2) run from cards that DOCS-3 rewrote to use `mk/*.mk` and registry modules. One sign-up flag only. The flag list is provisional until the AUTH-1 yes; a change after it, and anything DEPLOY-18 missed, is a lead one-liner. |
| `tests/db/conftest.py`, `tests/e2e/conftest.py` | QA lane owns them. Migration cards append one block through the lead. |
| `app.css` (generated), `STATUS.md`, `DECISIONS.md`, `CLAUDE.md`, `KNOWN_ISSUES.md`, `tasks/INDEX.md`, `.claude/agents/*`, `.claude/settings.json` | Lead only. A card whose inventory text lists one of these files (QA-4, DEPLOY-2, RULES-11, the contract tasks) has it removed from the owned list: the implementer returns **proposed lines only** and the lead applies them at merge. DOCS-12 is a lead edit, not an implementer task. D13 and D16 are drafted once, by the lead, in DOCS-5. Implementers run `make css` in their worktree before any e2e but **never stage `app.css`**; a pre-merge check rejects a branch diff that contains it. |
| Shared local stack | Reset only by the lead, at a merge-batch boundary, after marking "RESET" on the `tasks/INDEX.md` lockboard with no run in flight. The migration lane never resets it; it has its own stack. |
| Live Supabase project (= staging) | Until QA-2: no agent runs against it. If a merge needs a DB run, the **owner** runs `make test-db` in his own terminal (owner-only key file loaded there and nowhere else), one run at a time, and pastes the summary line; otherwise the run waits for the local stack. After QA-2: no test run targets it at all, except the owner-run QA-16 in Phase 2. |

---

## 7. Critical path and human long poles

**1A dev path:** DOCS-1 -> DESIGN-2 -> I18N-1 -> UI-1 -> DESIGN-18 -> A11Y-2 -> I18N-3 -> {UI-6 -> SCOPE-4 | SCOPE-6 -> RULES-16 | UI-7 -> RULES-9 session 2} -> QA-7 and DEPLOY-7 (in parallel; DEPLOY-7 does not depend on QA-7) -> UI-15 -> TRIAL-8 -> TRIAL-9. The path ends at TRIAL-9; UI-19 is float or the first Phase 2 task. RULES-8 and AUTH-6 are off this path (they run during the I18N-3 window).

**Data path into staging:** SCOPE-2 -> RULES-1 -> PUB-1 -> CONTENT-2 -> SCOPE-3 -> DATA-10a (you) ; AUTH-4 -> AUTH-5 -> DATA-10b (you). DEPLOY-7 needs neither; it comes up on the existing screens.

**1B integrity path:** QA-3 -> DATA-15 -> DATA-12 -> SCOPE-3 -> AUTH-4 -> AUTH-5 -> PUB-2 -> PUB-3 -> adversarial review -> PUB-4 (you) -> PUB-13b (you) ; CONTENT-6 -> CONTENT-6b -> CONTENT-7 -> CONTENT-9 import (you, after TRIAL-8) -> CONTENT-9 approval (checker). It no longer passes through CONSENT-4 or SEC-6.

The eight serial migrations plus DATA-15 and DATA-8 are about 15 sessions (7-8 days) in one lane. That lane must never idle, so it has no wave gates and the consent reviewer's lead time no longer sits in front of PUB-2.

**Long poles - all of them are people:**

| Pole | Lead time | Latest safe start |
|---|---|---|
| Round-1 recruits (TRIAL-1), **all 18+**: shared-phone user, Hindi-preferring user, an 18+ student or recent school-leaver, a parent, a teacher. Plus a moderator who is not the owner | 2-3 weeks | Day 1; book session slots by date in week 1 |
| Name and onboard the checker (CONTENT-1, PUB-13a, then PUB-13b) | 1-2 weeks | Day 1; hard stop day 5 |
| Hindi reviewer named (I18N-6); a Hindi speaker reads the TRIAL-2 consent sheet | 1 week | Day 3; sheet read by day 5-7 (blocks TRIAL-8) |
| Non-author consent reviewer and safeguarding person (CONSENT-2) | 1-2 weeks | Day 1; CONSENT-3 is written without them, but **CONSENT-4 cannot merge without the human read** |
| QA-1 (Docker + Supabase CLI) | Same day | Day 1 |
| SEC-15 (live keys out of the repo folder, into an owner-only file) | 30 minutes | Day 1; blocks any fan-out |
| SEC-16 (rotate the staging service-role key, JWT secret and DB password) | 30 minutes | The day QA-2 merges (about day 4-6); hard stop before DEPLOY-7 (day 8) and PUB-13b |
| Owner apply steps: DATA-10a, DATA-10b, PUB-4, DATA-10c | Same day each | Within 24 h of the lead's notice |
| DEPLOY-7 first bring-up (first-time, human-only) | 4-6 h spread over 3 days | Days 8-10 |
| SEC-13 signer booking (Phase 2) | Weeks | End of week 2 |
| TRIAL-14 school letter (Phase 3) | Weeks | Week 2-3 |

---

## 8. Agent team and parallel-workflow deployment ("team building")

**Read this first.** You already decided this. The top entry of `docs/DECISIONS.md` (2026-09-21, "No agent swarm" working rule removed) allows parallel multi-agent work, and the working-tree `CLAUDE.md` already reads: "One bounded task per agent; no whole-product attempts. Parallel multi-agent workflows are allowed (owner decision 2026-09-21): disjoint files, separate worktrees, never parallel edits to a migration, lockfile or shared schema; the lead session verifies and merges." Both edits are uncommitted; **DOCS-1 commits them**. The entry's guardrails, which this design follows to the letter:

- one bounded task per agent;
- parallel implementers only on disjoint files in separate worktrees;
- never parallel edits to a migration, lockfile or shared schema;
- the lead session verifies (runs the suite itself) and merges;
- reviewer agents stay read-and-test-only; every `CLAUDE.md` non-negotiable is unchanged.

So the only preconditions for fan-out are: DOCS-1 committed and fast-forwarded into `main` **with the `.claude/settings.json` deny rules in it**, SEC-15 done, and (for the full caps) your approval of the new agent files and the settings allowlist. The caps in 8.3 are **this plan's own, stricter operating limits**, not a new decision; you approve them on day 1 with DOCS-1. No second DECISIONS entry is written for this.

### 8.1 Roster

| Role | Model tier | Trigger | Tools | Stop conditions |
|---|---|---|---|---|
| **Operator** - you. Launches, watches and unblocks the sessions: worktree creation, permission prompts, rate-limit stalls, restarting a stopped implementer | - | Every working day | - | About 1 h a day in Waves 0-2 and 5, 2 h a day in Waves 3-4 (about 30 h; counted in section 10). The allowlist in `.claude/settings.json` (DOCS-13) keeps this low. |
| **Lead integrator** - the only merger; one lead session at a time. **Standard tier for routine verify-and-merge; strongest only for migration merges, conflict resolution and wave close** | standard / strongest | Every wave | All, **except** any staging or production credential | Suite red or any suite skipped. Two merges in a row need conflict fixes -> cap drops to 2. More than 3 merged branches waiting on the owner -> stop spawning. **More than 4 green branches waiting in its own queue -> no new fan-out.** |
| **Implementer** (N per wave, one worktree each) | per card | Card ready and its contract frozen | Read, Edit, Write, Grep, Glob, Bash for targeted tests only. Files holding live values are denied by `.claude/settings.json` (Read, Edit and the Bash patterns that print them); `.env.example`, `.env.test.example` and the local-stack `.env.test` are allowed | Needs a file outside its owned list. Same failure survived two fixes. Contract unclear. It reports and stops. |
| **Migration owner** (one serial lane) | strongest/standard per card | Any card in the migration group | As implementer + `make test-db-reset` on **its own second local stack** (never the shared one) | Asked to touch the freeze trigger without the full column list. Never two open migrations. Never edits a file already tagged for apply. Never applies to cloud. Never merges without its matrix rows. |
| **Shell lane** (serial until I18N-3) | strongest for UI-1, else standard | UI-1, DESIGN-18, A11Y-2, I18N-3 | As implementer | A reviewer template breaks. Never stages `app.css`. |
| **Test engineer** (a lane, not a new file) | strongest for QA-2, QA-6, QA-9 | QA-2, 3, 5, 6, 7, 9, 12 | As implementer | The localhost-only target guard trips. |
| **Contract agent** | strongest | Wave 1 only | Read, Edit, Write on docs | Finds a conflict it cannot settle from DECISIONS -> asks the lead. |
| **data-security-reviewer** (exists) | strongest | Migrations, definer functions, grants, auth, sessions, export, deletion, publication, import, unauthenticated writes, new data flows | Read, Grep, Glob, Bash (tests, local stack only) | Nothing in scope changed -> says so and stops. |
| **ux-qa-reviewer** (exists) | standard | Once per merged UI wave, and at DEPLOY-7 | Same | No reachable journey. |
| **ai-evaluator**, **release reviewer** | standard / strongest | Phase 2 only | Read-only | Always hands over to a person. |

Not built: a "content-import-checker" LLM agent (its four checks are deterministic, so they are ordinary code in `scripts/content/validation.py` behind `make content-check`, per the CLAUDE.md rule "ordinary code for facts, rules and arithmetic"), manager agents, an orchestration server, per-area architects, a separate i18n or a11y reviewer, judge panels, two implementers competing on one card.

### 8.2 Standard per-wave workflow template

| Step | Who | What |
|---|---|---|
| A. Freeze | Contract agent + owner | Contracts for the wave are merged. **Silence never decides anything in section 13 list (a)**: SCOPE-1/D2, D3, D6, D10, D13, D14, D16, the AUTH-1, CONSENT-3 and PUB-1 sign-offs, agent-file approvals, and anything touching consent, publication or data flows need your explicit yes; dependent work waits. For list (b) (reversible technical choices) a default applies after 24 h, written as "PROVISIONAL default - not owner-confirmed, reversible until <task>" on the task card or in `docs/CONTRACTS.md`, **never in `docs/DECISIONS.md` as a decision**. |
| B. Cards | Lead + owner | During the previous wave the lead fills `tasks/TEMPLATE.md` per task (owned files, forbidden files, contract section, tests to run, reserved migration number, flag names, matrix rows for a migration) and prepares **one card table per wave**: id, owned files, forbidden files, tier, tests, migration number. You approve the table once (about 1 h per wave); under the CLAUDE.md conflict order, approving the table approves those cards. Lead marks "in progress" in `tasks/INDEX.md` (the lockboard). |
| C. Fan-out | Lead + operator | One worktree per implementer from clean main. Worktree setup runs `npm ci` (or junctions `node_modules` from the main checkout) so `make css` works. Prompt = the card + `implementer.md` + one contract section. Never the whole repo, never the inventories or this plan. No secrets, no `.env` (denied by `.claude/settings.json`), no student data. |
| D. Targeted tests | Implementer | Local stack, strict no-skip flag; `make css` before any e2e. Completion report: files touched, anything DEPLOY-18's registry missed, proposed STATUS and DECISIONS lines, test counts and skip counts. |
| E. Review | Triggered reviewer only | Read-only, runs on the branch or on `main` while the next card starts. **Migrations, definer functions and RLS policies: one data-security pass per owner-apply batch, always before the apply; until the batch is tagged the file is fixed in place, so a finding never costs a ledger number.** **Auth, session and cookie code: one pass per wave, always before that code is deployed to staging.** Other items batched where listed (for example RULES-4, RULES-8, RULES-16 in one pass). The review ledger is in 8.6. |
| F. One fix round | Same implementer | A second failure of the same kind goes to the lead to diagnose. No third blind patch. |
| G. Lead verify | Lead | Until QA-5 exists: rebase, `make css`, `make verify` (lint, mypy, unit, `test-db`, e2e; one summary line per suite, logs read only on failure). **Once QA-5 CI exists:** a branch must be green in CI (three jobs, no skips) before it enters the merge queue. The lead stacks 3-4 file-disjoint green branches on an integration branch, runs the full local suite **once**, and bisects only if it goes red. Migrations and shell-lane merges are still verified one branch at a time. A full local suite also runs at every wave close. |
| H. Merge | Lead | Order: contracts -> migration -> shell -> features -> tests. A serial-chain task may branch from its predecessor's CI-green branch (a stacked branch) without waiting for the merge. Lead removes the worktree and branch (checks `git status` inside it first), pushes once per batch, then writes STATUS, INDEX and COSTS once per batch. The shared local stack is reset only at a batch boundary, after "RESET" is on the lockboard. |
| I. Owner batch | Owner | Apply steps (`--through`, from the tag), deploys and sign-offs in the fixed daily slot, from your own shell. You paste PII-free output (counts, pass/fail, commit hash) to the lead. |

### 8.3 Maximum safe implementers

| When | Writers |
|---|---|
| Before DOCS-1 (with the deny rules) is merged into `main` and SEC-15 is done | 1 (the lead) |
| After DOCS-1 and SEC-15, before DOCS-4/DOCS-13 are merged | Up to 3 lanes that need no `PARALLEL.md`: the contract burst (`docs/CONTRACTS.md` only), DESIGN-2 (new file `docs/COPY.md`), QA-2 (the only DB-touching lane). (No CONSENT-1 stopgap — superseded, not built.) |
| After DOCS-4/DOCS-13 are merged and you approved the agent files, until QA-3 merges | Burst + 4 (design docs, mechanical, tests, docs and scripts). The docs-and-scripts lane (CONTENT-3, DESIGN-3, CONTENT-18) is docs and unit tests only. The tests lane is the only DB-touching lane; PUB-5 waits for QA-3. |
| During QA-3's half-day window | Unit and docs lanes only |
| After QA-3 | Up to 3 DB-touching lanes (set from the QA-2 measurement; default 3) plus unit, docs and deploy-script lanes; **6 writers in total** |
| Wave 3 | 6, and only while the lead's queue stays under 3 green branches |
| Lead queue over 4 unmerged green branches | No new fan-out until it drains |
| After two conflicted merges in a row | Back to 2 until a clean wave close |
| A wave's actual sessions exceed plan by more than 25%, or fix rounds exceed 1 in 4 cards | The next wave's cap drops by 2 (8.6 tripwire) |

More than 6 buys nothing: the lead's verify-and-merge is serial, each extra worktree costs a lead cycle, and your apply steps are batched. Read-only research and drafting agents are not capped.

### 8.4 Test isolation

- **Live keys are not in the repo folder and not in any agent's environment** (SEC-15, day 1). They sit in one owner-only file outside the repo - **never a shell profile or a user or system environment variable**, because every agent Bash call inherits those and could print them. The owner loads that file only in a terminal he uses himself and never starts a Claude Code session from that terminal.
- **Deny rules land with DOCS-1, before any fan-out.** `.claude/settings.json` denies Read and Edit of `.env`, `.env.local`, the owner-only key file and `/etc/eduvation/**`, and denies the Bash patterns that would print them (`cat`, `type`, `more`, `less`, `head`, `tail`, `Get-Content` on those paths; `printenv`; bare `env` and `set`). It explicitly allows `.env.example`, `.env.test.example` and the per-worktree local-stack `.env.test`, which cards own and tests need. Bash patterns can be evaded, so they are the backstop; the real control is that the values are in no place an agent process can reach. After QA-2 the repo `.env` holds local-stack values only.
- Until QA-2: **no agent runs `test-db` or e2e against the live project, the lead included.** If a merge needs a DB run, the owner runs `make test-db` in his own terminal, one run at a time, and pastes the summary line; otherwise that run waits for the local stack.
- **SEC-16:** once QA-2 is merged and nothing needs the live project for tests, the owner rotates the staging service-role key, JWT secret and DB password, because the old values were readable by earlier agent sessions. It is a precondition of DEPLOY-7 and PUB-13b.
- After QA-2: one shared local Supabase stack per machine, localhost-only target guard (refuses any non-localhost URL), strict no-skip, a per-worktree `.env.test` with local keys only. **No test run targets the staging project again**, except the owner-run QA-16 in Phase 2.
- After QA-3: run-id-prefixed rows and users, function-scoped users, run-scoped sweep, `example.invalid` emails.
- **One rule for resets:** the migration lane always uses its own second local stack (dedicated project id and ports, fixed in QA-2's `supabase/config.toml`). The shared stack is reset only by the lead at a merge-batch boundary, after it marks "RESET" on the `tasks/INDEX.md` lockboard and no run is in flight.
- The machine is a Windows 11 desktop. Two Supabase Docker stacks, up to 6 worktrees, xdist workers, and Playwright plus uvicorn per lane is an **untested load**; QA-2 measures it and the DB-lane cap follows the measurement.
- CI (QA-5) is the first place real styling and the full suite are tested, and the final arbiter. A skipped suite is never a pass.
- **No agent on staging or production.** Before TRIAL-8 the lead may read PII-free deploy output only. **From the first TRIAL-8 session no agent, including the lead, holds staging or production credentials or queries those databases.** The owner runs `deploy.sh`, smoke, DATA-10a/b/c, PUB-4, and later QA-16 and AI-11 from the owner's own shell and pastes PII-free output (counts, pass/fail, commit hash). The owner purges `guest_sessions` and guest plan rows on staging after TRIAL-8 and before QA-16. **Production is never reachable by any agent.**

### 8.5 Quality patterns used, and why

| Pattern | Why it earns its cost |
|---|---|
| Reproduce before fix (failing test first) | The PUB-2 bypasses were found by reading SQL, never executed. |
| Revert-to-prove on every RLS, trigger and definer test | A test that cannot fail proves nothing. |
| Adversarial pass on 0010-0011 (PUB-2, PUB-3) before PUB-4. It **is** the batch-C review, not an extra pass | These guard the maker-checker non-negotiable. |
| Reviewer calibration on seeded flaws (QA-9, start of Wave 2) before the reviewer gates any migration batch. The stale trigger paths are fixed even earlier, in DOCS-13 | Otherwise a "pass" has unknown value. If calibration reveals a missed flaw class, the DEPLOY-18 and PUB-5 passes are re-run for that class. |
| Access matrix with a table guard (QA-6). **Every migration PR ships its own guest / A / B / reviewer rows; every auth or session card ships cross-user lines in its own test module** (AUTH-6, AUTH-2, AUTH-14, and in Phase 2 AUTH-9: the export contains only the caller's rows and guest and B are refused; AUTH-7 and AUTH-10: B cannot migrate or delete with A's identifiers) | Enforces "cross-user access tested every time auth, RLS or publication changes", on the changed surface and at the time of the change, not in a later batch. QA-10 (Phase 2) is the browser-level repeat. |
| CI lints: banned phrases (DESIGN-3), hardcoded strings (I18N-3), enum-vs-contract guard | Near-zero cost against re-review. |
| Two failed fixes -> stop and diagnose | CLAUDE.md rule. |
| Human-only sign-offs for consent, child data, production security | A model never signs these. |

Not used: judge panels, duplicate implementers, per-task reviews of forms or docs, strongest tier on mechanical cards, mutation or visual-regression gates, a reviewer pass per exam module (case tables plus human RULES-12 cover them).

### 8.6 Cost guardrails

- **Small context is the biggest lever.** `STATUS.md` is 29.8 KB and `DECISIONS.md` 33.6 KB today: about 16k tokens for every session that would otherwise read both. DOCS-2 (STATUS under 400 words) and DOCS-5 (decisions digest) remove that. This plan is about 30k tokens and each inventory is 115-168 KB, so **implementers never open them**: the CLAUDE.md line added in DOCS-1 and `implementer.md` say so, `CLAUDE.md` links only sections 8.8 and 6.4 for the lead, and the lead reads everything else only by Grep on a task id or heading.
- Paired sessions share one context: DOCS-2 + DOCS-5, DOCS-4 + DOCS-13 + DOCS-6. DOCS-12 is a short lead edit of `CLAUDE.md` that also applies QA-4's proposed lines (it is no longer paired inside the QA-4 implementer session, because `CLAUDE.md` is lead-only).
- Tier policy: strongest only for contracts, RLS/definer migrations, UI-1, QA-2, QA-6, QA-9 (one session), SEC-2, AUTH-2, RULES-4, RULES-8. **Standard** for CONTENT-6 and CONTENT-6b (the importer only ever writes drafts; PUB-2/PUB-3 enforce publication server-side and the data-security review is the safety net) and for DOCS-4 (it mostly transcribes sections 6.4 and 8.2), **and for DEPLOY-18** (it builds the middleware registry every security module hangs on, so it is not a cheap card). Cheap only where a test oracle exists. Exam modules on standard with a tiny context.
- **Lead integration is a real cost line** (section 9). The lead runs routine verify-and-merge on the standard tier, reads `make verify` summaries instead of full test output, merges in batches, and after QA-5 lets CI do the per-branch runs (`gh run view`).
- One fix round per task. Actual sessions by tier, fix rounds and rate-limit stalls go in `docs/COSTS.md` per merge batch. `docs/COSTS.md` is created in the DOCS-4 session, not as an optional extra.
- **Tripwire.** At each wave close the lead records sessions by tier, fix rounds and rate-limit stalls. If actual sessions exceed plan by more than 25% for a wave, or fix rounds exceed 1 in 4 cards, the next wave's cap drops by 2 and no seat is added without an owner DECISIONS line.
- **Seat plan (A4):** ONE seat for Waves 0-1. Early warning: any lane blocked more than 30 minutes on limits in Wave 2 -> add the **second** seat at once (it is already in the budget). ONE seat in the second billing month. No third seat and no API overflow by default; if limits still bite with two seats, route cheap-tier cards to quiet hours and stretch Wave 3 by a day rather than buy more. An API overflow needs your explicit yes and a rupee cap (D15).

**Review ledger (Phase 1): about 12 strongest-tier passes plus 3 ux-qa passes.**

| # | Pass | Covers | When |
|---|---|---|---|
| 1 | data-security | the day-1 deny rules, **DEPLOY-18 (registry fails closed when a required module is missing; middleware order test)**, PUB-5 auth equivalence, DATA-15 | Wave 1 (deny rules land with DOCS-1 on day 1; the rest in one pass once PUB-5 is up, about day 4-5) |
| 2 | data-security, batch A | 0006-0007 (DATA-12, SCOPE-3), DATA-8 | Before DATA-10a; after QA-9 calibration |
| 3 | data-security, Wave 2 code | SEC-1, SEC-2, SEC-5, OPS-2, A11Y-4, DEPLOY-15, DEPLOY-9, DEPLOY-6, QA-2/QA-3 guards | Before DEPLOY-7 |
| 4 | data-security, batch B | 0008-0009 (AUTH-4, AUTH-5) and their app code | Before DATA-10b |
| 5 | data-security, Wave 3 code | RULES-8, AUTH-6, CONTENT-6 session 1, CONTENT-4 | Wave 3 close |
| 6 | data-security, batch C, **adversarial** | 0010-0011 (PUB-2, PUB-3) | Before PUB-4 |
| 7 | data-security, batch D | 0012-0013 (SEC-6, CONSENT-4), CONTENT-6b, SCOPE-13 | Before DATA-10c |
| 8 | data-security, float code | AUTH-2/3/14, CONSENT-6/6b/7/8/10 - only what was actually built | Before any deploy that carries it |
| 9-12 | Allowance | Re-review after a fix round; contract reviews (AUTH-1, PUB-1, CONSENT-3) | As needed |
| u1-u3 | ux-qa | UI-1 + DESIGN-18 gallery; Wave 3 screens; DEPLOY-7 / `round1-rc` | Waves 2, 3, 3 |

The batch-B, C and D passes replace "a review per migration": nothing reaches a cloud database before its owner apply, so reviewing per apply batch loses nothing.

### 8.7 `.claude/agents` changes proposed (NOT yet made; each needs owner approval)

| File | Change | Made in |
|---|---|---|
| `implementer.md` | New: owned-files rule, forbidden single-writer list, strict-flag tests, completion-report format, stop conditions, no secrets or student data; **read only the card, this file and one CONTRACTS section; `npm ci` and `make css` before e2e; never stage `app.css`** | DOCS-13 |
| `migration-owner.md` | New: implementer rules + append-only, freeze-trigger column checklist, pinned `search_path` on definer functions, revert-to-prove, no cloud applies, **own second local stack, and "every migration card ships its guest / student A / student B / reviewer rows in `tests/db/access_matrix.py` in the same PR; the lead does not merge while the table guard is red"** (the same line goes into `tasks/TEMPLATE.md`) | DOCS-13 (no task owned it before) |
| `.claude/settings.json` | New, minimal. **Deny (lands with DOCS-1, day 1, before any fan-out):** Read and Edit of `.env`, `.env.local`, the owner-only key file (path named by the owner in SEC-15) and `/etc/eduvation/**` - that is, any file holding live values; Bash patterns `cat`, `type`, `more`, `less`, `head`, `tail` and `Get-Content` on those paths, `printenv`, and bare `env` / `set`. **Explicitly not denied:** `.env.example`, `.env.test.example` and the local-stack `.env.test` (owned by DEPLOY-18, QA-2 and needed per worktree). The old patterns `.env.*` and `**/*.env` are dropped because they blocked those files. **Allowlist (DOCS-13):** the implementer tool set | DOCS-1 (deny), DOCS-13 (allowlist). The only part of DOCS-10 that is kept |
| `data-security-reviewer.md` | **Wave 1 (DOCS-13):** replace stale trigger paths (`app/db/`, `app/api/admin*`); add definer functions, grants, storage; local-stack-only Bash. **QA-9:** calibration content and adversarial-refutation mode | DOCS-13, then QA-9 |
| `ux-qa-reviewer.md` | Add calibration section; drop "before M1" wording; add 360 px and zoom matrix, key use, ribbon, currency labels | QA-9b (Phase 2, before A11Y-11) |
| `ai-evaluator.md` | New | Phase 2 (AI-9) |

No `content-import-checker.md` is created (8.1). The rest of DOCS-10 (hooks) stays dropped.

### 8.8 Workflow deployment table - how many workflows at once, how many agents each

Added 2026-09-21 on the owner's instruction: "the report should tell how many workflows can run without conflicting and how many agents complete each workflow; motive fast, quality work at lower cost; Claude will work accordingly." This table is the operating instruction for the lead session. It is derived from the section 5 lane tables, the 8.3 caps and the 6.4 conflict groups; where they disagree, those sections win and this table is corrected.

**What the words mean here.** One **workflow = one lane**: a queue of task cards that share files, run one card after another in one git worktree. Lanes never share a file, so lanes run in parallel without conflict. One **agent = one fresh session doing exactly one card** (the same agent does that card's single fix round, then stops). So *agents needed by a workflow = its number of card-sessions*. Reviewers are **shared and batched** (8.6 ledger): they are not added per lane. The lead is always one extra session, and it is the only merger.

**A. How many workflows can run at the same time**

| Wave (days) | Max workflows at once | Of these, may touch the database | What sets the limit |
|---|---|---|---|
| 0 (1-2) | **1** (lead track only — the CONSENT-1 stopgap that used to run alongside it is superseded, not built) | 0 - no agent runs `test-db` yet | Main is not clean and live keys are still in the repo folder until DOCS-1 and SEC-15 |
| 1 (1-4) | **3** until DOCS-4/13 merge, then **5** ("burst + 4") | 1 (the tests lane only) | No ownership map yet; QA-3 holds `tests/db/**` exclusively for half a day |
| 2 (3-9) | **6** | 3 (tests, migration, eligibility) - reset from the QA-2 load measurement | One migration at a time; one writer per shared template; the local test stack on one Windows PC |
| 3 (7-13) | **6** (only while the lead has fewer than 3 green branches waiting) | 3 | The exclusive template window (3a), then one lane per template file (3b) |
| 4 (13-19) | **4-5** | 2-3 | No deploy or apply to staging during round 1; the owner's and the checker's hours |
| 5 (19-23) | **2-3** | 1 | Close-out; nothing new is opened |

Always on top of these: 1 lead session, read-only reviewers (not capped - they never write), and all people work. **Never more than 6 writing workflows**: the lead's verify-and-merge is serial, so a seventh lane only lengthens the queue and costs tokens (8.3). Automatic cut-backs: more than 4 green branches waiting -> no new lane; two conflicted merges in a row -> back to 2; a wave over plan by 25% or more than 1 fix round in 4 cards -> next wave's cap drops by 2.

**B. How many agents each workflow needs (Phase 1)**

Counts are card-sessions from section 5 ("x2" = a two-session card). They are planning estimates, to be replaced by actuals in `docs/COSTS.md`.

| Wave | Workflow (lane) | Model tier | Cards in order | Agents (sessions) |
|---|---|---|---|---|
| 0 | Memory (lead, on main) | cheap/standard | DOCS-1, DOCS-3, DOCS-2 with DOCS-5 | 3 |
| 1 | Protocol (lead, on main) | standard | DOCS-4 + DOCS-13 + DOCS-6 in one session | 1 |
| 1 | Contract burst | strongest | SCOPE-2, RULES-1, PUB-1, CONTENT-2, AUTH-1, CONSENT-3, A11Y-1 | 1 agent, 7 tasks strictly in order |
| 1 | Design docs | standard (strongest for DESIGN-1) | DESIGN-2, DESIGN-1, DESIGN-5, TRIAL-2 | 4 |
| 1 | Mechanical | cheap (standard for DEPLOY-18, SEC-1) | DEPLOY-18, SEC-7, UI-2, SEC-1, DEPLOY-5, PUB-5 | 6 |
| 1 | Tests | strongest | QA-2 x2, QA-3 | 3 |
| 1 | Docs and scripts | cheap | CONTENT-3, DESIGN-3, CONTENT-18 | 3 |
| 2 | Reviewer calibration | strongest | QA-9 | 1 |
| 2 | Tests | strongest/standard | QA-12, QA-6 x2, QA-4, QA-5 | 5 |
| 2 | Memory (lead) | standard | DOCS-12 | 1 |
| 2 | Migration (one at a time, own local stack) | strongest (SCOPE-3, AUTH-4) / standard (rest) | DATA-15, DATA-12, SCOPE-3 x2, DATA-8, AUTH-4 x2, AUTH-5 | 8 |
| 2 | Shell | strongest for UI-1 | I18N-1, I18N-2, UI-1 x2, DESIGN-18 | 5 |
| 2 | Rules (unit tests only) | standard (strongest for RULES-4) | RULES-2, RULES-3, RULES-4, RULES-5, RULES-6 x2, RULES-11, RULES-10 x2 | 9 |
| 2 | Eligibility | standard | SEC-5, SCOPE-5 | 2 |
| 2 | Hardening | standard/strongest | OPS-2, SEC-2, A11Y-5, A11Y-4 | 4 |
| 2 | Deploy scripts | cheap/standard | DEPLOY-2, DEPLOY-3, DEPLOY-4, DEPLOY-15, DEPLOY-9, DEPLOY-6, AI-2 | 7 |
| 2 | Docs and content prep | cheap/standard | TRIAL-10, CONTENT-4, CONTENT-5, CONTENT-15, CONTENT-6 session 1 | 5 |
| 3a | Template window | standard | A11Y-2, then I18N-3 split: shell part + 3 per-file sessions in parallel | 5 |
| 3a | New-file screens (2 lanes) | standard | UI-3 -> UI-4 ; UI-5 x2 | 4 |
| 3a | API, no template | strongest for RULES-8 | RULES-8 ; RULES-9 session 1 | 2 |
| 3a | Guest save | standard | AUTH-6 x2 | 2 |
| 3 | Migration (continues) | strongest | PUB-2 x2, PUB-3 x2 | 4 |
| 3b | `compare.html` lane | standard | UI-6, SCOPE-4 | 2 |
| 3b | `timeline_calculator.html` lane | standard | UI-7, RULES-9 session 2 | 2 |
| 3b | `requirements.html` lane | standard | SCOPE-6, RULES-16 | 2 |
| 3b | E2E | standard | QA-7 | 1 |
| 4 | Migration (continues) | strongest | SEC-6, CONSENT-4 x2 | 3 |
| 4 | Content | standard/cheap | CONTENT-6b, CONTENT-7 | 2 |
| 4 | Hardening | standard | SCOPE-13 | 1 |
| 4 | Trial prep | standard | TRIAL-3 (English draft) | 1 |
| 4 | Float: accounts (only if a lane and a merge slot are free) | strongest for AUTH-2 | AUTH-2, AUTH-3, AUTH-14 | up to 3 |
| 4 | Float: consent (needs CONSENT-4) | standard | CONSENT-6, CONSENT-7, CONSENT-8, CONSENT-10, CONSENT-6b | up to 5 |
| 5 | Float: round-1 fixes | standard | UI-19 x2 | up to 2 |
| 5 | Phase 2 head start (optional) | cheap/standard | SCOPE-8, SCOPE-14 | 2 |
| 5 | Exit (lead) | standard/strongest | Exit check against section 4 | 1 |

**C. Totals per wave**

| Wave | Workflows defined | Max at once | Agent sessions (firm) | Shared review passes (8.6) |
|---|---|---|---|---|
| 0 | 1 | 1 | 3 | - |
| 1 | 6 | 3, then 5 | 24 (the burst counted as 7) | 1 data-security (pass 1) |
| 2 | 10 | 6 (3 DB) | 47 | 2 data-security (passes 2, 3) + 1 ux-qa |
| 3 | 10 (6 in 3a, then 4 template/E2E lanes in 3b; migration runs through both) | 6 (3 DB) | 24 | 2 data-security (passes 4, 5) + 2 ux-qa |
| 4 | 4 firm + 2 float | 4-5 | 7 firm + up to 8 float | 3 data-security (6 adversarial, 7, 8) |
| 5 | 3 | 2-3 | 1 firm + 2 optional + up to 2 float | - |
| **Phase 1** | | **peak 6** | **about 106 firm + up to 10 float** | **about 12 strongest passes + 3 ux-qa** |

**D. Work that must always run alone** (full rules in 6.4): the migration lane (one open migration, fixed order 0006-0013); the contract burst (one agent, never two); the shell files `base.html` / `_components.html`; `_trust_badge.html`; each journey template (one open task per file); `tests/db/**` during QA-3's half day; lockfiles and `pyproject.toml`; `ci.yml`; and the lead-only files (`STATUS.md`, `DECISIONS.md`, `CLAUDE.md`, `tasks/INDEX.md`, `.claude/**`, `app.css`). Cloud applies and deploys are owner-only, never an agent.

**E. How Claude runs a wave (the recipe the lead follows)**

1. Check every lane's **start condition** (section 5). A lane whose condition is not met is not launched, even if the cap has room.
2. Launch the lanes that are ready, up to the cap in table A, as **one parallel run**: either separate Claude Code worktree sessions that the owner starts from the lead's list, or one Workflow-tool run in which each lane is one pipeline item with `isolation: worktree`. Inside a lane the cards run **strictly one after another**; across lanes they run in parallel.
3. Per card the stages are fixed (8.2): implement -> targeted tests on the local stack -> reviewer **only if its trigger fires, batched per 8.6** -> one fix round -> completion report. No judge panels, no duplicate implementers, no review without a trigger.
4. Model tier per card comes from table B. Strongest is used only where 8.6 lists it; cheap only where a test oracle exists.
5. The lead verifies by running the suite itself, merges serially in the 8.2 order (contracts -> migration -> shell -> features -> tests), then updates `STATUS.md`, `tasks/INDEX.md` and `docs/COSTS.md` once per merge batch.
6. The lead applies the cut-backs under table A without asking, and asks the owner before ever going above a cap.

**Why this is the fast, good and cheap shape.** Speed comes from lanes that cannot collide, so nothing waits except on real dependencies and on people. Quality comes from one lead that re-runs every test itself, reviewers calibrated on seeded flaws, and revert-to-prove on every security test. Low cost comes from small contexts (an implementer reads one card, not this plan), the cheapest tier that has a test oracle, batched reviews, and never paying for a lane the lead cannot merge.

**F. Where speed actually comes from (2026-09-21 finding — read this before asking to raise a cap).** The 22-27 day Phase 1 estimate is set by two things, neither of which is lane count: the migration lane (one open migration at a time, fixed order 0006-0013, about 15 sessions / 7-8 days, must never idle — section 7) and human turnaround (round-1 recruit readiness and the checker's CONTENT-9 sitting — section 7, calendar summary). Every other lane already runs in parallel alongside that path and finishes before it does, so speeding those lanes up does not move the exit date. Raising Table A's caps does not help either: past 6 concurrent lanes the lead's own verify-and-merge step is the limit (it is serial), so a 7th lane only lengthens the queue and spends tokens for no wall-clock gain, and in most waves the cap is set by a real single-resource constraint anyway (one migration, one local Windows stack, the owner's/checker's hours), not by an agent shortage. The two changes actually applied against this finding: (1) the prep-session rule (section 5 preamble) narrows each multi-session migration card to schema/RLS/revert-to-prove only; (2) SCOPE-3 and AUTH-4 (Wave 2 migration table, and Table B above) now run at strongest tier instead of standard, on the chance their second session was reviewer-fix overhead rather than genuine complexity. Track both in `docs/COSTS.md`; if the second sessions don't disappear, revert the tier note — it means the complexity was real. Non-critical-path lane splits (e.g. RULES-6 per-exam, section 6.3) remain worth doing for schedule slack, but do not by themselves change the exit date.

---

## 9. Cost plan - four ledgers

All figures are planning assumptions (A4-A6, A11 and A12 in section 1, honorarium Rs 500/hour, USD 1 = Rs 85 assumed on 2026-09-21, GST 18% **included** in seat figures). **None was checked against a vendor price list.** Replace with actuals in `docs/COSTS.md` from week 1.

**Phase 1 work:** about 106 firm dev sessions (roughly 20 strongest, 62 standard, 24 cheap; DEPLOY-18 moved from cheap to standard), up to 8 float sessions, about 12 strongest-tier reviewer passes and 3 ux-qa passes (8.6 ledger), plus lead integration (about 35 merge batches).

| Sessions | Phase 1 | Phase 2 | Phase 3 | Total |
|---|---|---|---|---|
| Dev sessions (estimate) | about 106 firm + 8 float | about 108 (the first draft's 95, plus RULES-15, AUTH-7/9/10, UI-13, SEC-3, A11Y-3, UI-19, QA-9b and UI-20) | about 12 (CONSENT-12 x 2, CONTENT-12 x 2, TRIAL-6, 12, 14, 18, OPS-12, AI-13, DESIGN-16, DESIGN-14) | about 234 |

Check against the task graph: 245 sessions in total, minus 27 for the 19 dropped tasks, plus about 7 added by this plan = about 225. The gap of about 10 is the fix-round allowance inside the phase figures. These are estimates, not counts.

**Ledger 1 arithmetic (seats x months x price; seats bill per calendar month, no pro-rating):**

| Billing month | Seats | Why | Rs, ex GST | Rs, incl. 18% GST |
|---|---|---|---|---|
| Month 1 (22 Sep - 21 Oct; Waves 0-4) | 1, plus a 2nd from Wave 2 **only if** a lane is blocked over 30 minutes on limits | 1-5 writers in Waves 0-1 (burst + 4 at the peak, two of them docs-only); up to 6 in Waves 2-3 | 17,000-40,000 | 20,000-47,000 |
| Month 2 (from 22 Oct; Wave 5 tail and exit) | 1 | 2-3 writers | 17,000-20,000 | 20,000-24,000 |
| **Phase 1 subscription total** | 2-3 seat-months | | 34,000-60,000 | **about 40,000-70,000** |

The owner's current seat counts as seat 1 and is shown as a cost (A4a). By API instead (A5): implementers 20 x 1,500 + 62 x 500 + 24 x 150 = about Rs 65,000; **lead integration** about 35 batches = about Rs 28,000 (about 25 standard-equivalents and 10 strongest); reviews 12 x 1,500 + 3 x 500 = about Rs 20,000; float up to Rs 5,000. **About Rs 1.1-1.3 lakh**, so subscription is the cheaper route.

| Ledger | Phase 1 | Phase 2 (outline) | Phase 3 (outline) | Whole pilot |
|---|---|---|---|---|
| 1. Dev agents (incl. GST) | Rs 40,000-70,000 (table above) | 2 billing months x 1-2 seats: Rs 40,000-94,000 | 1-2 seat-months: Rs 20,000-47,000 | Rs 1.0-2.1 lakh |
| 2. App inference | Rs 0 (AI off; tests use FakeProvider) | under Rs 300 for the live evaluation | Rs 500-3,000, hard cap Rs 1,000/month | Rs 500-3,300 |
| 3. Hosting and monitoring | Rs 0-1,000 (existing VM, Supabase Free, subdomain you already own; GitHub Actions free minutes per A12) | Rs 0-7,500: Rs 0-1,500 as before, plus Supabase Pro at about Rs 2,100-2,500 a month plus GST **only if** the Singapore project cannot be freed (A11) or fallback option (a) of A3 is used | Supabase Pro from Step 16: Rs 4,500-7,000 | Rs 4,500-15,500 |
| 4. Paid humans | Rs 4,500-6,000: checker 4 h + consent non-author read 2 h + safeguarding onboarding 1 h = 7 h x Rs 500 = Rs 3,500; round-1 thank-yous 5-8 x Rs 200-300 = Rs 1,000-2,400 | Rs 42,000-67,000: content 34 h (CONTENT-10) + 28 h (SCOPE-9) = 62 h x Rs 500 = Rs 31,000, **to be re-based on CONTENT-9 minutes per claim** (hole 17); production re-approval about 125 claims x 2 min = 4 h = Rs 2,000; Hindi reviewer about 18 h = Rs 9,000; SEC-13 security and child-data signer as its own named assumption: a fixed fee of Rs 10,000-25,000, or a named volunteer at Rs 0 | up to Rs 25,000-50,000, demand-gated | Rs 0.7-1.2 lakh |
| **Cash total** | **about Rs 45,000-80,000** | about Rs 0.8-1.7 lakh | about Rs 0.5-1.1 lakh | **about Rs 1.75-3.6 lakh** |
| Owner time (unpaid) | 86-96 h (section 10) | about 70 h | about 60 h | about 220 h |

Build pack comparison: a hired engineer alone is Rs 6-14 lakh; its honoraria plus QA lines are Rs 2-4.5 lakh.

**Top savings, ranked:**

1. Phase the scope: up to 4 states and UK first. Ceilings are maximums, not targets. Largest lever on any ledger.
2. Adults-only, invite-only until Step 16. Removes the minors route and the school agreement from the path to first users.
3. Drop 19 deferrables; hold OPS-5 and OPS-14 until something enqueues work. About 30 sessions.
4. Small context: DOCS-2, DOCS-5, cards with owned-file lists, one `CONTRACTS.md`, and implementers barred from the plan, inventories, build pack and DPR. One seat less, a cap of 6, and no third seat follow from this and from running RULES-6 in one worktree.
5. Contracts first, keys first, components first. Avoids an estimated 8-12 rework sessions.
6. Local test stack with no-skip mode. Tests cost Rs 0 and agents verify their own migrations.
7. UI-2 and PUB-5: two cheap sessions that remove most merge conflicts.
8. Owner applies in batches (DATA-10a/b/c, PUB-4, later DATA-11, DATA-13, DATA-14) instead of once per migration, and security reviews run per apply batch.
9. Free infrastructure until Step 16: Supabase Free, `pg_dump` backups, free Sentry and UptimeRobot tiers, nginx rate limiting, owner-run deploy script (a pinned-stack deviation that needs a DECISIONS entry - D13).
10. Hold paid offline verification until CONTENT-9 has measured minutes per claim. Verify once in the CSV with a verbatim quote; re-approve on production from packets at about 2 minutes per claim **only when the stored content hash matches the checker's signed sheet** (Wave 4 content-hash rule); any mismatch gets full re-verification.
11. Lead on the standard tier for routine merges, `make verify` summaries, batch merges and CI as the per-branch runner.

Do not buy: a registry, CDN/WAF, PITR, a staging VM, Supabase branching, n8n for two emails, WhatsApp templates, a designer.

---

## 10. Owner action list, in start order

Keep one fixed daily slot. Applies, deploys and sign-offs go in that slot and are run **from your own shell** - a terminal that no Claude Code session runs in, and the only place the owner-only key file is ever loaded. No single day below passes 4 hours, **except days 8-10, which peak at about 4-4.5 hours**: DEPLOY-7 (5 h spread over the three days, about 1.7 h a day), DATA-10a (1 h on one of them), operating the sessions (1 h a day) and the Wave 3 card table (1 h, done on day 7 if you can). To keep that peak down, the content human parts sit on days 5-7 and the CONTENT-9 maker entry on days 11-12; nothing else is booked on days 8-10. UI-15 on day 13-14 leaves at least a day of float if the bring-up overruns. "Run." is the running total of hours.

| # | Day | Action (task id) | Hours | Run. | Where / how / done when | Blocks |
|---|---|---|---|---|---|---|
| 1 | 1 | Approve the clean-up commit (DOCS-1), its one CLAUDE.md line, the day-1 `.claude/settings.json` deny rules, and the writer caps in 8.3 | 0.5 | 0.5 | The lead shows you the file list, the line and the deny list; reply "approved" in the session. Done when the branch is fast-forward merged into `main`, `git status` is clean and the lead shows you the `main` commit hash. | Every worktree |
| 2 | 1 | Install Docker + Supabase CLI; approve local test backend (QA-1) | 1 | 1.5 | Install Docker Desktop (WSL2 backend) and the Supabase CLI on the Windows dev machine. Done when `supabase start` prints local URLs. If it fails by day 2, tell the lead and D12 applies. | QA-2 and all agent-verified migrations |
| 3 | 1 | **Supabase dashboard: sign-ups OFF** (CONSENT-18) | 0.2 | 1.7 | Supabase dashboard > Mumbai project > Authentication > sign-in / provider settings > turn off "Allow new users to sign up" (menu labels change; look for the sign-up toggle). Done when a test sign-up is refused. | DEPLOY-7; non-negotiable on minors |
| 4 | 1 | **Move live Supabase keys out of the repo folder** (SEC-15) | 0.5 | 2.2 | Move the live values from the repo `.env` into one owner-only file **outside the repo folder** (for example under your user profile, readable only by you). **Not your shell profile, and not a Windows user or system environment variable** - every agent command inherits those. Load the file only in a terminal you use yourself, and never start Claude Code from that terminal. Tell the lead the file's path (not its contents) so the deny rules name it. Done when the repo `.env` is gone or holds no secret, and the terminal you launch Claude Code from has no Supabase secret variable set. **Until QA-2 merges (about day 3), if the lead asks for a DB run you run `make test-db` yourself in your own terminal and paste the one summary line** (10 minutes a run, inside your operating hour); no agent runs it. | **Any fan-out** |
| 5 | 1, then spread | Start recruitment, adults only; name a second moderator (TRIAL-1) | 6 (1 h on day 1) | 8.2 | Write to candidates; book TRIAL-8 slots **by date**; record recruits' school medium. Names go to the lead in chat, no contact details. | TRIAL-8 (about day 15) |
| 6 | 2 | Record VM and vendor facts (DEPLOY-1 + OPS-1), including whether the GitHub repo is public or private | 1.75 | 9.95 | Answer the DEPLOY-1 and OPS-1 question lists in chat, no secrets; the lead writes them to DECISIONS. | DEPLOY-2 -> DEPLOY-7 |
| 7 | 2 | Scope phasing - **explicit yes needed** (SCOPE-1 / D2); six rules decisions (RULES-17, provisional default after 24 h) | 1.5 | 11.45 | Reply in the session. D2 is never decided by silence. | State and country choices (not the schema) |
| 8 | 2 | Record the DigiLocker deferral (CONSENT-17) | 0.25 | 11.7 | One DECISIONS line; reply "approved". | - |
| 9 | 3 | Name checker, backup reviewer, corrections owner, Hindi reviewer (CONTENT-1, PUB-13a, I18N-6) | 3 | 14.7 | Names and roles to the lead; recorded in DECISIONS. Hard stop day 5. | CONTENT-5, CONTENT-9, TRIAL-2 Hindi read |
| 10 | 3 | Name safeguarding person + backup, and non-author consent reviewer (CONSENT-2) | 1 | 15.7 | As above. Hard stop day 4. | CONSENT-3 human read -> CONSENT-4 |
| 11 | 3-4 | Approve the new agent files and the `.claude/settings.json` allowlist (the deny rules were approved on day 1); check the real seat price incl. GST before confirming D15 | 0.75 | 16.45 | The lead shows each file; reply "approved" per file. | Full caps in 8.3 |
| 12 | 4 | Round-1 vehicle (DESIGN-6) | 1.5 | 17.95 | Open the mockup artifact, then reply with your choice (default: the real app). | TRIAL-8 |
| 13 | 4 | Open the editor-hours log (TRIAL-7) | 1 | 18.95 | Create the CSV header; log every minute of verification from now on. | DPR measurement |
| 14 | 2-6 | Contract sign-offs: **explicit yes** on AUTH-1, PUB-1 and (after the non-author read) CONSENT-3, 0.5 h each; 30-minute read-through of `docs/CONTRACTS.md`; other contracts: object within 48 h | 2 | 20.95 | Read the section, reply "approved" or list objections. | AUTH-4/5, PUB-2, CONSENT-4; read-through gates SCOPE-3, PUB-2, CONTENT-6 |
| 15 | each wave | Approve the per-wave card table (waves 1-5, 1 h each) | 5 | 25.95 | One page per wave from the lead; approving the table approves those cards. | That wave's fan-out |
| 16 | daily | **Operate the sessions**: launch, watch, unblock (1 h a day in Waves 0-2 and 5, 2 h a day in Waves 3-4) | 30 | 55.95 | Start worktree sessions from the lead's list; answer permission prompts; restart stalled lanes. | Everything |
| 17 | week 2 | Protect main, restrict repo and VM access (DEPLOY-17) | 0.5 | 56.45 | GitHub > Settings > Branches (branch protection on `main`); review collaborators and VM SSH keys. | DEPLOY-13. If skipped, any session can push to `main` unreviewed. |
| 18 | 5-7 | Get a Hindi speaker to read the TRIAL-2 participant consent sheet | 0.5 | 56.95 | Send the sheet; record "read, date, changes" with the lead. (The guardian sheet is parked until CONSENT-12; round 1 has no minors.) | TRIAL-8 |
| 19 | 5-7 | Human parts of CONTENT-4, CONTENT-5, CONTENT-15 (after CONTENT-18), about 2 h a day | 6.5 | 63.45 | Work in the CSV and the handbook draft; you fill `checked_by` and quote columns yourself, never an agent. Finished before day 8 so the bring-up days stay clear. | CONTENT-9 |
| 20 | 4-7, the day QA-2 merges | **Rotate the staging credentials (SEC-16)** | 0.5 | 63.95 | Supabase dashboard > Mumbai project: rotate the JWT secret (this re-issues the anon and service-role keys) and reset the database password. Put the new values only into your owner-only file (and, at DEPLOY-7, into `/etc/eduvation/staging.env` and `staging.migrate.env`). The app env gets the anon key only, **never the service-role key**. Update or stop the localhost app on the VM in the same sitting. Tell the lead "rotated, date" - no values. Done when the old service-role key is refused. | DEPLOY-7, PUB-13b |
| 21 | 7 | Staging DNS record | 0.25 | 64.2 | Your DNS provider: one A record for the staging subdomain to the VM's IP. | DEPLOY-7 |
| 22 | 8-10 | **DEPLOY-7 first bring-up (owner-only on the VM)** | 5 | 69.2 | Follow the lead's checklist, spread over the three days; you type every secret (the rotated values from SEC-16); paste PII-free output. Done when the standing gate in Wave 3 passes. | UI-15, TRIAL-8 |
| 23 | 8-9 | QA-12 sweep `--apply`, then **DATA-10a**: `apply --through 0007` from tag `staging-batch-A`, then the synthetic seed | 1 | 70.2 | Your shell; paste counts and the dry-run "zero matches" line. Only after the lead's notice that review, revert-to-prove and matrix rows are done. | Demo data on staging |
| 24 | 11-12 | CONTENT-9 maker entry, offline in the CSV (about 2 h a day) | 4 | 74.2 | Same CSV as row 19; timed in the TRIAL-7 log. Moved here from days 6-10; the import is not until after TRIAL-8, so nothing waits on it. | CONTENT-9 import |
| 25 | about 11 | **DATA-10b**: `apply --through 0009` from `staging-batch-B`, plus `deploy.sh staging` | 0.5 | 74.7 | Same as row 23. | Guest save on staging |
| 26 | about 13-14 | **PUB-4**: `apply --through 0011` from `staging-batch-C` and confirm the bucket; then **PUB-13b** (checker account by dashboard invite, `reviewers` rows by SQL, `critical_authorised`, cadence in `docs/DATA.md`). Needs SEC-16 done | 1.75 | 76.45 | Within 24 h of the adversarial review passing. You hold no second reviewer account. | CONTENT-9 approval |
| 27 | about 13-14 | UI-15 phone walk-through; deploy the `round1-rc` tag | 1.5 | 77.95 | On your own phone against staging; reply with the component-set freeze. | TRIAL-8 |
| 28 | about 15-18 | TRIAL-8 round 1: moderate at most half, observe two; **purge staging guest rows (record count = 0)**; de-identify notes | 7.25 | 85.2 | The purge SQL comes from the lead; you run it. No agent reads anything before both are done. | TRIAL-9 |
| 29 | about 18-21 | CONTENT-9 import on staging; the checker approves; **then run the integrity query** | 1 (+ 4 checker hours, paid) | 86.2 | You run the importer under your reviewer sign-in; the checker approves under theirs. After the last approval, run `make content-integrity` against staging from your own shell (10 minutes, inside this hour) and paste the three counts to the lead: `created_by = reviewed_by`, NULL `created_by`, unnamed or fixture verifier. Done when all three are zero. No agent runs this on staging. | Exit gate item 3 |
| 30 | about 18-20 | **DATA-10c**: `apply --through 0013` from `staging-batch-D` | 0.5 | 86.7 | After its batch review. Skipped if CONSENT-4 floated (then `--through 0012`). | Exit gate item 1 on staging |
| 31 | exit | Read the lead's exit check and `docs/COSTS.md` actuals | 1 | 87.7 | Reply "Phase 1 closed" or list gaps. | Phase 2 |
| 32 | weeks 2-3 | Phase 2 and 3 booking: SEC-13 signer; AI-10 provider terms; TRIAL-14 school letter (before the holidays); **confirm the unused Singapore Supabase project is empty** (dashboard > Table editor shows no tables; do not delete it yet - that happens in DEPLOY-11; see A11) | 8 | 95.7 | - | Phase 2 and 3 only |

Total: about 88 h for Phase 1 itself (SEC-16 added 0.5 h) plus about 8 h of Phase 2 booking = **about 96 h**. This is the single owner-hours figure; sections 0, 5 and 9 quote it. TRIAL-4 (1 h) moved to the end of Phase 2.

**Do not do in Phase 1:** open any hostname without basic auth, or a production hostname; enable sign-up; create real student accounts; admit an under-18 participant; publish real content before PUB-4; give any agent secrets, staging or production credentials, student data or raw usability notes; approve a claim through a second account you control.

---

## 11. Gates coverage matrix

P1 = proven in Phase 1. P2/P3 = later phase.

### Build pack section 9 steps

| Step | Task ids | Phase |
|---|---|---|
| 5 Staging (AI disabled) | DEPLOY-1, 2, 3, 4, 5, 6, 9, 15, 18, 7; CONSENT-18, SEC-15, SEC-16 (CONSENT-1 superseded); AI-2; DATA-15, DATA-12, DATA-8, DATA-10a/b/c; QA-12 | P1 |
| 6 UI system, Explore, keys | DESIGN-1, 2, 3, 18; UI-1, 2, 3, 4; I18N-1, 2, 3; SCOPE-6 (I18N-4, 5 in P2) | P1 |
| 7 Compare, calculators, five exams | UI-5, 6, 7; RULES-1 to 6, 8, 9, 10, 16; SCOPE-4, 5; SEC-5 in P1 (three exams). RULES-15 (CUET-UG, CLAT), UI-20 and I18N-15 in P2 | P1 + P2 |
| Usability round 1 | TRIAL-1, 2, 8, 9; DESIGN-5, 6; UI-15; QA-7; AUTH-4, 5, 6 in P1. UI-19 is float or the first P2 task | P1 |
| 8 Sign-in, plans, consent | P1 firm: AUTH-1, 4, 5, 6; SEC-2; CONSENT-2, 3, 4. P1 float, else P2-A: AUTH-2, 3, 14; CONSENT-6, 6b, 7, 8, 10. P2: AUTH-7, 9, 10, UI-13, then CONSENT-5, 9, 11, AUTH-12, 15, 17, QA-10 | P1 part-build, P2 build and reviews |
| 9 Publishing console | PUB-1 to 5, 13a, 13b, SCOPE-13, A11Y-4 - then PUB-6 to 10, 12, 14, 15 | P1 integrity, P2 console |
| 10 Real dataset | CONTENT-1 to 7, 6b, 9, 15, 18; TRIAL-7; QA-12 - then SCOPE-8, 9, 14, CONTENT-8, 10, 11, 17, RULES-7, 12 | P1 rehearsal, P2 dataset |
| 11 AI | AI-2 in P1; AI-1, 3 to 13, 16, 17; UI-11 | P2 |
| 12 Hindi, a11y, states; content freeze | A11Y-1, 2, 4, 5 in P1; A11Y-3; I18N-4 to 13, 15, 16; A11Y-6 to 12, 14; QA-9b; **CONTENT-20 (content freeze)** | P2 |
| 13 Ops safety, release review | OPS-2, SEC-1, 6, 7, RULES-11 in P1; SEC-3; OPS-4, 6, 7, 8, 9, 10, 15, 16; SEC-8, 10, 13, 14; QA-16; TRIAL-5, 16; RULES-13. Jobs table and worker (OPS-5, OPS-14): **P3 conditional - D16** | P2 |
| 14 Production | DEPLOY-10, 11, 12, 13, 17; **DATA-14** (apply all migrations to production and audit grants); PUB-13b on production | P2 |
| 15 Ten-person trial | TRIAL-2, 3 (English), 10 (P1 prep); TRIAL-3 Hindi half and TRIAL-4 (end of P2); TRIAL-11, 12; DESIGN-16 | P3 |
| 16 Expand to 100 | TRIAL-13, 6, 17, 18, 19, 14; DESIGN-14; OPS-12; CONSENT-12, 14; CONTENT-12; SCOPE-11 | P3 |

### Build pack section 12 gates and "Built means"

| Requirement | Task ids | Phase |
|---|---|---|
| A cannot read or change B's records | QA-6, QA-5, SEC-6, matrix rows in every migration PR, cross-user lines on AUTH-6 and the float auth cards (P1); AUTH-7/9/10 lines, QA-10, QA-16 (P2) | P1 + P2 |
| Critical rule test cases pass | RULES-11 for three exams (P1); RULES-15, and RULES-11 + RULES-12 human check **for every exam with published claims** (RULES-7's exams only if their claims are verified) (P2) | P1 + P2 |
| Instrument items have an app surface (next deadline, a backup, one scholarship) | CONTENT-5 subset rule (P1); DATA-4 `pathway_transitions`, UI-20; TRIAL-11 depends on UI-20 (P2) | P2 |
| Every published critical field has reviewed evidence | PUB-2, PUB-3, PUB-4, CONTENT-9 (P1, one family); PUB-12, PUB-14, CONTENT-8, CONTENT-10 (P2) | P1 + P2 |
| Unsupported questions fall back honestly | RULES-4, RULES-8, SCOPE-6 (P1); AI-6, UI-11 (P2) | P1 + P2 |
| Corrections invalidate cached answers; affected plans flagged | A11Y-4, PUB-3 (P1); AUTH-14 `needs_review` banner (float or P2); PUB-12, A11Y-9 (P2) | P1 + P2 |
| A backup has actually been restored | OPS-9, OPS-15 | P2 |
| App works with AI disabled | Whole of Phase 1; AI-2, AI-8 | P1 + P2 |
| Spending limits and alerts tested | AI-4, AI-10, AI-13 (AI-13 made a dependency of AI-17) | P2 |
| Named owner of source review and corrections | CONTENT-1, PUB-13a, PUB-13b | P1 |
| Consent workflow reviewed by a non-author | CONSENT-11; CONSENT-14 for minors | P2 / P3 |
| Outcome instrument piloted on the first ten | TRIAL-3 (P1 draft); TRIAL-11, TRIAL-17 | P3 |
| Distress rule tested in Hindi and Hinglish | CONSENT-7 (P1 build); CONSENT-9 | P2 |
| Step 15 gates approved before testing | TRIAL-4 (end of P2, before TRIAL-11) | P2 |
| Pinned dependencies, reviewed migrations, fresh-migration rebuild | SEC-7, DEPLOY-3, per-apply-batch reviews, QA-5 rebuild and additive-only check (P1); DATA-11, DATA-13, DATA-14 (P2) | P1 + P2 |
| No disguised synthetic content | DATA-12, DATA-8, UI-1 ribbon, QA-2, **QA-12 sweep before DATA-10a and in the DEPLOY-7 standing gate** (P1); DEPLOY-11 (P2) | P1 + P2 |
| Two authorised people, no bypass | PUB-2, PUB-3, PUB-13a, PUB-13b, exit gate 3 integrity query (`make content-integrity`, built in CONTENT-6b, run on staging by the owner) (P1); PUB-12, CONTENT-8 (P2) | P1 + P2 |
| English and Hindi critical content reviewed | I18N-11, I18N-16, CONTENT-17, DESIGN-15 | P2 |
| Mobile and accessibility checks | QA-7, UI-15 (P1); A11Y-6, 7, 11, 12, I18N-12 (P2) | P1 + P2 |
| Separate staging and production, protected release; callbacks and origins restricted | DEPLOY-2, 6, 17 (P1); DEPLOY-10, 11, 12, 13 (P2). "Protected release" is met by a protected `main` plus exact-SHA approval, not a GitHub Actions environment (D13 deviation). Supabase Auth site URL and redirect allow-list: CONSENT-5 for staging, DEPLOY-13 for production | P1 + P2 |
| Monitoring, support owner, restore | OPS-4, 7, 8, 15 | P2 |
| Real-data and minor-account approvals | SEC-8, SEC-13, CONSENT-11 (P2); CONSENT-14 (P3) | P2 / P3 |
| Ten-user results recorded honestly | TRIAL-12, TRIAL-13 | P3 |

### CLAUDE.md non-negotiables

| Non-negotiable | Phase 1 cover |
|---|---|
| AI never invents facts | AI is off. RULES-4, RULES-8, SCOPE-6 give "not verified". |
| Source, date, verifier; server-side maker-checker | PUB-2, PUB-3, SCOPE-3 (freeze trigger carries new columns), CONTENT-6/6b (importer never publishes; content hash), PUB-13b and exit gate 3 (two different named people; the owner holds no second reviewer account) |
| No predictions, labels, guarantees | DESIGN-2, DESIGN-3 lint (firm, in CI by the Wave 1 close), UI-4 |
| Synthetic labelled and never published as verified; minors disabled | DATA-12, DATA-8, UI-1 ribbon, exit-gate test 8, QA-12 sweep before any outside person sees staging; the merged guardian-consent gate (0004/0005, real, live in production), CONSENT-18, (CONSENT-4, CONSENT-6 when built). **Round 1 is adults only**; no minor's data is collected before CONSENT-11 and CONSENT-14 |
| No student data or secrets to dev agents | SEC-15 (live keys in an owner-only file outside the repo, never a shell profile or environment variable an agent inherits), `.claude/settings.json` deny rules for Read, Edit and Bash, **merged with DOCS-1 before any fan-out**, no agent `test-db` run before the local stack exists (the owner runs it and pastes the summary), **SEC-16 rotation of the staging keys that earlier sessions could read, before DEPLOY-7 and PUB-13b**, SEC-7 secret scan, local stack only with a localhost-only guard, **no agent holds staging or production credentials; owner-run applies, deploys, QA-16 and AI-11 with PII-free output; guest rows purged after TRIAL-8**, de-identified notes, DEPLOY-7 owner-only, DEPLOY-17 |
| Cross-user access tested on every auth, RLS or publication change | QA-6 table guard; matrix rows inside every migration PR; cross-user lines on every auth or session card; "matrix covers this wave" in the closing gates of Waves 2, 3 and 4; QA-5 in CI; DOCS-4 rule |
| Owner decisions are the owner's | Section 13 list (a): explicit yes only. Provisional defaults are labelled and never written into DECISIONS as decisions |

### Holes found, and where this plan closes them

| # | Hole | Fix |
|---|---|---|
| 1 | Distress rule not wired to other free-text fields | Added to AI-7 and OPS-6 acceptance (P2); otherwise fixed prompts only |
| 2 | Sign-up form fields and withdraw button unowned | CONSENT-6b (float in Wave 4, else P2-A) |
| 3 | Ribbon only in UI-13 | Moved into UI-1 |
| 4 | Pathway and career text could publish without a second person | DATA-4 becomes a dependency of CONTENT-10 (P2). **Owner to confirm.** |
| 5 | UI-11 waits on the whole AI chain | UI-11 depends only on UI-1, UI-2, AI-2; AI-7 depends on UI-11 |
| 6 | Real records on a synthetic-only staging project | CONTENT-9 is a labelled rehearsal; decision D3 |
| 7 | Nobody applies migrations to production | **DATA-14** (P2): after DEPLOY-11, DATA-11 and DATA-13; blocks the CONTENT-10 production import, PUB-13b on production, DEPLOY-12 and DEPLOY-13 |
| 8 | 0008-0009 never reach staging; the apply script cannot stop at a number | DATA-15 (`--through`), tagged batches: DATA-10a (0006-0007), DATA-10b (0008-0009), PUB-4 (0010-0011), DATA-10c (0012-0013) |
| 9 | No task created `migration-owner.md` | DOCS-13 |
| 10 | Console approve path and the importer may break after 0010-0011 | PUB-2 and PUB-3 acceptance lines; CONTENT-6 split so its DB half (CONTENT-6b) is written after PUB-3; slim PUB-7 only if needed |
| 11 | Round-1 participants and real details typed on staging | Round 1 is adults only (18+); no guardian-consent route exists before CONSENT-12. Moderators say "type nothing identifying"; the owner purges guest rows after the last session; no agent holds staging credentials |
| 12 | Supabase Auth site URL and redirect allow-list per hostname | CONSENT-5 acceptance for staging; DEPLOY-13 acceptance for production (P2) |
| 13 | Additive-only migrations not checked; rebuild-from-scratch check | Written into the QA-5 card in Wave 2 (section 5) and cited in the Wave 2 closing gate |
| 14 | Step 12 content freeze has no owner task | **CONTENT-20** (P2-D, 0.25 h, after CONTENT-10, before DEPLOY-12) |
| 15 | AI outbound PII allow-list; per-account AI rate limit | AI-6 acceptance: outbound field allow-list test and a PII redaction fixture. AI-4 acceptance: per-account and global caps (P2) |
| 16 | RULES-12 has no content dependency | Depends on verified claims (CONTENT-10 offline half) in P2 |
| 17 | Hours for CONTENT-10 and SCOPE-9 may double count (45 h vs 28 h vs 62 h) | Re-estimate after CONTENT-9 timing; ledger 4 shows the 34 h + 28 h arithmetic |
| 18 | PUB-13's account and authorisation half was scheduled nowhere, so critical-tier approval of CONTENT-9 would fail or tempt a second owner account | PUB-13b after PUB-4; exit gate 3 extended |
| 19 | Live keys readable by every agent; fixture claims possibly published on the project that becomes staging | SEC-15 + deny rules (Read, Edit, Bash) on day 1 with DOCS-1; owner-run `test-db` until QA-2; **SEC-16 rotates the exposed staging keys** after QA-2 and before DEPLOY-7; QA-12 sweep moved into Phase 1 before DATA-10a || 20 | Instrument items (deadline, backup, scholarship) and the "plans flagged" banner had no screen | UI-20 (P2), CONTENT-5 subset rule, AUTH-14 banner |
| 21 | Build pack deliverables cut without a DECISIONS entry | D16; TRIAL-18 reports measurement 8 as "not measured"; TRIAL-12 lists the deviations under "Built means" |
| 22 | DESIGN-14 (teacher pack) appeared nowhere | Phase 3, before the first school session |
| 23 | The DEPLOY-18 registry would skip a missing or misnamed security module silently | DEPLOY-18 is standard tier, in review pass 1, refuses to start outside development when a required module is absent, and has a middleware-order unit test |
| 24 | Exit gate 3's integrity query had no owner and no script | `make content-integrity` in CONTENT-6b; the owner runs it on staging (section 10 row 29) |

---

## 12. Risks and early-warning signals

| # | Risk | Likelihood / impact | Mitigation | Early warning |
|---|---|---|---|---|
| 1 | A minor's sign-up becomes reachable, or a minor's data is collected in round 1, before the consent gate is reviewed | Medium / critical | the merged guardian-consent gate (0004/0005, confirmed live in production), CONSENT-18, DEPLOY-9, adults-only round 1, guest-row purge; CONSENT-4, 6; later CONSENT-11, SEC-13 | An `auth.users` row you did not create; the RPC bug (0005 fix, in progress elsewhere) reopening the gap; an nginx site enabled before DEPLOY-9's fail-closed check passes |
| 2 | Synthetic or test data shows as verified | Medium / critical | DATA-12 strongest review, ribbon in UI-1, exit-gate test 8, QA-2 | A published claim whose source contains SYNTHETIC or a run id; demo mode on anywhere but staging |
| 3 | Maker-checker bypass still open when real content is entered | High (open now) / critical | PUB-2, PUB-3, PUB-4 before any real record enters staging | A published claim with NULL `created_by` |
| 4 | Reviewer capacity; people not named | High / high | Day-1 naming; two reviewers; TRIAL-7 timing | Nobody named by day 5; more than 20 minutes per claim; checker replies over 48 h |
| 5 | Owner is the bottleneck (about 96 h in 5 weeks, peaking at about 4-4.5 h a day on days 8-10, about 10 hand-offs with a 24 h turnaround each) | High / high | Fixed daily slot, batched applies, one card table per wave, non-blocking contract sign-offs except AUTH-1, PUB-1 and CONSENT-3, a second moderator, content human parts on days 5-7 and the CONTENT-9 maker entry on days 11-12 so days 8-10 hold only the bring-up, a day of float before UI-15 | **More than 3 merged branches waiting on you**; an apply older than 2 days |
| 5b | The lead is the bottleneck (serial verify-and-merge) | High / medium | Batch merges, CI as the per-branch runner, stacked branches, cap of 6 | More than 4 green branches in the lead's queue |
| 6 | Parallel agents collide; skipped suites look green | High / high | QA-1, 2, 3, DOCS-4, adaptive cap | Skip count equals test count; 429s in a run; two conflicted merges in a row |
| 7 | Migration number or freeze-trigger column loss | High / medium-high | DOCS-3 ledger, migration owner, revert-to-prove | Two branches with one number; a published claim's currency edited in place |
| 8 | Hardcoded strings force Hindi rework | High / medium | I18N-1 before screens; lint from I18N-3 session 1 | A template merged with literal strings |
| 9 | Scope widening eats the content budget | Medium / high | SCOPE-1 phasing, SCOPE-6 honest states | Subset past about 125 claims; a fifth state or third country asked for before TRIAL-12 |
| 10 | VM region or Supabase quota facts wrong | Medium / high | DEPLOY-1 + OPS-1 on day 1 | DEPLOY-1 not done in week 1 |
| 11 | Logs hold age, marks, domicile from GET forms | Medium / medium | SEC-5, OPS-2 before DEPLOY-7 | `age=` in nginx or journald logs |
| 12 | Subscription rate limits, possibly as early as Wave 2 | Medium / medium | Measure in Waves 0-1 (A4b); second seat is budgeted; cheap cards to quiet hours; stretch Wave 3 by a day. No third seat without an owner DECISIONS line | Any lane blocked more than 30 minutes on limits |
| 13 | Docker will not run on the dev machine, or two stacks plus 6 worktrees overload it | Low-medium / high | Fallback (b): local stack on the Oracle VM over an owner-opened tunnel, Rs 0; option (a) needs Supabase Pro later (A3, A11). Cap 2. QA-2 measures the load | QA-1 not done by day 2; test runs timing out under load |
| 14 | An agent reads a live key or participant data | Medium / critical | SEC-15 (owner-only file, never a shell profile), deny rules for Read, Edit and Bash from day 1, owner-run `test-db` until QA-2, **SEC-16 key rotation** (the old keys may sit in earlier transcripts), localhost-only guard, no agent on staging from TRIAL-8, owner-run applies and deploys, guest purge | A non-localhost URL in any worktree env; a Supabase secret variable visible in an agent terminal; an agent asking for SSH or a service-role key; SEC-16 not done by day 7 |
| 15 | Festival and school-holiday windows (Navratri, Dussehra, Diwali - dates to be checked) reduce tester, checker and school availability | High / medium | Book TRIAL-8 slots and the checker's CONTENT-9 sitting by date in week 1; send the TRIAL-14 letter before the holidays | A recruit or the checker cannot give a date by day 5 |
| 16 | The owner approves a claim through a second account because the checker is not set up | Medium / critical | PUB-13b before CONTENT-9; exit gate 3 integrity query; D14 | CONTENT-9 import ready but no `critical_authorised` checker exists |
| 17 | GitHub Actions minutes run out in the Wave 2-4 month | Medium / low | QA-5 path filter, caching, cancel-in-progress, batch pushes (A12) | Minutes used pass 60% before day 12 |

---

## 13. Open decisions, with recommended defaults

**D1 is not open.** You decided it on 2026-09-21 (top entry of `docs/DECISIONS.md`); DOCS-1 commits it. What is still yours to approve: the writer caps in 8.3 and the `.claude/settings.json` deny rules (day 1, with DOCS-1), and the new agent files plus the settings allowlist (days 3-4).

### List (a) - needs your explicit yes. Nothing here is ever decided by silence, and dependent work waits.

| # | Decision | Recommendation (not a default) | What waits |
|---|---|---|---|
| D2 | Scope phasing (SCOPE-1; DECISIONS 2026-09-21 marks it an open owner question) | Phased inside unchanged ceilings: Gujarat, Delhi and up to two tester home states; UK first, Canada only if reviewer hours allow. Everything else shows "not verified yet". **Rule: an exam or country is published only if its rule module or display task (RULES-6/15/7, SCOPE-7) and its human check (RULES-12 / the SCOPE-8 standard) are done; otherwise it shows "not verified yet".** | CONTENT-5 subset, SCOPE-14, SCOPE-9. Not the schema: SCOPE-2 and SCOPE-3 are phasing-independent and proceed. |
| D3 | Real content on staging (resolver contradiction 12) | CONTENT-9 is a timed, labelled rehearsal after PUB-4 and after TRIAL-8. The checked CSV is re-imported on production in Phase 2 and re-approved fast **only on a content-hash match**. The staging ribbon stays on. Accept the second approval pass (about 4 paid hours). | CONTENT-9 import |
| D6 | Accounts and studies | Invite-only, adults only, `SIGNUP_ENABLED=false` through Step 15. Round 1 adults only. | CONSENT-3, TRIAL-1 profiles |
| D10 | Rule approval in git, not a DB table (RULES-18 dropped) | Accept; DECISIONS entry because it deviates from build pack section 6. | RULES-11 |
| D13 | Hosting and release - **deviation from the pinned stack** | Existing Mumbai project = staging for good; fresh production project in Phase 2 (needs the Singapore slot freed or Supabase Pro - A11). Production release is an owner-run `deploy.sh` from a protected `main` plus exact-SHA approval (DEPLOY-10, 12, 17), **not** a GitHub Actions protected environment; n8n is not deployed for the pilot. The lead drafts the DECISIONS entry in DOCS-5, together with D16 (DEPLOY-2 only supplies the hosting facts as proposed lines); you approve it **before DEPLOY-13**. No other stack element changes. | DEPLOY-13 |
| D14 | Interim roles until people are named | Owner is maker, corrections owner, support, and moderator for at most half of round 1. Owner is **never** the checker of his own claim, the consent reviewer or the SEC-13 signer, and holds no second reviewer account. | CONTENT-9 approval |
| D16 | Build-pack deviations for the pilot (each with a reason and a revisit trigger; the lead drafts the entry in DOCS-5, you approve) | Jobs table and worker built only if something enqueues work (OPS-5, OPS-14; Step 13, stack s4). No public-only PWA caching (A11Y-13 dropped; D8 `no-store`). No separate "Saved" destination (UI-16; merged into My Plan). No family summary or support-staff case summary (CONSENT-16; DESIGN-11/12 shrunk). No institution-steward measurement (TRIAL-15; TRIAL-18 reports measurement 8 as "not measured"). "What changed" list replaced by the AUTH-14 banner (AUTH-13). DigiLocker route deferred (recorded by CONSENT-17, which is kept). Gujarati UI strings only if a majority of recruits are Gujarati-medium (I18N-14). Teacher pack in Phase 3 (DESIGN-14). Five exams in Step 7 reached in Phase 2, three in Phase 1 (RULES-15). TRIAL-12 lists all of these under "Built means". | Nothing in Phase 1; without the entry the build pack still binds |
| - | Contract sign-offs AUTH-1, PUB-1, CONSENT-3; agent files and `.claude/settings.json`; SEC-8 data-flow acceptance; an API overflow budget, if you ever want one | - | AUTH-4/5 and AUTH-2; PUB-2; CONSENT-4; full caps |

### List (b) - reversible technical choices. A provisional default applies after 24 h.

The lead records it as "PROVISIONAL default - not owner-confirmed, reversible until <task>" on the task card or in `docs/CONTRACTS.md`. It becomes a DECISIONS entry only when you confirm it.

| # | Decision | Provisional default | Reversible until |
|---|---|---|---|
| D4 | Six rules decisions (RULES-17) | Phase 1 exams NEET-UG, JEE Main, GUJCET; CUET-UG and CLAT in Phase 2; DOB per request, never stored; guests not asked for category; no verified rules -> `insufficient_information`. | RULES-4 |
| D5 | Round-1 vehicle (DESIGN-6) | The real app on staging, guest only, not the mockup. | UI-15 |
| D7 | Email confirmation | Off while invite-only. CONSENT-3 decides it (and CONSENT-3 itself needs your yes); CONSENT-5 applies it in the dashboard. | CONSENT-5 |
| D8 | Cache policy | `no-store` on everything except `/static`. | A11Y-4 |
| D9 | Rate limiting | nginx only (SEC-3, Phase 2). No in-app limiter. | SEC-3 |
| D11 | OPS-6 phase | Phase 2, with the distress rule in its acceptance. | P2-A |
| D12 | Test backend if Docker fails | Option (b): local stack on the Oracle VM over an owner-opened tunnel, Rs 0. Option (a), repurposing the Singapore project for tests, forces Supabase Pro for production later (A3, A11). Cap 2 writers either way. | QA-2 |
| D15 | Dev-agent billing | One seat for Waves 0-1; second seat from Wave 2 only on measured limits; one seat in month 2; no third seat, no API overflow. **You check the real seat price including GST first.** | Each billing date |

---

## 14. Phases 2 and 3 outline

### Phase 2 - about 108 sessions, 5-6 weeks, bounded by reviewer hours

| Block | Work |
|---|---|
| P2-A build (up to 6 lanes) | **First: UI-19 (round-1 fixes) and any float card left over from Phase 1** (AUTH-2, 3, 14; CONSENT-4, 6, 6b, 7, 8, 10). Accounts stream: AUTH-9 -> UI-13 -> AUTH-7 -> AUTH-10, each with its cross-user lines (the export contains only the caller's rows, guest and B refused; B cannot migrate or delete with A's identifiers). Migration lane, every PR with its matrix rows: AUTH-7, AUTH-10, DATA-4 (no stage tables, **keeps `pathway_transitions`**), I18N-7, I18N-8, AUTH-15, **OPS-6**, TRIAL-5, AI-4; owner applies DATA-11, then DATA-13, with `--through`. Rules: **RULES-15 (CUET-UG, CLAT)**; RULES-7 (NDA, SSC CGL, IBPS PO) only for exams whose claims will be verified (D2 rule). **SCOPE-7 is firm** (the only student-facing display for foreign pathways). **UI-20** after DATA-4 and SCOPE-4. Hardening: SEC-3, A11Y-3 (owns `error.html`). In parallel: AI-1, **UI-11 in deterministic mode first**, AI-3, AI-5, AI-9. Hindi and a11y: I18N-4 with I18N-5, I18N-9, 10, 12, 15; A11Y-6, 7, 8, 14; DESIGN-15; **QA-9b before A11Y-11**. Console: PUB-6, 7, 8, 9, 10, 15. Ops: OPS-4, 7 (the kill-switch step names `SIGNUP_ENABLED`), 9, 10; DEPLOY-10. Measurement: TRIAL-16, RULES-13. |
| P2-B content and AI | Offline verification for CONTENT-10 and SCOPE-9 (after SCOPE-8, SCOPE-14 and CONTENT-9 timing). CONTENT-8. AI-6 (outbound field allow-list test, PII redaction fixture), AI-4 (per-account and global caps), AI-7 (after UI-11), AI-8, QA-10. DEPLOY-11, then **DATA-14** (owner: apply all migrations to production, grant and exposure audit, data-security review), then **PUB-13b on production**. |
| P2-C one release candidate | Agent-assisted reviews on the local stack and from PII-free output: PUB-12, PUB-14, AUTH-12, AUTH-17, DATA-11. **Owner-run from the owner's shell, output pasted PII-free: QA-16, OPS-16, AI-11.** Owner drills: OPS-8, OPS-15, SEC-8, SEC-14. Human gates: CONSENT-5 (includes the Supabase Auth site URL and redirect allow-list for staging), CONSENT-9, CONSENT-11, RULES-12 (every exam with published claims), SEC-10 -> SEC-13. AUTH-18 only if findings need it. |
| P2-D go live | Import and approve CONTENT-10 and SCOPE-9 on production (content batch 1) - **a foreign claim is imported only after SCOPE-7 is merged**; fast re-approval only on a content-hash match. CONTENT-11, CONTENT-17. **CONTENT-20 (content freeze) before DEPLOY-12.** AI-11, AI-16, AI-12, **AI-13 before AI-17**. I18N-11, I18N-13, I18N-16. A11Y-9 (includes the AUTH-14 changed-info banner), 11, 12. **TRIAL-3 Hindi half and TRIAL-4.** DEPLOY-12 -> DEPLOY-13 (includes the production redirect allow-list; needs the D13 DECISIONS entry). |

### Phase 3

1. TRIAL-11 (ten users, round 2, instrument pre-test; depends on UI-20 and TRIAL-4), DESIGN-16, TRIAL-12 go/no-go (lists the D16 deviations under "Built means"), TRIAL-17 week-4 post-test.
2. OPS-12, TRIAL-6, AI-13 checks; OPS-5 and OPS-14 only if something enqueues work (D16); TRIAL-19 recruitment (start week 6, do not wait for TRIAL-12).
3. Minors only after CONSENT-12 and CONSENT-14, by the school route (TRIAL-14), with the **DESIGN-14 teacher pack** ready before the first school session. Restore the Gujarati-strings half of I18N-14 only if TRIAL-1 recorded a Gujarati-medium majority.
4. TRIAL-13 batches 10 -> 25 -> 50 -> 100 with per-batch checks. Supabase Pro bought only here.
5. CONTENT-12 (content batch 2), SCOPE-11 demand-driven; TRIAL-18 DPR measurements write-up (measurement 8, institution steward, reported as "not measured").

**Phase 3 data rule (CLAUDE.md: no student data to development agents).** For TRIAL-11, DESIGN-16, TRIAL-12, TRIAL-17, TRIAL-6, TRIAL-18 and AI-13, agents receive only de-identified aggregates and owner-pasted script output. The owner runs the TRIAL-6 and AI-13 scripts on production from the owner's own shell. Raw instrument answers, session notes and feedback text never enter an agent session. The same line goes into `tasks/TEMPLATE.md`.

---

## 15. Next five sessions or workflows to run, in order

Each entry has a block you can paste into Claude Code as the first message of that session. For sessions 1-3 no card template exists yet: **the pasted block plus your typed "approved" is the task card**, and DOCS-3 back-fills them as BCI-007..009 in `tasks/INDEX.md`. Pick the model with `/model` before pasting. Forbidden files for every non-lead session: `STATUS.md`, `docs/DECISIONS.md`, `CLAUDE.md`, `tasks/INDEX.md`, `.claude/**`, and `.env` (live values; also `.env.local`, the owner-only key file and `/etc/eduvation/**`). `.env.example`, `.env.test.example` and the local-stack `.env.test` are **not** forbidden: they hold variable names or local keys only, and a card may own them.

**1. Lead session on `main`: DOCS-1.** Your day-1 items (section 10, items 1-5) run alongside.

```text
Model: standard. You are the lead, working on main. Task DOCS-1.
Read only: docs/plan/inventory-3-platform-launch.md, heading "### DOCS-1" (use Grep -A 25, not a whole-file read); git status; git worktree list.
Do: show me the list of uncommitted files (CLAUDE.md, docs/DECISIONS.md, docs/DEVELOPMENT-PLAN.md, docs/plan/, tasks/INDEX.md). Propose ONE added CLAUDE.md working-rule line: "Implementers read only their task card, implementer.md and the one docs/CONTRACTS.md section named on the card; they do not open the build pack, the DPR, docs/DEVELOPMENT-PLAN.md, docs/plan/* or docs/DECISIONS.md." Also propose a minimal .claude/settings.json with permissions.deny only: Read and Edit of .env, .env.local, /etc/eduvation/** and the owner-only key file path I give you; Bash cat/type/more/less/head/tail/Get-Content on those paths, printenv, and bare env/set. Do NOT deny .env.example, .env.test.example or .env.test. Show me the file. Wait for my "approved" on the line and on the settings file. Then commit on a branch, fast-forward merge that branch into main, and show me the main commit hash. Then remove stale worktrees under .claude/worktrees/ except any locked one (check git status inside each first).
Owned files: CLAUDE.md (that one line), .claude/settings.json (deny rules only), the commit itself. Do not edit anything else. Do not read .env. Do not run make test-db (no agent runs it before the local stack exists).
Tests: make lint; make test-unit. Report pass/fail/skip counts you ran yourself.
Stop if: a worktree has uncommitted work; any test fails; anything needs a secret.
Report: main commit hash after the fast-forward merge, worktrees removed, test counts.
```

Done when: the branch is fast-forward merged into `main`, `git status` on `main` is clean, the deny rules are in `main`, and the lead shows you the `main` commit hash. Worktrees are cut from `main` only after this.

**2. SKIPPED — CONSENT-1 is superseded, do not paste this session.** Another session merged a real age + guardian-email consent gate (`db/migrations/0004_guardian_consent.sql`, `db/migrations/0005_guardian_consent_request_rpc.sql`, confirmed live in production) while this plan was being written. It does the actual job CONSENT-1's sign-up kill-switch was a cheap stand-in for, and does it more completely. Your day-1 actions for this slot are just: **switch dashboard sign-ups off (CONSENT-18)** and **do SEC-15 (move the live keys out of the repo folder)** — both still needed, neither is a dev-agent session. Proceed straight to session 3 below.

**3. Lead session on `main`: DOCS-3** (then DOCS-2 with DOCS-5 as a second short session).

```text
Model: standard. You are the lead, on main. Task DOCS-3.
Read only: docs/plan/inventory-3-platform-launch.md heading "### DOCS-3" (Grep -A 15); tasks/INDEX.md (the DRAFT); docs/DEVELOPMENT-PLAN.md sections 3, 5 (ledger and Wave 0 bullets) and 6.4.
Do: create tasks/TEMPLATE.md (owned files, forbidden files, contract section, tests, reserved migration number, flag names, matrix rows for migrations, completion-report format). Finalise tasks/INDEX.md: canonical ids incl. the 12 added tasks (add SEC-16, which the draft index lacks, and correct its "11 added = 259" line to "12 added = 260"), BCI-007+ card numbers (BCI-007..008 = DOCS-1, DOCS-3; **BCI-009 is not CONSENT-1 — that slot is skipped, superseded, not built**), the 0006-0013 ledger, the stale-name ledger. Generate one card stub per Phase 1 task from the inventories by Grep on each id heading, with corrected numbers. On the SEC-7, PUB-5, SEC-1, DEPLOY-5, OPS-2, A11Y-4, DEPLOY-9, DEPLOY-15 and AI-2 stubs replace Makefile, app/main.py, app/core/config.py and .env.example with mk/<task>.mk and a named registry module; on the QA-4, DEPLOY-2 and RULES-11 stubs replace CLAUDE.md, STATUS.md and docs/DECISIONS.md with "proposed lines in the completion report"; on the DEPLOY-18 stub copy the flag list from plan section 6.2 and the middleware slot order from 6.4, tier standard, fail-closed acceptance; PUB-5 start condition "QA-3 merged"; UI-1 does not edit the journey templates (A11Y-2 adds the _save.html include lines); DESIGN-18 start condition "SEC-5 merged". Create an empty docs/CONTRACTS.md skeleton (section headings only, 1,500-word cap note). Mark the three docs/plan/inventory-*.md files "ARCHIVED - lead-only; cards supersede" in their first line.
Owned files: tasks/TEMPLATE.md, tasks/INDEX.md, tasks/BCI-0xx.md stubs, docs/CONTRACTS.md, first line of each inventory file.
Tests: none (docs only). Run make lint to prove nothing else changed.
Stop if: two tasks claim the same migration number or card number.
Report: list of card numbers, the ledger, anything in the inventories that contradicts the plan.
```

Done when: you can open `tasks/INDEX.md` and find every task id with a card number.

**4. Lead session on `main`: DOCS-4 with DOCS-13 and DOCS-6.** The contract agent (entry 5a) may already be running: it touches only `docs/CONTRACTS.md`, and this session touches only `docs/PARALLEL.md`, `docs/COSTS.md` and `.claude/`. Section 8.3 allows exactly this overlap.

```text
Model: standard. You are the lead, on main. Tasks DOCS-4 + DOCS-13 + DOCS-6 in one session.
Read only: docs/DEVELOPMENT-PLAN.md sections 6.4, 8.1-8.4 and 8.7; .claude/agents/*.md; the three inventory headings "### DOCS-4", "### DOCS-13", "### DOCS-6" by Grep.
Do: write docs/PARALLEL.md (ownership map, single-writer list, merge rules, reset rule, actual model names per tier); docs/COSTS.md (four ledgers, per-batch metrics line, the tripwire); .claude/agents/implementer.md; .claude/agents/migration-owner.md; fix the stale trigger paths in .claude/agents/data-security-reviewer.md; propose an addition to .claude/settings.json (its deny rules already exist from DOCS-1; do not loosen or remove any): an allowlist for the implementer tool set. SHOW ME each agent file and the settings change and wait for "approved" per file before committing it.
Owned files: exactly those. Do not edit CLAUDE.md or DECISIONS.md in this session.
Tests: make lint.
Stop if: any rule here conflicts with the 2026-09-21 DECISIONS guardrails.
Report: files created, my approvals received, open questions.
```

Done when: you have approved each file and the lead shows the commit hash.

**5. First parallel workflow (allowed as soon as DOCS-1 is committed and SEC-15 is done):** (a) contract agent; (b) design docs; (c) QA-2 once QA-1 is done. The mechanical lane (DEPLOY-18 -> SEC-7 -> UI-2 -> SEC-1 -> DEPLOY-5 -> PUB-5 once QA-3 is merged) and the docs-and-scripts lane (CONTENT-3 -> DESIGN-3 -> CONTENT-18) start after entry 4 is merged; that is the "burst + 4" cap in 8.3.

```text
(a) Model: strongest. Implementer in worktree "contracts". Tasks, strictly in order: SCOPE-2 -> RULES-1 -> PUB-1 -> CONTENT-2 -> AUTH-1 -> CONSENT-3 -> A11Y-1 (A11Y-1 only after the lead tells you DESIGN-2 and DESIGN-1 are merged).
Read only: the inventory heading for the current task (Grep), docs/CONTRACTS.md, the docs/DEVELOPMENT-PLAN.md section 6.2 table, and the decisions digest once DOCS-5 exists. Until the digest exists you (the contract agent only) may read the top two entries of docs/DECISIONS.md (both dated 2026-09-21). 
Owned files: docs/CONTRACTS.md (one section per task), docs/CONSENT.md (CONSENT-3), one pointer line in docs/DATA.md; A11Y-1 also edits docs/UI.md.
Rules: settle every conflict in the 6.2 table. Until the owner gives an explicit yes on scope phasing, freeze only scope-neutral vocabulary. CONSENT-3 uses role placeholders and the adults-only, invite-only default. Never write an owner decision into docs/DECISIONS.md.
Stop after each task and report; stop at once on a conflict you cannot settle from the digest.

(b) Model: standard (strongest for DESIGN-1). Implementer in worktree "design-docs". DESIGN-2 -> DESIGN-1 -> DESIGN-5 -> TRIAL-2. Owned: docs/COPY.md, docs/UI.md (DESIGN-1 section only), docs/design/journeys.md, docs/research/*. TRIAL-2 does not edit docs/UI.md. TRIAL-2 recruitment and consent text is for adults (18+) only.

(c) Model: strongest. Test engineer in worktree "qa-2". Task QA-2 (2 sessions). Owned: supabase/config.toml, mk/testdb.mk, tests/db/conftest.py, tests/e2e/conftest.py, tests/db/test_api_auth.py, .env.test.example. Acceptance additions are in docs/DEVELOPMENT-PLAN.md section 5, Wave 1. Never point any test at a non-localhost URL.
```

Done when: each lane's completion report lists files touched, test and skip counts, and the lead has merged it. Your explicit yes on AUTH-1 and PUB-1, and the 30-minute contract read-through, then release AUTH-4/5, PUB-2, SCOPE-3 and CONTENT-6.

---

## 16. How this plan was produced, and its limits

- It was produced on 2026-09-21 by a multi-agent planning run that you requested: 18 area audits, a dependency resolver, six cross-cutting analyses, three competing plans (speed-first, cost-first, risk-first) and three judges. This document is based on the cost-first plan, uses the risk-first plan's safety ordering and caps, takes lane-packing ideas from the speed-first plan, and fixes every error the judges listed. No product code was written.
- **All estimates are model-generated and unverified by a person**: session counts, hours, days and every rupee figure. No vendor price, subscription price or per-answer AI cost was checked. Treat them as ranges to be replaced by actuals in `docs/COSTS.md`.
- Most analysts did not open repo files or run tests. Facts checked directly: migrations 0001-0003 exist; `.claude/agents/` has two reviewer files; the NULL `created_by` self-approval path in `0003_maker_checker.sql`; build pack sections 7, 9, 12 wording; the working tree state. Everything else comes from audits.
- A second pass on the same day applied six critic reviews (about 75 issues). Facts checked directly in that pass: the 2026-09-21 DECISIONS entry and the working-tree `CLAUDE.md` rule; the live `.env` in the repo root and the missing `.claude/settings.json`; `scripts/apply_migrations.py` has no upper bound; the three `_safe_source_url` copies; no `AI_ENABLED` in `app/`; the I18N and A11Y sections live in inventory-1; 22 Sep 2026 is a Tuesday. Festival dates were **not** checked.
- The task texts in the inventory still carry stale migration numbers, file names and dependencies that this plan overrides: DATA-10 (now 10a/b/c), PUB-4 (0010-0011 only), DATA-11, DATA-13 (its title still says "batch C (0012)", but 0012 is now SEC-6), PUB-13 (split), PUB-2's CONSENT-4 dependency (ordering only), SCOPE-3 (cut down), CONTENT-6 (split), QA-9 (one session), QA-12 (Phase 1), AUTH-6 (new files only, no AUTH-3 dependency), RULES-8 (no `comparison.py` edit), DEPLOY-7 (owner-only), TRIAL-2 (no `docs/UI.md` edit), TRIAL-8 (adults only), UI-11, the OPS-6 and CONTENT-18 tags, `SIGNUPS_ENABLED`, `reviewer_pages.py`, and the move of contract text into `docs/CONTRACTS.md`. The inventory's "Wave: N" field is a dependency depth, not this plan's wave. Where they disagree, DOCS-3's published ledger and the task card are what agents follow. All three inventory files are complete and all 248 audit ids are present as headings; the 12 added tasks are defined only in section 3. AUTH-16 is not a task heading: the inventory merged it into CONSENT-5, so this plan no longer cites it.
- A third pass on the same day applied one more review (11 issues): SEC-15 tightened (owner-only file, never a shell profile; no agent `test-db` before the local stack; Bash deny patterns; deny rules land with DOCS-1), SEC-16 key rotation added, start conditions added for UI-1, DESIGN-18, the Wave 3a window and PUB-5, DEPLOY-18 raised to standard tier with a fail-closed registry and a review pass, lead-only files taken off implementer cards, the deny patterns narrowed so `.env.example` and `.env.test` stay usable, the Wave 1 cap set to burst + 4, days 8-10 owner load restated, and `make content-integrity` given an owner (CONTENT-6b). `tasks/INDEX.md` was not edited in that pass, so it still lacks SEC-16 until DOCS-3.
- A fourth pass (lead session, same day) added section 8.8 (workflow deployment table) and applied six fixes from the final check: I18N-1 no longer touches the reviewer console (the lead adds its one import line at the PUB-5 merge); A11Y-4 waits for DEPLOY-15; CONSENT-1 starts only after SEC-15; the contract agent may read the top two DECISIONS entries until the DOCS-5 digest exists (DOCS-3 runs before DOCS-2 on purpose - a plan override of the graph); the DESIGN-3 step was removed from the `ci.yml` order; the Phase 3 no-student-data rule was added to section 14. **Still open from that check (medium/low, for DOCS-3 to close):** `tasks/INDEX.md` disagrees with this plan in five lines (SEC-16 missing, "11 added = 259", the UI-1 `_save.html` wording, the DEPLOY-2 D13/D16 wording, the DOCS-10 deny-rules wording) - until fixed, follow section 10, not the index; DOCS-3 is too big for one session and should be split into DOCS-3a (template, index, ledgers, the ~15 rewritten cards, CONTRACTS skeleton - gates the fan-out) and DOCS-3b (remaining card stubs by script, cheap, Wave 1 filler); the section 11 matrix lacks rows for the per-batch expansion checks, the "AI grounded, budgeted, interruptible and optional" clause and the Step 15 tester tasks (tasks exist: OPS-12, TRIAL-6, AI-13, TRIAL-10, TRIAL-13; AI-6, AI-11, AI-16, AI-2, AI-8, AI-17; AUTH-17, A11Y-4, TRIAL-2); float work is 8 tasks plus UI-19 = up to 10 sessions, not 8; RULES-9 session 1 before UI-7 is a deliberate override.
- **Fourth pass (lead, after discovering two concurrent sessions mid-edit in this same shared checkout).** Fetched and verified `origin/main` directly (didn't trust either session's chat claims) before acting. Merged the guardian-consent gate (`acc6534`/`c7d87bc`, commit `c0bd343`) after resolving one real `docs/DECISIONS.md` conflict; unit tests re-run, 191 pass. **Migration ledger shifted +1 throughout this plan**: `0004_guardian_consent.sql` is real, merged, and not this plan's to renumber — DATA-12 now 0006, SCOPE-3 0007, AUTH-4 0008, AUTH-5 0009, PUB-2 0010, PUB-3 0011, SEC-6 0012, CONSENT-4 0013. **CONSENT-1 (the sign-up kill-switch stopgap) is superseded** — the merged gate does the real job (age check + guardian email, fail-closed) — and is marked so in Wave 0. **Not yet done, flagged rather than rushed**: roughly two dozen *other* CONSENT-1 references in this plan (DEPLOY-18's start condition, the mechanical and tests lanes in Wave 1, the `app/api/auth.py` chain in 6.4, the 8.3 caps, the 8.6 review ledger, section 15's session-2 pasteable prompt, several cost-table rows) still name CONSENT-1 as a real gate task and need a dedicated re-derivation pass — what actually unblocks each of those now that CONSENT-1 itself is not built — before Wave 0/1 fan-out starts. **Do not paste section 15's session 2 as written**; it still targets the superseded task. **New gap found, not yet carded**: the "Held, not merged" student sign-up/save-plan UI (`STATUS.md`) is the locked worktree `wf_9b7797a4-e76-1` this plan's audits never saw (it's uncommitted, invisible to a normal `git status` scan) — real work, not scratch, and it still needs its own bounded merge-on-top-of-the-gate task. **Still contradicted, not resolved**: whether `0004` is actually applied to any live database right now — one message from the guardian-consent session claimed yes plus a live production RLS bug found by testing against it; that session's own `c7d87bc` commit says the opposite (not applied, no DB access, fails closed). Neither claim was independently verifiable by this session (no DB credentials sought or used) — the owner should confirm directly. A third session ("Workflow agents structure") separately edited this plan's section 8.8 live in the same shared checkout; its edit was left untouched and folded in as-is above.

- **Fifth pass (lead), minutes later — the flagged second collision was real.** The guardian-consent session replied and cleared up the earlier contradiction with evidence, not just assertion: `c7d87bc`'s own commit message (checked directly, not taken on trust) says "until the owner applied `db/migrations/0004_guardian_consent.sql` to the live project just now" — so **0004 is genuinely applied to a live production Supabase project** (the owner ran it manually in the SQL editor). `STATUS.md`'s "NOT applied" prose (still in this repo as pushed) is that session's own stale text from before the apply, not yet corrected by its author — treat the commit message as current, that prose as history, until it says otherwise. This makes the RPC bug that session is fixing a **real, live-impacting production issue**, not a hypothetical: every minor's guardian-consent request reaching production right now hits an unhandled 500 until the fix lands. Not this session's to fix (no DB access sought or used; that session is already running its own adversarially-verified workflow for it).
  Numbering: confirmed the fix is `db/migrations/0005_guardian_consent_request_rpc.sql` — a **new** file, not an in-place edit of 0004 (append-only now applies to 0004 too, since an instance of it is live somewhere real). **Ledger shifted +1 again**, this pass: DATA-12 now 0006 (was 0005), SCOPE-3 0007, AUTH-4 0008, AUTH-5 0009, PUB-2 0010, PUB-3 0011, SEC-6 0012, CONSENT-4 0013. Given this is the second such shift in under an hour, the ledger above is now marked provisional with a re-verify instruction rather than treated as settled — a third concurrent migration before Wave 2 actually starts would not be a surprise.

- **Sixth pass (lead) — the CONSENT-1 re-derivation, done.** Fetched and fast-forward-merged `0005_guardian_consent_request_rpc.sql` (`6e1fc05`, three commits) cleanly — no ledger collision, since the fifth pass had already reserved 0006 for this plan's own next migration. Re-ran lint and unit tests (193 pass) after the merge. Then closed the roughly two dozen stale CONSENT-1 references the fourth pass had flagged and deliberately not rushed: every start condition that named "CONSENT-1 merged/done" now names its real precondition instead (mostly "DOCS-1 merged" — a clean main is what those lanes actually needed, not a task that was never going to exist); the `app/api/auth.py` conflict-group chain, the 8.3 caps, the 8.6 review ledger, the workflow-deployment table (8.8, sections A-C), the gate-coverage and risk-table rows that named CONSENT-1 as a mitigant now name the real merged gate instead; section 15's session 2 is replaced with a short note explaining it's skipped, not a pasteable prompt for dead work. Passages describing *what earlier passes found or did* (this note included) are left as history, not silently rewritten — the one place that would have read as a live false statement (the third-pass note's closing line) got a bracketed correction instead of an edit. `.env.example` was read to get the real variable names for the owner's SEC-15 instructions (no secret values in that file, safe to read); `.env` itself was not touched or checked — this session's own `.claude/settings.json` deny rule now refuses even an `ls` on it, which is stricter than intended but the right direction, not a bug to route around.
- **Staleness caveat (checked by the lead after the run).** Another session committed product code while the audits were running (commits up to `8a19f31`, 14:30 on 2026-09-21): the M5 AI groundwork under `app/ai/` (adapter, budget, grounding, mock and Gemini providers, `tests/unit/test_ai_adapter.py`) at 14:13, and 11 reviewer-console audit fixes at 14:27, which changed `app/web/reviewer_pages.py`, `app/api/auth.py`, `app/api/claims.py` and `tests/db/test_reviewer_console.py`. The audits ran 14:06-14:18, so the Requirements and Timeline screens and the Playwright e2e wiring (13:56-13:59) are reflected, but the AI groundwork and the console fixes may not be. Before carding them, re-check against the code: AI-2, AI-3, AI-5, AI-6 (parts may already exist), PUB-5, SEC-2 and the `reviewer_pages.py` line references. Confirmed still true after those commits: there is no sign-up flag in `app/core/config.py` or `app/api/auth.py`, so CONSENT-1 is still needed. *(Correction, sixth pass: superseded shortly after this was written — see the fourth-pass note above. CONSENT-1 was never built.)*
- **This plan approves nothing.** Under the CLAUDE.md conflict order, each task needs an owner-approved card (from Wave 1 on: the per-wave card table) before work starts, and `docs/DECISIONS.md` outranks this file. D1 is already recorded there; it must be committed by DOCS-1.
- `STATUS.md` remains the source of truth for state. Update this plan only at phase boundaries; do not use it as a status tracker.
- No test was run for this plan. The "239 tests pass" figure is quoted from `STATUS.md`, not re-verified here.
