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
- **Round 1** (per `docs/DEVELOPMENT-PLAN.md` Wave 4, on the real app —
  the comparison and cost engines are already built and live, not a
  clickable prototype; this sentence was stale by the time round 1 was
  actually scheduled): 5–8 participants incl. a shared-phone user, a
  Hindi-preferring user, a parent, a teacher. **Phase 1's round 1 is
  adults-only (18+)** — no minor participant before CONSENT-11/CONSENT-14
  (Phase 2/3).
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

#### v1.1 status updates (additive — the rows above are not rewritten)

The freeze above records the state on 2026-09-21. Each line below names
a row whose **Status** has since changed, with the task that changed it.
The v1 rows stay as written, so the history of what was missing when
stays readable.

| Row | New status | Changed by |
| --- | --- | --- |
| Nav shell | **Exists.** `base.html` + `_nav.html` implement the four destinations (Explore, Compare, My Plan, Saved) and the utility menu. My Plan and Saved have no route yet and render as unavailable rather than as dead links | UI-1, 2026-09-22 |

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

## Shell and stub macro contract (frozen v1, 2026-09-22 — UI-1)

UI-1 rewrote the app shell and created the partials every later screen
task writes into. **These signatures are the interface other tasks
build against.** Changing an argument name or dropping one is a
breaking change across screens, so extend additively — a new optional
keyword argument at the end, never a reorder, a rename or a removal.

Additions after usability round 1 follow the same rule as the component
inventory above: additive v1.1 rows, never a silent rewrite.

### The shell — `base.html`

| Block | What it is for | Default |
| --- | --- | --- |
| `title` | the `<title>` text | `BCION Lite` |
| `head_extra` | a page-specific `<link>`/`<meta>` | empty |
| `student_nav` | the four-destination nav | `nav.student_nav(current_path)` |
| `utility_menu` | account / language / privacy / tools | `nav.utility_menu(current_path)` |
| `session_state` | guest vs account | `nav.session_state(session_state)` |
| `content` | the page | empty |
| `footer` | the standing footer | the synthetic-data line |

`current_path` is derived inside `base.html` from `request.url.path`; no
route passes it. **A reviewer page hides student navigation by
overriding `student_nav` and `utility_menu` with empty blocks** —
`reviewer_queue.html` and `reviewer_sign_in.html` both do, and that is
the supported mechanism for any future non-student surface.

`base.html` reads exactly one optional context variable,
`session_state` (`"guest"` / `"account"` / absent). Everything else the
shell needs it derives itself, so no route signature changes.

### Navigation — `_nav.html`

| Macro | Signature |
| --- | --- |
| `student_nav` | `student_nav(current_path="")` |
| `utility_menu` | `utility_menu(current_path="")` |
| `session_state` | `session_state(state=none, detail=none)` |

The four destinations and the utility items are two `{% set %}` lists at
the top of `_nav.html`. **A destination with `href: none` renders as
plainly unavailable** (text, never colour alone) and is not a link, so
no nav item can lead to a 404. The task that builds a route fills in
that one `href` and nothing else changes. Today: Explore and Compare are
live; My Plan and Saved are slots; in the utility menu only the timeline
calculator is live, with account, language, privacy and help as slots.

Zero JavaScript by construction: plain links that wrap rather than
overflow at 375px, and a native `<details>`/`<summary>` disclosure for
the utility menu.

### Stub partials — one owner each, all rendering nothing today

Each renders nothing until its owning task fills the body. Their call
sites already exist (UI-1 wired them), so an owner adds markup in one
file and it appears everywhere at once.

| Macro | File | Signature | Owner | Called from |
| --- | --- | --- | --- | --- |
| `report_issue` | `_report.html` | `report_issue(url=none, entity_type=none, entity_id=none, field=none, label=none)` | Ops/support (needs the feedback endpoint) | `evidence_line()` — so every consequential fact |
| `ask_bcion` | `_ask.html` | `ask_bcion(template_id, pathway_id=none, career_id=none, label=none, ai_enabled=false)` | UI-11 | `compare.html` cost card + pathway column, `requirements.html` eligibility line |
| `why_am_i_seeing_this` | `_why.html` | `why_am_i_seeing_this(reasons=none, preferences=none, unknowns=none, change_preferences_url=none, heading=none)` | the quick-start suggestion task | `explore.html`, `compare.html` |
| `save_action` | `_save.html` | `save_action(item_type, item_id, saved=false, label=none, return_to=none)` | UI-16 / AUTH-6 | `explore.html` per pathway, `compare.html` per column |

