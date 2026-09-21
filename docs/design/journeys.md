# End-to-end journeys — BCION Lite

Source: `docs/PRODUCT.md` ("The one journey": explore → compare three
pathways → calculate time and cost → see requirements → save next
actions) and `docs/UI.md`'s "Component and state contract v1" (component
status) and `docs/COPY.md` (fixed strings and keys). This file maps that
one journey onto three concrete, step-by-step walkthroughs plus one
teacher demonstration, so a Playwright scenario, a moderator's task list
(`docs/research/`) and a teacher pack (DESIGN-14) all point at the same
steps instead of three drifting descriptions of "the journey."

## Conventions used below

- **Persona** — a fictional composite for design purposes only. No real
  student, no real school, no real personal data of any kind.
- **Screen / route** — an actual FastAPI route if the screen is built
  today (`/explore`, `/compare/view`, `/requirements/view`,
  `/timeline/view`), or **"(unbuilt — no route yet)"** if it is not. Per
  `docs/UI.md`'s Component and state contract v1: quick start, My Plan,
  Saved and Ask BCION have no template or route today. `app/api/plans.py`
  exists as a bearer-token API for saved plans, but no page renders it —
  that gap is called out at each step it affects, not glossed over.
- **Component(s)** — the macro/class from `docs/UI.md`'s component
  inventory. A component marked "(planned, unbuilt)" there is marked the
  same way here.
