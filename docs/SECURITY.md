# Security & privacy — BCION Lite

Source: `docs/BCION-Lite-Build-Pack.md` §3 (Decisions — Residency), §4
(Stack), §8 (Data-flow map).

## Access model
- Application connects to Postgres as a **restricted role**, never the
  Supabase owner/service role, for any user-facing request.
- Row-level security (RLS) is enforced by passing the **signed-in user's
  access token** to Postgres on every request (`supabase-py` with the
  user's token, or per-request role/claims on a direct connection) — not by
  relying on a JS client's defaults. This is a Step-4/M1 contract, and it
  is tested (`make test-db`) on every table, view and storage bucket that
  is exposed.
- Access matrix tested on every auth/RLS/publication change: **guest,
  student A, student B, reviewer** × read/write/delete/export/storage.
  Cross-user reads/writes must fail; tests must NOT run as the database
  owner (owner bypasses RLS and would hide a real bug).

## Consent & safeguarding (a launch gate, not a checkbox)
Real accounts for minors stay **disabled** until this workflow is built and
reviewed by a person (not model review alone):
- Guardian identity via a verifiable route (school-mediated consent using
  the school's own records, or another route confirmed in Phase 0/−1 of
  the national DPR) — no identity documents collected by Lite itself.
- Consent is separate and revocable per purpose (saving marks/category/
  income, sharing a parent view, contacting an institution).
- A named staff member reviews the consent design before any real minor
  account is enabled.
- **Distress rule**: a keyword rule (Hindi + Hinglish + English) returns
  the national tele-mental-health helpline info and flags a named staff
  member within 24 hours. No counselling is promised by the software.

## Publishing security
- Author ≠ approver, enforced server-side (DB constraint / RLS policy),
  never just a disabled UI button.
- Approval binds to the exact draft content (hash/version); any edit after
  approval invalidates it.
- AI may extract a candidate claim; it can never set `status = published`.

## AI / LLM controls
- No write access to the database from the AI/guidance layer.
- No access to the student vault from the AI/guidance layer.
- PII redaction before any external model call — no names, phone numbers,
  identifiers; only retrieved records + stated interests/constraints go out.
- 15-second timeout; atomic per-request spend reservation; global + per-
  account spend caps; graceful fallback to deterministic tools at the cap.
- Retrieved external text (sources, imported catalogues) is treated as
  **data, never as instructions** — prompt-injection and data-poisoning
  resistance for the extraction pipeline.
- SSRF controls on the source fetcher (allow-listed domains only).

## Quality gates (must pass before any release)
- **Calculators:** zero values, boundaries, missing inputs, overlapping
  durations, rounding.
- **Eligibility:** cycle/jurisdiction, unknowns, cut-off dates, rule
  version.
- **Access:** guest/student A/student B/reviewer × read/write/delete/
  export/storage.
- **Publication:** separate maker/checker, exact draft approval,
  invalidation on edit.
- **AI:** wrong source IDs, unsupported claims, stale evidence, prompt
  injection, timeout, overspend.
- **Privacy:** PII-free logs, logout/cache behaviour, authorised
  export/deletion.
- **UI:** mobile + desktop, keyboard, screen-reader spot checks, Hindi text
  expansion, every error state.
- **Operations:** fresh migration, staging deploy, monitoring alert,
  backup restore.

No known critical/high security issue ships. A lower-severity exception
needs a named owner, a rationale and an expiry. **Model review alone never
signs off child data or production security** — a person does.

## Data-flow map (residency — replaces any blanket "India-only" claim)
| Flow | Where | Personal data? | Control |
| --- | --- | --- | --- |
| Database, auth, file storage | Supabase, South Asia (Mumbai, `ap-south-1`) — confirmed 2026-09-19, see `docs/DECISIONS.md` | Yes | RLS, restricted role, field-level encryption for optional sensitive fields |
| Application + worker | VPS, Mumbai (once provisioned) | Yes, in transit/memory | No personal data in logs; isolated containers; staging separate |
| Database backups | Supabase-managed; region to confirm at provisioning | Yes | Daily backups; point-in-time recovery only if a day's loss is unacceptable |
| Runtime AI requests | Hosted model provider; region may be outside India | No — PII redacted; retrieved records + stated interests/constraints only | Provider terms reviewed for retention/training; restricted key; spend cap |
| Error tracking / uptime | Monitoring vendor; region recorded at sign-up | No — payloads scrubbed, no session replay | Vendor region + retention noted here once chosen |
| WhatsApp reminders | Meta Cloud API | Phone number + deadline template | Opt-in only; template carries no personal field beyond first name |
| Transactional email (if used) | Provider; region recorded | Email address | Domain verified, delivery tested |
| Development agents (Claude Code) | Owner's machine | **Never** | Synthetic fixtures only; staging keys only |

**Rule:** a real minor's personal data does not enter the system until every
row above has a confirmed region and the owner has accepted this map in
writing. "India-only" is a statement about this table, not about the
database region alone.

## Standards (aspirational for Lite scale, tracked for the national plan)
CERT-In incident-reporting awareness; no production credential in the
everyday Claude Code development environment; secrets via provider
dashboards only, never committed or written to memory files.
