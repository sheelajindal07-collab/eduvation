# evals/

`ask_bcion_questions.yaml` is the AI evaluator's question set (AI-9):
36 synthetic questions against the AI adapter (`app/ai/*`), each keyed
by `synthetic-*-NNN` id placeholders only -- never real content, never
a real career, source, fee or date. Its own header states this in
plain text and it must never be treated as verified data, imported
into the content store, or shown to a student; it mirrors, for a YAML
file, the same rule `scripts/seed_synthetic.py`'s `SAMPLE_LABEL`
enforces for seeded database rows.

Each question is a mapping with these fields: `id` (unique string),
`category` (one of `supported`, `ambiguous`, `unsupported`, `stale`,
`injection`, `source_mismatch`, `api_failure`), `language` (`en`, `hi`
for Devanagari-script Hindi, or `hi-Latn` for romanized Hindi/Hinglish
-- this describes the language the *student's question* is written in,
not the app's own closed `en`/`hi` UI-chrome locale allow-list in
`app/i18n/`), `text` (the question), `expected_status` (one of
`answered`, `not_available`, `insufficient_information` -- these three
reuse `app.ai.grounding.AIAnswerStatus` exactly, deliberately not
reinvented -- or `provider_error`, an eval-set-only fourth value for
`api_failure` cases where no `AIAnswerStatus` verdict is ever reached
because the provider call itself is forced to fail and only the
fallback copy is correct), and `synthetic_record_ids` (the list of
`synthetic-*-NNN` placeholders the question concerns; an empty list
where no record covers the question at all, as in `unsupported` and
some `injection` cases). Optional fields: `scope` (`all_india` or
`abroad`, marking the cases the card requires -- at least two of each),
`notes` (free text on what the case calibrates), `injection_vector`
(`user_question` or `record_text`, `injection` cases only), and
`force_provider_error` (always `true`, `api_failure` cases only, a
flag that the case must be run with the provider forced to error
rather than against a normal response).

To add a question: append a mapping with at minimum `id`, `category`,
`language`, `text`, `expected_status` and `synthetic_record_ids` to the
`questions` list, keep the category/language/scope minimums enforced
by `tests/unit/test_eval_set_schema.py` intact, and never put a real
career name, real source, real number or anything that looks like a
real phone number or email address into `text` -- the schema test lints
for PII-shaped strings and will fail the build if one slips in.
