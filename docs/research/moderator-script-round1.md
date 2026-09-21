# Usability round 1 — moderator script

Round 1 tests **adults only**: 18+ students or recent school-leavers, a
parent, a teacher — never a real Class 8–12 minor (per the owner-decision
default recorded against TRIAL-1 in the plan: "Adults only for round 1
and the ten-person trial: 18+ students, parents and teachers. Minors
enter from batch 25, only after the consent workflow is reviewed by a
non-author and the data-flow map is accepted."). This is a **separate
mechanism from guardian consent** — the guardian-email consent gate for
real under-18 sign-ups is already built, merged and live-verified in
production; it has nothing to do with this session. The document a
participant signs for this round is
`docs/research/participant-info-consent.md`, an adult's consent for
their own participation in a usability session, not a guardian's consent
for a minor's account.

Run this script against **gated staging**, guest only (no accounts), on
the participant's own phone or a shared one, per `docs/UI.md`'s
"Round 1" description of the participant mix (a shared-phone user, a
Hindi-preferring user, a parent, a teacher) and TRIAL-8's execution plan
(5–8 sessions, 30–40 minutes each, at least one in Hindi).

## Fixed rules for every session

- **No audio or video recording.** Written, de-identified notes only, on
  `docs/research/notes-template.md`. (Recorded here per the plan's
  "Are sessions recorded?" question — recommended default: no. This
  needs the owner's formal sign-off in `docs/DECISIONS.md` alongside the
  other TRIAL-4 thresholds before the first real session; this script
  assumes that default so the pack is ready the day it is approved.)
- **Think-aloud.** Ask the participant to narrate what they are looking
  at and expecting, not just what they click. Prompt with "What are you
  looking for right now?" or "What did you expect to happen?" — never
  "Click the X button," which would turn an observation into an
  intervention (see `docs/research/scoring-sheet.md`).
- **Neutral prompts only.** Use the exact task wording below. Do not name
  a screen, a button or a label the interface has not already shown the
  participant. If a participant is stuck, use the two-step recovery in
  each task before recording it as not completed.
- **Distress-disclosure escalation.** If a participant discloses
  something distressing (a family, financial or personal crisis, or
  anything suggesting they or someone else may be at risk), stop the
  task immediately. Do not probe for details. Say: *"Thank you for
  sharing that with me. I want to make sure you have the right support —
  can I share a contact with you?"* Offer
  `[owner to supply a local student-support or counselling helpline
  before the first session — verify before use, do not invent one]`.
  Ask if they want to continue the session or stop; either is fine, and
  stopping is never recorded as a failure. Note the disclosure and the
  escalation step taken on `notes-template.md` with no identifying
  detail, and tell the support owner the same day.
- **Right to stop.** Remind the participant at the start that they can
  stop at any time with no consequence to their thank-you gift (per
  `docs/research/participant-info-consent.md`).

## Session structure (30–40 minutes)

1. **Welcome and consent (5 min).** Walk through
   `participant-info-consent.md`, confirm they are 18 or older, get their
   signed/initialled consent, assign a participant code (`P01`, `P02`, ...
   from `notes-template.md`), confirm no recording.
2. **Warm-up (2 min).** "Have you used a website like this before to
   research career or study options?" — context only, not scored.
3. **Tasks 1–6 (18–25 min).** See below. Present tasks in order; do not
   skip ahead for the participant.
4. **Debrief (5–8 min).** "What, if anything, was confusing?" "Was there
   a moment you weren't sure whether to trust something you saw?" "Would
   you come back to this?"
5. **Thanks and close.**

## Tasks

Each task maps to exactly one of `docs/UI.md`'s six round-1 criteria and
one step of `docs/design/journeys.md`'s Journey 1 (Undecided) or Journey 2
(Goal-focused), which is where these task prompts and their synthetic
fixtures come from. Score using `docs/research/scoring-sheet.md`'s
vocabulary (Completed unaided / Completed with intervention / Not
completed / Not testable this session).

### Task 1 — Find two plausible routes
**Criterion:** find two plausible routes.
**Prompt:** *"Imagine you're not sure yet what to study after school. Use
the site to find two routes you'd consider comparing."*
**Pass rule:** reaches `/explore`, selects two or three pathways, and
reaches `/compare/view` without being told where to click.
**Recovery (if stuck after ~90 seconds):** "What would you try next?" →
if still stuck, "Is there anything on this page that looks like a list of
options?" (an intervention — record it).

### Task 2 — Explain verified cost vs. estimate
**Criterion:** explain verified-cost vs. estimate.
**Prompt:** *"Look at the cost information for one of your routes. In
your own words, what part of this can you trust as confirmed, and what
part is a guess?"*
**Pass rule:** distinguishes a `checked_against_official_source` /
`institution_reported` figure from an `estimate` figure in their own
words, without being told the label names.
**Recovery:** "What does this label next to the number tell you?"
(pointing at a badge without naming it is a lighter intervention than
reading the label aloud; record which one was used).

### Task 3 — Locate an official source
**Criterion:** locate an official source.
**Prompt:** *"Show me where this fact came from."*
**Pass rule:** finds and opens (or states they would open) the source
link and notices the verification date on `/compare/view` or
`/requirements/view`.
**Recovery:** "Is there anything near the number that looks like a
link?"

### Task 4 — Save a next action
**Criterion:** save a next action.
**Not testable on the current build.** There is no guest-save or My Plan
screen yet (`docs/UI.md`'s Component and state contract v1, Nav-shell
row). Per the plan's recommended default ("score those two criteria on
the design mockup and mark them as prototype-tested"): show the
participant the My Plan screen in the design mockup (link in
`STATUS.md`'s "Design mockup" entry) instead of the live app, and ask:
*"If this were the real site, would you know how to save this option and
come back to it later?"*
**Score as:** "Prototype-tested" (a distinct value from the four in
`scoring-sheet.md` — record it exactly as that word, never as a pass on
the live app).

### Task 5 — Change a preference
**Criterion:** change a preference.
**Not testable on the current build.** There is no preferences or quick
start screen yet. Same substitution as Task 4: show the quick start
"what matters most" screen in the design mockup and ask: *"If you
changed your mind here, would you know how to update it?"*
**Score as:** "Prototype-tested," same convention as Task 4.

### Task 6 — Recognise uncertainty
**Criterion:** recognise uncertainty rather than treat the system as an
authority.
**Prompt:** present a pathway whose fixture includes a `Not available` or
`Needs rechecking` field (`docs/design/journeys.md` Journey 1's step 4
fixture is built for this). Ask: *"What would you do next, seeing this?"*
**Pass rule:** the participant treats the field as incomplete or
provisional ("I'd look elsewhere," "I wouldn't rely on this yet") rather
than guessing a number or treating the absence as a negative answer.
**Recovery:** "What does this label tell you about how sure the site is?"

## After the session

File notes on `notes-template.md` under the participant's code only.
Raw notes (if any exist outside this template) stay outside the repo per
this file's own no-recording rule. Aggregate findings go to
`docs/research/round1-findings.md` (TRIAL-8/TRIAL-9's output, not this
task's).
