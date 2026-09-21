# Contracts

Frozen shared definitions every parallel lane builds against. **1,500-word
cap for this whole file** — a contract states the decision and the
reason in a sentence or two, it does not re-explain the feature.

Filled by the Wave 1 contract burst (one strongest-tier agent, strictly
serial, in its own worktree — see `docs/DEVELOPMENT-PLAN.md` sections
5 and 6.2): SCOPE-2 -> RULES-1 -> PUB-1 -> CONTENT-2 -> AUTH-1 ->
CONSENT-3 -> A11Y-1, one section each, in that order. After the burst
merges, changes here are additive only and need a `docs/DECISIONS.md`
line from the lead.

Skeleton only below — each heading is empty until its task lands.

## Money and currency
<SCOPE-2 / RULES-1>

## Duration, dates, cycle, DOB
<RULES-1, SCOPE-2>

## Three eligibility outcomes
<RULES-1>

## Evidence states, stale data, sample label
<PUB-1, DATA-12, SCOPE-2>

## Publishing evidence in Phase 1
<PUB-1, CONTENT-2>

## Entity vocabulary
<SCOPE-2>

## Error shape, sessions, guest state, flags
<AUTH-1>

## Difficult states and cache class
<A11Y-1>

## Keys and components
<DESIGN-2, DESIGN-1 (docs/UI.md); I18N-1, UI-1 (code)>

## Rule approval lives in git JSON
<RULES-1>

## Migration ledger, fixtures
<DOCS-3, DOCS-4, QA-2/3/4 - see tasks/INDEX.md's own ledger line, marked
PROVISIONAL; re-verify against `ls db/migrations/` before trusting it>