`template_id` on `ask_bcion` is **required and is an id from a fixed
server-side list** — docs/UI.md's component set allows canned prompts
over retrieved records and forbids a blank chat box, and the fixed set
is also the DPR's Tier-0/Tier-1 spend control.

`return_to` on `save_action` must be validated server-side as a local
path before any redirect uses it.

### Content components — `_components.html`

| Macro | Signature |
| --- | --- |
| `comparison_section` | `comparison_section(heading, field=none, money=false, note=none, divider=false)` |
| `career_card` | `career_card(career, entry_routes=none, investigate=none, why=none, reality_check=none, detail_url=none)` |
| `why_seeing_this` | `why_seeing_this(reasons=none, preferences=none, unknowns=none, change_preferences_url=none, heading=none)` |
| `what_changed_list` | `what_changed_list(changes=none, heading=none, empty_message=none)` |
| `reminder_opt_in` | `reminder_opt_in(subject, action_url=none, opted_in=false, channel=none, deadline=none, note=none)` |
| `ask_bcion_entry` | `ask_bcion_entry(prompts=none, pathway_id=none, career_id=none, ai_enabled=false, heading=none)` |
| `pathway_detail_link` | `pathway_detail_link(pathway_id, label=none, class_names=none)` |

`why_seeing_this` (the component) and `_why.html`'s
`why_am_i_seeing_this` (the per-screen slot) are deliberately two names:
a screen calls the slot and never has to know the markup, and the
component could be built before the suggestion engine exists.

`career_card`'s four questions are the Build Pack's, in order: what
would I do; how could I enter; what should I investigate; why am I
seeing this — plus the reality check (common misunderstandings, hard
parts, what to try before committing, routes worth comparing).

### Source label — `evidence_line` (extended, DESIGN-18)

`evidence_line(source_authority, source_url, verification_date, label=none, applicable_cycle=none, report_issue_url=none)`

The two new arguments are optional and additive: existing callers are
unchanged, and each renders **nothing** when absent. `applicable_cycle`
is the admission/fee cycle a fact belongs to ("2026–27"); without it,
"verified 2026-09-01" cannot tell a reader which year's fee they are
looking at. `report_issue_url` is passed straight through to
`report_issue()` — so no report control can appear without a real URL
behind it.

### i18n inside a macro — `t()` and the formatting filters

`t("screen.component.purpose", name=value)` is a Jinja **global**, so it
works inside any template and inside any macro, including macros
imported without `with context` (`app/web/templating.py` explains the
mechanism). The same applies to the four display filters:

| Filter | Example | Output |
| --- | --- | --- |
| `inr` | `{{ fee \| inr }}` | `₹1,00,000` |
| `number` | `{{ seats \| number }}` | `1,00,000` |
| `date` | `{{ verification_date \| date }}` | `21 Sep 2026` / `21 सितंबर 2026` |
| `duration_weeks` | `{{ total_weeks \| duration_weeks }}` | `78 weeks (about 1 year 6 months)` |

Each takes an optional explicit locale — `{{ d \| date("hi") }}` — which
only the components gallery needs; every real screen inherits the
reader's locale. `None` and anything unrenderable become the catalogue's
"Not available" string, never a blank or a raw `None`.

Template text itself is still hardcoded English: extracting it into
`t()` keys, and setting `<html lang="{{ lang }}">`, is I18N-3's task,
not UI-1's.

### Components gallery

`components_gallery.html` renders every macro above at a synthetic label
and at both 360px and full width, for visual review.

**It has no route, deliberately.** Everything on it is synthetic
(CLAUDE.md: synthetic fixtures are clearly labelled and never published
as verified facts), so it is not served to anyone — it is rendered to a
local file when someone wants to look at it:

```bash
python -c "import pathlib; \
from starlette.requests import Request; \
from app.web.templating import templates; \
r = Request({'type':'http','method':'GET','path':'/','headers':[]}); \
pathlib.Path('gallery.html').write_text( \
templates.TemplateResponse(r,'components_gallery.html',{}).body.decode(), \
encoding='utf-8')"
```

Run it from the repo root and open `gallery.html` straight from disk:
the page links the compiled stylesheet by both its served path and a
repo-root-relative one, so it is styled either way, with or without the
app running. `.gitignore` has no rule for it — **delete it when you are
done**, or it will show up in the next `git status`.