- **Copy key(s)** — a key from `docs/COPY.md` where one is fixed. Where a
  step needs copy this pack does not yet fix (quick start's questions,
  for instance — out of DESIGN-2's fixed scope), that is stated plainly
  as "not yet defined" rather than invented here.
- **Synthetic fixture** — a fixture ID prefixed `SYN-`, standing for data
  that must be created, clearly labelled synthetic (the same "not
  verified facts" convention the design mockup already uses, per
  `STATUS.md`'s "Design mockup" entry), and **never** entered as if it
  were a reviewed, published claim. No fixture below reuses real content
  from `docs/content-drafts/` — those files are unreviewed real-world
  drafts awaiting human verification, not synthetic test data, and mixing
  the two would blur exactly the line `CLAUDE.md` draws ("Synthetic
  fixtures are clearly labelled and NEVER published as verified facts").
- A step that can trigger one of `docs/UI.md`'s eight difficult states
  names it and gives the `docs/COPY.md` key, where one exists.

---

## Journey 1 — Undecided

**Persona:** Priya, a fictional Class 10 student in Uttar Pradesh who has
not decided between Science, Commerce and Arts yet and is looking for a
starting point, not a final answer.

| # | Screen / route | Component(s) | Copy key(s) | Possible difficult state | Synthetic fixture needed |
| - | --- | --- | --- | --- | --- |
| 1 | Quick start — **(unbuilt, no route yet)** | none built; planned progressive question flow per `docs/UI.md`'s "Quick start" section | Not yet defined — quick-start question copy is outside DESIGN-2's fixed scope (trust labels, eligibility outcomes, difficult states, guest notice, closing prompt, not-verified answer only); flagged as a gap for a future copy pass, not solved here | none expected | none — the step only records Priya's own answers |
| 2 | `/explore` | `.card` (career listing; no dedicated "career card" macro yet — see `docs/UI.md`) | none needed for the happy path; `global.difficult_state.no_matching_result` if the list is empty | No matching result, if nothing is published yet | `SYN-CAREER-engineering`, `SYN-CAREER-commerce`, `SYN-CAREER-arts`, each with 1–2 `SYN-PATHWAY-*` records, clearly marked synthetic |
| 3 | `/explore` → select 2–3 pathways → `/compare/view` | checkbox row (44px touch target, `explore.html`), `.card` | none for the selection form itself | User-actionable error if 0–1 or 4+ pathways are selected (`compare.html`'s existing `error` alert) | same fixtures as step 2 |
| 4 | `/compare/view` | `field_value()`, `trust_badge()`, `evidence_line()` (`_trust_badge.html`) | `global.trust_badge.*` (whichever labels the synthetic claims carry); `compare.closing_prompt.text` at the foot of the screen | Needs rechecking / Not available, if a fixture claim is deliberately left stale or absent, to show the badge in context | claims on the step-2 fixtures: entry requirements, main stages, time range, and a cost breakdown mixing `estimate` and `institution_reported` labels |
| 5 | `/requirements/view?pathway_id=...` | `.field-input` (self-entry form: age, marks percentage, subjects studied, domicile state), `eligibility_outcome_badge()`, `trust_badge()`, `evidence_line()` | `global.eligibility_badge.insufficient_information_overall` ("Enter your details above to check this") — Priya leaves the form blank at first, since she has not picked a stream | Insufficient information (the expected, correct state here, not a bug) | `SYN-ELIGIBILITY-*` criteria (age, marks threshold, subjects, domicile) attached to one step-2 pathway |
| 6 | `/timeline/view` | `.field-input`, `.card`, `.btn-primary` | none fixed; the existing "Total not available yet" copy in `timeline_calculator.html` is code-owned, not a `docs/COPY.md` key | Insufficient information, if she leaves a stage's duration blank (the calculator's own existing behaviour) | none — she enters her own hypothetical stage rows |
| 7 | Save a next action → My Plan — **(unbuilt, no route yet)** | none built; `app/api/plans.py` exists as a bearer-token API with no page | `global.guest_session.notice`, `global.guest_session.save_prompt`, `global.difficult_state.save_failed` (all drafted in `docs/COPY.md`, none wired to a template yet) | Save failed; Shared device, if she is on a family phone | the pathway saved from step 2 |
| 8 | Return later → Saved / "what changed" — **(unbuilt, no route yet)** | none built; planned `what_changed_list` macro | `global.difficult_state.information_changed` (drafted, unwired) | Information changed | same saved pathway, plus a second version of one of its claims with a changed value, to demonstrate the "what changed" surface once built |

---

## Journey 2 — Goal-focused **(also the teacher demonstration journey)**

**Persona:** Farhan, a fictional Class 12 student in Bihar who has
already decided he wants to pursue Medicine (MBBS) and wants realistic
time, cost and requirement information before committing further.

This journey is deliberately the most linear of the three — a single
clear goal, a complete data set, no dead ends — which is why it is marked
here as the **teacher demonstration journey** `docs/UI.md`'s "Other
stakeholder views" calls for. It touches only real, already-built routes
except for saving the result, so it also doubles as the primary
Playwright end-to-end scenario, and DESIGN-14's teacher pack (session
guide, discussion prompts) is built directly on these steps.

| # | Screen / route | Component(s) | Copy key(s) | Possible difficult state | Synthetic fixture needed |
| - | --- | --- | --- | --- | --- |
| 1 | `/explore` | `.card`, checkbox row | none needed | none expected — fixture is complete | `SYN-CAREER-medicine` with three `SYN-PATHWAY-*` records: government MBBS, private MBBS, and BDS as a nearby alternative |
| 2 | `/explore` → select all three → `/compare/view` | checkbox row, `.card` | none | none expected | same as step 1 |
| 3 | `/compare/view` (three-column desktop / stacked mobile) | `field_value()`, `trust_badge()`, `evidence_line()` | `global.trust_badge.checked_against_official_source` (a NEET-UG cutoff illustration), `global.trust_badge.institution_reported` (fees), `global.trust_badge.estimate` (hostel/living costs), `compare.closing_prompt.text` | none expected — this is the demo's centrepiece and should show a clean, complete comparison | cost-breakdown claims (verified charges, estimated additional expenses, potential assistance) on all three step-1 pathways |
| 4 | "See requirements for..." link → `/requirements/view?pathway_id=government-mbbs` | `.field-input` form, `eligibility_outcome_badge()`, `trust_badge()`, `evidence_line()` | `global.eligibility_badge.meets_overall` or `does_not_meet_overall`, depending on the marks the demo enters live | Does-not-meet is a legitimate, plannable teaching moment ("what would you do next"), not treated as a failure of the demo | `SYN-ELIGIBILITY-neet` criteria (age, marks percentage, subjects studied, domicile) on the government-MBBS pathway |
| 5 | `/timeline/view` | `.field-input`, `.card`, `.btn-primary` | none fixed (calculator copy is code-owned) | none expected | none — stages entered live: Class 12 boards, NEET-UG preparation, exam-to-result, counselling, MBBS course |
| 6 | Save the government-MBBS pathway as a next action → My Plan — **(unbuilt, no route yet)** | none built | `global.guest_session.notice`, `global.guest_session.save_prompt` | Save failed (name only — expected not to occur in a clean demo run) | the government-MBBS pathway from step 1 |
| 7 | *(Teacher-only wrap-up, not scripted for a solo participant)* — discuss "why am I seeing this" and the future Ask BCION entry | `why_seeing_this`, `ask_bcion_entry` — both **(planned, unbuilt)** per `docs/UI.md` | `askbcion.answer.not_available`, `askbcion.answer.insufficient_information` (drafted, unwired — AI is not built yet, so this step is discussion only, never a live demo of a chat box) | AI unavailable / budget exhausted (`global.difficult_state.ai_unavailable`) — the teacher states this is the current, correct behaviour, not a bug | none |

---

## Journey 3 — Alternative-seeking (includes a foreign pathway)

**Persona:** Meera, a fictional Class 11 student in Kerala whose
first-choice engineering branch has a very competitive cutoff. She is
comparing a backup domestic engineering pathway against a study-abroad
alternative her family is also weighing.

| # | Screen / route | Component(s) | Copy key(s) | Possible difficult state | Synthetic fixture needed |
| - | --- | --- | --- | --- | --- |
| 1 | `/explore` | `.card`, checkbox row | none needed | none expected | `SYN-PATHWAY-domestic-engineering-backup` and `SYN-PATHWAY-foreign-engineering-germany` — both synthetic; the foreign one is loosely shaped like (never copied from) `docs/content-drafts/foreign-pathway-germany.md`, which is real, unreviewed draft content and must not be reused as test data |
| 2 | `/compare/view` (two columns) | `field_value()`, `trust_badge()`, `evidence_line()` | `global.trust_badge.*`; `compare.closing_prompt.text` | **Known v1 limitation, not a bug:** per `docs/UI.md`'s "Foreign-currency and visa slots: not in v1," the foreign pathway's cost fields render with the same bare `₹` formatting as the domestic one (or as `not_available`) — there is no currency-code or visa-requirement slot. This step exists specifically to surface that gap in a Playwright/moderator run, not to hide it | cost-breakdown claims on both pathways; the foreign one's fee left as `not_available` or in the same `₹` formatting, to show the actual (not idealised) v1 behaviour |
| 3 | "See requirements" → `/requirements/view` for the **domestic** pathway only | `.field-input` form, `eligibility_outcome_badge()`, `trust_badge()`, `evidence_line()` | `global.eligibility_badge.*` | none expected | `SYN-ELIGIBILITY-*` criteria on the domestic pathway only |
| 3a | Foreign pathway's own admission/visa requirements — **out of scope for v1, explicitly** | none — no visa/entry-requirement component exists (`docs/UI.md`) | n/a | n/a — this row exists to document the scope line, not to imply a hidden built screen | none |
| 4 | `/timeline/view`, run twice (once per assumption set) | `.field-input`, `.card`, `.btn-primary` | none fixed | none expected | none — stages entered live for each scenario |
| 5 | Save the domestic pathway as a next action, mark the foreign one for later → My Plan / Saved — **(unbuilt, no route yet)** | none built | `global.guest_session.notice`, `global.guest_session.save_prompt` | Save failed | both step-1 pathways |

---

## How this doubles as test and moderator material

- **Playwright scenario source:** Journey 2 (goal-focused) is the
  recommended primary end-to-end scenario — every step but saving hits a
  real, already-built route with no dead ends. Journeys 1 and 3 add the
  empty-state, validation-error and known-limitation coverage Journey 2
  does not exercise.
- **Moderator task source (`docs/research/`, TRIAL-2):** the six
  `docs/UI.md` round-1 criteria and the eight Step-15 tasks each map onto
  one or more steps above — see `docs/research/moderator-script-round1.md`
  and `docs/research/moderator-script-trial.md` for the exact task
  wording and pass rules built from these steps.
- **Teacher pack source (DESIGN-14):** the 40-minute classroom session
  guide is built directly on Journey 2's seven steps, in order.
