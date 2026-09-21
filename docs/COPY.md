# Copy rules — BCION Lite

Source of the rules: `CLAUDE.md` non-negotiables ("No rank predictions, no
'you are not suited', no personality-type labels, no guarantees. Ranges and
named assumptions only") and `docs/PRODUCT.md`'s emotional-progression
section. Source of the vocabulary this file fixes: the live templates in
`app/web/templates/` and the five-value/three-value badge vocabularies in
`app/web/templates/_trust_badge.html` — this file does not invent new
wording where code-shipped wording already exists; it fixes it in one
place and gives it a key.

This file is docs-only. It does not edit `docs/UI.md` (DESIGN-1 owns the
one new section added there) or any template or Python string. Wiring a
template to the key/string pairs below, and the lint that checks nothing
banned reaches a template, is a separate task (DESIGN-3).

## 1. Reading level and tone

- Plain English, aimed at a Class 8 reader (the youngest user this pilot
  supports per `CLAUDE.md`'s "Class 8–12"). Short sentences — one idea
  each, aim under ~20 words.
- Second person ("you"), active voice, present tense where possible.
- Calm, neutral register — matches `docs/UI.md`'s "Visual direction"
  (warm, generous spacing, no urgency-manufacturing language). No
  exclamation marks in body copy. Exclamation marks are acceptable only in
  a brief positive confirmation ("Saved!") and never in a difficult state.
- Name what is known and what is not; never imply more certainty than the
  underlying trust label supports. "Estimate" copy must read as a
  calculation from stated assumptions, not a prediction.
- Numbers: money as `₹{value with thousands separator}` (matches the
  `"{:,.0f}"` formatting already used in `_trust_badge.html` and
  `compare.html` — never a bare unformatted number, never a trailing
  `.0`). Dates as shown by the server (no copy rule invents a date
  format here; that is a code concern).
- Avoid idiom, metaphor and culturally narrow references — this content
  is read in English and Hindi (`docs/PRODUCT.md` "Languages"), and
  idiom is the first thing that breaks in translation.
- Every string in this file is something a Class 8–12 student, a parent,
  or a teacher reads without needing this file's own jargon (headings
  like "trust label" are for the team, not for the screen).

## 2. Key naming convention

Flat, dot-separated, three segments: **`screen.component.purpose`**.

- `screen` — the route or destination the string belongs to
  (`explore`, `compare`, `requirements`, `timeline`, `myplan`, `saved`,
  `quickstart`, `askbcion`, `reviewer`, `consent`), or `global` when the
  same string is shared verbatim across more than one screen (the trust
  labels, the eligibility outcomes, the difficult states — all reused
  wherever the underlying component is reused, per DESIGN-1's component
  inventory).
- `component` — the macro, class or UI element the string belongs to
  (`trust_badge`, `eligibility_badge`, `difficult_state`,
  `closing_prompt`, `guest_session`, `ai_answer`), lower snake_case.
- `purpose` — which specific string within that component
  (`checked_against_official_source`, `save_failed`), lower snake_case.

One key, one fixed English string, one row. Keys are flat strings (no
nested objects) on purpose — a future i18n table only needs `key,en,hi`
columns; nesting keys would force a translator tool to understand this
project's own JSON/YAML shape instead of a plain lookup.

Do not reuse a key for two different strings, and do not give the same
string two different keys — grep this file before adding either.

## 3. Fixed strings

### 3.1 Trust labels (five — `_trust_badge.html`'s `trust_badge()`)

These five strings are already shipped in `app/web/templates/_trust_badge.html`
and are fixed here verbatim, not reworded — this section exists so future
callers quote this file instead of re-typing the macro's output by hand.

| Key | English |
| --- | --- |
| `global.trust_badge.checked_against_official_source` | Checked against official source |
| `global.trust_badge.institution_reported` | Institution-reported |
| `global.trust_badge.estimate` | Estimate |
| `global.trust_badge.needs_rechecking` | Needs rechecking |
| `global.trust_badge.not_available` | Not available |

### 3.2 Eligibility outcomes (three, each with an overall and a per-criterion
form — `_trust_badge.html`'s `eligibility_outcome_badge()`)

Also already shipped; fixed here verbatim from the current macro.

| Key | English |
| --- | --- |
| `global.eligibility_badge.meets_overall` | You meet the published requirements |
| `global.eligibility_badge.meets_criterion` | Meets this requirement |
| `global.eligibility_badge.does_not_meet_overall` | At least one published requirement isn't met |
| `global.eligibility_badge.does_not_meet_criterion` | Does not meet this requirement |
| `global.eligibility_badge.insufficient_information_overall` | Enter your details above to check this |
| `global.eligibility_badge.insufficient_information_criterion` | Not yet known |

`meets` / `does_not_meet` / `insufficient_information` is the three-value
outcome vocabulary; `docs/UI.md`'s comparison-screen field "entry
requirements (met / not met / still unknown)" reuses this same
vocabulary rather than inventing a fourth wording, so `global` (not
`requirements`) is correct here even though the only current caller is
`requirements.html`.

### 3.3 Difficult states (eight — `docs/UI.md`'s "Difficult states" table)

One fixed string per row of that table. Status column below is honest
about what exists today: only the AI-unavailable row's copy is already
shipped (`docs/UI.md` itself quotes it); the rest are drafted here ahead
of the screens that will need them (My Plan, Ask BCION, sign-in/session
handling — none of which exist yet per `STATUS.md`), so a future
implementer has fixed wording to build against instead of inventing its
own at commit time.

| Key | English | Status |
| --- | --- | --- |
| `global.difficult_state.ai_unavailable` | You can still compare routes and use the calculators. | Shipped — quoted verbatim from `docs/UI.md`'s difficult-states table |
| `global.difficult_state.eligibility_uncertain` | You haven't entered {requirement} yet, so this can't be checked. | Drafted — `requirements.html`'s own `insufficient_information` badge covers the per-criterion case today; this is the surrounding sentence, not yet in any template |
| `global.difficult_state.information_changed` | {field} changed on {date}. Check whether it affects a plan you saved. | Drafted — no "what changed" surface exists yet (My Plan is unbuilt) |
| `global.difficult_state.no_matching_result` | No matching routes yet. Try a broader search, or look at related options below. | Partially shipped — `explore.html` currently says "No careers published yet. Check back soon." for the all-empty case; this key is for a narrower, filtered search returning nothing once search/filtering exists |
| `global.difficult_state.save_failed` | This didn't save. Nothing here is lost — try again. | Drafted — never render "Saved" when this key is shown; no save UI exists yet outside the reviewer console |
| `global.difficult_state.weak_connection` | Slow connection. Showing a lighter version of this page. | Drafted — not wired to any connection check yet |
| `global.difficult_state.shared_device` | On a shared device? Sign out when you're done — nothing sensitive stays saved here by default. | Drafted — no student-facing sign-in/sign-out UI exists yet (`app/api/auth.py` is Bearer-header only; the only cookie session today is the reviewer console's) |
| `global.difficult_state.permission_denied` | You don't have access to this. If that seems wrong, contact your reviewer. | Drafted — the reviewer console's own conflict messages (`app/web/reviewer_pages.py`) are a distinct, already-fine set of strings for reviewer-vs-reviewer conflicts; this key is for the general "wrong account" case `docs/UI.md` describes, not yet built |

