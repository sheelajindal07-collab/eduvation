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

## Infrastructure (confirmed 2026-09-19)
Supabase, GitHub, Oracle hosting and a Gemini API key are ready — **on
accounts separate from this dev machine's connected tools**. The GitHub
CLI here is signed in as `maheshjin-bot`; the Supabase MCP tool here only
sees an unrelated org (`ridhivi`) with no free slot. Neither was touched
beyond read-only checks, and **the Supabase MCP tool will not be used on
this project again** per your instruction. Schema work proceeds as plain
SQL migration files in the repo for you to apply yourself.

## Needs your input (tracked in full in `docs/DECISIONS.md`)
1. **GitHub repo** — give a URL (existing empty repo on your account) or
   say "create one" + which account, so I can add a remote and push.
2. **Supabase project URL** — once you've created a project on your own
   account (region: Mumbai/`ap-south-1` recommended, matching
   `docs/SECURITY.md`'s residency table), give me the project URL (not
   secret) so docs can reference it; put the actual keys straight into
   your own local `.env` — never paste secret values into chat.
3. **Pilot state** — still assumed Gujarat (Annex C.2, "if confirmed").
   Confirm or name another state before the content track writes real
   admission-rule content.
4. **Named content reviewers** — who verifies the 50–100 programme
   records, 8–10 exam rule sets and 10–20 scholarships (Annex C.3)? Not
   blocking engineering, but blocks real publishable content.
5. **Gemini model** — confirmed provider is Gemini; which model (flash vs
   pro) can wait until M5 unless you have a preference now.
6. **Stack confirmation** — silence keeps the pinned FastAPI/Supabase/VPS
   stack. Say so only if you want the Next.js/Vercel alternative.

## Not claimed
No RLS test, no e2e test, no live AI call, no deployment has happened.
`make test-db`, `make test-e2e` and `make build` are intentionally
placeholder targets (see `Makefile`) until M1/M5/hosting respectively
give them something real to run against.
