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

## Component set (frozen at Step 7 / M2, per Lite Build Pack §5)
Cards, source labels, inputs, alerts, comparison sections, reminder opt-in,
"what changed" list. Contextual "Ask BCION" entry points use canned prompts
over retrieved records (fixed template — this is also the Tier-0/Tier-1
cost control from the national DPR §9), never a blank chat box.

## Usability rounds
- **Round 1** (after Step 7 / week 5, on a clickable prototype, before the
  comparison/cost engines are built): 5–8 participants incl. a
  shared-phone user, a Hindi-preferring user, a parent, a teacher.
- **Round 2** (alongside the 10-user trial): same task criteria.
- **Task criteria (pass mark, both rounds):** find two plausible routes;
  explain verified-cost vs estimate; locate an official source; save a next
  action; change a preference; recognise uncertainty rather than treat the
  system as an authority.
