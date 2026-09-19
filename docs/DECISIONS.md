# Decisions log — BCION Lite

Dated decisions with reasons. Newest first. A superseded decision is marked,
never deleted.

---

## 2026-09-19 — Reservation/quota engine: out of scope for Lite
**Decision:** No reservation/quota engine (state-quota, category-wise
seat-reservation percentages) is built for BCION Lite. `docs/rules/`
stays at the three engines the Lite Build Pack §6 rules contract
actually names: eligibility, cost, timeline.
**Reason:** `docs/ARCHITECTURE.md`'s directory comment for `app/rules/`
lists "eligibility, cost, timeline, reservation" — but that comment
describes the *national* DPR's full decision-engine set
(`docs/BCION-DPR-v1.1.md`), not a commitment Lite's own build pack made.
Lite Build Pack §6 ("Data and rules contracts") only specifies
eligibility, timeline and cost; reservation/domicile rules in the
national DPR carry state-specific legal review and quota complexity
(see `docs/BCION-DPR-v1.1.md`'s reservation/domicile risk entries) that
is explicitly national-platform scope, not Phase −2 pilot scope
(CLAUDE.md: "a technical spike and measurement instrument, not the
national platform"). Building it now risked scope creep with no product
owner sign-off.
**Owner confirmed:** leave it out of Lite; revisit only if a future
national-platform phase needs it.
**Owner action needed:** none. If this changes, update this entry and
`docs/ARCHITECTURE.md`'s `app/rules/` comment together so they stop
disagreeing.

## 2026-09-19 — DPR annex structure reconciled with the online v1.2 doc;
## new `docs/BCION-Lite-Build-Pack.md` is now Lite's operating spec
**Decision/event log:** The living Claude Doc ("BCION — DPR and White Paper
v1.1") was restructured upstream (its "v1.2" tab) since this repo's
`docs/BCION-DPR-v1.1.md` was written: the old Annex C (10–100 user pilot
review), Annex E (Claude Code execution blueprint) and Annex F (step-by-step
build guide) were consolidated into one companion document, the "Lite build
pack" tab, and Annex C/D were repurposed to a Glossary and an Assumptions
register respectively; Annex F no longer exists as a separate annex.
`docs/BCION-DPR-v1.1.md` has been updated to match: its old Annex C/D/E/F
content (the "Problems" review tables reasoning from the four original
source documents to the adopted decisions) is removed from the live file —
fully recoverable from git history before this commit — and replaced with
the new Annex C (Glossary), Annex D (Assumptions register) and a short
Annex E pointer. The full Lite operating plan (scope, stack, interface
brief, data contracts, operating rules, data-flow map, 16-step schedule,
budget, gates, Step 1 prompt, daily prompts) now lives in the new
`docs/BCION-Lite-Build-Pack.md`, mirroring the online doc's "Lite build
pack" tab word for word (including the Gemini/Mumbai infra confirmations
synced into that tab the same day). `CLAUDE.md`'s Mission and Links
sections were updated to point at the new file.
**What this changes:** Citations to "Annex C.2/C.3", "Annex D.2/D.3",
"Annex E.2/E.3/E.5/E.6" and "Annex F/F.2/F.3/F.4" scattered through
`docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/UI.md`, `docs/DATA.md`,
`docs/SECURITY.md`, `STATUS.md`, `tasks/BCI-001.md`, `tasks/BCI-002.md`,
`app/ai/__init__.py`, `app/db/client.py`, `app/db/__init__.py`,
`app/rules/__init__.py`, `app/data/models.py`, `db/migrations/0001_init.sql`,
`Makefile`, `.github/workflows/ci.yml` and the `.env*` comments now point
at annex sections that hold different content (C, D) or no longer exist
(F). The facts those citations describe are still correct and now live in
`docs/BCION-Lite-Build-Pack.md`'s numbered sections (3 Decisions, 4 Stack,
5 Interface brief, 6 Data and rules contracts, 7 Operating rules, 8
Data-flow map, 9 Master schedule, 12 Gates, 14 Step 1 prompt) — only the
citation labels are stale, not the content they point to.
**Status:** `docs/BCION-DPR-v1.1.md`, `docs/BCION-Lite-Build-Pack.md` and
`CLAUDE.md` done. The ~15 files listed above are **not yet updated** —
deliberately paused for owner confirmation before touching application
source code, CI config and env-file comments, particularly since the
GitHub-connection entry below shows another session concurrently active
on this same repo.
**Owner action needed:** say go-ahead (or hand-pick which files) to sweep
the remaining stale annex citations; each is a label-only fix (low risk,
git-reversible) but several are source files a concurrent session may
also be touching right now.

## 2026-09-19 — GitHub repo connected; two exposed secrets rotated
**Decision/event log:** Owner gave the repo URL
(`github.com/sheelajindal07-collab/eduvation`); this machine's account
(`maheshjin-bot`) had no access, so the owner sent a collaborator invite,
which was found and accepted via `gh api` (not the web UI), then all
commits were pushed. First CI run failed on a real, previously-unseen bug
(`setuptools` flat-layout package discovery choked on `db/` existing
alongside `app/` — never triggered locally since the editable install
had only run once, before `db/` existed); fixed with an explicit
`[tool.setuptools.packages.find]`, reproduced and re-verified the fix
locally before pushing, CI green on the next run. Owner then confirmed
rotating the two secrets pasted in chat earlier (JWT secret, service-role
key) — re-ran `make test-db` afterward and all 9 tests still pass,
confirming the new values are correctly in the owner's local `.env`.
**Status:** Done. Repo live with passing CI; no known exposed secrets
remain live.

## 2026-09-19 — Supabase project: "project education" (Singapore) not used;
## a fresh Mumbai (ap-south-1) project will be created instead
**Decision:** The owner showed an existing Supabase project, "project
education" (org "education", free tier, `ap-southeast-1` / Singapore,
ref visible as `auxdtzizsdjjgmksaiur` — unverified transcription from a
screenshot; re-confirm before relying on it for anything). Given the
choice between keeping it or creating a fresh India-region project, the
owner chose to create a new one in `ap-south-1` (Mumbai), matching
`docs/SECURITY.md`'s residency table. `project education` is **not**
used for BCION Lite and was not touched.
**Status:** DONE. Owner created a new project, also displayed as "project
education" (same org, confusingly the same display name as the Singapore
one — they are different projects) but region **South Asia (Mumbai),
ap-south-1**, compute `t4g.nano`. Project URL (from a screenshot,
re-verify against your own dashboard if anything seems off):
`https://bvacroguuhgqufelascd.supabase.co`. Status "Healthy", no
migrations applied yet, no repo connected, no backups yet — a genuinely
fresh project.
**Owner action needed next:** apply `db/migrations/0001_init.sql` via
this project's SQL Editor (paste the file's contents, click Run), then
put `SUPABASE_URL=https://bvacroguuhgqufelascd.supabase.co` plus the
anon/publishable key and JWT secret (Project Settings → API Keys) into
your own local `.env` — keys never shared in chat.

