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
`reached`/`not_reached_count` (whether the run's own `--max-calls` cap cut
it short, and how many questions were never attempted because of it),
`matched_expected_status_count`/`mismatched_expected_status_count`
(against each question's own `expected_status` in the eval file — a
mismatch is not automatically a bug; see `questions[].architecture_note`
below), `status_counts` (how many questions landed on each real
`app.ai.schemas.AIAnswerStatus` value), `calls_used_total`/`max_calls`
(spend against the cap), and `mean_latency_ms`/`p95_latency_ms`. The
`questions` list carries one entry per question actually run — its own
`mapped_template_id`/`mapped_id_field`/`mapped_placeholder`/
`mapped_resolved_id` fields show exactly what `AskRequest` was built and
from which eval-set id, `actual_status`/`matched_expected_status` show the
real pipeline result, and `architecture_note` (when present) explains a
known, documented reason a mismatch is structural rather than a defect —
see `scripts/run_ai_eval.py`'s own module docstring for the full
architecture-mismatch analysis this field draws from. `not_reached` (top
level) lists every question id the run's cap prevented from starting at
all.
