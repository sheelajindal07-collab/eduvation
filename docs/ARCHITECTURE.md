# Architecture — BCION Lite

Source: `docs/BCION-Lite-Build-Pack.md`, §4 (Stack). Pinned; see
`docs/DECISIONS.md` for the one condition that would flip it. Do not
propose Next.js/Vercel without a recorded decision.

## Stack
| Layer | Choice | Note |
| --- | --- | --- |
| Application | FastAPI monolith (Python), modules: data / rules / planning / ai / api / db / core | One codebase, one deployment |
| Front end | Server-rendered templates (Jinja2) or a light PWA served by the same app; Tailwind CSS compiled via `make css`/npm | Node/npm is a dev-time build tool only (same tier as ruff/mypy) — the compiled `app/static/css/app.css` is checked in, nothing at runtime needs Node. No separate front-end framework |
| DB / Auth / Storage | Supabase (Mumbai): Postgres, Auth, Storage, RLS | App connects as a restricted role, never the owner role |
| Background worker | One process reading a Postgres jobs table (leases, bounded retries, idempotency keys) | No Redis, no broker |
| Workflow glue | n8n, off the request path | Reviewer notices, review-due reminders, scheduled source-allowlist checks only |
| Reminders | One WhatsApp Cloud API template, opt-in, deadline-only | No inbound bot |
| AI | One hosted provider behind a provider adapter; global spend cap wired live (in-memory, process-wide); a per-account/per-guest, database-backed cap exists (`app/ai/budget_db.py`, `db/migrations/0011_ai_usage.sql`) but is **not yet wired into any live route** (2026-09-23 audit finding — tracked, not fixed here) | No GPU, no multi-vendor gateway in Lite |
| Search | Postgres full-text + a synonym table (Hindi/Hinglish/English) | Enough for a curated catalogue |
| Monitoring | Error tracker + uptime check, scrubbed structured logs | No session replay |
| Hosting | VPS (Docker), reverse proxy, separate staging/production containers; deploy via GitHub Actions protected environment | See `docs/DECISIONS.md` for provisioning status |
| Tests / lint / types | pytest, Playwright (Python), ruff, mypy | `make test-db` runs RLS/policy tests against staging |

**Not bought:** Kubernetes, Redis, Kafka, Elasticsearch, graph or vector DB,
GPU, memory platform, agent orchestration frameworks, Vercel.

## Module layout
```
app/
  main.py          — FastAPI app factory, routing
  core/             — config, settings, logging, spend caps
  db/               — Supabase client, RLS-aware session helper, migrations
  data/             — Career, Pathway, Exam, Institution, Scholarship models + claims schema
  rules/             — deterministic engines: eligibility, cost, timeline, reservation
  planning/          — plan/save-next-actions logic, comparison assembly
  ai/                — provider adapter, retrieval, citation binding, prompt templates
  api/               — HTTP routes (explore, compare, plan, saved, admin/publishing)
  web/               — server-rendered HTML pages (Jinja2 templates, Tailwind-built CSS
                        in app/static/) -- the actual clickable journey; distinct paths
                        from api/'s JSON routes, calling the same assembly functions
  static/            — compiled CSS + any other static assets served directly
tests/
  unit/, e2e/, fixtures/   — fixtures are clearly labelled synthetic, never published as facts
```

## Layered read/write rules (mirrors the national DPR's layering, Section 8)
- Public tools (Explore, Compare, calculators) read the decision layer +
  knowledge base. No student vault access.
- The AI/guidance layer reads the knowledge base (retrieval) but has
  **no write access** to it and **no access** to the student vault.
- Only the publishing console (maker-checker, `rules/` + `api/admin`) writes
  verified facts. Claude/AI may *extract* a candidate fact from a source; it
  may never mark its own extraction verified.

## Background work
Postgres jobs table with `status`, `lease_until`, `attempts`,
`idempotency_key`. One worker polls with a lease; retries bounded; no job
processed twice by design (idempotency key), not by luck.

## Deployment flow (once hosting is provisioned)
Feature branch (synthetic data) → PR runs checks with **no production
secrets** → preview against staging only, restricted callbacks/origins →
reviewer findings resolved, checks rerun → owner approves the exact release
commit + migration plan → protected GitHub Actions environment applies
additive migrations and deploys to the production container → smoke tests →
monitor. Schema changes are append-only migration files, never dashboard
edits. No production credential lives in the everyday dev environment.

## Data residency
See `docs/SECURITY.md` for the full data-flow map (Lite Build Pack §8). Mumbai
database region does not by itself make the system India-only — logs,
monitoring, email and model processing are separate flows with their own
regions, tracked individually.

## AI
Ask BCION is a **two-pass** pipeline, and ordinary code — never the model —
writes every sentence a student reads.

Pass one (selection): the model is given a fixed prompt template plus the
retrieved, published records, and must answer with record ids only. Pass
two (verification): a second, adversarial call is made over *only* the ids
pass one selected, asking whether each one actually supports the question;
it may drop ids, never add them. Code validation then runs last: the
surviving ids are resolved against the same records fetched once at
retrieval (no second database fetch), and the sentences are generated from
those records' own fields. **Correction, 2026-09-23 audit**: the
banned-phrase guard does *not* run over each request's generated sentences
— it runs once, at process start, over the fixed template label strings
only (`app/ai/prompts.py`), on the reasoning that those never change
between requests. A claim *value* that happened to contain banned language
would reach a student unscanned; closing this (a genuine per-request scan
over generated sentences) is tracked as follow-up work, not done here. A
response that fails any earlier stage is discarded whole and degrades to a
status (`app/ai/schemas.py`'s `AIAnswerStatus`) — never repaired, never partially
salvaged.

The model therefore never authors user-facing prose. Its entire output
surface is a set of ids; "what the answer says" is a pure function of the
verified records plus code. That is what makes "AI never invents facts"
testable rather than aspirational.

**Free tier, no student text.** No student-typed text is ever sent to the
provider — a student picks a prompt template, they do not write a question.
`OutboundPayload` (`app/ai/schemas.py`) is the only permitted wire shape and
carries exactly four fields: `template_id`, `record_ids`, `record_values`,
`lang`. It forbids extra fields and requires every value to be namespaced by
an allow-listed record id, so there is no channel through which free-typed
text, PII or vault data could reach a hosted model even by mistake.
