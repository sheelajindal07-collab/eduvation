# Ten-person trial (Step 15) — moderator script delta

This is the delta over `docs/research/moderator-script-round1.md` for the
ten-person trial (TRIAL-11): the same fixed rules (no recording,
think-aloud, neutral prompts, distress-disclosure escalation, right to
stop) apply unchanged. This script adds the **signed-in tasks** and
covers the eight Build Pack §12 ("s12") tester tasks in full, since the
trial runs on production against real accounts, not guest-only staging.
Round-2 usability criteria are scored in the same sessions
(`docs/DECISIONS-pending`: see DESIGN-16, which computes the round-1 vs.
round-2 comparison from this script's output — not part of this task).

Participants: ten people. Default is adults only, unless the consent
workflow has by then been reviewed by someone other than its author and
the data-flow map has been accepted (TRIAL-11's own condition — this
script does not decide that; it is written to work either way, since
every task prompt below is age-neutral). Include at least one Hindi
session and one shared-device session.

**Build-status caveat, read before scheduling any session.** As of this
writing, three of the eight tasks below have no live equivalent: quick
start, guest/account save-a-plan, and student sign-out. If they are still
unbuilt when a trial session actually runs, do not skip the task —
follow the same "score as Prototype-tested" substitution
`moderator-script-round1.md` uses for Tasks 4–5, using whatever the
current design mockup or nearest built approximation is, and record the
substitution used in `docs/research/trial-results.md`'s limitations
section. Never record a substituted task as a plain pass.

## The eight tasks

### Task 1 — Explore without signing in
**Prompt:** *"Without signing in, see what career routes this site has
for you."*
**Route:** `/explore`.
**Pass rule:** reaches the career list and can name at least one route,
with no account.

### Task 2 — Find two plausible routes and compare
**Prompt:** *"Pick two or three routes you'd consider and compare them."*
**Route:** `/explore` → `/compare/view`.
**Pass rule:** same as round-1 Task 1.

### Task 3 — Change a cost assumption and explain the result
**Build-status note:** `/compare/view` has no editable cost assumption
today — cost figures are read-only. The only live editable-assumption
surface is the Timeline calculator's stage durations and overlaps
(time, not cost). Use that as the task and log the cost-assumption gap
as a limitation; do not claim this fully covers the Build Pack's "change
a cost assumption" wording.
**Prompt:** *"Change how long you expect one stage to take, and tell me
what changed in the total."*
**Route:** `/timeline/view`.
**Pass rule:** edits a stage's duration, recalculates, and explains in
their own words what changed and why.

### Task 4 — Identify verified versus estimated
**Prompt:** same as round-1 Task 2.
**Route:** `/compare/view`.
**Pass rule:** same as round-1 Task 2.

### Task 5 — Open an official source
**Prompt:** same as round-1 Task 3.
**Route:** `/compare/view` or `/requirements/view`.
**Pass rule:** same as round-1 Task 3.

### Task 6 — Save a plan and find the next action
**Build-status note:** no My Plan screen exists yet; `app/api/plans.py`
is a bearer-token API with no page. **Not testable** unless a save
surface has shipped by the time this session runs.
**Prompt (if shipped):** *"Save this route, then find where you'd look
to see what to do next."*
**Prompt (if not shipped):** same design-mockup substitution as
round-1 Task 4; score as "Prototype-tested."

### Task 7 — Log out safely on a shared device
**Build-status note:** there is no student-facing sign-in/sign-out UI
today (`app/api/auth.py` is Bearer-header only; the only cookie session
in the app is the reviewer console's `/reviewer/sign-out`, which is not
student-facing). **Not testable** unless a student session/sign-out flow
has shipped by the time this session runs.
**Prompt (if shipped):** *"This is a shared family phone. When you're
done, make sure nothing sensitive stays visible for the next person."*
**Pass rule (if shipped):** signs out (or confirms sign-out is not
needed for a guest session) and nothing sensitive persists by default,
matching `docs/COPY.md`'s `global.difficult_state.shared_device`.
**If not shipped:** score as "Prototype-tested" against the design
mockup's shared-device state, same convention as Task 6.

### Task 8 — Ask a question outside coverage and notice the limitation
**Build-status note:** Ask BCION does not exist yet
(`docs/UI.md`'s Component and state contract v1). There is also no
search bar on `/explore` today — it is a plain list. Substitute: open
`/requirements/view` with a `pathway_id` that does not exist, or a
pathway outside this pilot's coverage ceilings
(`docs/PRODUCT.md`'s "Coverage ceilings"), and observe the honest
not-found fallback. This is a different mechanism from a real AI refusal
and does not fully cover the task — log that gap.
**Prompt:** *"Look for something this site probably doesn't cover yet —
for example, a career family well outside its usual list — and tell me
what it says."*
**Pass rule:** the participant notices the system says it does not know,
rather than reading a wrong or invented answer as if it were confirmed.
**Once Ask BCION ships:** replace this substitution with a real
out-of-coverage question and score against
`docs/COPY.md`'s `askbcion.answer.not_available` /
`insufficient_information` copy.

## Scoring and de-identification

Score every task with `docs/research/scoring-sheet.md`'s vocabulary.
File notes under a participant code only, per
`docs/research/notes-template.md`. Aggregate into
`docs/research/trial-results.md` (TRIAL-11's own deliverable, not this
task's) — that file states the four Step-15 gates against the TRIAL-4
thresholds and lists which tasks, if any, were substituted rather than
run live.
