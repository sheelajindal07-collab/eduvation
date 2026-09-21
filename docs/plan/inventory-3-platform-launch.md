# Task inventory - Platform, QA and launch

**ARCHIVED - lead-only reading; task cards under tasks/ (tasks/TEMPLATE.md) supersede this file.** Generated 2026-09-21 by the planning workflow from verified area audits, then superseded once DOCS-3 finalised tasks/INDEX.md the same day. Migration numbers and a few task descriptions here are stale — docs/DEVELOPMENT-PLAN.md's ledger and a task's own card are what agents follow; find a task with Grep on its id heading, never a whole-file read.

## Operational safety: jobs worker, reminders, monitoring, runbook, restore drill, load test

Area: `ops-worker-monitoring`

The audit's core finding is confirmed: almost nothing in Step 13 exists. What exists is /healthz (liveness only), reserved env variable names, one PII-conscious logger call in app/api/auth.py, the jobs-table design text and the migration runner. There is no jobs table, worker, logging module, error tracker, feedback capture, docs/RUNBOOK.md, backup, restore drill or load test. Main corrections: mixed dev/owner tasks split, the worker split from its migration, jobs worker and in-app feedback retagged to expand-100 (no section 12 gate needs them earlier), reviewer notices retagged deferrable, a false external dependency removed (claims.review_due_date already exists), the build pack dropped from touches (DECISIONS says it is not edited), a Supabase-compatible restore target, and the Oracle VM region recorded.

### Already done

- Liveness endpoint /healthz reports config flags only (no DB round-trip); no /readyz exists - F:\the competetion project\app\api\health.py (single route, confirmed)
- Env variable names reserved for error tracking, uptime, n8n webhook and WhatsApp; all default None and no code reads them - F:\the competetion project\app\core\config.py (whatsapp_*, error_tracking_dsn, uptime_check_url, n8n_webhook_url); F:\the competetion project\.env.example
- Jobs-table design documented (status, lease_until, attempts, idempotency_key; one polling worker) - text only - F:\the competetion project\docs\ARCHITECTURE.md section 'Background work'
- Data-flow map rows exist for monitoring vendor, backups, WhatsApp and app+worker, but are unfilled or inaccurate (backups row claims Supabase-managed daily backups; app row says 'VPS, Mumbai (once provisioned)' while the real host is an Oracle VM with unrecorded region) - F:\the competetion project\docs\SECURITY.md 'Data-flow map' table
- One precedent for PII-free logging via stdlib logging.getLogger (the only logger in app/) - F:\the competetion project\app\api\auth.py lines 33, 44, 126
- Migration runner with _schema_migrations tracking, using the OPS-only DATABASE_URL which the running app never reads - F:\the competetion project\scripts\apply_migrations.py; F:\the competetion project\.env.example DATABASE_URL comment
- App runs as systemd unit eduvation.service on Oracle VM moulding-app-a1, port 8010, localhost only, shared with hisab/lekha/attendance-app - F:\the competetion project\STATUS.md lines 15, 32, 334
- Supabase prod project is Mumbai ap-south-1; DECISIONS noted 'no backups yet' at creation - F:\the competetion project\docs\DECISIONS.md lines 349-365 (the audit cited 340-347, which is wrong)
- claims.review_due_date column already exists (NOT NULL) and is exposed through the claims API - a review-due query needs no schema change - F:\the competetion project\db\migrations\0001_init.sql line 60; F:\the competetion project\app\api\claims.py lines 87, 127
- httpx and psycopg are already pinned dependencies, so a load script and a worker need no new packages - F:\the competetion project\pyproject.toml lines 13, 15

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No jobs table migration (db/migrations has only 0001-0003) and no worker process, handler registry or scheduler | Build pack s4 'Background worker'; s9 Step 13; ARCHITECTURE.md 'Background work' | phase1-required |
| No central logging config: no app/core/logging.py, no JSON logs, no redaction filter, no request-id middleware, no PII-free log test. Uvicorn's default access log (raw URL + client IP) is still on in `make dev` and presumably in the systemd unit | Build pack s4 'Monitoring'; SECURITY.md quality gate 'Privacy: PII-free logs' | launch-blocker |
| Error tracking not wired (ERROR_TRACKING_DSN unused, no sentry dependency), no payload scrubbing, vendor region/retention not recorded in SECURITY.md | Build pack s4 Monitoring; s8 row 'Error tracking and uptime' | phase1-required |
| No uptime check; /healthz cannot detect a paused or unreachable Supabase project; no alert has ever been tested | Build pack s4 Monitoring; SECURITY.md quality gate 'Operations: monitoring alert' | phase1-required |
| No docs/RUNBOOK.md (incident, pause/kill switch, secret rotation, correction, restore, stuck worker, data-incident contact, support owner) | Build pack Step 13 'runbook'; Step 14 'pause and kill-switch documented'; s12 Built-means 'monitoring, support owner, restore and recovery verified' | launch-blocker |
| No backup exists and none has ever been restored. The Supabase plan is unconfirmed, and the SECURITY.md backups row ('Supabase-managed daily backups') is probably untrue on the free tier | Build pack s12 'a backup has actually been restored'; SECURITY.md quality gate 'backup restore' | launch-blocker |
| Oracle VM region and compute shape are unrecorded (DECISIONS 'Still open'). The 'Application + worker' data-flow row cannot be confirmed, which blocks the owner's written acceptance of the map | SECURITY.md 'Rule' under the data-flow map; DECISIONS.md line 444, 518-519 | launch-blocker |
| No feedback capture and no triage procedure. For the ten-user trial the Step 15 moderator collects feedback; an in-app form only matters for expansion | Build pack Step 13 'feedback triage'; s12 expansion check 'support requests per 100 users' | phase1-required |
| No 25-session load test; no tests/load directory | Build pack Step 13 '25-session load test' | phase1-required |
| No release checklist document and no human release-review step | Build pack Step 13 'release checklist'; section title 'Operational safety and release review' | phase1-required |
| No reviewer notices or review-due reminders (n8n or other); n8n status still open; the reviewer console shows nothing for review-due | Build pack s4 'Workflow glue'; DECISIONS.md line 518 | phase1-nice |
| No expansion-batch operational check sheet | Build pack s12 'Expansion checks per batch' | defer |
| WhatsApp opt-in deadline template: no reminders table (only a comment in 0002_saved_plans.sql line 3), no opt-in field, no sender | Build pack s3/s4 'Reminders'; Step 13 'optional WhatsApp template' | defer |
| Scheduled source-allowlist checks via n8n | Build pack s4 'Workflow glue' | defer |

### Owner decisions

- **Error-tracking and uptime vendors and their regions** - blocks: OPS-4, OPS-8, acceptance of the data-flow map - recommended default: Sentry free tier (EU region, payloads scrubbed, no tracing or replay) plus UptimeRobot free at a 5-minute interval on /readyz. Record both in SECURITY.md.
- **Backup approach: Supabase Pro managed backups, or free tier with a nightly encrypted pg_dump on the VM** - blocks: OPS-9, OPS-15 and the s12 'backup restored' gate - recommended default: Nightly encrypted pg_dump on the Oracle VM with 7-day retention (Rs 0) through the ten-user trial. Move to Supabase Pro before expanding to 100; Pro also removes inactivity pausing.
- **Restore drill target** - blocks: OPS-15 - recommended default: A second free Supabase project in Mumbai, deleted after the drill. It has the roles and extensions a Supabase dump needs, and nothing new to install. If Docker is confirmed on the VM, the supabase/postgres image is an acceptable alternative. Avoid vanilla Postgres. Run the drill while data is synthetic only.
- **Record the Oracle VM region and accept (or not) that the app host may be outside Mumbai** - blocks: SECURITY.md 'Application + worker' row; owner's written acceptance of the data-flow map; real-users-gate - recommended default: Record the actual region now. If it is an Indian region (Mumbai or Hyderabad), accept it. If not, either move the app to an Indian-region VM before real users, or record an explicit acceptance in DECISIONS.md. Do not leave it blank.
- **Is n8n actually running, and is it worth using for the pilot** - blocks: OPS-11 - recommended default: Skip reviewer notices for Phase 1. Reviewers check /reviewer/queue on a fixed weekday, and OPS-12 reports stale and pending counts. Revisit only if pending reviews age beyond a week.
- **WhatsApp reminder template in Phase 1?** - blocks: OPS-13 - recommended default: Defer. Show deadlines inside My Plan. Record the deferral in DECISIONS.md.
- **Build the jobs table and worker before the ten-user trial or before expansion** - blocks: OPS-5, OPS-14 timing - recommended default: Before expansion. No section 12 gate needs it, and no async work exists yet. Pull it forward only if the export/deletion or AI areas decide they need a background job.
- **In-app feedback form vs a support email address for the trial** - blocks: OPS-6 timing - recommended default: For the trial: moderator notes plus a support email in the footer, triaged weekly per the runbook. Build the in-app form, merged with the Step 8 support queue if one exists, before the 25-user batch.
- **Named support/incident owner, alert recipient and second person for release review** - blocks: OPS-7, OPS-8, OPS-17 - recommended default: The owner is primary and one named fact reviewer is backup. Alerts go by email plus phone push. The same backup person co-signs the release review.

### Tasks

### OPS-1 - Owner: vendors, backup tier, VM region, n8n status

- What: Owner signs up for an error tracker (Sentry free, region chosen and noted) and an uptime checker (UptimeRobot free). Confirms the prod Supabase plan and whether any managed backup exists. Records the Oracle VM region, shape and whether Docker is available. Answers whether n8n actually runs. Puts the DSN in the server env only.
- Acceptance: Vendor names, regions and retention, Supabase plan, VM region/shape/Docker and n8n yes/no are written into a DECISIONS.md entry (values only, no secrets). No secret appears in repo or chat.
- Step: 13 | Wave: 0 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 1
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: none
- Risk: none recorded

### OPS-2 - PII-free structured logging + request id

- What: Add app/core/logging.py: JSON formatter, redaction filter (emails, phone numbers, JWT/cookie-shaped strings), and a configure_observability(app) hook called from create_app. Request-id middleware logs method, route template, status and latency only, never query strings, bodies or client IP. Document that uvicorn must run with --no-access-log. Emit named events for failed login and failed save.
- Acceptance: make test-unit passes new tests proving email, phone and token strings never appear in emitted lines and that the access line uses the route template. ruff and mypy are clean. Event names are listed in the module docstring.
- Step: 13 | Wave: 0 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: none
- Touches: app/core/logging.py, app/main.py, Makefile, tests/unit/test_logging_redaction.py
- Reviewers: data-security-reviewer
- Risk: none recorded

### OPS-4 - Error tracking with scrubbed payloads; vendor region recorded

- What: Wire sentry-sdk behind ERROR_TRACKING_DSN inside configure_observability (no-op when unset). Set send_default_pii False and include_local_variables False, with no tracing and no replay. A before_send hook drops request bodies, cookies, headers, query strings and user context. Record vendor, region and retention in the docs/SECURITY.md data-flow row. Do not edit the build pack (DECISIONS: it mirrors the online doc).
- Acceptance: A unit test passes a synthetic event with body, cookie, header and email through before_send and asserts all are stripped. The app boots with the DSN unset. The SECURITY.md row shows vendor, region and retention.
- Step: 13 | Wave: 1 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: OPS-1, OPS-2
- Touches: app/core/monitoring.py, app/core/logging.py, pyproject.toml, docs/SECURITY.md, tests/unit/test_monitoring_scrub.py
- Reviewers: data-security-reviewer
- Risk: none recorded

### OPS-5 - Jobs table migration + claim/complete SQL functions

- What: Add a migration (next free number; 0004 provisional, orchestrator allocates). It creates a jobs table (kind, payload jsonb, status, run_at, lease_until, attempts, max_attempts, idempotency_key unique, last_error), RLS on with no policy, and a dedicated low-privilege worker role. Security-definer functions enqueue_job, claim_job (FOR UPDATE SKIP LOCKED plus lease), complete_job and fail_job (backoff, bounded). Payloads carry ids only.
- Acceptance: make test-db proves a duplicate idempotency_key is rejected, an expired lease is reclaimed, and attempts over max go to failed. Guest, student A/B and reviewer clients cannot select, insert or call claim_job. The worker role cannot read student_profiles or saved_plans.
- Step: 13 | Wave: 0 | Needed by: expand-100
- Executor: dev-agent | Model tier: strongest | Dev sessions: 1 | Human hours: 0.5
- Depends on: none
- Touches: db/migrations/0004_jobs.sql, tests/db/test_jobs.py, docs/ARCHITECTURE.md
- Reviewers: data-security-reviewer
- Risk: First server-side credential outside user-scoped RLS. It must be a narrow role, never service_role or the migration DATABASE_URL.

### OPS-6 - In-app 'Report a problem' form + feedback table

- What: Add a zero-JS form linked from base.html. It stores category, page path and up to 500 characters of text in a feedback table (insert-only for guest/student, select for reviewer). It has a per-IP/session rate limit and a 'do not enter personal details' hint. Text is never logged. If the Step 8 area builds a support_requests table, merge into that table instead of creating a second one.
- Acceptance: make test-db shows guest and student can insert but not read, and a reviewer can read. 501 characters are rejected. Repeated posts are throttled. No feedback text appears in captured logs. The ux-qa reviewer checks mobile layout and the error state.
- Step: 13 | Wave: 3 | Needed by: expand-100
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: UI-1, UI-2, OPS-2
- Touches: db/migrations/0005_feedback.sql, app/api/feedback.py, app/web/templates/feedback.html, app/web/templates/base.html, app/main.py, tests/db/test_feedback.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: none recorded

