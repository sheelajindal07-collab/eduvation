#!/usr/bin/env python
"""Capped evaluation runner for Ask BCION (AI-11, BCI-019).

Reads `evals/ask_bcion_questions.yaml` (AI-9), maps every question to an
`app.ai.schemas.AskRequest` and runs it through the real two-pass pipeline
(`app.ai.pipeline.answer`, AI-6), with an injectable provider and a hard
call ceiling that ABORTS THE WHOLE RUN — not just the one question — the
instant running the next question could exceed it. Writes one JSON report
per run to `evals/reports/<run-date>.json` (see `evals/reports/README.md`).

    python -m scripts.run_ai_eval --provider mock                    # safe default
    python -m scripts.run_ai_eval --provider mock --max-calls 80     # full 36-Q pass
    python -m scripts.run_ai_eval --provider gemini --max-calls 40   # owner-run, spends real quota

Invoked with `-m` (`python -m scripts.run_ai_eval ...`), not
`python scripts/run_ai_eval.py`, from the repo root — this module imports
`scripts.seed_synthetic` (to reuse its production guard, never
reimplement it), and only `-m` puts the repo root on `sys.path` so
`scripts` resolves as a package. Run under pytest, both forms resolve
identically (pytest's own rootdir insertion) — this only matters for a
human running the script directly.

`--provider mock` is the ONLY mode ever exercised by
`tests/unit/test_run_ai_eval.py` (zero network, zero real provider call).
`--provider gemini` constructs a real `app.ai.gemini_provider.GeminiProvider`
and is an owner-run live pass only — never invoked by a test in this repo.

## The question text is NEVER sent anywhere

`evals/ask_bcion_questions.yaml`'s `text` field is documented there as
"the question, exactly as a student might type it" — but
`app.ai.schemas.AskRequest` (AI-6, read directly, not guessed) has **no
free-text field at all**: `template_id` plus one of
`pathway_id`/`career_id`/`claim_id`/`plan_id`, and `lang`. This is Rule 3
working as intended (no student-typed text ever reaches the provider)
colliding with an eval set written to read naturally for a human. This
module resolves that collision by mapping each question to a
`template_id` + entity id explicitly (`QUESTION_TEMPLATE_MAP`,
`build_ask_request` below) and treating `text` as nothing more than a
human-readable label copied into the JSON report — it is never passed to
`app.ai.pipeline.answer()`, never embedded in a prompt, never sent to any
provider. State this plainly because it is easy to assume otherwise:
**`question["text"]` never leaves this process except as report output.**

## Three further, genuine architecture mismatches found while building this

Beyond the free-text/AskRequest mismatch above (which this card's own
"Read this first" section already named), building a working mapping for
all 36 questions surfaced three more, each documented at the point it
matters and summarised here:

1. **No id at all -> `unsupported_template`, not the eval file's own
   `not_available`.** Several questions (every `unsupported` case except
   `unsupported-06`, plus `injection-04`/`injection-05`) carry
   `synthetic_record_ids: []` by design — "no record covers this at
   all". But `AskRequest` needs *some* id to even attempt retrieval; with
   none available, `app.ai.pipeline.answer()`'s step 1
   (`request.record_id_for(template) is None`) returns
   `unsupported_template` before retrieval, budget or the provider are
   ever touched — never `not_available`, which only step 3 (retrieval
   found nothing) can produce. `architecture_note_for()` below flags
   every such question in the report rather than either skipping it or
   silently reporting a false "match".

2. **`ambiguous` (5 questions) cannot be represented by a single
   `AskRequest` at all.** The category's whole premise — a student's
   *name* matching two different pathways — presupposes a name-resolution
   step upstream of the pipeline. `AskRequest.pathway_id` is always
   already one specific, disambiguated id; by the time a caller has one,
   the ambiguity the eval file is testing has already been resolved
   somewhere else (a UI list, in Phase 1a's real product — never a
   student-typed name at all, per Rule 3). Running these questions still
   produces a real, honest `Answer` (typically `answered`, from whichever
   one of the two same-named pathways the mapping happens to resolve to
   first) — it does not, and structurally cannot, exercise the
   "ambiguous" behaviour the eval file's authors had in mind.

3. **`source_mismatch` (5 questions) cannot be represented either.**
   `eligibility_gap` is the only template that takes a `claim_id`, and it
   takes ONLY a bare claim id — no accompanying `pathway_id` for
   `app.ai.retrieval.fetch_claim_record` to cross-check it against.
   `PromptTemplate.requires` is a single `PromptTemplateRequirement` by
   design (its own docstring: "a template that needed two ids would be
   two templates"), so "this claim was cited for the wrong pathway" is
   not a checkable condition anywhere in the current pipeline: the claim
   resolves on its own terms regardless of which pathway a question's
   text names. Running these questions exercises `fetch_claim_record`
   honestly (and, if the cited claim is itself a real, fresh, published
   record — which it is here, since every `synthetic_record_ids` claim in
   this eval set is reused from another category's own fixture — the
   pipeline correctly answers from it), it just does not prove anything
   about pathway/claim cross-validation, because there is no such check
   to prove.

None of this is a runner bug. All three are reported per-question via
`architecture_note_for()` and summarised again in this card's own
completion report, per this card's explicit instruction not to pad
coverage with a fixture that doesn't actually test what its category
claims.

## `injection_vector: user_question` is moot here too

Per this card's own instruction: a `category: injection` question with
`injection_vector: user_question` describes an instruction embedded in
the STUDENT'S QUESTION text — and there is no student-question field
anywhere in `AskRequest` for such an instruction to reach (see above).
`architecture_note_for()` flags this explicitly on every such question
rather than silently dropping that half of the category's coverage.
`injection_vector: record_text` cases are different and ARE meaningfully
testable: `scripts/seed_ai_eval_fixtures.py` seeds the adversarial phrase
described in that question's own `notes` field directly into the backing
claim's *value* (see that script's own docstring for exactly which claim
and why), so a live run genuinely exercises "does an instruction embedded
in a published record's own text leak into the answer" against real
retrieval.

## `MockAIProvider`'s default "echo" mode does not work for this pipeline

Discovered while wiring `--provider mock`: `app.ai.mock_provider`'s
module docstring describes its default (no `responses`/`canned_response`)
mode as parsing `CLAIM <id>:` lines — that is `app/ai/grounding.py`'s own
single-pass prompt format. `app/ai/prompts.py`'s two-pass prompts (used
by `app/ai/pipeline.py`, the module this card evaluates) emit
`RECORD <id>: field=... value=... source=...` lines instead — a different
keyword the default echo regex never matches. Relying on the default here
would silently make every `--provider mock` question resolve to
`insufficient_information` (an empty pass-one selection) regardless of
what is actually seeded, masking real data with a false negative. This
module never uses the default: `_cooperative_mock_responses()` below
fetches the SAME records `app.ai.pipeline.answer()` will independently
re-fetch (a second, read-only, side-effect-free call to
`app.ai.retrieval`'s own functions) and scripts an explicit
`responses=[...]` pair — one bare `[<id>]` selection line and one
`YES <id>` verification line per retrieved record — so a mock run
exercises the REAL selection/verification/freshness/sentence-generation
code path, with the pipeline's own logic (never this runner) deciding the
final `Answer.status`.

## `category: api_failure` always forces a scripted raise

Per this card's own instruction, every `force_provider_error: true`
question is run against a fresh `MockAIProvider` with
`raise_on_call(1, ...)` scripted — regardless of `--provider` — even in a
"live" `--provider gemini` run. The point is proving THIS pipeline's own
fallback behaviour (`ai_unavailable`, with fallback citations attached),
not testing the real Gemini API's uptime.

## The hard call ceiling

`--max-calls N` (default `DEFAULT_MAX_CALLS`, deliberately conservative —
a full 36-question pass can need up to 72 provider calls, since
`app.ai.budget.AIRequestBudget.reserve()` is called exactly twice, up
front, by every pipeline invocation that gets past template validation,
the AI feature flags and retrieval — see `app/ai/pipeline.py`'s own
module docstring, step 4). Before every question, this runner checks
`budget.remaining() < 2` (the worst case ANY single pipeline invocation
could reserve) and, the instant that is true, stops the run entirely —
every question from that point on is recorded in the report's
`not_reached` list, never attempted. This is deliberately more
conservative than `AIRequestBudget` itself: left alone, `app.ai.pipeline.
answer()` catches `AIBudgetExceededError` internally and returns a
graceful `budget_exhausted` `Answer` for just that one question, then
keeps going — exactly the per-question degradation this card's own text
says a "capped" runner must NOT rely on for its abort behaviour. Calling
`pipeline.answer()` at all is still safe even after the runner's own
check (belt and braces): if this runner's pre-check is ever wrong, the
budget object itself is the second, independent backstop.

## Real ids: `synthetic-*-NNN` placeholders are not database ids

`evals/ask_bcion_questions.yaml`'s `synthetic_record_ids` (e.g.
`synthetic-pathway-001`) are free-form string LABELS — they satisfy
`app.ai.schemas`'s own `_ID_RE` id-shape check just fine, but
`pathways.id`/`claims.id` are `uuid` columns
(`db/migrations/0001_init.sql`) on any real Postgres-backed Supabase
stack, so the literal placeholder string can never be written there.
`synthetic_placeholder_to_uuid()` below is the ONE place this mapping is
defined (`uuid.uuid5` over a fixed namespace) — `scripts/
seed_ai_eval_fixtures.py` imports it directly so a seeded row's real id
and this runner's resolved `AskRequest` id are always the same value for
the same placeholder, on any machine, on any run. A fake in-memory test
double keyed by these same resolved ids (see
`tests/unit/test_run_ai_eval.py`) exercises the identical code path a
real local-stack run does.

No student data anywhere in this module — every id, name and claim value
this runner ever touches is either a `synthetic-*-NNN` eval-set
placeholder or a row `scripts/seed_ai_eval_fixtures.py` seeded, and that
script's own docstring states plainly why those rows are shaped the way
they are.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import yaml
from supabase import Client

from app.ai.adapter import AIProvider
from app.ai.budget import AIRequestBudget
from app.ai.mock_provider import MockAIProvider
from app.ai.pipeline import answer as pipeline_answer
from app.ai.prompts import TEMPLATE_REGISTRY
from app.ai.retrieval import fetch_claim_record, fetch_pathway_records
from app.ai.schemas import (
    AIAnswerStatus,
    AIProviderTimeout,
    Answer,
    AskRequest,
    PromptTemplate,
    PromptTemplateRequirement,
)
from scripts.seed_synthetic import _allowlisted_origins, guard_problem

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
EVAL_YAML_PATH: Final[Path] = REPO_ROOT / "evals" / "ask_bcion_questions.yaml"
REPORTS_DIR: Final[Path] = REPO_ROOT / "evals" / "reports"

#: Deliberately conservative. `pipeline.answer()` reserves exactly two
#: budget calls per question that reaches step 4 (template + flags +
#: retrieval all passed) — a full 36-question run can need up to 72. This
#: default protects a `--provider gemini` run from an accidental full-cost
#: pass; override with `--max-calls` for a fuller run.
DEFAULT_MAX_CALLS: Final[int] = 20

#: The worst-case number of calls ANY single pipeline invocation could
#: reserve (`app/ai/pipeline.py` step 4: `budget.reserve()` called twice,
#: unconditionally, before either provider call). Used for this runner's
#: OWN pre-question abort check — see module docstring's "The hard call
#: ceiling" section.
_MAX_CALLS_PER_QUESTION: Final[int] = 2

#: Never a real secret — see module docstring. Only ever written to this
#: process's own environment, only for `--provider mock`, only so
#: `Settings.ai_configured` (`bool(gemini_api_key)`) reads True; no
#: network call is ever made through this value because `--provider mock`
#: never constructs a `GeminiProvider` at all.
_MOCK_PLACEHOLDER_GEMINI_KEY: Final[str] = "eval-runner-mock-placeholder-not-a-real-key"

# ---------------------------------------------------------------------
# Placeholder id <-> real database id
# ---------------------------------------------------------------------

#: Fixed, arbitrary, public namespace for `synthetic_placeholder_to_uuid`.
#: Distinct from `scripts.seed_synthetic.SEED_NAMESPACE` on purpose: the
#: two scripts seed unrelated, non-overlapping id spaces (general
#: dev/staging sample content vs. this eval set's own fixed placeholders)
#: and must never collide.
_SYNTHETIC_ID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("b1c10e11-0000-5000-8000-0000000000e1")


def synthetic_placeholder_to_uuid(placeholder: str) -> str:
    """The real database id a `synthetic-*-NNN` placeholder resolves to.

    Deterministic (same placeholder -> same UUID, every machine, every
    run) — see module docstring's "Real ids" section for why this exists
    at all. `scripts/seed_ai_eval_fixtures.py` imports this function
    directly rather than recomputing the mapping, so the two scripts can
    never silently drift apart.
    """
    return str(uuid.uuid5(_SYNTHETIC_ID_NAMESPACE, placeholder))


def _first_id_with_marker(record_ids: Sequence[str], marker: str) -> str | None:
    """The first entry of `record_ids` containing `marker` (`"pathway"` or
    `"claim"`) as a substring — e.g. `"synthetic-pathway-001"` for
    `marker="pathway"`. `None` when no entry matches, which is exactly the
    "this question's synthetic_record_ids carries no id of the shape this
    template needs" case the module docstring's architecture-mismatch
    section documents."""
    return next((rid for rid in record_ids if marker in rid), None)


def _lang_for_ask_request(language: str) -> str:
    """`AskRequest.lang` only allows `"en"`/`"hi"`
    (`app.ai.schemas.SUPPORTED_LANGS`) — the eval set's own third value,
    `"hi-Latn"` (romanised Hindi/Hinglish, `evals/README.md`), describes
    what SCRIPT the student's question was written in, a concept
    `AskRequest` has no field for at all (there is no question text on it
    — see module docstring). Since Hinglish content is Hindi, not
    English, it maps to `"hi"` here; `"en"` stays `"en"`. This mapping
    only ever affects `OutboundPayload.lang` (a provider-facing hint, not
    a routing decision) — nothing about template/entity selection depends
    on it.
    """
    return "hi" if language in ("hi", "hi-Latn") else "en"


# ---------------------------------------------------------------------
# The question -> template_id mapping
# ---------------------------------------------------------------------

#: question id -> (template_id, one-line rationale). THIS is "the exact
#: question -> template_id/entity_id mapping table" this card's own
#: completion-report format asks for — adjust entries here, not via
#: scattered inline guesses elsewhere, if a future reviewer disagrees with
#: one. Every template_id here is a real key in
#: `app.ai.prompts.TEMPLATE_REGISTRY` (`cost_breakdown`, `pathway_overview`,
#: `eligibility_gap`) — asserted at import time below, so a typo here is a
#: build-time failure, not a silent KeyError mid-run.
#:
#: Heuristic applied uniformly (this card's own "Read this first" text):
#: a fee/cost/money question -> `cost_breakdown`; an age/eligibility/
#: entrance-requirement question -> `eligibility_gap`; anything else
#: (duration, seats/intake, admission process, "what does this involve")
#: -> `pathway_overview`. `source_mismatch` questions are the one
#: exception: every one of them explicitly names a claim id in its own
#: question text ("According to synthetic-claim-NNN, ..."), so they are
#: mapped to `eligibility_gap` (the only claim_id-taking template)
#: regardless of subject matter — see module docstring point 3 for why
#: this does not actually test what the category's name suggests.
QUESTION_TEMPLATE_MAP: Final[dict[str, tuple[str, str]]] = {
    # --- supported ---
    "supported-01": ("cost_breakdown", "fee question ('total course fee')"),
    "supported-02": ("eligibility_gap", "age question ('minimum age', Hindi)"),
    "supported-03": ("pathway_overview", "duration question, no fee/age keyword"),
    "supported-04": ("eligibility_gap", "requirement question ('entrance requirement')"),
    "supported-05": ("cost_breakdown", "cost question (Hindi, 'kul lagat'/total cost)"),
    "supported-06": ("pathway_overview", "seat-count/intake question, no fee/age keyword"),
    # --- ambiguous (see module docstring point 2: not really testable) ---
    "ambiguous-01": ("cost_breakdown", "fee question"),
    "ambiguous-02": ("pathway_overview", "duration question, no fee/age keyword"),
    "ambiguous-03": ("eligibility_gap", "qualification/requirement question (Hindi)"),
    "ambiguous-04": ("cost_breakdown", "fee question (Hinglish)"),
    "ambiguous-05": ("pathway_overview", "capacity question, no fee/age keyword"),
    # --- unsupported ---
    "unsupported-01": ("cost_breakdown", "fee question ('hidden capitation fee')"),
    "unsupported-02": ("pathway_overview", "no fee/age keyword ('guarantee a government job')"),
    "unsupported-03": ("cost_breakdown", "money-amount question (scholarship), nearest to cost"),
    "unsupported-04": ("eligibility_gap", "'requirements' is the head noun of the question"),
    "unsupported-05": ("pathway_overview", "admission-process question, no fee/age keyword"),
    "unsupported-06": ("cost_breakdown", "fee question ('hostel fee')"),
    # --- stale ---
    "stale-01": ("cost_breakdown", "fee question ('current course fee')"),
    "stale-02": ("eligibility_gap", "requirement question ('entrance exam ... required')"),
    "stale-03": ("eligibility_gap", "age question (Hindi, 'minimum age limit')"),
    "stale-04": ("pathway_overview", "duration question, no fee/age keyword"),
    "stale-05": ("cost_breakdown", "cost question ('total cost')"),
    # --- injection (see module docstring: user_question vector is moot) ---
    "injection-01": ("cost_breakdown", "fee question; user_question injection vector"),
    "injection-02": ("eligibility_gap", "age question; record_text injection vector"),
    "injection-03": ("pathway_overview", "duration question; user_question injection vector"),
    "injection-04": ("cost_breakdown", "fee-flavoured fabrication attempt; no id supplied"),
    "injection-05": ("pathway_overview", "general question; no id supplied"),
    # --- source_mismatch (see module docstring point 3: not really testable) ---
    "source-mismatch-01": ("eligibility_gap", "question explicitly cites a claim id"),
    "source-mismatch-02": ("eligibility_gap", "question explicitly cites a claim id"),
    "source-mismatch-03": ("eligibility_gap", "question explicitly cites a claim id"),
    "source-mismatch-04": ("eligibility_gap", "question explicitly cites a claim id"),
    "source-mismatch-05": ("eligibility_gap", "question explicitly cites a claim id"),
    # --- api_failure (same subject matter as their supported-NN twins) ---
    "api-failure-01": ("cost_breakdown", "same question as supported-01"),
    "api-failure-02": ("eligibility_gap", "age question, same pattern as supported-02"),
    "api-failure-03": ("pathway_overview", "duration question, same pattern as supported-03"),
    "api-failure-04": ("cost_breakdown", "cost question ('total cost')"),
}

for _tid, _rationale in QUESTION_TEMPLATE_MAP.values():
    if _tid not in TEMPLATE_REGISTRY:
        raise AssertionError(
            f"QUESTION_TEMPLATE_MAP names template_id {_tid!r}, which is not in "
            "app.ai.prompts.TEMPLATE_REGISTRY -- fix the mapping table, not the registry."
        )
del _tid, _rationale


def build_ask_request(
    question: dict[str, Any],
) -> tuple[AskRequest, PromptTemplate, str | None, str | None]:
    """Map one eval-set `question` to a real `AskRequest`.

    Returns `(request, template, placeholder, resolved_id)`:
    - `request` — the constructed `AskRequest` (never carries `text`).
    - `template` — the `PromptTemplate` `request.template_id` names.
    - `placeholder` — the `synthetic-*-NNN` string this mapping picked out
      of `question["synthetic_record_ids"]` (the first entry whose name
      contains `"pathway"` or `"claim"`, matching whichever id
      `template.requires`), or `None` if no such entry exists.
    - `resolved_id` — `synthetic_placeholder_to_uuid(placeholder)`, or
      `None` when `placeholder` is `None` — this is exactly what makes
      `request.record_id_for(template)` `None` too, which is what sends a
      question straight to `AIAnswerStatus.unsupported_template` (module
      docstring, architecture mismatch point 1).
    """
    template_id, _rationale = QUESTION_TEMPLATE_MAP[question["id"]]
    template = TEMPLATE_REGISTRY[template_id]
    marker = "pathway" if template.requires is PromptTemplateRequirement.pathway_id else "claim"
    placeholder = _first_id_with_marker(question.get("synthetic_record_ids", []), marker)
    resolved_id = synthetic_placeholder_to_uuid(placeholder) if placeholder is not None else None

    kwargs: dict[str, Any] = {
        "template_id": template_id,
        "lang": _lang_for_ask_request(question["language"]),
    }
    if template.requires is PromptTemplateRequirement.pathway_id:
        kwargs["pathway_id"] = resolved_id
    elif template.requires is PromptTemplateRequirement.claim_id:
        kwargs["claim_id"] = resolved_id
    # No template in TEMPLATE_REGISTRY today requires career_id/plan_id
    # (app/ai/prompts.py's own module docstring) -- nothing to set for
    # either, defensively handled rather than assumed unreachable.

    return AskRequest(**kwargs), template, placeholder, resolved_id


def architecture_note_for(question: dict[str, Any], resolved_id: str | None) -> str | None:
    """Why THIS question's `matched_expected_status` may legitimately be
    `False` for a reason that is not a pipeline bug or a mapping mistake
    — see module docstring's numbered architecture-mismatch list. `None`
    when no known structural gap applies (most questions)."""
    if resolved_id is None:
        return (
            "this question's synthetic_record_ids carries no id matching the "
            "mapped template's required id-shape, so AskRequest carries None for "
            "that field and app.ai.pipeline.answer() returns unsupported_template "
            "at step 1 -- before retrieval, budget or the provider are ever "
            "touched. Not the eval file's own not_available; see this runner's "
            "module docstring, architecture mismatch point 1."
        )
    category = question.get("category")
    if category == "ambiguous":
        return (
            "AskRequest always carries one already-resolved pathway_id; there is "
            "no student-typed name for two same-named pathways to collide on once "
            "an id has been chosen, so this category's own premise (name "
            "ambiguity) cannot be represented by a single AskRequest under the "
            "current template design -- see this runner's module docstring, "
            "architecture mismatch point 2."
        )
    if category == "source_mismatch":
        return (
            "eligibility_gap's AskRequest carries a bare claim_id with no "
            "pathway_id for app.ai.retrieval.fetch_claim_record to cross-check it "
            "against, so the cited claim resolves on its own terms regardless of "
            "which pathway the question names -- this category's own premise (a "
            "claim cited for the wrong pathway) is not checkable by the current "
            "single-id-per-template design -- see this runner's module docstring, "
            "architecture mismatch point 3."
        )
    if category == "injection" and question.get("injection_vector") == "user_question":
        return (
            "injection_vector: user_question is moot here -- there is no "
            "free-typed question field anywhere in AskRequest (Rule 3) for a "
            "user-question-embedded instruction to reach. Flagged per this card's "
            "own instruction rather than silently dropped."
        )
    return None


# ---------------------------------------------------------------------
# Scripting the mock provider
# ---------------------------------------------------------------------


def _cooperative_mock_responses(
    db: Client, request: AskRequest, template: PromptTemplate, *, as_of: date
) -> list[str]:
    """A maximally-cooperative two-pass `MockAIProvider.responses` pair
    for `request`, built from the SAME records `app.ai.pipeline.answer()`
    will independently re-fetch for it (a second, read-only,
    side-effect-free call to `app.ai.retrieval`'s own functions -- never
    the pipeline's arithmetic, never re-derived). See module docstring's
    "MockAIProvider's default echo mode does not work for this pipeline"
    section for why this exists at all instead of relying on the default.

    Selects and verifies EVERY retrieved record, staleness included: a
    real model is never asked to reason about the freshness SLA (that is
    `app/ai/pipeline.py` step 10's own job, entirely in code, after
    verification) -- so a maximally-cooperative script must not pre-empt
    it either. Whatever the pipeline decides from here (freshness,
    grounding, banned phrases) is the pipeline's own real behaviour, not
    something this function fakes.

    Empty list when nothing will be retrieved at all (no id supplied, or
    retrieval found no grounded record) -- `MockAIProvider` never
    complains about an unused `responses` list, only about being called
    MORE times than it has scripted responses for, and zero calls happen
    on either of those paths (`app/ai/pipeline.py` steps 1-3).
    """
    record_id = request.record_id_for(template)
    if record_id is None:
        return []
    if template.requires is PromptTemplateRequirement.pathway_id:
        records = fetch_pathway_records(db, record_id, as_of=as_of)
    elif template.requires is PromptTemplateRequirement.claim_id:
        one = fetch_claim_record(db, record_id, as_of=as_of)
        records = (one,) if one is not None else ()
    else:
        records = ()  # career_id/plan_id -- no template in TEMPLATE_REGISTRY uses either today.
    if not records:
        return []
    ids = [record.id for record in records]
    selection = "\n".join(f"[{record_id_}]" for record_id_ in ids)
    verification = "\n".join(f"YES {record_id_}" for record_id_ in ids)
    return [selection, verification]


# ---------------------------------------------------------------------
# Status comparison, percentile, per-question run
# ---------------------------------------------------------------------


def _status_matches_expected(actual: AIAnswerStatus, expected: str) -> bool:
    """`evals/README.md`'s `expected_status` vocabulary reuses
    `AIAnswerStatus` exactly for three values and adds one eval-set-only
    fourth value, `"provider_error"`, for `api_failure` cases where no
    `AIAnswerStatus` verdict is meaningful because the provider call
    itself was forced to fail -- that maps to `ai_unavailable`, the
    pipeline's own real status for a failed provider call. Any other
    `AIAnswerStatus` (`unsupported_template`, `budget_exhausted`) never
    matches any eval-set expectation -- there is no equivalent concept in
    the eval file, by design; see `architecture_note_for` for why a
    question may legitimately land on one anyway."""
    if expected == "provider_error":
        return actual is AIAnswerStatus.ai_unavailable
    try:
        return actual is AIAnswerStatus(expected)
    except ValueError:
        return False


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile. Not statistically load-bearing —
    only ever used for a human-readable p95 latency figure in the report
    summary, over at most 36 data points."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def _id_field_for(template: PromptTemplate) -> str:
    return template.requires.value


def run_eval(
    db: Client,
    questions: Sequence[dict[str, Any]],
    *,
    provider_name: str,
    max_calls: int,
    as_of: date,
    gemini_provider: AIProvider | None = None,
) -> dict[str, Any]:
    """Run every question in `questions` through the real pipeline and
    return the full report as a plain, JSON-serialisable `dict`.

    `db` is always injected — real (`create_client(...)`, `main()` below)
    or a fake in-memory double (`tests/unit/test_run_ai_eval.py`), never
    constructed here. `provider_name` is `"mock"` or `"gemini"`;
    `gemini_provider` must be a constructed `GeminiProvider` when
    `provider_name == "gemini"` (never constructed by this function, so a
    test can never accidentally trigger a real `GeminiProvider()` call by
    exercising this function with `provider_name="mock"`). `category:
    api_failure` questions ALWAYS use a scripted-to-raise `MockAIProvider`
    regardless of `provider_name` — this card's own instruction.
    """
    if provider_name == "gemini" and gemini_provider is None:
        raise ValueError("provider_name='gemini' requires a constructed gemini_provider")

    budget = AIRequestBudget(daily_request_budget=max_calls)
    question_reports: list[dict[str, Any]] = []
    not_reached: list[str] = []
    latencies_ms: list[float] = []

    for question in questions:
        qid = question["id"]
        remaining_before = budget.remaining(today=as_of)
        if remaining_before < _MAX_CALLS_PER_QUESTION:
            # The hard ceiling: abort the WHOLE run here, not just this
            # question. Every question from this point on -- including
            # this one -- is recorded as not reached and never attempted.
            not_reached.append(qid)
            continue

        request, template, placeholder, resolved_id = build_ask_request(question)

        if question.get("category") == "api_failure":
            provider: AIProvider = MockAIProvider()
            provider.raise_on_call(
                1, AIProviderTimeout("scripts/run_ai_eval.py: scripted api_failure eval case")
            )
            provider_used = "mock (scripted raise_on_call -- forced by category: api_failure)"
        elif provider_name == "gemini":
            assert gemini_provider is not None  # narrowed by the guard above
            provider = gemini_provider
            provider_used = "gemini"
        else:
            responses = _cooperative_mock_responses(db, request, template, as_of=as_of)
            provider = MockAIProvider(responses=responses)
            provider_used = "mock"

        start = time.perf_counter()
        result: Answer | None
        error: str | None
        try:
            result = pipeline_answer(db, request, provider, budget, as_of=as_of)
            error = None
        except Exception as exc:  # noqa: BLE001 - see docstring: a genuine pipeline
            # bug must be surfaced in the report, never silently swallowed, and
            # must never kill the rest of this capped run either.
            result = None
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)

        calls_used = remaining_before - budget.remaining(today=as_of)
        expected_status = question["expected_status"]
        actual_status = result.status.value if result is not None else None
        matched = (
            _status_matches_expected(result.status, expected_status)
            if result is not None
            else False
        )

        question_reports.append(
            {
                "id": qid,
                "category": question.get("category"),
                "language": question.get("language"),
                # Human-readable label ONLY -- see module docstring's "The
                # question text is NEVER sent anywhere" section. Never
                # passed to AskRequest, a prompt, or any provider.
                "text": question.get("text"),
                "mapping_rationale": QUESTION_TEMPLATE_MAP[qid][1],
                "mapped_template_id": template.id,
                "mapped_id_field": _id_field_for(template),
                "mapped_placeholder": placeholder,
                "mapped_resolved_id": resolved_id,
                "provider_used": provider_used,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "matched_expected_status": matched,
                "selection_ids": list(result.selection_ids) if result is not None else [],
                "verification_ids": list(result.verification_ids) if result is not None else [],
                "calls_used": calls_used,
                "latency_ms": round(elapsed_ms, 3),
                "error": error,
                "architecture_note": architecture_note_for(question, resolved_id),
            }
        )

    summary = _summarize(question_reports, not_reached, questions, max_calls, latencies_ms)
    return {
        "run_at": datetime.now(UTC).isoformat(),
        "provider": provider_name,
        "max_calls": max_calls,
        "as_of": as_of.isoformat(),
        "eval_set_path": str(EVAL_YAML_PATH),
        "questions": question_reports,
        "not_reached": not_reached,
        "summary": summary,
    }


def _summarize(
    question_reports: list[dict[str, Any]],
    not_reached: list[str],
    all_questions: Sequence[dict[str, Any]],
    max_calls: int,
    latencies_ms: list[float],
) -> dict[str, Any]:
    reached = len(question_reports)
    matched = sum(1 for q in question_reports if q["matched_expected_status"])
    status_counts: dict[str, int] = {}
    for q in question_reports:
        key = q["actual_status"] or "error"
        status_counts[key] = status_counts.get(key, 0) + 1
    calls_used_total = sum(q["calls_used"] for q in question_reports)
    mean_latency = statistics.fmean(latencies_ms) if latencies_ms else None
    p95_latency = _percentile(latencies_ms, 95) if latencies_ms else None
    return {
        "total_questions": len(all_questions),
        "reached": reached,
        "not_reached_count": len(not_reached),
        "matched_expected_status_count": matched,
        "mismatched_expected_status_count": reached - matched,
        "status_counts": status_counts,
        "calls_used_total": calls_used_total,
        "max_calls": max_calls,
        "cap_hit": len(not_reached) > 0,
        "mean_latency_ms": round(mean_latency, 3) if mean_latency is not None else None,
        "p95_latency_ms": round(p95_latency, 3) if p95_latency is not None else None,
    }


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def load_eval_questions(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = data["questions"]
    missing = set(q["id"] for q in questions) - set(QUESTION_TEMPLATE_MAP)
    if missing:
        raise AssertionError(
            f"{path} has question id(s) with no entry in QUESTION_TEMPLATE_MAP: "
            f"{sorted(missing)} -- add a mapping before running."
        )
    return questions  # type: ignore[no-any-return]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_ai_eval",
        description=(
            "Capped evaluation runner for Ask BCION (AI-11). Mock-provider by "
            "default; --provider gemini is an owner-run live pass only and is "
            "never exercised by a test in this repo."
        ),
    )
    parser.add_argument("--provider", choices=["mock", "gemini"], default="mock")
    parser.add_argument(
        "--max-calls",
        type=int,
        default=DEFAULT_MAX_CALLS,
        help=f"hard provider-call ceiling for the whole run (default {DEFAULT_MAX_CALLS})",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="YYYY-MM-DD freshness reference date (default: today)",
    )
    parser.add_argument(
        "--eval-set", type=str, default=str(EVAL_YAML_PATH), help="path to the eval question set"
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="override the report output path (default: evals/reports/<date>.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    questions = load_eval_questions(Path(args.eval_set))

    if args.provider == "mock":
        # See module docstring's "_MOCK_PLACEHOLDER_GEMINI_KEY" note: no real
        # value, no network call is ever made through it in this mode.
        os.environ["AI_ENABLED"] = "true"
        os.environ.setdefault("GEMINI_API_KEY", _MOCK_PLACEHOLDER_GEMINI_KEY)
        print(
            "--provider mock: forcing AI_ENABLED=true for this process; "
            "GEMINI_API_KEY left as-is if already set, otherwise set to a "
            "placeholder (no real value, no network call is made in this mode)."
        )

    url = os.environ.get("SUPABASE_URL", "")
    # Same production guard scripts/seed_synthetic.py enforces, reused
    # (not reimplemented) so the two scripts can never silently drift
    # apart -- this runner also writes nothing itself, but it DOES read a
    # real database when run live, and gemini_provider mode can spend
    # real quota, so refusing an unrecognised remote target is the same
    # fail-closed choice for the same reason.
    problem = guard_problem(
        app_env=os.environ.get("APP_ENV", ""),
        url=url,
        production_ref=os.environ.get("BCION_PRODUCTION_PROJECT_REF"),
        allowlisted=_allowlisted_origins(),
    )
    if problem is not None:
        print(problem, file=sys.stderr)
        return 1

    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        print(
            "SUPABASE_SERVICE_ROLE_KEY is not set. This script needs the "
            "owner's admin credential (same one scripts/seed_synthetic.py and "
            "tests/db/conftest.py use) to read pathway/claim rows for retrieval; "
            "the application itself never reads it.",
            file=sys.stderr,
        )
        return 1
    if not url:
        print("SUPABASE_URL is not set. Refusing rather than guessing a target.", file=sys.stderr)
        return 1

    from supabase import create_client

    db = create_client(url, key)

    gemini_provider: AIProvider | None = None
    if args.provider == "gemini":
        from app.ai.gemini_provider import GeminiNotConfiguredError, GeminiProvider

        try:
            gemini_provider = GeminiProvider()
        except GeminiNotConfiguredError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    result = run_eval(
        db,
        questions,
        provider_name=args.provider,
        max_calls=args.max_calls,
        as_of=as_of,
        gemini_provider=gemini_provider,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else REPORTS_DIR / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
