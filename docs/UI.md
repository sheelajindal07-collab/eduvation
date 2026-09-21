# UI — BCION Lite

Source: `docs/BCION-Lite-Build-Pack.md`, §5 (Interface brief). Component
set and tokens live here; Tailwind implements them.

## Visual direction
Warm white background, deep charcoal text, one deep-blue accent, teal/green
for positive states (with text + icon, never colour alone), amber with
explanation for caution, red sparingly. Generous spacing, short sections,
one primary action per screen. Brief functional motion, respects
`prefers-reduced-motion`. Images only where they explain work — no glass
effects, giant gradients, decorative dashboards, stock graduation imagery,
animated mascots.

## Typography
Noto Sans family with system-font fallback (Devanagari + Latin; Gujarati if
the pilot state needs it). No web-font download in the text-only / 2G mode.

## Trust labels (per field — replaces any whole-record badge)
| Status | Meaning |
| --- | --- |
| Checked against official source | Reviewed evidence supports this field |
| Institution-reported | Supplied by the institution; not independently confirmed |
| Estimate | Calculated from stated assumptions |
| Needs rechecking | Verification overdue or evidence has changed |
| Not available | No sufficient evidence |

Each consequential fact shows: source authority, applicable cycle,
verification date, official link, "Report an issue". A recommendation shows
why it appeared, which preferences influenced it, what remains unknown, and
how to change the preferences.

## Comparison screen (the central screen)
Fields, in order: entry requirements (met / not met / still unknown) · main
stages · time as a range with assumptions · total cost as verified charges
+ separated estimates · funding as confirmed vs potential · location · work
realities · alternatives if plans change · evidence with sources, dates,
missing information. Desktop: side-by-side columns. Mobile: stacked
sections or a pathway switch keeping the same field in view — never a
sideways-scrolling table. Closing prompt: "Which option would you like to
investigate further?"

## Timeline & cost
Editable milestones; required vs optional stages vs user assumptions are
visually distinguished. A failed attempt offers "Revise this scenario", not
a failure badge. **Three separate amounts, always**: verified charges,
estimated additional expenses, potential assistance not yet awarded.

## Quick start (progressive, skippable where not essential)
One question at a time: studying now → what to decide → interests → what
matters most (affordable / near home / start work sooner / keep options
open / a particular interest / not sure yet). Account creation only when
the user wants to save or sync — not before.

## Guest sessions
Anonymous server session, random token, no personal fields, 7-day expiry,
shown as "not saved to an account." Account creation migrates it. Never
local storage for a plan (leaks on shared/family phones).

## Difficult states (design these before the homepage)
| Situation | Response |
| --- | --- |
| AI unavailable / budget exhausted | "You can still compare routes and use the calculators." |
| Eligibility uncertain | Name the missing requirement; never guess |
| Information changed | Say what changed and which saved plans may be affected |
| No matching result | Broader searches and alternatives |
| Save failed | Keep the draft visible; never say "Saved" |
| Weak connection | Lightweight content, visible connection status |
| Shared device | Easy sign-out; nothing sensitive persists by default |
| Permission denied | Explain the boundary without exposing another user's data |

## "What changed" surface
Under My Plan and in the utility menu: field, old value, new value, date,
source — the interface side of the public correction log (DPR §11).

## Other stakeholder views
- **Parent:** student-approved family summary only (options explored, time
  and cost assumptions, questions to discuss, a suggested next
  conversation). The student controls what it shows.
- **Teacher:** a session guide, a demonstration journey, printable prompts,
  a referral route. No individual-student analytics at 100-user scale.
- **Support staff:** an authorised case summary (decision faced, options
  considered, constraints volunteered, unresolved questions) — never a
  model-generated label.
- **Institutions / coaching / lenders / employers:** no student-facing
  controls; corrections enter the review workflow.

## Component set (frozen v1, 2026-09-21)
Cards, source labels, inputs, alerts, comparison sections, reminder opt-in,
"what changed" list. Contextual "Ask BCION" entry points use canned prompts
over retrieved records (fixed template — this is also the Tier-0/Tier-1
cost control from the national DPR §9), never a blank chat box.

