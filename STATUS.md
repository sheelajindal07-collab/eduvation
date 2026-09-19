# Status

**Milestone:** M0 complete (BCI-001). **Commit:** `4c06a4d` on `main`
("M0 bootstrap: BCION Lite repo, memory files, app shell (BCI-001)").

## What works right now
`make lint`, `make typecheck`, `make test-unit` all pass for real (see
`tasks/BCI-001.md` for exact output). The FastAPI app boots
(`uvicorn app.main:app`) and serves `/healthz` and `/docs` live. No
database, no auth, no AI calls yet — by design, per the M0 scope.

## Blockers
None for continuing engineering work. Real blockers are owner decisions,
not technical ones — see "Needs your input" below. Engineering can proceed
on synthetic fixtures regardless.

## Next task
**BCI-002 — M1 first vertical slice**: published career record → explore
→ compare two options, on synthetic fixtures, backed by a real staging
Supabase/Postgres with RLS actually enforced and tested. See
`tasks/BCI-002.md` for the full breakdown. This is the first task that
benefits from — but is not strictly blocked by — a real Supabase project;
it can start against a local Postgres if nothing is provisioned yet.

## Needs your input (tracked in full in `docs/DECISIONS.md`)
1. **Pilot state** — assumed Gujarat per Annex C.2's suggestion "if
   confirmed." Confirm or name another state before the content track
   writes real admission-rule content.
2. **AI provider** — assumed Anthropic (adapter pattern keeps this cheap
   to change). Doesn't block anything before M5.
3. **What's already provisioned** — do you have a Supabase project, a VPS,
   a WhatsApp Business/Cloud API account, or an AI provider key already,
   or should M1 target local/free-tier infrastructure until those exist?
4. **Named content reviewers** — who verifies the 50–100 programme
   records, 8–10 exam rule sets and 10–20 scholarships (Annex C.3)? The
   publishing console itself doesn't need a specific name to be built, but
   the content track (the DPR's own "long pole," Annex C Problem #2)
   can't produce real, publishable content without a reviewer assigned.
5. **Stack confirmation** — silence keeps the pinned FastAPI/Supabase/VPS
   stack (`docs/DECISIONS.md`). Only say something if you want the
   Next.js/Vercel alternative (Annex F.2's stated flip condition: you want
   Claude Code, not yourself, to remain long-term front-end maintainer
   with per-PR preview deployments).

## Not claimed
No RLS test, no e2e test, no live AI call, no deployment has happened.
`make test-db`, `make test-e2e` and `make build` are intentionally
placeholder targets (see `Makefile`) until M1/M5/hosting respectively
give them something real to run against.