### OPS-7 - Write docs/RUNBOOK.md and docs/RELEASE-CHECKLIST.md

- What: Runbook covers: start/stop/restart eduvation.service, where logs live and journald retention, pause and kill switch (AI off, sign-up off, maintenance page), secret rotation, wrong-fact correction, Supabase paused or unreachable, suspected data incident with named contact and CERT-In/DPDP awareness note, support owner, weekly feedback triage (trial: moderator notes plus support email), and restore (stub until OPS-9). The release checklist mirrors the s12 gates and SECURITY.md quality gates.
- Acceptance: Every procedure has exact commands or dashboard paths, a named owner and a verification step. No secret values. The owner fills the named-person blanks and confirms by reading it once end to end.
- Step: 13 | Wave: 3 | Needed by: real-users-gate
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 1
- Depends on: DEPLOY-5, OPS-4, DOCS-5, AI-2, CONSENT-1
- Touches: docs/RUNBOOK.md, docs/RELEASE-CHECKLIST.md
- Reviewers: human
- Risk: none recorded

### OPS-8 - Owner: uptime check live and alert actually tested

- What: Owner points the uptime checker at the public /readyz (staging first, then prod) at a 5-minute interval, with email plus phone-push alerts. Deliberately stops the service once and confirms the alert and recovery notices arrive. Records date and result in STATUS.md, and the uptime vendor region in the SECURITY.md row.
- Acceptance: An alert is received within 10 minutes of a deliberate stop, and a recovery notice after restart. Date and result are in STATUS.md.
- Step: 13 | Wave: 5 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 0.5
- Depends on: OPS-1, DEPLOY-5, DEPLOY-7
- Touches: STATUS.md, docs/SECURITY.md
- Reviewers: none
- Risk: none recorded

### OPS-9 - Backup dump + restore-check scripts and nightly timer

- What: Add scripts/backup_dump.sh (pg_dump of public and auth schemas via the OPS-only DATABASE_URL, pg_dump major version matching the server, output encrypted with age or gpg, 7-day rotation). Add scripts/restore_check.py (row counts per table plus one RLS probe against a target URL) and a systemd timer unit file. Correct the SECURITY.md backups row to the real mechanism. Write the runbook restore section.
- Acceptance: Scripts are shellcheck/ruff clean. restore_check has unit tests with a mocked connection. The dump file is never written unencrypted. The SECURITY.md backups row states the actual mechanism, location and retention. The runbook restore section has exact commands.
- Step: 13 | Wave: 4 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: OPS-1, OPS-7
- Touches: scripts/backup_dump.sh, scripts/restore_check.py, scripts/bcion-backup.timer, scripts/bcion-backup.service, tests/unit/test_restore_check.py, docs/RUNBOOK.md, docs/SECURITY.md
- Reviewers: data-security-reviewer
- Risk: A Supabase dump references roles (anon, authenticated, supabase_auth_admin) and extensions that a vanilla Postgres lacks. The restore target must be Supabase-compatible.

### OPS-10 - 25-session load script (no live model calls)

- What: Add tests/load/run_load.py using asyncio plus the already-pinned httpx (no locust dependency). It runs 25 concurrent journeys: explore, compare, eligibility, timeline, and save-plan using pre-created synthetic accounts read from env. It refuses to run if the target reports ai_configured true, unless a mock flag is set. Reports p50/p95 and error rate. Add a make load target, excluded from CI.
- Acceptance: The script runs against local make dev with 25 sessions and prints p95 and error rate. It aborts with a clear message when the AI guard trips. It performs no sign-ups during the run. ruff is clean.
- Step: 13 | Wave: 1 | Needed by: ten-user-trial
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: DEPLOY-5, AI-2
- Touches: tests/load/__init__.py, tests/load/run_load.py, Makefile
- Reviewers: none
- Risk: none recorded

### OPS-11 - Reviewer notice + review-due reminder (optional)

- What: Two job handlers: review_requested, enqueued from submit_claim in app/api/claims.py, and a daily review_due scan over claims.review_due_date (the column already exists). Each POSTs a PII-free payload (claim id, field, count) to N8N_WEBHOOK_URL. One n8n workflow emails the named reviewers. Skip entirely if n8n is not running. OPS-12 stale counts plus the reviewer queue cover the pilot.
- Acceptance: Mocked-webhook unit tests pass. The payload holds no student data. A webhook failure retries up to max_attempts and never delays the /claims response. One real test notice reaches a reviewer on staging.
- Step: 13 | Wave: 2 | Needed by: deferrable
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 1
- Depends on: OPS-5, OPS-14, CONTENT-1
- Touches: app/jobs/handlers.py, app/api/claims.py, tests/unit/test_job_handlers.py, docs/RUNBOOK.md
- Reviewers: data-security-reviewer
- Risk: none recorded

### OPS-12 - Expansion batch ops check script

- What: Add scripts/ops_check.py printing the s12 per-batch numbers as aggregate counts only. It covers failed logins/saves (from OPS-2 log event names), pending reviews, claims past review_due_date, last backup file date, and failed jobs and feedback per 100 users (when those tables exist). It is read-only and run by the owner on the VM before each 10/25/50/100 batch.
- Acceptance: Output contains counts only, no ids or emails. The script opens a read-only transaction. It tolerates missing jobs/feedback tables. A sample output and a go/pause note are recorded in STATUS.md before the first expansion batch.
- Step: 16 | Wave: 1 | Needed by: expand-100
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.5
- Depends on: OPS-2
- Touches: scripts/ops_check.py, tests/unit/test_ops_check.py, docs/RUNBOOK.md
- Reviewers: none
- Risk: none recorded

### OPS-13 - WhatsApp opt-in deadline reminder template (optional, recommend defer)

- What: Would need a reminders table, guardian-aware opt-in, a Meta-approved deadline template and a job handler. Requires a WhatsApp Business account, template approval and a phone-number data flow for minors. Recommended action for Phase 1: write a DECISIONS.md deferral entry and show deadlines in My Plan instead.
- Acceptance: If deferred: a DECISIONS.md entry records the deferral and its reason. If built: opt-in is timestamped, opt-out works, the template carries first name and deadline only, and sends are idempotent per reminder.
- Step: 13 | Wave: 8 | Needed by: deferrable
- Executor: mixed | Model tier: standard | Dev sessions: 2 | Human hours: 4
- Depends on: OPS-5, OPS-14, CONSENT-12
- Touches: docs/DECISIONS.md, db/migrations/00xx_reminders.sql, app/jobs/handlers.py, app/integrations/whatsapp.py, docs/SECURITY.md
- Reviewers: data-security-reviewer, human
- Risk: The only flow that sends a minor's phone number to a vendor outside India. It has high consent cost for low pilot value.

### OPS-14 - Single worker process + handler registry + daily scheduler

- What: Add app/worker.py: connects with the narrow worker role (WORKER_DATABASE_URL, name only in .env.example), polls claim_job, dispatches through a handler registry in app/jobs/, and handles SIGTERM cleanly. It logs via app/core/logging. A daily tick enqueues scheduled kinds with an idempotency key of kind plus date. The first handler is a heartbeat. Add a make worker target.
- Acceptance: Unit tests with a fake connection cover success, a handler exception (fail_job called) and an unknown kind. A test-db run processes one heartbeat job exactly once with two workers started. SIGTERM finishes the current job, then exits 0.
- Step: 13 | Wave: 1 | Needed by: expand-100
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: OPS-5, OPS-2
- Touches: app/worker.py, app/jobs/__init__.py, app/jobs/handlers.py, app/core/config.py, .env.example, Makefile, tests/unit/test_worker.py, tests/db/test_jobs_worker.py
- Reviewers: data-security-reviewer
- Risk: none recorded

### OPS-15 - Owner: restore drill into a separate target

- What: Owner runs backup_dump.sh on the VM, then restores the dump into a Supabase-compatible throwaway target. The target is a second free Supabase project in Mumbai, or the supabase/postgres Docker image on the VM. Owner runs scripts/restore_check.py, records date, duration and issues, then destroys the target. Do this while only synthetic data exists.
- Acceptance: The restore completes into a non-production target. Table counts match the source. The RLS probe passes. The result is recorded in docs/RUNBOOK.md and STATUS.md. The target is deleted. The dump never left the VM unencrypted.
- Step: 13 | Wave: 5 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 2
- Depends on: OPS-9
- Touches: docs/RUNBOOK.md, STATUS.md
- Reviewers: human
- Risk: none recorded

### OPS-16 - Run the 25-session load test on staging and record results

- What: Pre-create 25 synthetic accounts on staging. Run make load off-peak from outside the VM for 5 minutes with AI disabled. Record p95, error rate, Supabase connection count and VM CPU/memory, since the VM is shared with other apps. Stop immediately if the neighbouring services degrade.
- Acceptance: 25 concurrent sessions run for 5 minutes with under 1% errors and p95 under 2s. Zero AI provider calls. Results and date are in STATUS.md. Synthetic accounts are removed afterwards.
- Step: 13 | Wave: 5 | Needed by: ten-user-trial
- Executor: mixed | Model tier: cheap | Dev sessions: 1 | Human hours: 0.5
- Depends on: OPS-10, DEPLOY-7
- Touches: STATUS.md
- Reviewers: none
- Risk: none recorded

### Merged into other tasks

- OPS-3 -> DEPLOY-5
- OPS-17 -> DEPLOY-12

## Staging, production, Docker, CI/CD, public domain

Area: `deploy-staging-prod`

Audit verified as substantially correct: nothing of Steps 5/14 exists beyond a CI skeleton, /healthz, APP_ENV and the migration runner. No Dockerfile, compose, deploy/ dir, smoke script, kill switch, RELEASE_CHECKLIST or RUNBOOK; one Supabase project serves dev, tests and the VM. Main corrections: the Supabase free-project limit is already consumed (unused Singapore project + Mumbai project), so a free production project needs the Singapore one paused/deleted; sign-up kill switch must land BEFORE staging is opened (dependency was missing); an infeasible CI "PROD secret name" guard replaced by a test-suite production guard; app hardening split out of the compose task; OPERATIONS.md renamed to the build pack's docs/RUNBOOK.md; branch-protection owner task added.

### Already done

- CI skeleton: ruff, mypy, unit tests, tests/db (skips cleanly without secrets); no deploy job, no production secrets referenced; e2e step commented out - F:\the competetion project\.github\workflows\ci.yml (verified; single job lint-typecheck-test, e2e commented at end of file; header comment is stale - says test-db stays commented out but it is enabled)
- make targets dev/css/lint/typecheck/test-unit/test-e2e/test-db exist; build is an echo stub - F:\the competetion project\Makefile (verified; note make dev binds 0.0.0.0:8000, VM uses 8010)
- Liveness endpoint GET /healthz (app_env, db_configured, ai_configured); no DB ping, no /readyz - F:\the competetion project\app\api\health.py; tests\unit\test_health.py exists
- APP_ENV switch: /docs off only in production; reviewer cookie secure only in production. APP_ENV is an unvalidated str (typo such as 'prod' silently behaves as development) - F:\the competetion project\app\main.py line 31; app\web\reviewer_pages.py line 188; app\core\config.py line 29
- Idempotent migration runner with --dry-run and _schema_migrations table, using ops-only DATABASE_URL (read from process env or .env, so it already works with a VM env file without code change) - F:\the competetion project\scripts\apply_migrations.py lines 40-95; db\migrations\0001..0003
- Playwright e2e harness with 6 tests (explore, compare, requirements, timeline, reviewer sign-in, queue) against a real uvicorn subprocess; reuses tests/db fixtures and service-role key; skips without a Supabase project - F:\the competetion project\tests\e2e\conftest.py, tests\e2e\test_smoke.py; commit 2db356e
- Env var names documented; .env git-ignored - F:\the competetion project\.env.example; .gitignore lines 15-17
- Compiled Tailwind CSS is committed, so a Docker image needs no Node stage - git ls-files app/static -> app/static/css/app.css
- Deployment flow and data-flow map written as intent only - F:\the competetion project\docs\ARCHITECTURE.md lines 19, 58-65; docs\SECURITY.md line 79 ('VPS, Mumbai (once provisioned)'); build pack line 141 names Hostinger
- App running on Oracle VM moulding-app-a1 as eduvation.service, localhost:8010, co-tenant with hisab/lekha/attendance-app (STATUS only; no unit file, nginx config or deploy script in repo; region/shape/Docker unrecorded) - F:\the competetion project\STATUS.md Infrastructure table (line 334); docs\DECISIONS.md lines 444-445, 519-520

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No separate staging and production Supabase projects: one Mumbai project serves dev, tests (throwaway users + synthetic rows via service-role key) and the VM deployment. Breaches 'no synthetic records in production; no real data in staging' the moment a real user arrives | Build pack s4 Database row, s7 Deployment, s9 Step 5, s12 Built means | launch-blocker |
| Supabase free-project quota is already used up: the owner has the unused Singapore 'project education' plus the Mumbai project (DECISIONS 2026-09-19). A free production project cannot be created until the Singapore project is paused/deleted or a paid plan is taken | docs/DECISIONS.md 2026-09-19 Supabase entry; build pack s11 budget | launch-blocker |
| Service-role key and DATABASE_URL for the only project sit in the dev workspace .env used by dev agents | Build pack s7 Deployment 'No production credential in the everyday Claude Code environment', s8 row 'Development agents' | launch-blocker |
| Nothing stops the test suite (which creates/deletes users and rows with the service-role key) from being pointed at a production project by mistake | Build pack s7 Deployment; CLAUDE.md non-negotiables (synthetic never published, no student data to dev agents) | launch-blocker |
| No Dockerfile, .dockerignore, compose file or deploy/ directory; make build is a stub; image never built | Build pack s4 Hosting and CI, s10 make build; CLAUDE.md verified commands | phase1-required |
| Dependencies are version ranges only; no constraints/lock file | Build pack s12 'reproducible repository with pinned dependencies' | phase1-required |
| No staging instance behind a gate at its own hostname for usability round 1 | Build pack s9 Step 5 and inserted usability round 1, s10 | phase1-required |
| No sign-up off switch; opening staging (even behind basic auth) exposes ungated POST /auth/sign-up to every participant given the password | CLAUDE.md non-negotiable on minor accounts; DECISIONS 2026-09-19 security review finding 1 | launch-blocker |
| No nginx site, TLS, OCI ingress, public hostname; Supabase Auth site URL/redirects not allow-listed per hostname | Build pack s10; STATUS 'Needs your input' item 2 | launch-blocker |
| No protected release authority (neither GitHub protected environment nor owner-run script), no rollback procedure, no release log; no branch protection on main recorded | Build pack s4, s9 Step 14, s12 'protected release authority' | launch-blocker |
| No post-deploy smoke script; /healthz has no DB reachability check | Build pack Step 5 'health checks', Step 14 'smoke checks' | phase1-required |
| No pause procedure or application kill switch (maintenance mode) implemented or documented | Build pack Step 14, s7 Spend controls, s12 Expansion checks | launch-blocker |
| docs/RELEASE_CHECKLIST.md and docs/RUNBOOK.md (both named in build pack s7 'Memory in files') do not exist | Build pack s7, s10 Release review, Step 13 | phase1-required |
| Hosting discrepancy: build pack says Hostinger VPS Mumbai, SECURITY.md says 'VPS, Mumbai (once provisioned)', ARCHITECTURE.md says hosting not provisioned; actual host is an Oracle VM, region/shape/arch/Docker unrecorded, shared with three apps. Data-flow map cannot be accepted until corrected | Build pack s8 row 'Application and worker'; DECISIONS lines 444, 519 | launch-blocker |
| Behind-proxy/config hardening missing: cookie secure only when APP_ENV==production (HTTPS staging gets a non-secure cookie); APP_ENV is a free string; no trusted-host/proxy-header handling; APP_SECRET_KEY has an insecure default and no fail-closed startup check outside development | docs/SECURITY.md access model; app/web/reviewer_pages.py:188; app/core/config.py:29-30 | phase1-required |
| CI does not run e2e or build the image; unknown whether SUPABASE_* repo secrets are set; ci.yml header comment is stale | Build pack s7 Deployment, s10 CI | phase1-required |
| GitHub Actions protected environment with deploy key | Build pack s4 (explicitly allows owner-run script instead) | defer |

