# Contracts

Frozen shared definitions every parallel lane builds against. **1,500-word
cap for this whole file** — a contract states the decision and the
reason in a sentence or two, it does not re-explain the feature.

Filled by the Wave 1 contract burst, strictly serial, one section each:
SCOPE-2 -> RULES-1 -> PUB-1 -> CONTENT-2 -> AUTH-1 -> CONSENT-3 ->
A11Y-1. After the burst merges, changes here are additive only and need
a `docs/DECISIONS.md` line from the lead. A heading still showing
`<TASK>` is not frozen yet.

## Money and currency

`Money` is one value type: an **integer** `amount` in the currency's major
unit (whole rupees, whole pounds — never paise, never a float) plus an
ISO 4217 `currency`, default `INR`. Amounts are never converted: no FX
rate exists anywhere in Lite. Components sum only within one currency; a
total over mixed currencies is `None` with reason `mixed_currencies`,
shown to the student, never silently dropped or coerced. A money claim
with a null currency renders `not_available`. One formatter,
`format_money(amount, currency)` — no currency symbol literal may exist
outside it.
**Settled:** RULES-10 introduces `Money` in every component and total
signature, so the type changes once; SCOPE-4 is then limited to the
no-cross-currency-sum guard, display and the template.

## Duration, dates, cycle, DOB

"Today" is the current date in Asia/Kolkata, computed server-side; every
`as_of` defaults to it and the client's clock is never trusted. Durations
are whole weeks. `academic_cycle` is a text **label**, not a date:
`YYYY` or `YYYY-YY` (`2026`, `2026-27`), stored exactly as the source
states it, compared as a string, never parsed.
Date of birth is a per-request input: POST body only, never a query
param, never in a URL, never logged, never in analytics.
**Settled — "DOB is never stored" vs. the merged gate:** the one store is
`student_accounts.date_of_birth`, written at sign-up by the merged
guardian-consent gate (`0004`–`0006`), because the server must be able to
re-check the age gate itself. Nothing else stores a date of birth or a
birth year, and no lane may add a second store.

## Three eligibility outcomes

Exactly three: `eligible`, `not_eligible`, `insufficient_information`.
Never a fourth, never a score, probability or rank. Reasons are machine
codes (`no_verified_rules`, `missing_date_of_birth`, `missing_category`,
…) resolved to English or Hindi at the presentation layer; the engine
never returns display text.
**Settled:** a pathway with no published rules returns
`insufficient_information` + `no_verified_rules` — never `not_eligible`.
A missing personal input the rule needs gives the same outcome, never a
guess. Every personal input (`date_of_birth`, `category`,
`year_of_passing`, `qualification_level`, `appearing`) is POST-only.

## Evidence states, stale data, sample label

Claim status is `draft` → `in_review` → `published` → `superseded`; only
`published` reaches a student-facing result.
**Settled — per-tier review-due:** each claim carries its freshness tier
and `review_due_on` is derived from that tier, never typed by hand. Past
due is *stale*, not unverified: the value still shows, with a "last
checked &lt;date&gt;" qualifier.
**Settled — `is_sample`:** a boolean on both source and claim. A sample
row can never be published, and carries a visible label wherever it
appears.
**Settled — coverage:** absence of a published claim reads "not verified
yet" — never "no", never zero, never blank. Coverage is derived from
published claims, never hand-maintained.

## Publishing evidence in Phase 1

Maker ≠ checker, enforced by trigger server-side; `created_by` is
server-set and cannot be rewritten; editing a value while `in_review`
drops the row to `draft`, invalidating the approval.
**Settled — per-row content hash:** `content_hash` covers an ordered,
frozen field list — entity type, entity natural key, field, value, unit,
jurisdiction, academic cycle, source version, section reference, quote.
Adding a field to the hash is a migration plus a re-hash, not an edit.
**Settled — `source_version` without PUB-6:** in Phase 1 the importer
creates one row per (source, checked-on date) straight from the sources
register CSV; there is no fetcher and no stored document. A
`source_version` is immutable once a claim references it.
**Settled — fast re-approval:** Wave 4, and only when the content hash is
unchanged; any hash change means full review. Import rows lacking
`checked_by`, `checked_on` or a status column are rejected.

## Entity vocabulary

Closed `entity_type` list, frozen now even though the tables arrive in
DATA-4: `career`, `pathway`, `pathway_stage`, `pathway_transition`,
`exam`, `exam_cycle`, `institution`, `programme`, `scholarship`. A new
type is a contract change, not a data edit.
A backup or alternative route is a `pathway_transition` row (from stage,
to stage, transition type) — not a second pathway, not free text. That
row is UI-20's source.
Jurisdiction is one text code: ISO 3166-1 alpha-2 for a country, ISO
3166-2 for a subdivision. **Scope phasing is NOT frozen here** — which
states and countries the trial verifies is SCOPE-1, still with the owner.
Until it is answered, no covered-set list may be hardcoded in code,
fixtures or UI copy; anything unclaimed reads "not verified yet". Fields
on a non-`IN` pathway are display-only: shown with source and currency,
never fed to the eligibility engine or into a total.
**Settled — two published claims on one field:** later `checked_at` wins,
tie broken by later source publication date, then lower claim id. The
loser is flagged for review, never silently discarded.

## Error shape, sessions, guest state, flags

