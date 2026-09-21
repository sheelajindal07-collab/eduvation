# Usability scoring sheet — definitions and per-task rubric

Used with `docs/research/moderator-script-round1.md` and
`docs/research/moderator-script-trial.md`. This file fixes the two terms
TRIAL-4 asks the owner to sign off before any trial session
("intervention" and "critical failure"), so that sign-off has an actual
definition to approve rather than a moderator's on-the-day judgment call.

## Definitions

### Intervention
Any moment the moderator gives the participant information, a hint or a
physical indication (pointing, naming a button or label the interface
has not already shown them, explaining what a badge or icon means)
**beyond the fixed neutral prompt and its scripted recovery line.**

Not an intervention: encouraging think-aloud narration ("What are you
looking for?", "What did you expect?"), repeating the original task
prompt verbatim, or waiting silently.

Is an intervention: naming a specific element ("try the checkbox"),
reading a label aloud, explaining what a trust badge means before the
participant has asked, or taking over the mouse/keyboard.

Each task's scripted "Recovery" line in the moderator scripts is a
**permitted, pre-approved** intervention — using it still marks the task
"Completed with intervention," it does not disqualify the task, and using
anything beyond that scripted line is a second, unplanned intervention
and must be noted separately.

### Critical failure
Any of the following, regardless of which task was in progress:

1. The participant cannot complete a task's core action at all, even
   after one neutral re-prompt **and** the task's one scripted
   intervention.
2. The interface shows information that contradicts its own trust label
   or evidence (for example, a figure whose displayed value does not
   match what its own source link/evidence line supports), or silently
   drops a difficult state that `docs/UI.md` requires (for example, a
   `not_available` field rendered as a blank instead of the badge).
3. A cross-user or privacy exposure of any kind — one participant's
   guest session data becoming visible to another, or any data leaving
   the session that `docs/COPY.md`/`docs/UI.md` says must not persist by
   default. **This is escalated immediately, the session is paused, and
   the support owner and owner are told the same day** — this is a
   `CLAUDE.md` non-negotiable ("Cross-user access ... is tested every
   time"), not just a scoring category.
4. A repeated, unexplained save failure (the same action fails more than
   once with no visible reason) — the Step-15 gate text names this
   explicitly ("no repeated unexplained save failure").

A **critical failure is never scored as "Completed with intervention."**
It is its own category and is flagged in the findings file the same day,
not batched to the end-of-round writeup.

## Per-task score values

Record exactly one of these four values per task, per participant. No
other wording.

| Value | Meaning |
| --- | --- |
| Completed unaided | Passed the task's pass rule with zero interventions |
| Completed with intervention | Passed only after the task's scripted recovery line (or, if more than that was needed, note the extra intervention separately — this task is still "Completed with intervention," but flag it for review, since more-than-scripted help suggests a bigger issue than the criterion alone shows) |
| Not completed | Did not pass the pass rule even after the scripted recovery |
| Not testable this session | The underlying feature does not exist yet (see each script's build-status notes) — **never** recorded as a pass, and never left blank |

`docs/research/moderator-script-round1.md`'s Tasks 4–5 and
`moderator-script-trial.md`'s Tasks 6–7 additionally allow a fifth value,
**"Prototype-tested,"** only when the script's own substitution
instructions were followed (design-mockup walkthrough in place of a live
feature). Prototype-tested is not interchangeable with "Completed
unaided" in any roll-up math below — keep it in its own column.

## Roll-up math (feeds DESIGN-16, TRIAL-9, TRIAL-12)

- **"8 of 10 complete the core journey without intervention"** (Step-15
  gate): count participants whose *every* task is "Completed unaided" or
  "Prototype-tested" (state which, since they are not equivalent), out of
  10. "Completed with intervention" on any task removes that participant
  from this count.
- **"8 of 10 correctly distinguish estimated from verified cost"**: count
  by Task 2 (round 1) / Task 4 (trial) alone: "Completed unaided" or
  "Completed with intervention" both count as distinguishing it
  correctly (the criterion is about recognising the distinction, not
  about needing zero help to notice it) — only "Not completed" and "Not
  testable" are excluded from the numerator, but "Not testable" is also
  excluded from the denominator for that specific count (an untestable
  task cannot be evidence either way).
- **Per-criterion completion rate** (round 1's own acceptance
  requirement, TRIAL-8): completed (unaided + with intervention) ÷
  (completed + not completed), excluding "not testable"/"prototype-tested"
  from the denominator and reporting their count separately, so a
  criterion that could not be tested is never silently folded into a
  lower pass rate.

## De-identification

Every row on the sheet is keyed by participant code (`P01` and up, from
`docs/research/notes-template.md`) only — no name, phone number, school
or other identifier is ever written on this sheet or the notes template
it pairs with.