### Owner decisions

- **Which Supabase project is staging and which is production** - blocks: DEPLOY-2, DEPLOY-8, DEPLOY-11 - recommended default: Existing Mumbai project becomes STAGING permanently (it holds test users and synthetic rows, its keys live in the dev workspace). Create a brand-new production project only at the real-users gate. No rotation and no work needed for the staging demo.
- **How to get a slot for the production project (free quota already used by the unused Singapore project plus the Mumbai one)** - blocks: DEPLOY-11 - recommended default: Pause or delete the unused Singapore 'project education' (DECISIONS says it was never used; owner re-confirms it is empty first) and create production on Free for the ten-user trial with a restore-tested nightly dump; move production to Pro (about USD 25/month) before Step 16.
- **Docker containers versus keeping the existing systemd unit** - blocks: DEPLOY-3, DEPLOY-4, DEPLOY-6 - recommended default: Docker, one image, two-service compose file, built on the VM (no registry, no ARM cross-build). Matches the pinned stack and make build. If the VM has under about 1 GB free RAM or Docker cannot be installed beside the co-tenant apps, fall back to two systemd units using the same env-file contract and keep the Dockerfile for CI only.
- **Release authority: GitHub protected environment or owner-run script** - blocks: DEPLOY-6, DEPLOY-13 - recommended default: Owner-run scripts/deploy.sh on the VM (explicitly allowed by the build pack). Free, no production key leaves the VM. Defer DEPLOY-14.
- **Confirm Oracle VM region and accept it in the data-flow map (build pack assumed Hostinger Mumbai)** - blocks: Data-flow map acceptance, hence DEPLOY-13 - recommended default: If the VM is in an Indian OCI region (Mumbai or Hyderabad), record it and proceed. If not, move the app to an Indian-region VM before real users; staging demo with no personal data may proceed meanwhile.
- **Staging and pilot hostnames** - blocks: DEPLOY-7, DEPLOY-13 - recommended default: Subdomains of a domain the owner already controls (staging.<domain> now, pilot hostname later). Staging may go live once DEPLOY-9 and DEPLOY-15 are deployed (basic auth plus sign-up off); the pilot hostname waits for the consent gate.
- **May a dev agent hold SSH access to the VM** - blocks: DEPLOY-7, DEPLOY-13 - recommended default: Allowed for staging bring-up only, under a user that cannot read other apps' files, while no production env file exists. After /etc/eduvation/prod.env exists, production deploys are owner-typed only.

### Tasks

### DEPLOY-1 - Owner: record Oracle VM facts and hosting decisions

- What: Owner reports (no secrets): OCI region, shape/CPU arch, free RAM/disk, whether Docker and nginx are installed and how the co-tenant apps are served, GitHub repo visibility and plan, a staging subdomain, and how many free Supabase projects are in use. Accept or override the ownerDecisions defaults.
- Acceptance: All answers supplied in writing; region named explicitly; Docker-vs-systemd, staging/prod project designation and fate of the unused Singapore project decided.
- Step: 5 | Wave: 0 | Needed by: staging-demo
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 0.75
- Depends on: none
- Touches: none
- Reviewers: none
- Risk: none recorded

### DEPLOY-2 - Record environment contract and fix hosting docs

- What: DECISIONS.md entry: existing Mumbai project is STAGING; production project created later; Oracle VM (named region) replaces Hostinger; owner-run deploy script is release authority. Update SECURITY.md data-flow row (line 79), ARCHITECTURE.md hosting row and deployment flow, .env.example (APP_ENV semantics; SIGNUPS_ENABLED, MAINTENANCE_MODE, ALLOWED_HOSTS names). Freeze ports, hostnames placeholders and env-file paths.
- Acceptance: Docs name real host and region; contract written (staging 8011, prod 8010, /etc/eduvation/{staging,prod}.env plus separate migrate env holding DATABASE_URL); no secret values; build pack discrepancy noted.
- Step: 5 | Wave: 1 | Needed by: staging-demo
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.25
- Depends on: DEPLOY-1
- Touches: docs/DECISIONS.md, docs/SECURITY.md, docs/ARCHITECTURE.md, .env.example, STATUS.md
- Reviewers: human
- Risk: none recorded

### DEPLOY-3 - Dockerfile, pinned constraints, make build, CI image build

- What: python:3.11-slim Dockerfile (non-root, committed app/static/css/app.css so no Node stage, uvicorn --proxy-headers, HEALTHCHECK on /healthz), .dockerignore excluding .env, .claude/, node_modules, tests, docs; generated constraints.txt used by image and CI install; real make build; CI step building the image (amd64) without pushing; fix stale ci.yml header comment.
- Acceptance: make build produces an image; container answers /healthz with no env set; image contains no .env or .claude; CI build green; constraints.txt committed and used. arm64 build is proven later on the VM (DEPLOY-7).
- Step: 5 | Wave: 1 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: SEC-7
- Touches: Dockerfile, .dockerignore, constraints.txt, Makefile, .github/workflows/ci.yml
- Reviewers: data-security-reviewer
- Risk: none recorded

### DEPLOY-4 - Compose file and nginx site templates

- What: deploy/docker-compose.yml with staging and prod services bound to 127.0.0.1 only, env_file paths outside the repo, restart policy, memory limit. deploy/nginx templates: staging (auth_basic, X-Robots-Tag noindex, TLS) and prod (security headers, HSTS), placeholders for hostnames. No app code in this task.
- Acceptance: docker compose config validates; templates contain no secrets or real hostnames; no port binds 0.0.0.0; staging template returns 401 without credentials when rendered locally.
- Step: 5 | Wave: 2 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: DEPLOY-2, DEPLOY-3
- Touches: deploy/docker-compose.yml, deploy/nginx/staging.conf.template, deploy/nginx/prod.conf.template, deploy/README.md
- Reviewers: data-security-reviewer
- Risk: none recorded

### DEPLOY-5 - Readiness endpoint and read-only smoke script

- What: Add GET /readyz doing one cheap published-table read via the guest client (no PII, 503 on failure). scripts/smoke.py takes a base URL and optional basic-auth from env: /healthz, /readyz, /explore renders, /careers JSON, /plans without token 401, /reviewer/queue redirects to sign-in, /docs 404 in production, expected APP_ENV. Never writes.
- Acceptance: Unit tests for /readyz ok and failure paths; smoke exits non-zero on any failed check, passes against local make dev, issues only GET requests.
- Step: 5 | Wave: 0 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: none
- Touches: app/api/health.py, scripts/smoke.py, tests/unit/test_health.py, Makefile
- Reviewers: none
- Risk: none recorded

### DEPLOY-6 - Owner-run deploy and rollback script

- What: scripts/deploy.sh <staging|prod> <sha>, run ON the VM: refuse dirty tree or SHA not on main, checkout exact SHA, build image tagged with SHA, show apply_migrations --dry-run and require typed confirmation, apply migrations with DATABASE_URL from the separate migrate env file (apply_migrations.py already reads process env; no change needed), restart one service, run smoke.py, roll back to previous tag on smoke failure. Prod requires retyping the SHA. Appends to a release log.
- Acceptance: shellcheck clean; --dry-run prints every step without acting; secrets read only from VM env files; app container never receives DATABASE_URL. Live rollback is exercised in DEPLOY-7.
- Step: 14 | Wave: 3 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: DEPLOY-3, DEPLOY-4, DEPLOY-5
- Touches: scripts/deploy.sh, deploy/README.md
- Reviewers: data-security-reviewer
- Risk: none recorded

### DEPLOY-7 - Bring up private staging on the VM

- What: Owner (agent may assist with staging-only access): DNS record, open 80/443 in OCI security list and host firewall, certbot, htpasswd, install staging nginx site without disturbing co-tenant sites, create staging env files (mode 600, SIGNUPS_ENABLED=false, no AI key), run deploy.sh staging (proves arm64 build), exercise one rollback, add staging URL to Supabase Auth allow-list, retire the old eduvation.service.
- Acceptance: Staging returns 401 without basic auth; smoke passes with it; guest journey Explore-Compare-Requirements-Timeline works on a phone; sign-up returns closed; rollback demonstrated; other VM apps unaffected.
- Step: 5 | Wave: 4 | Needed by: staging-demo
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 2
- Depends on: DEPLOY-6, DEPLOY-9, DEPLOY-15
- Touches: VM only: /etc/nginx/sites-available/, /etc/eduvation/staging.env, /etc/eduvation/staging.migrate.env; STATUS.md
- Reviewers: ux-qa-reviewer, human
- Risk: none recorded

### DEPLOY-9 - Pause and sign-up kill-switch flags

- What: Env-driven MAINTENANCE_MODE (every route except /healthz returns a styled 503 paused page, no DB access) and SIGNUPS_ENABLED (default false outside development; POST /auth/sign-up returns a clear closed message before any Supabase call). Flipped by editing the VM env file and restarting one container.
- Acceptance: Unit tests: maintenance on gives 503 on student, API and reviewer routes and 200 on /healthz; signups off blocks sign-up with no Supabase call; defaults fail-closed in staging and production.
- Step: 14 | Wave: 3 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: DEPLOY-2, DEPLOY-15, CONSENT-1
- Touches: app/core/config.py, app/main.py, app/api/auth.py, app/web/templates/paused.html, tests/unit/test_kill_switches.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: none recorded

### DEPLOY-10 - RELEASE_CHECKLIST.md and RUNBOOK deploy sections