## 2026-09-19 — Migrations applied via a direct script, not the dashboard
## or the MCP tool, going forward
**Decision:** Owner applied `0001_init.sql` manually via the SQL Editor
once, confirmed working (all 9 RLS tests pass live), then said not to
require that manual step again. Since the Supabase MCP tool and any
equivalent management-API route are both off-limits (per the earlier
"Infrastructure accounts" entry), the alternative is a direct Postgres
connection: `scripts/apply_migrations.py`, using `psycopg` and a
`DATABASE_URL` the owner puts in their own `.env` — never in chat, never
committed. It tracks applied migrations in a `_schema_migrations` table
so re-running is safe. This is fully auditable (it's ~80 lines, read
top to bottom) and touches only the one database `DATABASE_URL` points
at — categorically different from a broad management-API/MCP capability.
**Status:** Script written, lint/typecheck clean. Not yet run (no
`DATABASE_URL` in `.env` yet) — `0001_init.sql`'s effects already exist
in the database (applied manually), so the first real run needs to
record that fact in `_schema_migrations` rather than re-apply it (see
`db/migrations/README.md` "One-time bootstrap note").
**Owner action needed:** add `DATABASE_URL` to your local `.env`
(Project Settings → Database → Connection string → URI, password filled
in yourself) whenever you're ready for me to apply future migrations
directly instead of using the SQL Editor.

