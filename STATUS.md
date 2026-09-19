# Status

**Milestone:** M0 (BCI-001), M1 (BCI-002), **M2 all DONE** (BCI-003).
**M3 starting** (BCI-004). **Commit:** see `git log -1` on `main`.
**Repo:** [github.com/sheelajindal07-collab/eduvation](https://github.com/sheelajindal07-collab/eduvation),
CI green. **Hosting:** live on the Oracle VM (`eduvation.service`,
verified healthy, talking to the real database).

## What works right now — live routes, all verified
- `GET /careers` — published careers/pathways.
- `GET /compare?pathway_id=X&pathway_id=Y` — trust-labelled comparison
  fields plus a real computed `net_to_arrange` (not just a raw claim
  value); `?estimated_additional_expenses=` overrides the assumption for
  one request, never persisted; a missing verified-charges claim still
  correctly returns `net_to_arrange: null`, even with an override
  present.
- `GET /eligibility?pathway_id=X&age=..&marks_percentage=..&...` —
  criteria built **dynamically from a pathway's own published claims**,
  never hardcoded per exam. No claims published → vacuously `meets`,
  not a fabricated unknown.
- `POST /timeline` — stateless Career Life Span Calculator; client sends
  editable stages, gets the computed total, honest about unknown
  durations and overlap.
- Deployed on your Oracle VM alongside `hisab`/`lekha`/`attendance-app`,
  same conventions, nothing else touched.

**110 tests passing** (92 unit + 18 live DB), lint/typecheck clean, CI
green on every push this session.

## Blockers
None.

## Next task
**M3 — sign-in, saved plans, consent** (`tasks/BCI-004.md`, just
started). First slice: guest sessions made explicit, Supabase Auth
sign-in/sign-up, a `saved_plans` table with RLS, guest→account
migration. Explicitly NOT in this first slice: the distress/support
queue (needs M5's AI surface), full consent/safeguarding for real minor
accounts (a separate, deliberately gated decision), export/deletion.

## Infrastructure
| Thing | Status |
| --- | --- |
| Supabase | **Live.** Mumbai (`ap-south-1`), schema applied, RLS verified. |
| GitHub | **Live.** `sheelajindal07-collab/eduvation`, CI green. |
| Oracle hosting | **Live.** `eduvation.service` on `moulding-app-a1`, port 8010 (localhost only — no public domain/nginx site yet). |
| AI provider | Gemini, owner-confirmed. Not used before M5. |

## Needs your input — none blocking
1. **Public domain** — if you want the app reachable from outside the
   VM, send a domain/subdomain and I'll add an nginx site.
2. **Pilot state** — still assumed Gujarat, confirm or correct.
3. **Named content reviewers** — not blocking engineering.
4. **Gemini model** — can wait until M5.

## Not claimed
No e2e test, no live AI call, no public exposure of the deployed app
yet. No real content exists — every test uses clearly-labelled synthetic
fixtures; nothing has been published as a verified fact for an actual
student to see.

## Concurrent sessions — multiple sessions worked this repo today
This session shared the repo with at least one other active Claude
session for a significant stretch (same machine, same working
directory, not separate clones). Coordination happened via direct
cross-session messaging: file-touch lists exchanged before editing,
commits deliberately kept separate when both sides had uncommitted work,
and a real circular-import bug (comparison.py <-> cost.py) was caught
independently by both sessions within moments of each other and
confirmed fixed before either committed further. See `docs/DECISIONS.md`
for the full log. If you're running multiple sessions on purpose, this
worked cleanly; if not, worth knowing — check `git log`/`git status`
before starting a new session's task.