Naming this list "frozen at Step 7 / M2" was inaccurate before this freeze
existed: Step 7 (Build Pack §9) covers Compare and calculators, not a
component-freeze event, and several items on this exact list (reminder
opt-in, "what changed" list) still have no implementation. "Component and
state contract v1" below is what actually freezes, and what actually
exists today, per component — see that section for status.

## Usability rounds
- **Round 1** (after Step 7 / week 5, on a clickable prototype, before the
  comparison/cost engines are built): 5–8 participants incl. a
  shared-phone user, a Hindi-preferring user, a parent, a teacher.
- **Round 2** (alongside the 10-user trial): same task criteria.
- **Task criteria (pass mark, both rounds):** find two plausible routes;
  explain verified-cost vs estimate; locate an official source; save a next
  action; change a preference; recognise uncertainty rather than treat the
  system as an authority.

## Component and state contract v1 (frozen v1, 2026-09-21)

This section is the shared contract other screens are built against — the
mapping from each build-pack component (per the "Component set" list
above) to its actual class or macro name and file today, plus the state
vocabulary every component in this app follows. It is additive: it
freezes what exists now and names what is still missing; it does not
change any of the sections above. Amendments after usability round 1
(DESIGN-6) are v1.1, additive-only over this table, never a silent
rewrite of a row.

### Component inventory

Statuses are checked directly against the current templates and styles
(`app/web/templates/`, `app/web/styles/input.css`) as of this freeze —
not against the plan.