- What: docs/RELEASE_CHECKLIST.md: exact-SHA approval, cross-user matrix run, migration plan, secrets check, restore evidence, AI-off check, mobile journey, smoke, rollback ready. Add deploy, rollback, pause, kill-switch, key and basic-auth rotation, Supabase pause/restore sections to docs/RUNBOOK.md (build pack's name; file shared with the ops area).
- Acceptance: Checklist exists; every line names how it is verified and references only real scripts and flags; RUNBOOK sections present; owner sign-off recorded in DECISIONS.md.
- Step: 14 | Wave: 4 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.5
- Depends on: DEPLOY-6, DEPLOY-9, OPS-7
- Touches: docs/RELEASE_CHECKLIST.md, docs/RUNBOOK.md, docs/DECISIONS.md
- Reviewers: human
- Risk: none recorded

### DEPLOY-11 - Owner: create clean production Supabase project and VM prod env

- What: Owner frees a project slot (pause/delete unused Singapore project) or takes Pro, creates a second Mumbai project, runs apply_migrations from the VM only, creates reviewer accounts, writes prod env files (mode 600) on the VM, sets Auth site URL/redirects to the prod hostname only, confirms the dev .env and GitHub hold staging values only.
- Acceptance: Fresh project reaches 0001..latest with zero manual SQL; no prod key on the dev machine or in GitHub; production has no synthetic or test rows; owner confirmation in DECISIONS.md.
- Step: 14 | Wave: 4 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 1.5
- Depends on: DEPLOY-6, QA-2
- Touches: VM only: /etc/eduvation/prod.env, /etc/eduvation/prod.migrate.env; docs/DECISIONS.md
- Reviewers: human
- Risk: none recorded

### DEPLOY-12 - Release review of the candidate commit

- What: Read-only review of the exact candidate SHA against RELEASE_CHECKLIST.md using the build pack release-review prompt: cross-user access, source integrity, secrets, migrations, recovery, AI failure, mobile journeys. Owner triages; a person signs off child-data and production-security items.
- Acceptance: Findings with reproducible steps and an explicit untested-areas list; zero open critical/high; owner sign-off line with SHA in DECISIONS.md.
- Step: 14 | Wave: 12 | Needed by: real-users-gate
- Executor: mixed | Model tier: strongest | Dev sessions: 1 | Human hours: 1.5
- Depends on: OPS-7, OPS-8, OPS-15, DEPLOY-10, SEC-13, CONSENT-11, PUB-14, DATA-11, QA-16, QA-10, RULES-12, AUTH-18, SCOPE-8, CONTENT-8, A11Y-3, A11Y-5, UI-13
- Touches: docs/DECISIONS.md, STATUS.md
- Reviewers: data-security-reviewer, human
- Risk: none recorded

### DEPLOY-13 - Production deploy, public hostname, pause drill

- What: Owner points the pilot hostname at the VM, installs the prod nginx site and certificate, runs deploy.sh prod with the approved SHA, runs smoke.py, then one pause drill (MAINTENANCE_MODE on, verify 503, off) and one rollback to the prior tag. SIGNUPS_ENABLED stays false until the consent sign-off is recorded.
- Acceptance: Prod smoke green over HTTPS; /docs 404; pause and rollback demonstrated and timed; release log shows approved SHA; sign-up closed unless consent sign-off exists.
- Step: 14 | Wave: 13 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 2
- Depends on: DEPLOY-11, DEPLOY-12, DEPLOY-17, OPS-4, OPS-9
- Touches: VM only: nginx prod site, release log; STATUS.md
- Reviewers: human
- Risk: none recorded

### DEPLOY-14 - GitHub Actions protected-environment deploy

- What: Optional replacement of the owner-run trigger by a workflow_dispatch job in a protected production environment with an SSH deploy key and required approver. Puts a production credential with a third party and may need a paid GitHub plan on a private repo; no pilot gate requires it.
- Acceptance: Only if adopted: deploy job cannot start without owner approval; key restricted to running deploy.sh via forced command.
- Step: 14 | Wave: 14 | Needed by: deferrable
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.5
- Depends on: DEPLOY-13
- Touches: .github/workflows/deploy.yml
- Reviewers: data-security-reviewer
- Risk: none recorded

### DEPLOY-15 - Behind-proxy and config hardening in the app

- What: Make APP_ENV a validated Literal; reviewer cookie secure whenever APP_ENV != development; TrustedHostMiddleware from ALLOWED_HOSTS env; startup fails outside development if APP_SECRET_KEY is the insecure default or Supabase vars are missing; /docs stays off in production. Split out of the original DEPLOY-4.
- Acceptance: Unit tests: staging cookie is secure; unknown host rejected; invalid APP_ENV and default secret in staging/production raise at startup; development behaviour and all existing unit tests unchanged.
- Step: 5 | Wave: 2 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: DEPLOY-2, SEC-1
- Touches: app/core/config.py, app/main.py, app/web/reviewer_pages.py, tests/unit/test_config_hardening.py
- Reviewers: data-security-reviewer
- Risk: none recorded

### DEPLOY-17 - Owner: protect main and restrict repo/VM access

- What: Owner enables branch protection on main (required CI check, no force-push) if the GitHub plan allows it for this repo's visibility, reviews collaborator list (dev machine account maheshjin-bot has write access), and confirms who holds SSH access to the VM. If branch protection is unavailable on a free private repo, record that deploy.sh's exact-SHA confirmation is the control.
- Acceptance: DECISIONS.md entry listing protection state, collaborators and VM SSH holders; no unexpected account has write or SSH access.
- Step: 14 | Wave: 0 | Needed by: real-users-gate
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 0.5
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: none recorded

### Merged into other tasks

- DEPLOY-8 -> QA-5
- DEPLOY-16 -> QA-2

## Test and QA infrastructure

Area: `test-qa-infra`

Unit, DB (10 files) and a 6-test Playwright smoke suite exist and are sound. But every DB and e2e test seeds into whatever Supabase project the root .env names, including fake "official, published" claims, and that project's auth rate limit is saturated. CI never runs DB or e2e tests: ci.yml maps no secrets into env, so tests/db always skips. A fresh git worktree has no .env, so both suites skip and look green. There are no viewport, axe, calibration, export or storage tests. The fix is a local Supabase CLI stack, a target guard, a strict no-skip mode, and run-tagged fixtures. Totals: 16 tasks, about 18 dev sessions, about 6 human hours.

### Already done

- Make targets lint, typecheck, test-unit, test-db and test-e2e are wired. test-e2e runs pytest tests/e2e. `make install` does not install Playwright browsers, and `make build` is an echo stub. - F:\the competetion project\Makefile lines 6-32
- Playwright-for-Python smoke suite: 6 tests in 3 classes (Explore, Explore to Compare, Requirements, Timeline, reviewer sign-in, reviewer queue). It runs a real uvicorn subprocess on an ephemeral port, asserts on rendered content, and four of the six tests assert no page errors. - F:\the competetion project\tests\e2e\conftest.py (live_server, _free_port); F:\the competetion project\tests\e2e\test_smoke.py; commit 2db356e
- pytest-playwright is pinned in dev extras. Default testpaths is tests/unit, so bare pytest never touches the DB. pytest-xdist is NOT a dependency. - F:\the competetion project\pyproject.toml lines 19-25, 46-48
- RLS matrix in test_rls.py: 9 tests over careers, claims (guest draft read) and student_profiles, for guest, student A, student B and reviewer, covering read, insert and update. Assertions never run as the service role. - F:\the competetion project\tests\db\test_rls.py
- Cross-user cases for saved_plans exist at HTTP level: B cannot see, update or delete A's plan; reviewer has no special access; guest cannot save. Verified by the test names in the file. The previous audit had not opened it. - F:\the competetion project\tests\db\test_api_plans.py lines 56, 135, 217, 244, 278
- Shared role fixtures exist (guest_client, student_a, student_b, reviewer, second_reviewer, synthetic_source). They are function-scoped, use uuid-named users and tear down after each test. The suite skips cleanly when unconfigured or when a migration is missing. - F:\the competetion project\tests\db\conftest.py
- Ten live DB/HTTP test files exist (auth, claims, maker-checker, eligibility, explore/compare, web pages, reviewer console, client isolation, plans, rls). STATUS.md reports 239 passing and zero skipped locally. I did not run them. - Glob tests/db/*.py; F:\the competetion project\STATUS.md line 126
- CI runs ruff, mypy, unit tests and `pytest tests/db`. The workflow has NO env/secrets mapping, so tests/db always skips in CI. The e2e step is commented out and there is no browser install. - F:\the competetion project\.github\workflows\ci.yml lines 38-48 (no env block anywhere)
- Labelled synthetic model fixtures exist. - F:\the competetion project\tests\fixtures\synthetic_data.py
- Two read-and-test-only reviewer agents are defined. Only data-security-reviewer.md has a Calibration section, and it states the requirement only. ux-qa-reviewer.md has none. No fixtures back either. - F:\the competetion project\.claude\agents\data-security-reviewer.md lines 36-40; Grep 'Calibrat' in .claude/agents returns that one hit
- A psycopg migration runner exists and can be reused against a local or staging DATABASE_URL. - F:\the competetion project\scripts\apply_migrations.py; db/migrations/0001-0003

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| Tests seed and delete rows in whatever project the root .env names. STATUS.md implies this is the single live project the VM app also uses; I did not read .env. Seeds include source_type=official plus status=published claims (tests/e2e/test_smoke.py eligibility_pathway). A crashed run leaves a fake verified fact publicly readable. Nothing blocks a test run against production. | Build pack s7 Deployment ('No synthetic records in production; no real data in staging'); CLAUDE.md synthetic-fixture non-negotiable | launch-blocker |
| No local Supabase test target exists: no supabase/ directory, no compose file, no Dockerfile. The live auth rate limit is saturated (STATUS.md lines 142-143), and three sign-up tests treat a 429 as acceptable (tests/db/test_api_auth.py lines 124, 157, 286). | Build pack s4 Tests row (line 59); s10 line 188; Step 4 'rebuild from scratch' | launch-blocker |
| Silent skip in worktrees and CI. .env is gitignored, so a fresh git worktree has none and both conftest hooks skip every DB/e2e test with exit code 0. An implementer agent can report green having run nothing. CI has the same problem because ci.yml has no env mapping. There is no strict mode that turns a skip into a failure. | Build pack s7 Hooks ('no success via ... skipped suites'); CLAUDE.md 'Never claim a test passed without having run it' | launch-blocker |
| No test-isolation contract for parallel implementers: no run-id tagging of seeded rows, no orphan sweeper, no pytest-xdist, no per-worktree env file, and no rule on who runs the full suite. The e2e reviewer fixture uses @example.com, a real domain, rather than example.invalid. | Build pack s7 Agents and Token rules; DECISIONS 2026-09-21 (parallel agents allowed; lead verifies and merges) | phase1-required |
| CI does not run e2e and has no Playwright browser install. DB tests never execute in CI because no env is mapped. `make install` lacks `playwright install chromium`. | Build pack Step 2; s7 Hooks | phase1-required |
| The cross-user matrix is not systematic. student_profiles (read, update) and saved_plans (read, update, delete, reviewer) are covered. There is no declarative matrix for sources, pathways, reviewers, claims write cells or student_profiles delete. No guard fails when a new table ships without RLS or a matrix row. Export and storage cells do not exist because those features are not built. | Build pack s7 Quality gates Access; s12 'Student A cannot read or change Student B's records'; Built-means 'account isolation tested beyond the UI' | phase1-required |
| No automated 360 px or desktop viewport checks. There are no 'viewport' hits in tests/. | Build pack s7 Quality gates UI; Built-means 'mobile and accessibility checks done' | phase1-required |
| No automated accessibility checks: no axe, no keyboard order, no 200% zoom. | Build pack s4 Tests row; Step 12; s7 Quality gates UI | phase1-required |
| Reviewer calibration fixtures do not exist (cross-user flaw, missing source, stale deadline, misleading status). ux-qa-reviewer.md has no calibration section at all. Step 3's 'calibrated' is unproven, yet the parallel plan leans on these reviewers for quality. | Build pack s7 Agents; Step 3 | phase1-required |
| No browser-level signed-in journey tests: sign up, save a plan, find the next action, log out on a shared device, failed save. The student signed-in UI does not exist. The only templates are explore, compare, requirements, timeline_calculator, reviewer_queue and reviewer_sign_in. | Build pack s12 Step 15 tester tasks; s7 Quality gates Privacy | phase1-required |
| No difficult-state or Hindi text-expansion e2e coverage. The app has no locale handling beyond base.html. | Build pack Step 12; docs/UI.md 'Difficult states' (line 60) | phase1-required |
| No seedless, read-only smoke suite that takes a base URL for use against staging and after a production deploy. | Build pack s7 Deployment ('smoke tests'); Step 5; Step 14 | phase1-required |
| No release-candidate run of the DB suite against the cloud staging project. Drift between local GoTrue/PostgREST and the cloud versions would go undetected. | Build pack s7 Deployment ('preview against staging only'); Quality gates Operations ('fresh migration, staging deploy') | phase1-required |
| Memory files are stale on e2e. STATUS.md lines 326 and 387 say Playwright e2e isn't wired. The ci.yml header says test-db and test-e2e are commented out, but test-db is not. There is no docs/TESTING.md. | Build pack s7 Memory in files | phase1-nice |
| No human screen-reader spot test is on record. | Build pack s7 Quality gates UI | phase1-nice |
| No 25-session load test without live model calls. | Build pack Step 13; s7 Quality gates Operations (in no s12 gate) | defer |
| Cost per accepted slice, failed-fix cycles and escaped defects are not tracked. | Build pack s7 Token and time rules | defer |

### Owner decisions

- **Where destructive tests run: a local Supabase CLI stack in Docker, a second cloud project, or the current live project.** - blocks: QA-2, and with it all safe parallel implementer work and CI. - recommended default: Use the local Supabase CLI stack on the dev machine and in CI. It is free, has no rate limits, and matches the build pack s4 and s10 wording 'local Supabase'. It is a localhost CLI, not the Supabase MCP or management API that the owner ruled out (DECISIONS 2026-09-19). If Docker is impossible, use a second free-tier cloud project for tests only. Never use the live project.
- **Is the current Supabase project production, or is it the dev and staging project?** - blocks: QA-12, QA-16, and the hosting area's staging-versus-production split. - recommended default: Treat the current project as dev and staging, since it is already polluted by fixtures. Create a fresh production project at Step 14 whose keys never reach a dev machine. Still run the QA-12 sweep.
- **Concurrency cap for implementer agents. The ceiling itself was already lifted on 2026-09-21; only the number and the precondition are open.** - blocks: The design of the agent team. - recommended default: At most 2 implementers until QA-2 and QA-3 land, working only on tasks that need unit tests alone. After that, up to 4-5 implementers in separate worktrees on disjoint files against one shared local stack. One agent at a time owns migrations. The lead runs the full suite before every merge.
- **Who performs the human accessibility spot test and the calibration sign-off.** - blocks: QA-14 and the sign-off for QA-9. - recommended default: The owner does both, for about 2.5 hours. No paid QA contractor is needed.
- **The axe failure threshold.** - blocks: QA-8. - recommended default: Fail on serious and critical violations. Log moderate and minor ones. Every waiver carries an owner and an expiry, per s7.

### Tasks

### QA-1 - Owner: approve test backend; install Docker + Supabase CLI

- What: Owner installs or confirms Docker Desktop (WSL2) and the Supabase CLI on the Windows dev machine. Owner approves the local stack as the only target for destructive tests. Owner confirms whether the project named in the current .env is the one the Oracle VM app uses, and whether the repo is public or private.
- Acceptance: `supabase start` succeeds on the dev machine. A docs/DECISIONS.md entry records the test target, the Docker host, the repo visibility, and whether the VM and the tests share a project.
- Step: 4 | Wave: 0 | Needed by: staging-demo
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 1
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: none
- Risk: If Docker is impossible, fall back to a second free cloud Supabase project for tests only. Rate limits then return, and safe parallelism is capped at about 2 agents.

### QA-2 - Local Supabase stack, target guard and strict no-skip mode

- What: Add supabase/config.toml: auth rate limits raised, email confirmation off, studio, realtime, functions and imgproxy disabled. Add make test-db-up, test-db-down and test-db-reset, which apply db/migrations via scripts/apply_migrations.py to the local DB and reload the PostgREST schema. Add .env.test.example. Make targets export .env.test vars. Conftest guard: abort unless SUPABASE_URL is localhost or in the BCION_TEST_TARGET allowlist. BCION_REQUIRE_LIVE=1 turns skips into failures.
- Acceptance: A clean checkout passes fully on localhost after `make test-db-up && make test-db`. A live-project URL aborts before any write. With BCION_REQUIRE_LIVE=1 and no env, the suite FAILS rather than skips. Sign-up tests no longer accept 429 on localhost.
- Step: 4 | Wave: 1 | Needed by: staging-demo
- Executor: dev-agent | Model tier: strongest | Dev sessions: 2 | Human hours: 0.5
- Depends on: QA-1
- Touches: supabase/config.toml, Makefile, tests/db/conftest.py, tests/e2e/conftest.py, tests/db/test_api_auth.py, .env.test.example, db/migrations/README.md, .gitignore
- Reviewers: data-security-reviewer
- Risk: PostgREST caches the schema, so NOTIFY pgrst 'reload schema' is needed after psycopg-applied migrations. Local GoTrue differs from cloud; QA-16 mitigates that.

### QA-3 - Run-tagged fixtures, sweeper and xdist for concurrent runs

- What: Keep users function-scoped, because student_profiles uses the user id as its primary key and the local stack has no rate limit. Add a RUN_ID helper. Prefix every seeded name and email with it. Move e2e emails to example.invalid. Add a session-finish sweeper that deletes this run's rows and users. Audit tests/db/*.py for assertions on global table state and scope them to own ids. Add pytest-xdist to dev extras.
- Acceptance: Two simultaneous `make test-db` runs against one local stack both pass. `pytest -n 4 tests/db` passes. After a run, including an interrupted one that is rerun, zero rows or users carry that RUN_ID.
- Step: 4 | Wave: 2 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: QA-2
- Touches: tests/db/conftest.py, tests/e2e/conftest.py, tests/e2e/test_smoke.py, tests/db/test_*.py (seed names only), pyproject.toml
- Reviewers: data-security-reviewer
- Risk: Queue and listing tests may assert on counts. The reviewer-queue test must filter by its own claim id, as test_smoke.py already does.

### QA-4 - Parallel-agent testing contract (docs/TESTING.md) and stale-memory fix

- What: Write the rules. Implementers run targeted tests against the shared local stack with BCION_REQUIRE_LIVE=1. Each worktree copies .env.test. The lead runs the full suite before merge. Migrations go through one owner agent, followed by `make test-db-reset`. A migration prototype uses a second stack on alternate ports. Fix the stale e2e statements in STATUS.md, the CLAUDE.md command notes and the ci.yml header.
- Acceptance: docs/TESTING.md is under 80 lines. CLAUDE.md commands match the Makefile. STATUS.md no longer says e2e is unwired. A fresh agent in a new worktree can run a targeted DB test by following the doc alone.
- Step: cross | Wave: 3 | Needed by: staging-demo
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.25
- Depends on: QA-3
- Touches: docs/TESTING.md, CLAUDE.md, STATUS.md
- Reviewers: human
- Risk: none recorded

### QA-5 - CI: local stack DB job, e2e job, caching, no-skip

- What: Split ci.yml into three parallel jobs: (1) ruff, mypy and unit; (2) supabase/setup-cli, then test-db-up and tests/db; (3) the same stack plus `playwright install --with-deps chromium` (cached) and tests/e2e. Set BCION_REQUIRE_LIVE=1 in jobs 2 and 3. Use no cloud Supabase secrets. Set concurrency cancel-in-progress. Add `playwright install chromium` to `make install`, and add a `make smoke` target.
- Acceptance: A PR run shows three green jobs. The DB and e2e logs show zero skipped tests. Wall time is under 10 minutes. The workflow references no secrets.
- Step: 2 | Wave: 3 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: DEPLOY-2, DEPLOY-3, QA-2, QA-3, SEC-7
- Touches: .github/workflows/ci.yml, Makefile
- Reviewers: data-security-reviewer
- Risk: The Supabase image pull takes about 2 minutes. If e2e duplicates the stack cost, merge jobs 2 and 3.

### QA-6 - Declarative cross-user access matrix with a table guard

- What: First read the existing tests/db files so nothing is duplicated. Add tests/db/access_matrix.py: a table of role, table, operation and expected result for all 7 tables across read, insert, update and delete. It drives one parametrized test. Add a guard via direct psycopg that fails if any public table lacks RLS or has no matrix rows. Add explicit xfail(strict) placeholders for export and storage cells.
- Acceptance: The matrix covers sources, careers, pathways, claims, reviewers, student_profiles and saved_plans across 4 roles and 4 operations. A table without matrix rows fails the guard. No assertion runs as the service role.
- Step: 4 | Wave: 3 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: strongest | Dev sessions: 2 | Human hours: 0.5
- Depends on: QA-3
- Touches: tests/db/access_matrix.py, tests/db/test_access_matrix.py
- Reviewers: data-security-reviewer, human
- Risk: none recorded

### QA-7 - Mobile and desktop viewport e2e, plus the full guest journey

- What: Parametrize e2e over a 360x740 viewport and a 1280x800 viewport. Add one guest journey: quick start, explore, compare, change a cost assumption, requirements, timeline, open an official source link. On every page, assert no horizontal overflow (scrollWidth is at most clientWidth). Check tap-target size only where docs/UI.md specifies one.
- Acceptance: `make test-e2e` runs the journey at both viewports. The overflow assertion passes on explore, compare, requirements and timeline_calculator. A missing screen fails the test rather than skips it.
- Step: 7 | Wave: 5 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: UI-3, UI-4, UI-5, UI-6, UI-7, QA-3
- Touches: tests/e2e/conftest.py, tests/e2e/test_guest_journey.py
- Reviewers: ux-qa-reviewer
- Risk: If the UI screens are late, land the viewport parametrization and overflow checks over existing pages first, then extend the journey.

### QA-9 - Reviewer calibration fixtures and a calibration run

- What: Create tests/calibration/ with four labelled flaw patches: a cross-user RLS flaw, a claim missing its source, a stale deadline shown as current, and a misleading status label. Add an answer key and a README. Apply each in a throwaway worktree, run the matching reviewer blind, and record hit or miss. Add a Calibration section to ux-qa-reviewer.md. Run this early, because the reviewers gate all parallel work.
- Acceptance: The four patches apply cleanly to main. Each reviewer is run once. Results and any prompt fixes are recorded in docs/DECISIONS.md. tests/ is excluded from the future image via a .dockerignore note.
- Step: 3 | Wave: 4 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: strongest | Dev sessions: 2 | Human hours: 0.5
- Depends on: QA-2, DOCS-4, DOCS-5
- Touches: tests/calibration/, docs/DECISIONS.md, .claude/agents/ux-qa-reviewer.md, .claude/agents/data-security-reviewer.md
- Reviewers: human
- Risk: The patches go stale as the code moves, so re-verify before each release review. Passing calibration never replaces human sign-off for child data.

### QA-10 - Signed-in journey e2e and browser-level cross-user checks

- What: In the browser: sign up through the consent-gated flow with a synthetic adult account, save a plan, find the next action, and log out. After logout, confirm the back button and cache show no plan. Confirm student B cannot open student A's plan URL. Confirm a simulated failed save shows the UI.md state. Turn the export and storage matrix cells from xfail to live.
- Acceptance: Step 15 tester tasks that can be automated pass at 360 px. After logout, plan pages return the sign-in page with Cache-Control: no-store. No export or storage xfail remains.
- Step: 8 | Wave: 11 | Needed by: real-users-gate
- Executor: dev-agent | Model tier: standard | Dev sessions: 2 | Human hours: 0
- Depends on: AUTH-3, AUTH-6, OPS-6, UI-11, AUTH-7, QA-6, QA-7, AUTH-14, AUTH-10, CONSENT-6
- Touches: tests/e2e/test_signed_in_journey.py, tests/db/access_matrix.py
- Reviewers: data-security-reviewer, ux-qa-reviewer
- Risk: none recorded

### QA-12 - Sweep test residue out of the live project

- What: Write scripts/sweep_test_residue.py, with dry-run as the default. It lists rows and users that match the fixture markers: 'E2E', 'RLS test', 'SYNTHETIC', 'TEST FIXTURE', example.invalid, verifier 'e2e-smoke-test-fixture' or 'test-fixture', and the bcion-test- and bcion-e2e- email prefixes (the latter at example.com). The owner reviews the list, runs --apply themselves, then reruns to confirm zero matches.
- Acceptance: The owner has reviewed the dry-run report. After the owner-run apply, a rerun reports zero matches. A DECISIONS entry records that the project is clean and that the guard is active.
- Step: 10 | Wave: 2 | Needed by: real-users-gate
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 0.5
- Depends on: QA-2
- Touches: scripts/sweep_test_residue.py, docs/DECISIONS.md
- Reviewers: data-security-reviewer, human
- Risk: This is a destructive database action. The owner runs the apply, not an agent. Anchor marker matching so it can never match real content.

### QA-16 - Release-candidate DB and e2e run against the staging project

- What: The lead only, serialised, once per release candidate. Add the staging Supabase URL to the BCION_TEST_TARGET allowlist. Run the full tests/db and tests/e2e suites with RUN_ID tagging against the staging project, which holds synthetic data only by policy, to catch local-versus-cloud drift. Confirm the sweeper leaves zero residue. Never run this against production.
- Acceptance: The full suite passes against staging with zero skips, or the failures are filed. Zero RUN_ID residue afterwards. The run is recorded in STATUS.md with the commit hash.
- Step: 13 | Wave: 8 | Needed by: real-users-gate
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: QA-2, QA-3, DATA-11
- Touches: STATUS.md, .env.test.example
- Reviewers: data-security-reviewer
- Risk: Cloud auth rate limits still apply. Run once, not per agent.

### Merged into other tasks

- QA-8 -> A11Y-6
- QA-11 -> DEPLOY-5
- QA-13 -> A11Y-9
- QA-14 -> A11Y-11
- QA-15 -> OPS-10

## Usability rounds, ten-person trial, outcome instrument, DPR measurements, expansion

Area: `trial-measurement`

Verified: nothing in this area is built and only the spec exists. Migrations 0001-0003 have no feedback, audit_events, ai_usage or events table. app/main.py has no middleware. docs/research/ does not exist. I found four missed gaps. Two round-1 criteria (save a next action, change a preference) cannot be tested today because there is no quick-start, guest-save or plan template and no student browser session. No task existed to recruit the roughly 90 expansion users. No task existed for the week-4 post-test. The week-4 post-test lands after Step 16 starts, so the "instrument piloted" gate needs an owner interpretation. Week 1 must start: roles, recruitment, the school letter, the research pack, the instrument, the templates and the editor-hours log.

### Already done

- Usability round composition (5-8 participants including shared-phone user, Hindi-preferring user, parent, teacher) and the six task criteria are specified - F:\the competetion project\docs\UI.md lines 94-102 (confirmed). Build pack s9 line 165 says 'Five people, guest only, on staging'.
- 100-user gate list, Step 15 gates, eight tester tasks, per-batch expansion checks and the 'Built means' list are written as spec - F:\the competetion project\docs\BCION-Lite-Build-Pack.md lines 214-220 (confirmed)
- The s13 measurement table (8 rows) and the five decision-quality items are specified - F:\the competetion project\docs\BCION-Lite-Build-Pack.md lines 222-233 (confirmed); docs/PRODUCT.md line 61 (confirmed)
- Four guest screens exist as server-rendered zero-JS pages: Explore, Compare, Requirements, Timeline calculator. They are reachable on localhost only. This covers only part of what round 1 needs: there is no quick-start, guest-save, my-plan or preferences screen. - F:\the competetion project\app\web\templates\explore.html, compare.html, requirements.html, timeline_calculator.html; STATUS.md lines 34-54 and 334; commits 1adb212 and 2db356e
- A design mockup of all seven screens exists as a fallback stimulus; no person has reviewed it - F:\the competetion project\STATUS.md lines 226-237 (confirmed)
- The missing usability round and the missing 'Report an issue' control are recorded as known gaps - F:\the competetion project\tasks\BCI-006.md lines 134 and 167 (confirmed)

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| No moderator script exists for round 1 (six criteria) or Step 15 (eight tester tasks). There is no scoring sheet and no docs/research/ directory. | Build pack s5; s9 Step 15; s12 Step 15 gates; docs/UI.md Usability rounds | phase1-required |
| No participants are recruited: the shared-phone user, Hindi-preferring user, parent and teacher for round 1, and the ten trial users | Build pack s9 inserted round 1, Step 15 | launch-blocker |
| Nothing recruits the roughly 90 additional users for the 10->25->50->100 batches, and the audit had no task for it. Those batches probably include minors, so this chains to the consent route. | Build pack s9 Step 16; s12 expansion checks | phase1-required |
| No participant information and consent sheet for research sessions. No rule on recordings or notes. No moderator escalation route if a participant discloses distress. | Build pack s2; s9 Step 15 'de-identified feedback'; CLAUDE.md non-negotiables | launch-blocker |
| The five-item pre/post instrument is not drafted in English or Hindi, has no rubric and has no administration rules | Build pack s3 line 41; s12 'outcome instrument piloted on the first ten users'; s13 row 5 | phase1-required |
| There is no task or schedule for the week-4 post-test. A trial in weeks 9-10 puts week 4 at weeks 13-14, after Step 16 starts, so the 'instrument piloted' gate needs an owner interpretation. | Build pack s3 line 41; s12 100-user gate; s9 Steps 15-16 | phase1-required |
| The owner has not approved the Step 15 gate thresholds before testing, and 'intervention' and 'critical failure' are undefined | Build pack s12 'Step 15 gates, approved before testing' | phase1-required |
| No privacy-safe interaction event log exists. app/main.py only includes routers and has no middleware, and no events table is in migrations 0001-0003. The no-model-call share and the weeks 2-4 return visits cannot be computed. Return-visit data is lost for good if capture does not start at the first sign-up. | Build pack s13 rows 1 and 7 | phase1-required |
| No feedback table, no 'Report an issue' control and no support-request capture, so support requests per 100 users cannot be counted. The Ops/support area owns the build; this area only reads it. | Build pack s6; s5 Trust labels; s13 row 2; s12 expansion checks | phase1-required |
| Editor hours per record are not logged anywhere. About 129 agent-drafted files already sit in docs/content-drafts/, and docs/DECISIONS.md (2026-09-19) still records the named fact reviewers as unassigned. Human verification has not started, so the measurement can still be captured if logging begins now. | Build pack s13 row 3; s12 expansion checks 'reviewer hours per record' | phase1-required |
| AI cost per Hindi answer cannot be measured: there is no ai_usage table and no language tag. The AI area owns this. | Build pack s13 row 4; s7 | phase1-required |
| No go/no-go report template and no per-batch expansion checklist with pause limits | Build pack s9 Steps 15-16; s12 | phase1-required |
| Two of the six round-1 criteria (save a next action, change a preference) cannot be tested on the current app. Three of the eight Step-15 tasks (explore via quick start, save a plan and find the next action, log out safely on a shared device) cannot either. There is no quick-start, guest-save, my-plan or preferences template. Student auth is Bearer-header only, and the only cookie session is scoped to /reviewer. The UI and auth areas own the build. | docs/UI.md lines 99-102; build pack s12 tester tasks; STATUS.md lines 70-80 | launch-blocker |
| School-channel measurement: there is no school contact and no approach letter | Build pack s13 row 6 | phase1-nice |
| Institution-steward measurement has no mechanism | Build pack s13 row 8 | defer |
| docs/UI.md lines 95-97 say round 1 runs on a clickable prototype before the engines are built. Build pack lines 39 and 165 say it runs on staging, guest only. The engines now exist, so UI.md is stale. | docs/UI.md lines 95-97 vs build pack s3 and s9 | phase1-nice |
| The teacher session guide and printable prompts do not exist | docs/PRODUCT.md line 52; build pack s5 | phase1-nice |

### Owner decisions

- **Are the round-1 and ten-person-trial participants adults only, or do they include real Class 10-12 minors?** - blocks: TRIAL-1, TRIAL-11, TRIAL-19 - recommended default: Adults only for round 1 and the ten-person trial: 18+ students, parents and teachers. Minors enter from batch 25, only after the consent workflow is reviewed by a non-author and the data-flow map is accepted. State the adult-proxy limitation in the go/no-go report.
- **Who are the moderator, the note-taker, the support owner, the independent consent-workflow reviewer and the fact reviewers? The fact reviewers have been unassigned since DECISIONS 2026-09-19.** - blocks: TRIAL-1, TRIAL-7, TRIAL-8, TRIAL-11 and the s12 100-user gate - recommended default: The owner moderates. One content reviewer takes notes and acts as support owner. A teacher or lawyer acquaintance who did not write the consent flow reviews it. Record roles or initials only.
- **What does 'outcome instrument piloted on the first ten users' mean, given that the week-4 post-test falls after Step 16 starts?** - blocks: TRIAL-4, TRIAL-12, TRIAL-13 start date - recommended default: Piloted means the pre-test is administered and scorable for all ten and the item wording problems are fixed. The week-4 post-test (TRIAL-17) runs in parallel with batch 25 and is reported as an addendum. Do not delay expansion by four weeks.
- **Are sessions recorded?** - blocks: TRIAL-2 - recommended default: No audio or video. Written de-identified notes and scoring sheets only.
- **Participant incentive** - blocks: TRIAL-1, TRIAL-19 - recommended default: A token thank-you in the Rs 200-300 range for round 1 and trial participants, and none for expansion batches. Owner sets the amount.
- **How is the instrument administered: in-app form, or by the moderator on paper?** - blocks: TRIAL-3 - recommended default: Moderator or paper (a phone call at week 4) for all batches in Lite. An in-app form is deferrable.
- **Numeric pause limits for the expansion checks** - blocks: TRIAL-4, TRIAL-10, TRIAL-13 - recommended default: Pause a batch on: any cross-user or privacy incident; more than 2% failed saves; any critical claim past its review-due date; AI spend above 80% of the monthly cap; more than 10 open support requests per 100 users, or any unanswered for over 48 hours; pending reviews older than 7 days.
- **Should round 1 wait for the Hindi UI, or for quick start and guest save?** - blocks: TRIAL-8 timing - recommended default: Do not wait for Hindi; the moderator translates and logs the limitation. Do wait for a minimal guest 'save a next action' and preference change, or score those two criteria on the design mockup and mark them as prototype-tested.
- **Which school to approach, and is the steward measurement in scope?** - blocks: TRIAL-14, TRIAL-15, TRIAL-19 - recommended default: Approach one school the owner already has a relationship with in week 1. Mark the steward measurement as 'not measured in Lite' unless hours remain.

### Tasks

### TRIAL-1 - Week-1 owner kickoff: name people, start round-1 and trial recruitment

- What: Owner names the moderator, note-taker, support owner, an independent consent-workflow reviewer and the still-unassigned fact reviewers. Owner starts recruiting 5-8 ADULT round-1 participants: a shared-phone user, a Hindi-preferring user, a parent and a teacher. Owner pencils in a 10-person trial pool and tentative dates.
- Acceptance: A roles list is in docs/DECISIONS.md, using roles or initials only. At least 6 adults are confirmed, covering all four profiles. Tentative dates are set. No participant personal data is in the repo.
- Step: cross | Wave: 0 | Needed by: staging-demo
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 6
- Depends on: none
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: Recruitment takes 2-3 weeks. Starting late is the most likely cause of round-1 slip.

### TRIAL-2 - Research pack: moderator scripts, scoring sheet, consent sheet, notes template

- What: One docs-only session creates docs/research/. Contents: round-1 script (six UI.md criteria, guest only, think-aloud, neutral prompts); Step-15 script (eight s12 tasks); scoring sheet defining 'intervention' and 'critical failure'; de-identified notes template (codes P01 and up); adult information and consent sheet in English and Hindi; no-recording rule; distress-disclosure escalation line. Also fixes the stale round-1 wording in docs/UI.md.
- Acceptance: Every s12 tester task and every UI.md criterion maps to one scripted task with a pass rule. The notes template has no name, phone or school field. UI.md lines 95-97 match the build pack. A Hindi speaker has read the consent sheet.
- Step: 15 | Wave: 1 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 2
- Depends on: DESIGN-5
- Touches: docs/research/moderator-script-round1.md, docs/research/moderator-script-trial.md, docs/research/scoring-sheet.md, docs/research/participant-info-consent.md, docs/research/notes-template.md, docs/UI.md
- Reviewers: ux-qa-reviewer, human
- Risk: Leading questions inflate completion rates. The moderator dry-run in TRIAL-8 is mandatory.

### TRIAL-3 - Five-item decision-quality instrument (EN + HI) with rubric

- What: Draft the five s13 items as open recall questions: three pathways, total cost of first choice, next deadline, a backup, one eligible scholarship. Write a 0/1/2 rubric per item and a Hindi version. Provide a moderator or paper form and administration rules for sign-up and week 4. Students see no scores, no labels and no personality framing.
- Acceptance: docs/research/outcome-instrument.md holds the EN and HI items, the rubric, the administration rules and a response sheet keyed by participant code. A Hindi speaker has reviewed the wording. Nothing in it labels the student.
- Step: 15 | Wave: 0 | Needed by: ten-user-trial
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 2
- Depends on: none
- Touches: docs/research/outcome-instrument.md
- Reviewers: human
- Risk: Item 5 cannot be scored unless the published scholarship content covers the participant.

### TRIAL-4 - Owner approves Step 15 gates, definitions and pause limits before testing

- What: Before any trial session, the owner signs off four things in writing. First, the four Step 15 gates as written in s12. Second, the TRIAL-2 definitions of 'intervention' and 'critical failure'. Third, the numeric pause limits proposed in the TRIAL-10 checklist. Fourth, the interpretation of 'instrument piloted on the first ten users'.
- Acceptance: A dated docs/DECISIONS.md entry with the thresholds exists before the first TRIAL-11 session. The TRIAL-10 templates reference it.
- Step: 15 | Wave: 2 | Needed by: ten-user-trial
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 1
- Depends on: TRIAL-2, TRIAL-10
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: none recorded

### TRIAL-5 - usage_events table, RLS and metric views (migration only)

- What: Add one append-only usage_events table. Columns: event_type (fixed enum), route template, model_called boolean, language, event_day (date only), actor_key (salted server-side hash of the student id, or 'guest'). No IP address, query text, plan contents or notes. RLS: insert for the app role, select for reviewer or admin only. Add views for the no-model-call share and the weeks 2-4 return visits. Add data-flow and deletion-path rows to the docs.
- Acceptance: The migration file is added and the owner applies it via scripts/apply_migrations.py. test-db proves that guest, student A and student B cannot select rows. The views are correct on synthetic rows. docs/DATA.md and the docs/SECURITY.md data-flow row are updated. The events are in their own table, not in audit_events.
- Step: 13 | Wave: 0 | Needed by: ten-user-trial
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.5
- Depends on: none
- Touches: db/migrations/000N_usage_events.sql (N assigned by schema serialiser; 0004 if first), tests/db/test_usage_events_rls.py, docs/DATA.md, docs/SECURITY.md
- Reviewers: data-security-reviewer
- Risk: A pseudonymous key is still personal data for a signed-in minor. Salt it server-side and include it in the data-flow acceptance.

### TRIAL-6 - Pilot metrics script for the s13 figures and s12 per-batch checks

- What: A read-only scripts/pilot_metrics.py plus a make target. It joins the usage_events views, the AI area's ai_usage (cost, language) and the Ops feedback/support table into the s13 figures and the s12 per-batch checks. Output is aggregate markdown only, with small cells suppressed.
- Acceptance: On synthetic rows it prints every automatable s13 measurement and s12 check. Any cell with n<5 is flagged. No row-level student data appears in the output. It degrades to 'not available' when a source table is absent.
- Step: 16 | Wave: 8 | Needed by: expand-100
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0
- Depends on: TRIAL-5, AI-4, OPS-6
- Touches: scripts/pilot_metrics.py, Makefile, tests/unit/test_pilot_metrics.py
- Reviewers: data-security-reviewer
- Risk: none recorded

### TRIAL-7 - Editor-hours log, started before the first human verification

- What: The owner or editor starts a plain spreadsheet, kept outside the repo or as a CSV. Columns: date, reviewer role, record type (programme, exam rule, scholarship), record id, minutes correcting the draft, minutes verifying, drafted-by-agent yes/no. Editors fill it from the first verified record. No in-app timer and no dev session.
- Acceptance: The log exists before the first claim is approved. The first 10 verified records have minutes logged. The median per record type can be computed. Agent-drafted records are distinguished from human-drafted ones.
- Step: 10 | Wave: 1 | Needed by: ten-user-trial
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 1
- Depends on: CONTENT-1
- Touches: docs/research/editor-hours-log.csv (header row only; optional)
- Reviewers: human
- Risk: If logging starts late, the DPR headcount figure becomes guesswork.

### TRIAL-8 - Run usability round 1 (guest only, gated staging)

- What: The moderator dry-runs the script once. The moderator then runs 5-8 sessions of 30-40 minutes each with adults on gated staging, on their own or a shared phone, with no accounts. At least one session is in Hindi; if the Hindi UI is absent, the moderator translates and logs that as a limitation. Sessions are scored on the TRIAL-2 sheet. Raw notes stay outside the repo.
- Acceptance: At least 5 sessions are scored on the six criteria, covering all four profiles. docs/research/round1-findings.md holds completion per criterion and ranked issues, with no names. Any criterion that cannot be tested is recorded as such, not as a pass.
- Step: 7 | Wave: 7 | Needed by: staging-demo
- Executor: external-participant | Model tier: none | Dev sessions: 0 | Human hours: 12
- Depends on: TRIAL-1, TRIAL-2, DESIGN-6, UI-15, AUTH-6
- Touches: docs/research/round1-findings.md
- Reviewers: human
- Risk: none recorded

### TRIAL-9 - Round-1 synthesis into ranked fix list

- What: One session turns the round-1 findings into a prioritised issue list (blocker, major, minor) mapped to screens and UI.md criteria, plus task-card stubs for the UI area. Any change to the frozen component set is flagged for an owner decision.
- Acceptance: Every criterion under 80% completion has at least one linked fix card. The owner has accepted or rejected each blocker.
- Step: 7 | Wave: 8 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 1
- Depends on: TRIAL-8
- Touches: docs/research/round1-findings.md, tasks/BCI-0NN.md (new stubs; next free is BCI-007)
- Reviewers: ux-qa-reviewer
- Risk: none recorded

### TRIAL-10 - Go/no-go template and batch expansion checklist with proposed limits

- What: Write docs/research/go-no-go-template.md: gate-by-gate results, the s12 100-user gate checklist with an evidence-link column, limitations, an instrument pre-score table and a decision section. Write docs/research/batch-expansion-checklist.md: the eight s12 checks with PROPOSED default pause limits and pause/resume rules, for the owner to approve in TRIAL-4.
- Acceptance: Every s12 gate and every expansion check has a row with an evidence-source column. The 'Small-sample gates, not impact claims' line is included. The limits are marked 'proposed' until TRIAL-4.
- Step: 15 | Wave: 0 | Needed by: ten-user-trial
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.5
- Depends on: none
- Touches: docs/research/go-no-go-template.md, docs/research/batch-expansion-checklist.md
- Reviewers: human
- Risk: none recorded

### TRIAL-11 - Run ten-person trial + usability round 2 + instrument pre-test

- What: Ten participants run the eight s12 tasks on production. Round 2 criteria are scored in the same sessions. The pre-instrument is administered at sign-up and the week-4 post-test date is booked. Default: adults only, unless the consent workflow has been human-reviewed and the data-flow map accepted. Include one Hindi session and one shared-device session.
- Acceptance: 10 scored sessions and a de-identified docs/research/trial-results.md exist. Pre-instrument scores are recorded for all 10. The four gates are computed against the TRIAL-4 thresholds. Critical failures are logged with timestamps.
- Step: 15 | Wave: 14 | Needed by: ten-user-trial
- Executor: external-participant | Model tier: none | Dev sessions: 0 | Human hours: 20
- Depends on: TRIAL-1, TRIAL-2, TRIAL-3, TRIAL-4, TRIAL-16, DEPLOY-13, CONTENT-10, SCOPE-9, RULES-12, AI-17, AI-8, UI-11, OPS-6, I18N-4, I18N-16, A11Y-12, A11Y-9, UI-19, OPS-16, DATA-13, AUTH-17
- Touches: docs/research/trial-results.md
- Reviewers: human
- Risk: If participants are minors, the whole consent and safeguarding chain is on the critical path. Adult proxies weaken validity; disclose that in the report.

### TRIAL-12 - Go/no-go report

- What: Fill the TRIAL-10 template from the trial results and the usage_events views, plus TRIAL-6 output if it is ready. The owner decides go, fix-and-retest or stop, and records the decision. No claim goes beyond the small-sample gates. Limitations are stated: adult proxies, week-4 post-test pending.
- Acceptance: docs/research/go-no-go-report.md is committed with every gate marked pass or fail and linked to evidence. The owner's decision is dated in docs/DECISIONS.md. STATUS.md is updated.
- Step: 15 | Wave: 15 | Needed by: ten-user-trial
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 2
- Depends on: TRIAL-10, TRIAL-11
- Touches: docs/research/go-no-go-report.md, docs/DECISIONS.md, STATUS.md
- Reviewers: human
- Risk: none recorded

### TRIAL-13 - Batch expansion 10->25->50->100 with per-batch checks

- What: Before each batch the owner runs make pilot-metrics and the checklist, then records a dated batch record. The pre-instrument is administered at each batch's sign-up. Pause on any breached limit. Scope stays frozen. This is four discrete owner actions of about 3 hours each.
- Acceptance: Four dated records exist in docs/research/batch-records/. Any pause and resume has a documented reason. No batch is admitted while any s12 100-user gate item is open.
- Step: 16 | Wave: 16 | Needed by: expand-100
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 12
- Depends on: TRIAL-6, TRIAL-12, TRIAL-19, OPS-12, AI-13
- Touches: docs/research/batch-records/
- Reviewers: human
- Risk: none recorded

### TRIAL-14 - School-channel approach (30 students under parental consent)

- What: One cheap agent session drafts a one-page letter covering purpose, the consent route and what data is and is not collected. In week 1 the owner approaches one school. The measurement is whether the school agrees and whether 30 consented students take part. It can sit inside the 50 or 100 batch.
- Acceptance: The letter exists. The school's yes, no or no-answer is recorded with a date and its reasons. If yes, the consent route used is documented. No student list is in the repo.
- Step: 16 | Wave: 1 | Needed by: expand-100
- Executor: mixed | Model tier: cheap | Dev sessions: 1 | Human hours: 6
- Depends on: TRIAL-1
- Touches: docs/research/school-approach-letter.md
- Reviewers: human
- Risk: School approval cycles run for weeks and stall around exams. A refusal is still a valid DPR measurement.

### TRIAL-15 - Institution-steward measurement (deferrable)

- What: The owner emails 3-5 institutions asking them to confirm or correct their self-declared profile, and logs response rate and turnaround. No product feature is involved. Otherwise record 'not measured in Lite'.
- Acceptance: Either a small response log exists, or an explicit 'not measured' line is written in dpr-measurements.md.
- Step: cross | Wave: 0 | Needed by: deferrable
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 3
- Depends on: none
- Touches: docs/research/dpr-measurements.md
- Reviewers: human
- Risk: none recorded

### TRIAL-16 - Usage event write hook (middleware)

- What: app/observability/events.py plus one add_middleware line in app/main.py. It records one event per page or API interaction: route template, language, model_called (default false; the AI adapter sets it to true), and a salted actor_key. It fails open: if the insert fails, the request is never broken. Excludes /healthz, static files and /reviewer.
- Acceptance: Unit tests prove that no request body, query string, IP address or raw user id is stored, that an insert failure does not affect the response, and that excluded routes are not logged. The salt is read from an environment variable name and is never committed.
- Step: 13 | Wave: 1 | Needed by: ten-user-trial
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0
- Depends on: TRIAL-5
- Touches: app/observability/__init__.py, app/observability/events.py, app/main.py, tests/unit/test_usage_events.py, .env.example
- Reviewers: data-security-reviewer
- Risk: none recorded

### TRIAL-17 - Week-4 post-test for the first ten + return-visit readout

- What: Four weeks after each trial participant's sign-up, the moderator administers the post-instrument by phone or paper and scores it with the rubric. The weeks 2-4 return-visit view is read for the cohort. The results are appended to the go/no-go report as an addendum.
- Acceptance: Post scores are recorded by participant code for at least 8 of the 10; drop-outs are reported, not imputed. Pre and post figures are shown as counts, with no significance claim. The return-visit figure is recorded with its n.
- Step: 16 | Wave: 15 | Needed by: expand-100
- Executor: human-reviewer | Model tier: none | Dev sessions: 0 | Human hours: 5
- Depends on: TRIAL-3, TRIAL-11, TRIAL-16
- Touches: docs/research/go-no-go-report.md (addendum)
- Reviewers: human
- Risk: Falls in weeks 13-14, outside the 12-week schedule.

### TRIAL-18 - DPR measurements write-up

- What: One session fills docs/research/dpr-measurements.md from the pilot_metrics output, the editor-hours log medians, the instrument pre/post counts, and the school and steward outcomes. Each s13 row gets a value, n and caveat, or the phrase 'not measured'. The Annex D assumption each row tests is cited.
- Acceptance: All 8 s13 rows are present. No row has a figure without an n. No fabricated or extrapolated values. The owner has read and signed the file.
- Step: 16 | Wave: 17 | Needed by: expand-100
- Executor: mixed | Model tier: standard | Dev sessions: 1 | Human hours: 2
- Depends on: TRIAL-6, TRIAL-7, TRIAL-13, TRIAL-17
- Touches: docs/research/dpr-measurements.md
- Reviewers: human
- Risk: none recorded

### TRIAL-19 - Recruit expansion cohort (about 90 users), starting week 6

- What: The owner builds the pipeline for batches 25, 50 and 100, using the school from TRIAL-14, coaching contacts, and the parent and teacher referrals from round 1. The owner decides the adult and minor mix per batch. Minors are admitted only through the reviewed consent route. The invite list is kept outside the repo.
- Acceptance: A committed-count tracker (numbers only) shows at least 15 for batch 25 before TRIAL-12. The channel and the consent route per batch are recorded in docs/DECISIONS.md.
- Step: 16 | Wave: 2 | Needed by: expand-100
- Executor: owner | Model tier: none | Dev sessions: 0 | Human hours: 10
- Depends on: TRIAL-1, TRIAL-14
- Touches: docs/DECISIONS.md
- Reviewers: human
- Risk: If recruitment waits for go/no-go, Step 16 cannot finish inside weeks 11-12.

### Merged into other tasks

- None

## Project memory, process hygiene and agent definitions

Area: `docs-process`

Core memory exists (CLAUDE.md 68 lines, scoped docs, DECISIONS, six task cards, two reviewer agents) but the token-hygiene layer does not. STATUS.md is 401 lines / 3,379 words (8x the rule) and stale versus main (e14c560): Requirements/Timeline screens, Playwright smoke tests and an M5 AI adapter (app/ai/, tests/unit/test_ai_adapter.py) all landed after it. Missing: KNOWN_ISSUES, RUNBOOK, RELEASE_CHECKLIST, tasks/INDEX.md, card template, implementer and AI-evaluator agent definitions, hooks, cost ledgers, reviewer calibration, and a written parallel-work protocol. No branch is unmerged, so worktree cleanup is low-risk. Fourteen small tasks; DOCS-1..4 plus DOCS-13 must land before any parallel implementation wave.

### Already done

- CLAUDE.md within the 60-100 line rule with mission, non-negotiables, stack, verified commands, links - F:\the competetion project\CLAUDE.md - 68 lines / 516 words. Uncommitted working-tree edit (+4/-1) replaces the no-swarm rule with the parallel-workflow guardrails.
- Scoped topic docs PRODUCT / ARCHITECTURE / UI / DATA / SECURITY, each short - F:\the competetion project\docs\ - wc: ARCHITECTURE 653w, DATA 577w, PRODUCT 498w, SECURITY 837w, UI 789w
- Dated decisions log, newest first; 2026-09-21 entry lifting the concurrency ceiling while keeping disjoint-files / separate-worktrees / never-parallel-migration-lockfile-schema / lead-verifies-and-merges - F:\the competetion project\docs\DECISIONS.md (543 lines, 4,614 words). Only the 19-line 'No agent swarm rule removed' entry is uncommitted; the scope-widening 2026-09-21 entry is already committed.
- One task card per milestone BCI-001..006 (de facto contract plus session history) - F:\the competetion project\tasks\BCI-001..006.md, 454-1,585 words each
- Two read-and-test-only reviewer agents with trigger, exclusions, checklist, stop condition, evidence-based output (NOT calibrated) - F:\the competetion project\.claude\agents\data-security-reviewer.md (47 lines; Calibration section lines 36-40 says it still has to be run); ux-qa-reviewer.md (50 lines)
- Real make targets for dev, css, lint, typecheck, test-unit, test-e2e, test-db; e2e smoke directory exists - F:\the competetion project\Makefile; tests\e2e\conftest.py, test_smoke.py (commits 84b1a1e, 2db356e). CI still has test-db/test-e2e commented out (.github\workflows\ci.yml lines 6, 47). `make build` is only an echo placeholder - not done.
- Worktree isolation in use; no unmerged branches - git worktree list: main e14c560; wf_14eda97f (7338bd0, locked), wf_9b7797a4 (7338bd0), wf_f5a0f93f (9aeae6b, merged by e14c560); orphan dir .claude/worktrees/wf_21ae8c35-7dc-1. `git branch --no-merged main` returns nothing.
- STATUS.md exists with milestone, blockers, infra table, owner-input list, 'Not claimed' section - F:\the competetion project\STATUS.md - content good, size and freshness are the problem (line 13 'see git log -1', line 387 'No e2e test, no live AI call')

### Gaps

| Gap | Spec ref | Severity |
|---|---|---|
| STATUS.md is 401 lines / 3,379 words versus 'under 400 words'; carries bug narratives that belong in task cards/history. Every session and sub-agent pays ~4.5k tokens for it. | Build pack s7 'Memory in files' (line 116); s14 line 260 | phase1-required |
| STATUS.md is stale against main e14c560: claims no timeline/requirements UI, 'No e2e test' and no AI, but 1adb212/2db356e added Requirements+Timeline screens and e2e tests, and 9aeae6b added app/ai/ (adapter, budget, grounding, gemini/mock providers) with tests/unit/test_ai_adapter.py. No exact commit recorded; 'Next task' is a menu, not one task. The 239-test count is also unverified after these commits. | Build pack s7 (exact commit, one exact next task); s15 'End a session' | phase1-required |
| tasks/INDEX.md (ordered checklist of the 16 steps) missing; no mapping of BCI-001..006 / M0-M5 to Steps 1-16. | Build pack s14 line 270; s9 | phase1-required |
| No task-card template/contract: no owned files, forbidden files, frozen contracts, neededBy, model tier, tests-to-run or completion-report block. | Build pack s7 'tasks/BCI-xxx.md: one task contract each', 'Contracts before parallel work' | phase1-required |
| No written parallel-work protocol: ownership map, serialized files (db/migrations next = 0004, pyproject.toml, package.json/package-lock.json, app/main.py include_router block, app/core/config.py, .env.example, app/web/templates base layout, tailwind.config.js, tests/db/conftest.py, .github/workflows/ci.yml, CLAUDE.md, STATUS.md, docs/DECISIONS.md), merge order, who runs the full suite, worktree cleanup. | Build pack s7 'Agents'; DECISIONS 2026-09-21; CLAUDE.md working rules (uncommitted) | phase1-required |
| No implementer agent definition; .claude/agents has reviewers only. Every parallel implementer prompt must restate the same rules, costing tokens and inviting drift. | Build pack s7 'Agents'; CLAUDE.md 'Agent roles: .claude/agents/' | phase1-required |
| docs/KNOWN_ISSUES.md missing; issues scattered across STATUS, DECISIONS, BCI-006 'Not done yet', content drafts. | Build pack s7; s14 line 269 | phase1-required |
| docs/RELEASE_CHECKLIST.md missing; s15 'Release review' prompt depends on it. | Build pack s7; s15; s12 gates | launch-blocker |
| docs/RUNBOOK.md missing (deploy, rollback, AI off, backup restore, secret rotation, contact). Note there is no AI_ENABLED flag in app/core/config.py today - only ai_daily_request_budget and ai_monthly_spend_cap_inr; a real kill switch must come from the AI area. | Build pack s7 'Memory in files'; s12 'Built means' (AI interruptible; restore and recovery verified) | launch-blocker |
| Reviewer calibration never run (build pack Step 3 says 'calibrated'); tests/fixtures holds only synthetic_data.py. | Build pack s9 Step 3; s7 'Agents'; data-security-reviewer.md lines 36-40 | phase1-required |
| AI evaluator agent definition missing, and the first AI code has already landed (9aeae6b) without it; needed before any AI route is wired. | Build pack s7 'Agents' | phase1-required |
| No hooks (.claude has only agents/ and worktrees/, no settings.json): format changed files, warn on secret-like additions, flag prohibited tool actions. | Build pack s7 'Hooks' (line 126) | phase1-nice |
| CLAUDE.md 'Verified commands' lists `make build`, but the Makefile target only echoes a message and no Dockerfile or .dockerignore exists. Spec requires real, verified commands. | Build pack s7 'Hooks' paragraph (real package commands, verified) | phase1-nice |
| No cost tracking: four ledgers and per-slice metrics exist nowhere; reviewer hours per record is also a DPR measurement. | Build pack s7 'Token and time rules'; s12 expansion checks; s13 | phase1-required |
| DECISIONS.md is 4,614 words with no digest; agents pay ~6k tokens or skip it. | Build pack s7 'Token and time rules' | phase1-nice |
| Uncommitted CLAUDE.md/DECISIONS edits sit in main's working tree; new worktrees branch from commits, so parallel agents would not see the current rules. CLAUDE.md links omit process files. | Build pack s7 'Memory in files' | phase1-required |
| Dashboards/tooling for escaped-defect or failed-fix metrics beyond a markdown ledger | Build pack s7 'Track cost per accepted slice' | defer |

### Owner decisions

- **May the stale wf_ worktrees, their branches (all merged into main) and the orphan wf_21ae8c35 directory be removed, including the locked one?** - blocks: DOCS-1 - recommended default: Yes once this workflow has finished: lead checks git status inside each; removes those with no uncommitted files; anything else is kept and listed in KNOWN_ISSUES.
- **Where does removed STATUS.md history go?** - blocks: DOCS-2 - recommended default: Verbatim into docs/HISTORY.md, never read by default; nothing is deleted.
- **Maximum simultaneous implementer agents** - blocks: DOCS-4 - recommended default: Up to 4 implementers on disjoint directories plus 1 reviewer, one lead merging serially; drop to 2 if two merges in a row need conflict fixes. Read-only research/content-draft agents are uncapped.
- **Approve adding project .claude/settings.json hooks (agent configuration change)** - blocks: DOCS-10 - recommended default: Approve warn-only hooks with no permission changes; CI grep is the real enforcement. If not approved, ship only the CI step.
- **How dev-agent cost is measured for the ledger** - blocks: DOCS-6 - recommended default: Sessions x model tier per task plus the monthly subscription/API bill entered by the owner; no token-level tooling.
- **Keep new task ids in the BCI-xxx series or use area-prefixed ids from this plan** - blocks: DOCS-3 - recommended default: Use area-prefixed ids in tasks/INDEX.md; create a card file from TEMPLATE.md only when a task starts.
- **Who is the second authorised person for release sign-off on child data and production security** - blocks: DOCS-14 - recommended default: The same second person who acts as checker in maker-checker publishing; name them in RUNBOOK contacts.

### Tasks

### DOCS-1 - Commit pending memory edits and clean stale worktrees

- What: Lead session: commit the uncommitted CLAUDE.md and docs/DECISIONS.md edits on main. List worktrees (wf_14eda97f locked and wf_9b7797a4 at 7338bd0; wf_f5a0f93f at 9aeae6b already merged; orphan dir wf_21ae8c35). Confirm each has no uncommitted files and no unmerged commits, check the locked one is not in use, ask the owner, then remove. Record base commit.
- Acceptance: git status clean on main; git worktree list shows only main or explicitly kept worktrees; nothing with uncommitted or unmerged work removed without owner yes; base commit hash recorded for DOCS-2.
- Step: cross | Wave: 0 | Needed by: staging-demo
- Executor: mixed | Model tier: cheap | Dev sessions: 1 | Human hours: 0.25
- Depends on: none
- Touches: CLAUDE.md, docs/DECISIONS.md, .claude/worktrees/
- Reviewers: human
- Risk: Removing a worktree with uncommitted files (branches are all merged, but working files may not be); check git status inside each first.

### DOCS-2 - Slim STATUS.md to under 400 words and re-verify against main

- What: Rewrite STATUS.md: step/milestone, exact commit, what is live (one line per route group), blockers, owner inputs, not claimed, one exact next task. Move removed narrative verbatim to docs/HISTORY.md (never read by default). Reconcile with code: Requirements/Timeline pages, tests/e2e, app/ai adapter (not wired to any route). Re-run make test-unit to restate the test count.
- Acceptance: wc -w STATUS.md < 400; exact commit hash present; AI adapter, e2e and new screens reflected; consent-gate blocker prominent; test count only stated if run in that session; HISTORY.md holds removed text unchanged.
- Step: cross | Wave: 1 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: DOCS-1
- Touches: STATUS.md, docs/HISTORY.md
- Reviewers: human
- Risk: Losing the consent-gate warning or a live caveat during compression.

### DOCS-3 - Task-card template and tasks/INDEX.md

- What: Create tasks/TEMPLATE.md (about 150 words of headings): id, goal, neededBy, build-pack step, model tier, owned files, forbidden/serialized files, frozen contracts referenced, acceptance, exact make commands, reviewers, completion report, cost line. Create tasks/INDEX.md: Steps 1-16 mapped to BCI-001..006, M5 groundwork commit 9aeae6b, and this plan's task ids with status.
- Acceptance: TEMPLATE.md has every field listed; INDEX.md lists all 16 steps with status and links; done steps match the slimmed STATUS.md; notes build-pack Progress paragraph is stale; filled cards capped at about 300 words.
- Step: cross | Wave: 2 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: DOCS-2
- Touches: tasks/TEMPLATE.md, tasks/INDEX.md
- Reviewers: human
- Risk: Template bloat raising per-card token cost.

### DOCS-4 - Parallel-work protocol: ownership map, serialized files, merge rules

- What: Write docs/PARALLEL.md (under 500 words): owner workstream per app/ and tests/ directory; single-writer files (db/migrations - next is 0004, lead reserves numbers; pyproject.toml; package.json and package-lock.json; app/main.py router block; app/core/config.py; .env.example; base template; tailwind.config.js; tests/db/conftest.py; ci.yml; CLAUDE.md; STATUS.md; DECISIONS.md); worktree per implementer from a named commit; numbered merge steps; cross-user retest trigger; worktree cleanup.
- Acceptance: Every directory under app/ and tests/ has an owner; serialized list explicit; migration number reservation rule stated; merge steps numbered with lead running the full suite; auth/RLS/publication changes trigger cross-user tests; under 500 words.
- Step: cross | Wave: 3 | Needed by: staging-demo
- Executor: dev-agent | Model tier: strongest | Dev sessions: 1 | Human hours: 0.5
- Depends on: DOCS-3
- Touches: docs/PARALLEL.md
- Reviewers: data-security-reviewer, human
- Risk: Ownership map drifts from the real layout; keep it directory-level.

### DOCS-5 - KNOWN_ISSUES.md plus a decisions-in-force digest

- What: Create docs/KNOWN_ISSUES.md seeded from STATUS.md, DECISIONS.md, BCI-006 'Not done yet' and docs/content-drafts: id, severity, owner, expiry, link. Include consent gate, engine gaps noted in drafts, CI test-db/test-e2e commented out, make build placeholder, no AI kill-switch flag, English only. Add a 150-word 'Decisions in force' digest atop DECISIONS.md; change no entry.
- Acceptance: Each seeded issue has severity and owner; consent gate marked launch-blocker; digest <= 150 words linking dated entries; git diff of DECISIONS.md shows additions only.
- Step: cross | Wave: 2 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: DOCS-2
- Touches: docs/KNOWN_ISSUES.md, docs/DECISIONS.md
- Reviewers: human
- Risk: Digest misstates a decision; each line checked against its dated entry.

### DOCS-6 - Four-ledger cost file and per-slice metrics line

- What: Create docs/COSTS.md with four tables (dev agents, application inference, hosting/monitoring, human verification/support) and a per-slice row: task id, sessions, model tier, failed-fix cycles, escaped defects, hours to tested feature. Include reviewer hours per record for the DPR measurement. Lead appends a row per merged task; owner fills hosting and subscription figures.
- Acceptance: COSTS.md has four ledgers and one example row labelled as estimate; TEMPLATE.md cost line matches the row format; owner-entered monthly hosting and subscription figures present; row-append step added to PARALLEL.md merge list.
- Step: cross | Wave: 4 | Needed by: ten-user-trial
- Executor: mixed | Model tier: cheap | Dev sessions: 1 | Human hours: 0.5
- Depends on: DOCS-3, DOCS-4
- Touches: docs/COSTS.md, tasks/TEMPLATE.md, docs/PARALLEL.md
- Reviewers: human
- Risk: Ledger abandoned after week one.

### DOCS-10 - Minimal narrow hooks plus CI secret-pattern check

- What: Add project .claude/settings.json hooks: ruff format on changed .py files; warn on secret-like additions (JWT-shaped strings, service_role, key literals); warn on prohibited tool actions (edits under db/migrations outside a migration card, Supabase MCP writes). Mirror the secret pattern as a CI step. Test on harmless fixtures. No permission settings changed. Owner approves first.
- Acceptance: Hooks fire on a fake-key fixture and a mis-formatted fixture; CI step fails on the same fake key in a test branch; settings.json contains hooks only, no permission changes; owner approval recorded in DECISIONS.md by the lead.
- Step: cross | Wave: 4 | Needed by: deferrable
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.25
- Depends on: DOCS-4, SEC-7
- Touches: .claude/settings.json, .github/workflows/ci.yml, tests/fixtures/hooks/
- Reviewers: data-security-reviewer, human
- Risk: Noisy false positives slow every agent; keep warn-only locally.

### DOCS-12 - Refresh CLAUDE.md links and verified commands (lead-only edit)

- What: One lead edit once DOCS-3/4/5/13 exist: add links to tasks/INDEX.md, TEMPLATE.md, docs/PARALLEL.md, KNOWN_ISSUES.md; state 'agents read STATUS.md, their card and PARALLEL.md only'; mark `make build` as not yet real or remove it; check each listed target against the Makefile. Later files (RUNBOOK, RELEASE_CHECKLIST, COSTS) get their link line added by the lead when merged.
- Acceptance: CLAUDE.md <= 100 lines; every linked file exists at commit time; every listed make target does real work; non-negotiables text byte-identical (git diff).
- Step: cross | Wave: 5 | Needed by: staging-demo
- Executor: dev-agent | Model tier: cheap | Dev sessions: 1 | Human hours: 0.1
- Depends on: DOCS-4, DOCS-5, DOCS-13
- Touches: CLAUDE.md
- Reviewers: human
- Risk: Accidental weakening of a non-negotiable; owner reviews the diff.

### DOCS-13 - Implementer agent definition for parallel waves

- What: Add .claude/agents/implementer.md (under 300 words): reads STATUS.md, its task card and docs/PARALLEL.md only; edits owned files only; never touches serialized files, STATUS or DECISIONS; runs the card's make commands; two failed fixes then stop; no student data, no secrets; writes the completion report into its card; never claims unrun tests.
- Acceptance: File follows the existing agents' section structure; every rule above present; a dry-run on one small card produces a completion report and edits no file outside the card's owned list.
- Step: cross | Wave: 4 | Needed by: staging-demo
- Executor: dev-agent | Model tier: standard | Dev sessions: 1 | Human hours: 0.1
- Depends on: DOCS-4
- Touches: .claude/agents/implementer.md
- Reviewers: human
- Risk: Duplicates CLAUDE.md; keep it to behaviour that differs for a worktree implementer.

### Merged into other tasks

- DOCS-7 -> QA-9
- DOCS-8 -> OPS-7
- DOCS-9 -> OPS-7
- DOCS-11 -> AI-9
- DOCS-14 -> DEPLOY-12