Errors stay FastAPI-shaped with `detail` as an object:
`{"detail": {"code": "<stable_code>", "message": "<translatable text>"}}`.
The code is the contract, the message is not. Existing routes return a
bare string and are migrated by whichever lane next touches them.
The JSON API is Bearer-only; cookies belong to the web layer alone.
Student cookie `bcion_student_session` (httponly, samesite=lax, secure in
production, `path=/`, max-age = token expiry), beside today's
`bcion_reviewer_session` on `/reviewer`. No refresh token in Phase 1:
expiry means re-sign-in behind a "your session ended" notice.
State-changing web posts need an `Origin` matching `ALLOWED_HOSTS`;
absent or mismatched is a 403.
**Settled — guest state:** quick-start answers are stateless query params
(no server state, no personal data). A guest *plan* uses a server-side
guest session (opaque id, httponly cookie) over
`guest_sessions`/`guest_plans`, merged into the account at sign-up by a
one-way, idempotent definer function. No birth year is stored for a guest.
**Settled — the flag list, and only this list:** `SIGNUP_ENABLED`,
`MAINTENANCE_MODE`, `AI_ENABLED`, `HINDI_UI_ENABLED`, `ALLOWED_HOSTS`,
`MINOR_ACCOUNTS_ENABLED`, plus the demo-mode guard. DEPLOY-18 adds all to
`config.py` with fail-closed defaults. `SIGNUPS_ENABLED` (with an S) is a
stale name and must not exist anywhere.

## Difficult states and cache class

Copy for every difficult state lives only in `docs/COPY.md`'s
`global.difficult_state.*` keys (`ai_unavailable`, `eligibility_uncertain`,
`information_changed`, `no_matching_result`, `save_failed`,
`weak_connection`, `shared_device`, `permission_denied`); a lane names the
key and renders it, never restates or forwards the English inline.
`docs/UI.md`'s difficult-states and state-pattern tables carry the
shipped/drafted status per key — check there, it is not duplicated here.
Offline deadline stays out of scope while OD-1 (no service worker) holds;
it gets a ninth key only if that decision reverses.
**Settled — cache class:** no route sets `Cache-Control` today (checked
`app/web/pages.py`, `app/web/reviewer_pages.py`), so this is a fresh
default, not a change. Three classes: **no-store** — the default for
every response, and the only class for any cookie-bearing request, every
POST, `/reviewer/*`, `/auth/*`, `/plans`, and any view carrying personal
params (a saved plan, filled-in requirements); **public-anonymous** —
short max-age, allow-listed anonymous GETs only (`/explore`,
`/compare/view`, `/timeline/view` GET) with no `Cookie` or `Authorization`
header — either header present falls back to no-store even on an
allow-listed path; **static** — long max-age, `/static/*` and compiled
CSS/JS only, cache-busted by filename hash, never by content. Reviewer
sign-out also sends `Clear-Site-Data: "cache"`, the shared-device state's
mechanism.

## Keys and components

**Catalogue keys (I18N-1, frozen).** Flat, dot-separated,
`screen.component.purpose`, lower snake_case, one key per fixed string —
no nesting, enforced at import by `app/i18n/__init__.py`. `_meta.*` is
the one exempt prefix (catalogue provenance, never rendered). One
string, one key: a formatter's "not available" output reuses
`global.trust_badge.not_available` rather than a second key for the same
words. Placeholders are `{name}` only, substituted by regex (never
`str.format`), so a missing variable or stray brace degrades visibly
instead of crashing a page. Locale resolution is the `lang` cookie then
`en`, with per-key fallback to English — `lang` is a strict allow-list
(`en`/`hi`) and is never used to build a file path. Full rationale:
`docs/DECISIONS.md`'s I18N-1 entry; wording source of truth:
`docs/COPY.md`.

**Component and shell contracts (DESIGN-1, DESIGN-2, UI-1, frozen).**
The component/state contract lives in `docs/UI.md`'s "Component and
state contract v1" section; the app shell (`base.html` blocks,
`_nav.html` macros, the four stub partials, `_components.html` macros)
lives in that same file's "Shell and stub macro contract (frozen v1)"
section. Both are additive-only from here: a new optional keyword
argument at the end is fine, a rename, reorder or removal is a breaking
change across every screen that already calls them.

## Rule approval lives in git JSON

A rule set's approved version is a reviewed JSON case table committed to
the repo and approved in a pull request, not a database row.
`rule_version` on a `RuleSet` is that file's declared version string;
changing a rule is a reviewed PR, never a runtime edit. Git already gives
an immutable, attributable, diffable approval trail, and a `rule_versions`
table would need its own maker-checker console for no pilot benefit — it
is deferred to RULES-18.
**This deviates from build pack section 6 and needs a dated
`docs/DECISIONS.md` entry from the lead; this task must not write it.**

## Consent and account admission

Full contract: `docs/CONSENT.md`. Frozen here for other lanes: account
status is the merged enum `active` / `pending_guardian_consent`, extended
additively by CONSENT-4 with `frozen` and `deletion_due`; admission is
invite-only through `redeem_invite`, the only way an account becomes
admitted; `MINOR_ACCOUNTS_ENABLED` defaults false and the pilot's first
phase is adults-only.

## Migration ledger, fixtures
<DOCS-3, DOCS-4, QA-2/3/4 - see tasks/INDEX.md's own ledger line, marked
PROVISIONAL; re-verify against `ls db/migrations/` before trusting it>

## AI (Ask BCION)
`AIAnswerStatus` (`app/ai/schemas.py`) is exactly: `answered`,
`not_available`, `insufficient_information`, `ai_unavailable`,
`budget_exhausted`, `unsupported_template`. Only `answered` carries
sentences; the other five carry none, ever.

An outbound provider payload carries exactly four fields — `template_id`,
`record_ids`, `record_values`, `lang` — and nothing else; every value must
trace to an allow-listed record id, so no student-typed text reaches a model.

Answers are produced in two passes: a selection call returning record ids,
then an adversarial verification call over only those ids, then code
validation — the model never writes a sentence a student reads.
