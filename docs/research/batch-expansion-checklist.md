# Batch expansion checklist — 10 -> 25 -> 50 -> 100 (TRIAL-10)

Covers the eight per-batch expansion checks from the build pack (§12,
"Expansion checks per batch"). TRIAL-13 runs this checklist before each
of the four batches, after `make pilot-metrics` (TRIAL-6) produces the
numbers it needs.

**Every pause limit below is PROPOSED.** None of them is in force until
the owner approves them in TRIAL-4 ("Third, the numeric pause limits
proposed in the TRIAL-10 checklist"). Until that sign-off, this document
is a draft for review, not an operating rule — no script or runbook may
enforce these numbers yet.

**Small-sample gates, not impact claims.** At 10-25 users several of
these counts will be tiny (n<5 per `pilot_metrics.py`'s own suppression
rule); a breach on a handful of events is a real signal at this scale
but is not evidence of a population-level rate.

## General pause/resume rule

- Any breach below is a **pause**, not an automatic rollback: no new
  batch is admitted until the item is resolved or the owner records an
  explicit, dated exception.
- The owner declares the pause and records it, with the breached check,
  the evidence and the date, in `docs/research/batch-records/` (TRIAL-13
  owns that directory).
- Resuming needs a documented reason (what changed, who verified it) in
  the same batch record — never a silent resume.
- A privacy, data-integrity or spend breach pauses immediately, even
  mid-batch, independent of the per-batch review point; the others are
  checked at the batch boundary.
- No batch is admitted while any Section-1 ("Before admitting 100
  users") gate from `docs/research/go-no-go-template.md` is open, on top
  of the eight checks here (see TRIAL-13's own acceptance).

## The eight checks

| # | Check | Proposed pause limit (draft, needs TRIAL-4 sign-off) | Evidence source | Notes |
| --- | --- | --- | --- | --- |
| 1 | Failed logins and saves | Pause if the failed-save rate exceeds 5% of save attempts in any rolling 24h window, or 3+ users each report an unexplained failed save in one batch | `scripts/pilot_metrics.py` (OPS-2 log event names); `scripts/ops_check.py` | "Repeated unexplained save failure" is also a Step 15 gate (Section 2 of the go/no-go template) — a breach here at trial scale should already have failed that gate |
| 2 | Critical source freshness | Pause if any published Tier-1 (`docs/DATA.md` critical tier: exam dates, deadlines, eligibility, fees) claim is past its `review_due_date` | `scripts/content/coverage_report.py` (CONTENT-8); reviewer `/reviewer/due` view (PUB-11) | Zero tolerance proposed because Tier-1 is exam dates/deadlines/eligibility/fees — the highest-harm category if stale |
| 3 | Pending reviews | Pause if the `in_review` queue depth exceeds 25 claims, or any single claim has sat `in_review` for more than 14 days | `scripts/content/coverage_report.py`; reviewer queue counts | Matches Tier-1's proposed 14-day review-due cadence (`docs/plan/inventory-2-trust-content.md` open question, recommended default, not yet owner-confirmed) |
| 4 | AI fallback rate | Pause if the "not verified" / fallback rate exceeds 50% of AI-eligible questions in the batch | `scripts/pilot_metrics.py` (ai_usage table) | A high fallback rate is the *safe* failure mode (build pack §12: "unsupported questions produce an honest fallback"), so this is a coverage-gap signal for the content track, not a safety pause in itself — still tracked so a persistently thin content set is visible before more users hit it |
| 5 | Usage budget | Pause if `ai_monthly_spend_cap_inr` projected month-end spend exceeds 90% of the cap, or the daily request budget is hit on 2 consecutive days | `scripts/pilot_metrics.py`; `app/core/config.py` cap values | Ties to build pack §11 budget range (₹1,000-5,000/month for AI at Hindi-adjusted volumes) |
| 6 | Backup status | Pause if the last verified backup is more than 48h old, or no restore has been test-verified in the last 30 days | `scripts/ops_check.py` (last backup file date) | The "backup has actually been restored" before-100-users gate is a one-time proof; this is the ongoing per-batch check that it stays true |
| 7 | Reviewer hours per record | Flag (not an automatic pause) if average editor/reviewer hours per newly published record exceeds 2x the CONTENT-15/CONTENT-5 planning estimate for that record type | Reviewer time log (`docs/CONTENT-EDITOR-HANDBOOK.md`'s batch time-logging section, CONTENT-15) | This is a capacity/scaling signal (DPR measurement, build pack §13 "Editor hours per verified programme record"), not a student-facing safety issue, so it is proposed as a flag-and-review item rather than a hard pause — the owner may downgrade or keep it a pause in TRIAL-4 |
| 8 | Support requests per 100 users | Pause if support requests exceed 10 per 100 active users per week | `scripts/pilot_metrics.py` (Ops feedback/support table, once built) | No existing baseline in this pilot; proposed as a starting point only, expect TRIAL-4 to revise once round-1/Step-15 data exists |

## Batch record

Each batch run produces one dated record under
`docs/research/batch-records/` (TRIAL-13) stating: batch size admitted,
date, the eight checks' values on that date, which (if any) breached,
any pause and its documented resume reason, and the owner's sign-off.
This checklist does not create that directory or its records — TRIAL-13
does.
