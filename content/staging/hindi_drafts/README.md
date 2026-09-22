# Hindi translation drafts (staging)

Each CSV in this directory is machine output from `scripts/ai_translate_drafts.py`
(AI-20): one row per `app/i18n/en.json` key that was missing from
`app/i18n/hi.json` when the script ran, with a proposed Hindi translation and a
separate back-translation-into-English check for that translation. The
`agreement_flag`/`agreement_score` columns are a cheap, lexical (word-overlap)
sanity check, not a correctness guarantee — they catch gross translation
failures, not subtle wrong-meaning ones, so **every row must be read by a
human, whether it is flagged `agrees` or `needs_review`**. This CSV is a
draft for a human Hindi reviewer only. It is never a source of truth, it is
never read by any application code, and `scripts/ai_translate_drafts.py` never
writes `app/i18n/hi.json` itself.

To accept a row: the reviewer copies the (possibly hand-corrected)
`hindi_draft` text into `app/i18n/hi.json` under that row's `key` by hand, and
updates `hi.json`'s own `_meta.reviewed_by` and `_meta.reviewed_on` fields
(task I18N-11) to record who reviewed it and when. A row that is not copied
across — including one flagged `agrees` — is simply left out; nothing here
is applied automatically.
