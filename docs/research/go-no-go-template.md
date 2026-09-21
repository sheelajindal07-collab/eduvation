# Ten-user trial go/no-go report — template (TRIAL-10)

This is a **blank template**, not a report. TRIAL-12 fills it in from
`docs/research/trial-results.md` (TRIAL-11), the `usage_events` views and
`scripts/pilot_metrics.py` output (TRIAL-6, if ready) and commits the
filled copy as `docs/research/go-no-go-report.md`. Nothing in this file
is a real result — every "Result" and "Evidence" cell below is a
placeholder to be replaced, never pre-filled by an agent.

**Small-sample gates, not impact claims.** Ten (or fewer) participants
can show a gate was breached or clearly met; they cannot support a claim
about impact, effectiveness or the wider student population. The go/no-go
report only states which gates passed or failed on this sample, with
their evidence — it does not extrapolate.

## How to fill this in

1. Copy this file to `docs/research/go-no-go-report.md`.
2. For every gate below, set Result to `pass`, `fail` or `not testable`
   (with a reason) and link the evidence (a file path, a line range, a
   dated note in `docs/research/trial-results.md`, or a metric from
   `pilot_metrics.py`).
3. Fill the limitations and instrument pre-score sections.
4. Record the owner's decision in the Decision section **and** add a
   dated line to `docs/DECISIONS.md` (per TRIAL-12's acceptance — this
   template does not write that entry).
5. Update `STATUS.md`.

## Section 1 — Before-100-users gates (build pack §12, "Before admitting
100 users")

| # | Gate | Result | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 1 | Student A cannot read or change Student B's records | | | |
| 2 | Critical rule test cases pass | | | |
| 3 | Every published critical field has reviewed evidence | | | |
| 4 | Unsupported questions produce an honest fallback | | | |
| 5 | Corrections invalidate cached answers | | | |
| 6 | A backup has actually been restored | | | |
| 7 | The application works with AI disabled | | | |
| 8 | Spending limits and alerts have been tested | | | |
| 9 | A named person owns source review and corrections | | | |
| 10 | Consent and safeguarding workflow reviewed by someone other than its author | | | |
| 11 | The outcome instrument piloted on the first ten users | | | |
| 12 | The distress rule tested in Hindi and Hinglish | | | |

## Section 2 — Step 15 gates (build pack §12, approved before testing per
TRIAL-4)

| # | Gate | Threshold | Result | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | No critical data or security failure | zero | | | |
| 2 | Core journey completed without intervention | at least 8 of 10 | | | |
| 3 | Correctly distinguish estimated from verified cost | at least 8 of 10 | | | |
| 4 | No repeated unexplained save failure | zero repeats | | | |

"Intervention" and "critical failure" are defined in
`docs/research/scoring-sheet.md` (TRIAL-4 sign-off item 2), not redefined
here.

### Step 15 tester tasks — per-task completion (from `docs/research/moderator-script-trial.md`)

| Task | Completed unaided | Completed with intervention | Not completed | Notes |
| --- | --- | --- | --- | --- |
| Explore without signing in | | | | |
| Find two plausible routes and compare | | | | |
| Change a cost assumption and explain the result | | | | |
| Identify verified versus estimated | | | | |
| Open an official source | | | | |
| Save a plan and find the next action | | | | |
| Log out safely on a shared device | | | | |
| Ask a question outside coverage and notice the limitation | | | | |

## Section 3 — Limitations

State every limitation that qualifies the results below; do not omit one
because it is inconvenient. At minimum, address:

- Adult proxies used in place of real minors, if `MINOR_ACCOUNTS_ENABLED`
  stayed false for this trial (weakens validity for the Class 8-12
  target population — disclose, per TRIAL-11's own acceptance note).
- Week-4 post-test status: pending / not yet due / completed (TRIAL-11
  books the date; it may not have arrived by go/no-go time).
- Sample size (n ≤ 10) and what it can and cannot support statistically.
- Any Hindi or shared-device session that could not run as scripted.
- Anything else that came up during TRIAL-11 (device issues, recruitment
  skew, moderator changes, script deviations).

## Section 4 — Instrument pre-score table (build pack §13, five-item
pre/post instrument)

Pre-instrument scores recorded at sign-up, per TRIAL-11's acceptance
("Pre-instrument scores are recorded for all 10"). Post-test (week 4)
scores are added when TRIAL-11's booked date arrives; until then this
table stays partially blank and this document says so explicitly rather
than silently omitting the row.

| Participant | Item 1: names three pathways | Item 2: total cost of first choice | Item 3: next deadline | Item 4: a backup | Item 5: one scholarship they're eligible for | Pre total | Post total | Post administered on |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | | | | | | | | |
| P02 | | | | | | | | |
| P03 | | | | | | | | |
| P04 | | | | | | | | |
| P05 | | | | | | | | |
| P06 | | | | | | | | |
| P07 | | | | | | | | |
| P08 | | | | | | | | |
| P09 | | | | | | | | |
| P10 | | | | | | | | |

Target referenced by the DPR: a 15-point uplift (build pack §13). Ten
participants cannot confirm or refute that target; this table only
records what was observed on this sample.

## Section 5 — Decision

- **Decision:** Go / Fix-and-retest / Stop *(delete the two that don't apply)*
- **Decided by:** *(owner name or initials)*
- **Date:** *(ISO date)*
- **Rationale:** *(one paragraph, referencing the specific failed or
  passed gates above — not a general impression)*
- **If fix-and-retest:** list the specific fixes required and who owns
  each, plus the re-test scope (full Step 15 script again, or targeted
  re-check of the failed gate only).
- **`docs/DECISIONS.md` entry:** *(date + one-line pointer to the entry
  recording this decision — added by whoever runs TRIAL-12, not by this
  template)*
- **`STATUS.md` updated:** yes / no
