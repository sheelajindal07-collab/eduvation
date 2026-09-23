"""The two-pass Ask BCION orchestrator (AI-6) — selection, then an
adversarial verification pass, over records `app.ai.retrieval` already
fetched and trust-checked. `app.ai.schemas.Answer` is the only shape this
module ever returns; `answer()` never raises for anything short of a
genuine bug in its own prompt construction (see
`app.ai.guards.UntraceableRecordValueError`).

## Order of operations (this card's own numbered steps, `tasks/BCI-015.md`)

1. **Template validation.** `request.template_id` must be a key in
   `app.ai.prompts.TEMPLATE_REGISTRY`, AND
   `request.record_id_for(template)` (`app/ai/schemas.py`) must not be
   `None` (that method's own docstring: "`None` is what a caller turns
   into `AIAnswerStatus.unsupported_template`"). Either failure ->
   `unsupported_template`, before anything else runs — no retrieval, no
   settings check, no budget touch.
2. **`Settings.ai_enabled` / `Settings.ai_configured`.** Either false ->
   `ai_unavailable`, before any retrieval or budget reservation (per this
   card's own step 2). This is the one failure path that genuinely
   carries NO fact cards at all — retrieval has not run yet at this
   point, so there is nothing to attach.
3. **Retrieval**, dispatched by which `PromptTemplateRequirement` the
   template declares (`_fetch_records` below) — `fetch_pathway_records`
   / `fetch_career_records` / `fetch_claim_record`
   (`app/ai/retrieval.py`, AI-5, read directly for the real signatures,
   not guessed). No records -> `not_available`; the provider is never
   called (nothing to spend the budget on).
4. **Reserve exactly two calls up front**, both before any provider call
   (this card's own step 4, literally: "Reserve exactly two calls ...
   before any provider call"). `AIRequestBudget.reserve()`
   (`app/ai/budget.py`) reserves one call per invocation and has no
   batch form, so this calls it twice in a row. If EITHER raises
   `AIBudgetExceededError`, this returns `budget_exhausted` — even if the
   first reservation already succeeded, since `AIRequestBudget` exposes
   no release/refund method (confirmed by reading `app/ai/budget.py`
   directly, per this card's contract note); the reservation that never
   led to a call is not given back, which is the conservative direction
   for a spend cap to err in. See the module docstring's "On 'settling'
   the budget" section below for why step 13 needs no further call here.
5. **Build the selection prompt** (`app.ai.prompts.build_selection_prompt`)
   and, immediately before that, the traceability self-check this card's
   step 5 asks for: `app.ai.guards.build_outbound_payload` +
   `assert_payload_traceable`. A failure there is
   `app.ai.guards.UntraceableRecordValueError` — deliberately NOT caught
   here (see that exception's own docstring: it can only mean a bug in
   this pipeline's own prompt construction, never a runtime student
   input, so it is allowed to propagate rather than being silently
   absorbed into some Answer status).
6. **Send the selection prompt.** Any of `app/ai/schemas.py`'s four typed
   provider errors (`AIProviderTimeout`, `AIProviderQuota`,
   `AIProviderMalformed`, or the `AIProviderError` base for anything
   else) caught here -> `ai_unavailable`, with whatever records step 3
   found attached as citations (never sentences — see point 11 below).
7. **Validate the selection response** — `app.ai.guards.parse_selection_response`,
   the same whole-response all-or-nothing rules
   `app/ai/grounding.py`'s `_parse_and_validate` already established,
   retargeted to `RetrievedRecord` ids (see that guard's own docstring
   for exactly how and why it is a documented duplication, not a second
   design). No valid ids survive (malformed line, out-of-context id, the
   literal `NOT_GROUNDED` token, or an empty response) ->
   `insufficient_information`, fact-card citations still attached. The
   verification pass is never sent in this case — nothing to verify.
8. **Build and send the verification prompt**
   (`app.ai.prompts.build_verification_prompt`) over only the ids pass
   one selected. Any typed provider error here -> `ai_unavailable` too,
   `selection_ids` still populated on the returned `Answer` (pass one DID
   succeed) but no `verification_ids`.
9. **Validate the verification response** —
   `app.ai.guards.parse_verification_response`. A format violation (any
   line outside the exact `YES <id>` / `NO <id>` shape, an id pass one
   never selected, or a self-contradictory YES+NO for the same id) ->
   `insufficient_information`. Otherwise the surviving id set is the
   ids confirmed `YES` — which `parse_verification_response`'s own
   contract already guarantees is a subset of pass one's selection; this
   function re-derives the intersection explicitly anyway as a second,
   defensive check of the exact invariant `app.ai.schemas.Answer` itself
   enforces (`verification_ids` subset of `selection_ids`). An empty
   result here -> `insufficient_information`, fact cards still attached
   (this card's step 9: "never a bare refusal with nothing useful").
10. **Freshness.** Any surviving id backed by a stale
    `RetrievedRecord` (`.is_stale`, already computed by
    `app/ai/retrieval.py` against `DEFAULT_FRESHNESS_SLA_DAYS` — nothing
    to re-derive here, unlike `grounding.py`, since `retrieval.py`
    already flags it) downgrades the WHOLE answer to
    `insufficient_information`, same all-or-nothing rule
    `grounding.py`'s own module docstring documents for its single-pass
    equivalent.
11. **Sentence generation, in code, from the surviving records' own
    fields** — `app.ai.guards.fact_sentence_for_record`. There is no
    parameter through which a character the provider wrote could reach
    `Answer.sentences`: the provider's response only ever contributes a
    SET of ids (validated against the retrieved set at every step above),
    never a value or a word. `tests/unit/test_ai_pipeline.py`'s
    `test_answered_sentences_are_generated_entirely_by_code_never_by_the_provider`
    proves this directly, mirroring `app/ai/grounding.py`'s own
    identically-purposed test.
12. **Banned-phrase guard (fixed strings, import time)** —
    `app.ai.guards.assert_no_banned_phrases`, run over
    `app.ai.prompts.TEMPLATE_REGISTRY`'s labels at import time (see that
    module) rather than per-request here, since these are fixed strings
    that never change between requests; a hit is a build/test-time
    failure, never something this function's runtime control flow needs
    to branch on. **Its own, independent runtime companion (BCI-027)**
    runs between steps 11 and 13, below: `app.ai.guards.
    scan_generated_sentences` over the `sentences` step 11 just
    generated from the surviving records' own (published, reviewer-
    approved) values. Unlike the import-time check, this one is real
    per-request control flow — a published record's *value* could, in
    principle, itself contain hedge/guarantee language (a human content
    error at review time, never an AI hallucination), and nothing
    previously re-checked that before rendering it. A hit downgrades the
    WHOLE answer to `insufficient_information`, the same all-or-nothing
    shape steps 9 and 10 use, never a partial redaction of just the
    offending sentence — this function never raises on this path, since a
    real request must degrade gracefully like every other failure mode
    here, not crash.
13. **"Settling" the budget.** `app/ai/budget.py`'s `AIRequestBudget` —
    read directly, per this card's contract note, rather than guessed —
    exposes only `reserve()` and `remaining()`; there is no `settle(...)`
    method taking `selection_ids`/`verification_ids` for this in-memory
    budget to call (that shape belongs to the DB-backed budget design,
    `docs/plan` inventory language for a different, still-blocked card —
    this card's own step 4 explicitly says "do not wait for or import
    `app/ai/budget_db.py`"). Both reservations already happened in step 4
    above, unconditionally, before either provider call — which IS this
    in-memory budget's entire job ("how many provider calls may be made
    today", `app/ai/budget.py`'s own module docstring): a reservation
    that led to a failed/rejected call still correctly counted as a call
    attempted. No prompt text, no answer text, no id list is ever passed
    to `budget` here or anywhere — `AIRequestBudget` has no field that
    could hold any of that, so "no prompt text ... ever recorded" is true
    by construction rather than by a discipline this function has to
    maintain. `selection_ids`/`verification_ids` are instead recorded the
    one place `app.ai.schemas.Answer` already has a slot for them: the
    returned `Answer` itself.

Every failure path returns a usable `Answer` carrying whatever
`RetrievedRecord`s step 3 found, rendered as structured `citations`
(`app.ai.guards.citation_for_record`) — plain data, never prose — EXCEPT
steps 1 and 2, which return before retrieval ever runs and so legitimately
carry none. `Answer.sentences` is populated in exactly one case: full
success through every step above. This mirrors
`app.ai.schemas.Answer`'s own model-validated invariant: any status other
than `answered` MUST carry zero sentences, enforced by pydantic, not by
this function's own discipline.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from supabase import Client

from app.ai.adapter import AIProvider
from app.ai.budget import AIBudgetExceededError, AIRequestBudget
from app.ai.guards import (
    assert_payload_traceable,
    build_outbound_payload,
    citation_for_record,
    fact_sentence_for_record,
    parse_selection_response,
    parse_verification_response,
    scan_generated_sentences,
)
from app.ai.prompts import TEMPLATE_REGISTRY, build_selection_prompt, build_verification_prompt
from app.ai.retrieval import (
    RetrievedRecord,
    fetch_career_records,
    fetch_claim_record,
    fetch_pathway_records,
)
from app.ai.schemas import (
    AIAnswerStatus,
    AIProviderError,
    Answer,
    AskRequest,
    PromptTemplate,
    PromptTemplateRequirement,
)
from app.core.config import get_settings


def _fetch_records(
    db: Client, template: PromptTemplate, record_id: str, *, as_of: date
) -> tuple[RetrievedRecord, ...]:
    """Dispatch retrieval by which id kind `template` declares. Only
    `pathway_id` and `claim_id` are exercised by `app.ai.prompts`'s
    actual registry today; `career_id` is included for completeness
    (a future template may use it) and `plan_id` returns no records since
    `app/ai/retrieval.py` exposes no plan-level fetch function at all —
    see `app.ai.prompts`'s own module docstring for why that is a
    deliberate, documented gap rather than an oversight."""
    if template.requires is PromptTemplateRequirement.pathway_id:
        return fetch_pathway_records(db, record_id, as_of=as_of)
    if template.requires is PromptTemplateRequirement.career_id:
        return fetch_career_records(db, record_id, as_of=as_of)
    if template.requires is PromptTemplateRequirement.claim_id:
        record = fetch_claim_record(db, record_id, as_of=as_of)
        return (record,) if record is not None else ()
    return ()  # PromptTemplateRequirement.plan_id — see docstring above.


def _fallback_citations(records: tuple[RetrievedRecord, ...]) -> list[dict[str, Any]]:
    """Deterministic, code-only fact cards for every failure path that
    ran retrieval (step 3) but could not produce a fully-verified answer
    — plain structured data, never a sentence (see module docstring)."""
    return [citation_for_record(record) for record in records]


def answer(
    db: Client,
    request: AskRequest,
    provider: AIProvider,
    budget: AIRequestBudget,
    *,
    as_of: date | None = None,
) -> Answer:
    """Answer `request` via the two-pass selection/verification pipeline.
    See module docstring for the full, numbered order of operations.

    `provider` and `budget` are always injected — this function never
    constructs a `GeminiProvider` or a default budget itself, so tests
    (and any real caller) fully control both and no test path ever
    touches the network (this card's own contract).
    """
    resolved_as_of = as_of if as_of is not None else date.today()

    # Step 1 — template + required-id validation.
    template = TEMPLATE_REGISTRY.get(request.template_id)
    if template is None:
        return Answer(status=AIAnswerStatus.unsupported_template)
    record_id = request.record_id_for(template)
    if record_id is None:
        return Answer(status=AIAnswerStatus.unsupported_template)

    # Step 2 — AI feature flags, before any retrieval or budget touch.
    settings = get_settings()
    if not settings.ai_enabled or not settings.ai_configured:
        return Answer(status=AIAnswerStatus.ai_unavailable)

    # Step 3 — retrieval.
    records = _fetch_records(db, template, record_id, as_of=resolved_as_of)
    if not records:
        return Answer(status=AIAnswerStatus.not_available)
    fallback_citations = _fallback_citations(records)

    # Step 4 — reserve exactly two calls, both before any provider call.
    try:
        budget.reserve(today=resolved_as_of)
        budget.reserve(today=resolved_as_of)
    except AIBudgetExceededError:
        return Answer(status=AIAnswerStatus.budget_exhausted, citations=fallback_citations)

    # Step 5 — build the selection prompt; traceability self-check first.
    # UntraceableRecordValueError is deliberately not caught (see module
    # docstring point 5 / app.ai.guards' own docstring): a pipeline bug,
    # never a runtime student input.
    payload, records_map = build_outbound_payload(template.id, records, lang=request.lang)
    assert_payload_traceable(payload, records_map)
    selection_prompt = build_selection_prompt(template, records)

    # Step 6 — send the selection prompt.
    try:
        raw_selection = provider.generate(selection_prompt)
    except AIProviderError:
        return Answer(status=AIAnswerStatus.ai_unavailable, citations=fallback_citations)

    # Step 7 — validate the selection response.
    valid_ids = {record.id for record in records}
    selection_ids = parse_selection_response(raw_selection, valid_ids)
    if not selection_ids:
        return Answer(status=AIAnswerStatus.insufficient_information, citations=fallback_citations)

    records_by_id = {record.id: record for record in records}

    # Step 8 — build and send the verification prompt.
    verification_prompt = build_verification_prompt(
        template, [records_by_id[record_id] for record_id in selection_ids]
    )
    try:
        raw_verification = provider.generate(verification_prompt)
    except AIProviderError:
        return Answer(
            status=AIAnswerStatus.ai_unavailable,
            citations=fallback_citations,
            selection_ids=list(selection_ids),
        )

    # Step 9 — validate the verification response.
    verification_ids = parse_verification_response(raw_verification, set(selection_ids))
    if verification_ids is None:
        return Answer(
            status=AIAnswerStatus.insufficient_information,
            citations=fallback_citations,
            selection_ids=list(selection_ids),
        )

    # Defensive re-derivation of the intersection — see module docstring
    # point 9. `verification_ids` is already a subset of `selection_ids`
    # by `parse_verification_response`'s own contract; this is a second,
    # independent check of that same invariant, not a trust decision.
    verification_id_set = set(verification_ids)
    surviving_ids = [
        record_id for record_id in selection_ids if record_id in verification_id_set
    ]
    if not surviving_ids:
        return Answer(
            status=AIAnswerStatus.insufficient_information,
            citations=fallback_citations,
            selection_ids=list(selection_ids),
            verification_ids=list(verification_ids),
        )

    # Step 10 — freshness, all-or-nothing.
    if any(records_by_id[record_id].is_stale for record_id in surviving_ids):
        return Answer(
            status=AIAnswerStatus.insufficient_information,
            citations=fallback_citations,
            selection_ids=list(selection_ids),
            verification_ids=list(verification_ids),
        )

    # Step 11 — sentences and citations, generated entirely by code from
    # the surviving records' own fields, never from provider output.
    sentences = [fact_sentence_for_record(records_by_id[record_id]) for record_id in surviving_ids]
    citations = [citation_for_record(records_by_id[record_id]) for record_id in surviving_ids]

    # Runtime banned-phrase scan (BCI-027) — over the SENTENCES THIS
    # PIPELINE JUST GENERATED, not the fixed TEMPLATE_REGISTRY labels
    # step 12 below checks at import time. A hit here means a published,
    # reviewer-approved record's own `.value` contained hedge/guarantee
    # language that survived maker-checker review — a real request, so it
    # must degrade, never crash and never partially redact: the WHOLE
    # answer downgrades to `insufficient_information`, same all-or-nothing
    # shape steps 9/10 above use, with `fallback_citations` (every record
    # step 3 retrieved) attached the same way step 10's own staleness
    # downgrade does, so a caller can see which record blocked the answer.
    if scan_generated_sentences(sentences):
        return Answer(
            status=AIAnswerStatus.insufficient_information,
            citations=fallback_citations,
            selection_ids=list(selection_ids),
            verification_ids=list(verification_ids),
        )

    # Step 13 — "settling" the budget: see module docstring point 13 for
    # why no further call against `budget` happens here.
    return Answer(
        status=AIAnswerStatus.answered,
        sentences=sentences,
        citations=citations,
        selection_ids=list(selection_ids),
        verification_ids=list(verification_ids),
    )
