# evals/reports/

A report file here (`<run-date>.json`) is the JSON output of one run of
`scripts/run_ai_eval.py` against `evals/ask_bcion_questions.yaml` — never
a record of anything a real student asked. Every id, question label and
claim value a report can possibly contain is either an eval-set
`synthetic-*-NNN` placeholder or a row `scripts/seed_ai_eval_fixtures.py`
seeded (see that script's own docstring for why those rows are shaped the
way they are); it is synthetic input either way, exactly like the eval set
it was generated from, and must never be treated as, or published as, a
verified fact about any real pathway, career or claim.

To read a report: `summary` at the top level is the run in one glance —
`total_questions` (the eval set's full size, e.g. 36 — distinct from
`reached`), `reached`/`not_reached_count` (whether the run's own
`--max-calls` cap cut it short, and how many questions were never
attempted because of it), `cap_hit` (`true`/`false` — whether the cap was
actually the reason the run stopped early; `not_reached_count` can be 0
with `cap_hit` still worth checking), `matched_expected_status_count`/
`mismatched_expected_status_count` (against each question's own
`expected_status` in the eval file — a mismatch is not automatically a
bug; see `questions[].architecture_note` below), `status_counts` (how many
questions landed on each real `app.ai.schemas.AIAnswerStatus` value),
`calls_used_total`/`max_calls` (spend against the cap), and
`mean_latency_ms`/`p95_latency_ms`.

The `questions` list carries one entry per question actually run. Beyond
`id`/`category`/`language`/`text` (copied straight from the eval file) and
`mapped_template_id`/`mapped_id_field`/`mapped_placeholder`/
`mapped_resolved_id`/`mapping_rationale` (exactly what `AskRequest` was
built and from which eval-set id, and why), the fields that matter most
for diagnosing a run:
- `actual_status`/`matched_expected_status` — the real pipeline result
  and whether it matched the eval file's expectation.
- `error` — **the field that tells you whether a mismatch is a real bug
  or a crash.** `null` means the pipeline ran to completion and returned
  a real status (a mismatch here is a genuine behavioural finding, or a
  documented `architecture_note` case). A non-null string (`"<exception
  type>: <message>"`) means the pipeline raised and this question never
  produced a real answer at all — always check this before reading
  `actual_status` for a question that surprised you.
- `architecture_note` (when present) explains a known, documented reason
  a mismatch is structural rather than a defect — see
  `scripts/run_ai_eval.py`'s own module docstring for the full
  architecture-mismatch analysis this field draws from.
- `provider_used`, `selection_ids`, `verification_ids`, `calls_used`,
  `latency_ms` — which provider mode ran this question, the two-pass
  pipeline's own id lists, and per-question spend/timing.

`not_reached` (top level) lists every question id the run's cap prevented
from starting at all.
