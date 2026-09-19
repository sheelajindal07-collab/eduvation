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
| AI | One hosted provider behind a provider adapter; per-account and global spend caps; 15s timeout | No GPU, no multi-vendor gateway in Lite |
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
