# BCION Lite — operating memory

## Mission
Build BCION Lite: a 10–100 user career-decision pilot for Indian students
(Class 8–12), specified in `docs/BCION-Lite-Build-Pack.md` (the DPR's own
Annex E points here). One journey: explore → compare three pathways →
calculate time and cost → see requirements → save next actions. This is
Phase −2 of the national BCION DPR — a technical spike and measurement
instrument, not the national platform. Read the build pack (and the DPR's
Annex D assumptions register) before proposing anything already decided.

## Non-negotiables
- AI never invents facts. It explains and personalises over retrieved,
  human-verified records. No record → answer is "not verified".
- Every published fact has a source, a verification date and a verifier.
  Unapproved facts never reach public results (maker-checker, enforced
  server-side, not by a button).
- No rank predictions, no "you are not suited", no personality-type labels,
  no guarantees. Ranges and named assumptions only.
- Synthetic fixtures are clearly labelled and NEVER published as verified
  facts. Real minor accounts stay disabled until the consent and
  safeguarding workflow is reviewed by a person.
- No student data to development agents. No secrets in repo memory —
  variable names only, values via provider dashboards / environment.
- Cross-user access (guest, student A, student B, reviewer) is tested every
  time auth, RLS or publication changes.

## Stack (pinned — see docs/DECISIONS.md; do not propose Next.js or Vercel)
FastAPI monolith (Python) · Supabase (Mumbai) for Postgres/Auth/Storage with
RLS · Tailwind + `docs/UI.md` component set, server-rendered templates or a
light PWA · Postgres jobs table + one worker process (no Redis/broker) ·
n8n off the request path (reviewer notices, review-due reminders only) ·
one hosted AI provider behind an adapter, spend-capped · pytest + Playwright
for Python + ruff + mypy · GitHub Actions with a protected prod environment.

## Verified commands
- `make dev` — run the app locally
- `make lint` — ruff
- `make typecheck` — mypy
- `make test-unit` — pytest (unit)
- `make test-e2e` — Playwright (once UI exists)
- `make test-db` — RLS/policy tests against a live Postgres (once DB exists)
- `make build` — build the Docker image (once Dockerfile is exercised)

## Working rules
- One bounded task per agent; no whole-product attempts. Parallel
  multi-agent workflows are allowed (owner decision 2026-09-21): disjoint
  files, separate worktrees, never parallel edits to a migration, lockfile
  or shared schema; the lead session verifies and merges.
- Lead session only: before starting or fanning out build work, Grep
  `docs/DEVELOPMENT-PLAN.md` for "### 8.8" (workflows at once per wave,
  agents per workflow, cut-backs) and "### 6.4" (never-parallel groups) and
  work to them; never exceed a cap without the owner's yes. Implementers
  and reviewers never open that file or `docs/plan/` — they get a task card.
- Read `STATUS.md` and the specific files a task touches — not the whole
  repo.
- Ordinary code for facts, rules and arithmetic. AI only for grounded
  explanation with server-owned citations.
- Two failed fixes of the same failure → stop and diagnose; don't patch a
  third time blind.
- Update `STATUS.md` at the close of every session. Never claim a test
  passed without having run it in this session.
- Conflict order: approved task card > `docs/DECISIONS.md` > code/tests as
  evidence > anything else (including this file, if stale).

## Links
- Lite's own plan (governs this repo day to day): `docs/BCION-Lite-Build-Pack.md`
- National context: `docs/BCION-DPR-v1.1.md` (Annex A state variant, Annex B
  change log, Annex C glossary, Annex D assumptions register)
- `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/UI.md`, `docs/DATA.md`,
  `docs/SECURITY.md`, `docs/DECISIONS.md`, `STATUS.md`
- Task cards: `tasks/BCI-xxx.md`
- Agent roles: `.claude/agents/`