| Component | Class / macro | File | Status |
| --- | --- | --- | --- |
| Cards | `.card` | `app/web/styles/input.css` | Exists |
| Source label (with cycle and report slot) | `evidence_line()` macro | `app/web/templates/_trust_badge.html` | Partial — renders source authority, official link and verification date today; has no `applicable_cycle` or "Report an issue" slot yet (planned: DESIGN-18's extension of `evidence_line`) |
| Inputs | `.field-input` (**canonical**, see declaration below) | `app/web/styles/input.css` | Exists |
| Alerts | `.alert` + `.alert--caution`, `.alert--neutral`, `.alert--error` | `app/web/styles/input.css` | Exists (three variants only; no positive/success variant yet) |
| Comparison section | no macro yet — markup is written inline in `compare.html`; planned `comparison_section` macro | `app/web/templates/compare.html`; planned `app/web/templates/_components.html` | Missing as a reusable component. The screen itself works; it is not yet a component another screen could reuse without copying markup |
| Reminder opt-in | none; planned `reminder_opt_in` macro | planned `app/web/templates/_components.html` | Missing |
| "What changed" list | none; planned `what_changed_list` macro | planned `app/web/templates/_components.html` | Missing — the My Plan screen it belongs under does not exist yet either |
| Career card | none distinct — `explore.html` currently lists careers inside the plain `.card` component, not a dedicated career-card layout; planned `career_card` macro (four questions plus reality check) | planned `app/web/templates/_components.html` | Missing |
| Why-seeing-this | none; planned `why_seeing_this` macro | planned `app/web/templates/_components.html` | Missing |
| Ask BCION entry | none; planned `ask_bcion_entry` macro (canned prompts only, hidden when AI is off) | planned `app/web/templates/_components.html` | Missing. `app/ai/grounding.py` and `app/ai/budget.py` implement the grounded-answer and budget logic this component will call; no template or route renders it yet |
| Nav shell | `<header>`/`<nav>` in `base.html` | `app/web/templates/base.html` | Partial — today it is a wordmark link to `/explore` plus one link to `/timeline/view`. It does not yet implement `docs/PRODUCT.md`'s four-destination model (Explore / Compare / My Plan / Saved) or the utility menu (account, language, privacy); My Plan and Saved have no route to link to yet |

The five items marked "planned `_components.html`" all come from the same
not-yet-built file (DESIGN-18's task). Until it exists, treat every macro
name in this table as reserved, not available to import.

### `.field-input` is canonical

`app/web/styles/input.css` currently defines **two** input styles:

- `.field-input` — used by `requirements.html` and `timeline_calculator.html`.
  Padding clears the 44–48px touch-target minimum (`input.css`'s own
  comment on this class documents the fix and the reviewer finding behind
  it).
- `.input` — used only by `reviewer_sign_in.html`. `input.css`'s own
  comment on `.field-input` notes that `.input`'s shorter padding computes
  to roughly 42px, under the minimum.

**`.field-input` is the canonical input class for v1.** Every new screen
uses `.field-input`. `.input` is a pre-existing duplicate, not a second
approved option; migrating `reviewer_sign_in.html` off `.input` is a
follow-up implementation task, not part of this docs-only freeze (this
section changes no code).

### Foreign-currency and visa slots: not in v1

**Not in v1.** `docs/DECISIONS.md`'s 2026-09-21 entry ("Pilot scope
widened: all-India admission rules, foreign pathways for Indian students
added") added foreign/study-abroad pathways to pilot scope, but recorded
in the same entry that "foreign pathways add a second content category
(foreign fee currencies, visa/entry requirements, non-Indian source
verification) with no schema support yet." `docs/CONTRACTS.md`'s "Money
and currency" section is still an empty skeleton (`<SCOPE-2 / RULES-1>`).
Concretely: `field_value()` and `evidence_line()` (`_trust_badge.html`)
have no currency-code or visa-specific field today — a foreign pathway
rendered on the Compare screen right now would show its cost with the
same bare `₹` formatting as a domestic one, which is a known gap, not a
feature. A currency/visa slot is a new component, not a variant of an
existing one, and needs its own task and its own row in this table before
any foreign pathway reaches a comparison screen. Until then, a foreign
pathway shown anywhere in this app should be treated the same as any
other pathway with an out-of-scope field: the field is either omitted or
shown as `not_available`, never invented in a display currency.

### State-pattern table

The state a component is in is never conveyed by colour alone (`docs/UI.md`
"Visual direction"); every row below pairs a state with the concrete
mechanism this app already uses for it, or names the gap.

| State | When it applies | Visual pattern | Implemented today in |
| --- | --- | --- | --- |
| Has a value | A field has a real, published value | Plain text value + the relevant trust badge below it | `field_value()`, `_trust_badge.html` |
| Not available | No record exists for this field at all | `trust_badge(not_available)`: dashed border, em-dash icon, text "Not available" — never a blank space | `_trust_badge.html` |
| Needs rechecking | A published fact's verification is overdue or evidence changed | `trust_badge(needs_rechecking)`: caution colour + warning icon + text | `_trust_badge.html` |
| Insufficient information | Some input exists but not enough to give a definite eligibility or AI answer | `eligibility_outcome_badge(insufficient_information)`; `app/ai/grounding.py`'s `AIAnswerStatus.insufficient_information` (not yet rendered by any template — see Ask BCION entry above) | `_trust_badge.html`; `app/ai/grounding.py` |
| Empty (no results for this user/filter) | A list has nothing to show | `.alert--neutral` + icon + plain-language copy (`docs/COPY.md` `global.difficult_state.no_matching_result`, or a screen's own empty copy such as `explore.html`'s "No careers published yet") | `explore.html`, `requirements.html` |
| User-actionable error | A request failed in a way the user can retry or route around (bad link, missing pathway) | `.alert--caution` + icon + explanation + a way back | `compare.html`, `requirements.html` |
| System/workflow error | A conflict the user cannot fix by retrying (two reviewers racing a claim, an invalid transition) | `.alert--error` + icon + `role="alert"` | `reviewer_queue.html` |
| One of the eight difficult states | See the "Difficult states" table above | Alert or badge per state, exact copy from `docs/COPY.md`'s `global.difficult_state.*` keys | Mixed — see each key's Status column in `docs/COPY.md` |
| Disabled | An input is temporarily unavailable (e.g. a checkbox once 3 pathways are already selected) | `disabled` attribute + a visible text change in a live region, never a colour-only dim | `explore.html`'s compare-selection script |
| Loading (a request is in flight) | N/A for v1 | Not implemented anywhere and not needed yet: every current screen is a full server-rendered response with zero client-side async fetch. A future screen that adds one (e.g. Ask BCION) must define this row for real rather than inherit this placeholder | none |

Every touch target in every state above keeps the 44–48px minimum already
established by `.btn-primary`, `.btn-secondary` and `.field-input`; a
disabled or empty state is exempt from nothing here. Motion, where any
exists, keeps respecting `prefers-reduced-motion` (`input.css`'s global
media query) in every state row, including states not yet built.