`{requirement}`, `{field}`, `{date}` are the only placeholders in this
file — plain `{name}` interpolation, no other templating syntax, so a
translator or a Python `.format()` call can both use these strings
unmodified.

### 3.4 Guest-session notice

`docs/UI.md`'s Guest sessions section quotes this fragment; fixed here as
a standalone sentence plus one companion prompt string.

| Key | English |
| --- | --- |
| `global.guest_session.notice` | Not saved to an account. |
| `global.guest_session.save_prompt` | Create a free account to keep this after 7 days. |

### 3.5 Closing compare prompt

Already shipped verbatim in `app/web/templates/compare.html`; fixed here
so nothing later re-types it slightly differently.

| Key | English |
| --- | --- |
| `compare.closing_prompt.text` | Which option would you like to investigate further? |

### 3.6 "Not verified" answers (`app/ai/grounding.py`'s `AIAnswerStatus`)

`app/ai/grounding.py` already fixes the *status vocabulary*
(`not_available`, `insufficient_information`, `answered`) but not the
user-facing sentence for the first two — no template renders an AI
answer yet (Ask BCION is unbuilt). Fixed here ahead of that build.

| Key | English |
| --- | --- |
| `askbcion.answer.not_available` | We don't have a verified record for this yet. |
| `askbcion.answer.insufficient_information` | We have some information, but not enough here for a confident answer. |

## 4. Approved phrasing (use these instead)

| Situation | Use | Never |
| --- | --- | --- |
| Introducing a pathway | "Explore this route" | "Your perfect career" |
| Shortlisting | "Save as an option" | any ranking language ("your #1 match") |
| After a choice | "You can change this later" | "This is your final answer" |
| A cost figure | "Estimate", "Verified charges", "Checked against official source" | "Guaranteed cost", a bare number with no trust label |
| Eligibility | "Meets this requirement" / "Does not meet this requirement" / "Not yet known" | "You qualify" / "You're not cut out for this" |
| Uncertainty | "Not available", "Needs rechecking", "not verified" | inventing a number or a source to fill a gap |
| Subject/stream choice | "Many students in this route study X; other combinations exist too" | "You must choose science" |

## 5. Banned patterns (machine-readable)

One Python-compatible regular expression per line, matched
case-insensitively against rendered template output and prompt/template
text (see DESIGN-3). Patterns are written as **phrases**, not bare words,
so that an honest, approved use of a word (for example "no guarantee of
admission" — an accurate, required disclaimer) is never itself flagged;
only an affirmative claim of certainty, a rank, a suitability score or a
personality label is banned. Do not add a bare word like `guarantee` or
`suited` on its own line — see the Risk note on DESIGN-2's task card.

```regex
your perfect career
the perfect career for you
you are \d{1,3}\s?%\s?(suitable|suited|fit|matched|compatible)
you('re| are) (definitely |certainly )?(not )?(suited|cut out) (for|to)
you must (choose|pick|become|study|take)
you have to (choose|pick|become|study|take)
your (predicted|expected|likely) rank
you will (rank|score|get) (in the )?(top|rank) \d
we guarantee
i guarantee
guaranteed (admission|selection|a seat|success|placement|a job|a rank|a score)
100\s?%\s?(guarantee|guaranteed|sure|certain)
sure[- ]shot
this is your (only|best) option
you are an? (introvert|extrovert|analytical type|creative type|born leader)
your personality type
this is (definitely|certainly) the right (choice|career|path) for you
```

## 6. Reserved for future sections

`docs/design/case-summary.md` (DESIGN-11) and `docs/design/family-summary.md`
(DESIGN-12) keep their own copy keys in their own files, by design, "to
avoid COPY.md write conflicts" (per their task cards) — do not duplicate
their keys here.
