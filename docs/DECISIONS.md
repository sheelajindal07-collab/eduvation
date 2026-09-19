# Decisions log — BCION Lite

Dated decisions with reasons. Newest first. A superseded decision is marked,
never deleted.

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
**Decision:** Implement the AI provider adapter (`app/ai/`) against the
Anthropic Messages API first, behind a provider-agnostic interface so a
second provider can be added without touching callers.
**Reason:** No provider was specified in the annexes beyond "one hosted
model behind a provider adapter." This is a Claude Code project; Anthropic
is the reasonable default and the adapter pattern keeps the cost of being
wrong low.
**Status:** Assumption. Does not require an API key until M5 (bounded AI
milestone) — M0–M4 use no live AI calls.
**Owner action needed:** confirm, or name a different provider/model.

## 2026-09-19 — Hosting/Supabase/n8n/WhatsApp: not yet provisioned
**Decision:** Treat all external accounts (Supabase project, VPS, n8n
instance, WhatsApp Business/Cloud API, AI provider key, monitoring vendor)
as **not yet provisioned**. Build M0–M4 to run and test locally
(`uvicorn`, pytest, ruff, mypy) without requiring any of them. Environment
variables are named and documented (`.env.example`) but left unset.
**Reason:** Annex C/E/F's cost tables and stack descriptions read as if a
Mumbai VPS, an existing Supabase project and WhatsApp access already exist
("a builder who runs FastAPI, Supabase, n8n and the WhatsApp Cloud API").
No evidence in this repo or from the owner confirms these are actually
provisioned yet for *this* project.
**Status:** Assumption. Explicitly flagged for the owner — see
`STATUS.md` "Needs your input."
**Owner action needed:** confirm what's already provisioned (Supabase
project? VPS? domain? WhatsApp Business account? AI provider account?) so
`.env.example` values and `docs/SECURITY.md`'s data-flow map can be
finalised with real regions instead of placeholders.

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
branch `main`. No remote configured yet.
**Reason:** Annex E.4 owner checklist item ("repository location and
branch permissions"); the working directory was already given.
**Owner action needed:** none required now; add a GitHub remote when ready
to enable the CI workflow in `.github/workflows/`.
