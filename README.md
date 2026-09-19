# BCION Lite

A 10–100 user career-decision pilot for Indian students (Class 8–12) —
explore career pathways, compare them side by side, and see verified
time/cost/eligibility, with every fact carrying a source and a trust label.

This is **Phase −2** of the larger *Bharat Career Intelligence & Opportunity
Network (BCION)* DPR — a technical spike and measurement instrument, not
the national platform. See [`docs/BCION-DPR-v1.1.md`](docs/BCION-DPR-v1.1.md),
Annexes C–F, for the full specification this repo implements.

## Start here
- [`CLAUDE.md`](CLAUDE.md) — operating rules, non-negotiables, verified commands
- [`STATUS.md`](STATUS.md) — current milestone, blockers, what needs your input
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — every assumption made and why
- [`docs/PRODUCT.md`](docs/PRODUCT.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
  [`docs/UI.md`](docs/UI.md), [`docs/DATA.md`](docs/DATA.md),
  [`docs/SECURITY.md`](docs/SECURITY.md)
- [`tasks/`](tasks/) — task cards, one per milestone slice

## Quick start (development)
```bash
python -m venv .venv
./.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
make dev                        # http://127.0.0.1:8000/healthz and /docs
```

```bash
make lint          # ruff
make typecheck      # mypy
make test-unit       # pytest
```

No database or AI provider is required to run the above — `/healthz`
honestly reports what's configured and what isn't.

## Stack (pinned — see `docs/DECISIONS.md`)
FastAPI · Supabase (Postgres/Auth/Storage, RLS) · Tailwind · a Postgres
jobs-table worker · n8n (off the request path) · one hosted AI provider
behind an adapter · pytest/Playwright/ruff/mypy · GitHub Actions.

## Status
M0 (bootstrap) complete. See [`STATUS.md`](STATUS.md) for what's next and
what decisions are waiting on you.