## 2026-09-19 — AI provider naming fixed: Gemini, not a stale Anthropic
## field name left over from the original (superseded) assumption
**Decision:** `app/core/config.py`'s `anthropic_api_key` field and
`ai_provider` default were still "anthropic" even though the Gemini
decision (above) was recorded the same day — an inconsistency between
the docs and the code. Renamed to `gemini_api_key` / default `"gemini"`;
`.env.example` and `app/ai/__init__.py`'s docstring updated to match.
Caught while fixing `tests/unit/test_health.py` (below), not something
the owner had to flag separately.
**Status:** Done. No behaviour change (M0–M4 make no AI calls either way).

## 2026-09-19 — GitHub: owner will create the repo on their own account
**Decision:** The owner is on a GitHub account different from this
machine's authenticated `gh` CLI (`maheshjin-bot`) and has no repo yet.
They'll create one themselves (private, e.g. `bcion-lite`) and set up
push credentials for that account on this machine (e.g. a personal
access token via `gh auth login` or a credential-manager entry) — I will
not use the `maheshjin-bot` session for this project.
**Status:** Waiting on the repo URL + local credentials being ready.
**Owner action needed:** create the repo, tell me the URL, and confirm
push access works locally (or say if you'd like help setting up the
credential once the repo exists).

---

## 2026-09-19 — Infrastructure accounts: owner-provided, separate from this
## machine's connected tools; MCP/CLI management tools not used for them
**Decision:** The owner confirmed Supabase, GitHub, Oracle hosting and a
Gemini API key are ready to use — but on accounts **different** from the
ones already authenticated in this dev session (GitHub CLI was signed in
as `maheshjin-bot`; the session's Supabase MCP tool only saw an org named
`ridhivi` with unrelated projects and no free-project slot). The owner
explicitly said to use different accounts and **not to use the Supabase
MCP tool** for this project.
**What this changes:**
- No project was created and nothing was touched in the `ridhivi`
  Supabase org or under `maheshjin-bot` on GitHub (checked read-only:
  `list_projects`/`list_organizations`/`get_cost`/`confirm_cost` — no
  write action was taken before the instruction arrived).
- Supabase schema work proceeds as **versioned SQL migration files in the
  repo** (`db/migrations/`), for the owner to apply via their own
  project's SQL editor or the Supabase CLI — not applied by an agent
  through the management API.
- GitHub remote/push is deferred until the owner gives a repo URL (their
  own account) or says to create one there.
- AI provider: "Gemini API ready" is read as Google Gemini; the adapter
  interface is written provider-agnostic regardless (per Annex E.2), so
  this costs nothing to get right or wrong before M5.
- Oracle hosting: noted ready; specifics (region, compute shape, whether
  Docker is already installed) are gathered when deployment work starts
  (M6 / Annex F Step 13-14), not blocking now.
**Status:** Confirmed by owner. Supersedes the 2026-09-19 "Hosting ...
not yet provisioned" entry below for account *availability*, but not for
account *identity* — real URLs/keys are still not in this repo and still
won't be; only `.env`, never committed (`CLAUDE.md` non-negotiable).
**Owner action needed:** when ready, give (a) the GitHub repo URL to push
to (or "create one, here's the account"), and (b) confirm Gemini vs a
different provider. Supabase project URL/keys go straight into your own
local `.env` — never paste them into chat.

---

## 2026-09-19 — Stack pinned to FastAPI/Supabase/VPS (not Next.js/Vercel)
**Decision:** Use the Annex E.2/F.2 pinned stack (FastAPI monolith, Supabase
Mumbai, Tailwind + server-rendered templates or a light PWA, one VPS worker,
n8n off the request path) as the default for this repo.
**Reason:** Annex F.2 states one condition for using Next.js/Vercel instead:
the owner intends Claude Code (not themself) to remain the front-end
maintainer long-term and wants per-PR preview deployments. That condition
has not been stated by the owner. The pinned stack is also runnable and
testable without a paid hosting account (local `uvicorn`, local/staging
Postgres), which fits where this project currently is (pre-provisioning).
**Status:** Assumption — flip only via an explicit owner instruction,
recorded here.
**Owner action to confirm or flip:** none needed to keep this; say so
explicitly to switch to Next.js/Vercel.

