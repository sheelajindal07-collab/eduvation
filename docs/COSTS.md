# Costs

Four ledgers (`CLAUDE.md` "Spend controls"). Updated by the lead once
per merge batch — not a live dashboard, a running log.

## 1. Development agents (tokens, sessions)
| Date | Batch | Sessions by tier (strongest/standard/cheap) | Fix rounds | Rate-limit stalls | Notes |
|---|---|---|---|---|---|
| 2026-09-21 | DOCS-1, DOCS-3a | 0 / 3 / 0 | 0 | 0 | Lead-only, on main |

Per-batch metrics line (append one row per merge batch, in the format
above). **Tripwire** (plan section 8.6): if a wave's actual sessions
exceed its planned count by more than 25%, or fix rounds exceed 1 in 4
cards, the next wave's writer cap drops by 2 and no seat is added
without an owner `docs/DECISIONS.md` line.

## 2. Application inference (AI spend)
Not applicable yet — `AI_ENABLED` does not exist in `app/` (AI-2 adds
the flag, default off). Nothing here until Phase 2.

## 3. Hosting and monitoring
- Oracle VM (`eduvation.service`) — existing, shared with other
  projects, ₹0 incremental for BCION Lite.
- Supabase project — one project today (used since M1), no separate
  staging project yet (DEPLOY-4/DEPLOY-7 gap).
- No monitoring vendor chosen yet (OPS-4).

## 4. Human verification and support
- Owner hours: tracked in `docs/DEVELOPMENT-PLAN.md` section 10's
  per-session estimates, not duplicated here until actuals exist.
- Reviewer/editor honoraria: not yet paid — no reviewers named yet
  (CONTENT-1, CONSENT-2 are still open owner actions).

## Seat plan (plan section 8.6, decision A4)
One Claude Code subscription seat through the early waves. Add a
second seat at the first sign of a lane blocked more than 30 minutes on
rate limits — it is already inside the plan's budget range. No third
seat or API overflow without an explicit owner yes and a rupee cap.