## 2026-09-19 — Pilot state: Gujarat (assumed, pending confirmation)
**Decision:** Draft/scaffold content assumptions (admission body names,
CET name) around Gujarat: GSEB, GUJCET, ACPC (engineering/pharmacy),
ACPUGMEC (medical), GCAS (general degree) — names to be verified against
current official sources before any content is published.
**Reason:** Annex C.2, problem #8 names Gujarat as "the natural choice for
a Surat-based builder," explicitly "if confirmed." No confirmation has been
given yet.
**Status:** Assumption, [PA]. Does not block M0 (no real content is
published at M0). **Must be confirmed before the content track starts
writing real Gujarat-specific admission rules (Annex F.4, alongside Step 1,
week 1).**
**Owner action needed:** confirm Gujarat, or name a different pilot state.

## 2026-09-19 — AI provider: Anthropic Claude API (assumed)
**SUPERSEDED same day — see below.** Original text kept for the record:
implement the AI provider adapter (`app/ai/`) against the Anthropic
Messages API first, behind a provider-agnostic interface. Reason: no
provider was specified in the annexes beyond "one hosted model behind a
provider adapter"; Anthropic was the reasonable default in a Claude Code
project.

## 2026-09-19 — AI provider: Google Gemini API (owner-confirmed)
**Decision:** Owner confirmed "Gemini API ready." Adapter
(`app/ai/`, built at M5) targets the Gemini API as the first
implementation, behind the same provider-agnostic interface — swapping
providers later stays a small, contained change.
**Status:** Confirmed. Still does not require a live key until M5;
M0–M4 make no AI calls.
**Owner action needed:** none, unless you want a specific Gemini model
pinned (e.g. flash vs pro) ahead of M5 — otherwise that's chosen at M5
based on the cost/latency numbers at the time.

## 2026-09-19 — Hosting/Supabase/n8n/WhatsApp: not yet provisioned
**PARTIALLY SUPERSEDED same day** — see "Infrastructure accounts" entry
above. Supabase and Oracle hosting are confirmed ready by the owner (on
accounts separate from this session's connected tools, which must not be
used to manage them). n8n and WhatsApp Cloud API status is still
unconfirmed. Original text kept for the record: all external accounts
were assumed not yet provisioned, built to run and test locally
(`uvicorn`, pytest, ruff, mypy) without requiring any of them; reasoning
was that Annex C/E/F's cost tables read as if a VPS, a Supabase project
and WhatsApp access already existed for "a builder who runs FastAPI,
Supabase, n8n and the WhatsApp Cloud API" with nothing in this repo
confirming that for *this* project.
**Still open:** n8n instance status; WhatsApp Business/Cloud API status;
Oracle hosting specifics (region, compute shape, Docker availability) —
gathered at the deployment milestone (M6), not blocking now.

## 2026-09-19 — Named fact reviewers: not yet assigned
**Decision:** The publishing console (maker-checker) is built so that ANY
two distinct accounts can act as maker/checker; no specific person is
hard-coded. Real content review capacity (who actually verifies the 50–100
programme records, 8–10 exam rule sets, 10–20 scholarships) is an open
owner decision, tracked in `STATUS.md`, not blocking M0–M3 engineering.
**Reason:** Annex C's Owner Checklist before M0 lists "pilot scope and the
named fact reviewers" as an owner decision; Annex C's Problem #2 says the
content track (not the code) is the actual long pole.
**Owner action needed:** name who verifies content (yourself, an editor,
a small reviewer pool) before Week 1 of the content track in earnest.

## 2026-09-19 — Repository and version control
**Decision:** Git-initialised in place (`F:\the competetion project`),
branch `main`. No remote configured. The dev machine's GitHub CLI is
signed in as `maheshjin-bot`, but the owner uses a **different** GitHub
account for this project — that account was not used or touched.
**Reason:** Annex E.4 owner checklist item ("repository location and
branch permissions"); the working directory was already given.
**Owner action needed:** give the target repo's URL (existing empty repo)
or say "create one" plus which account, so a remote can be added and
`.github/workflows/ci.yml` starts running.
