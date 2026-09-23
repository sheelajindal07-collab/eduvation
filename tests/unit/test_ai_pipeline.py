"""Tests for app/ai/pipeline.py (AI-6) — the two-pass selection +
verification orchestrator, `app/ai/prompts.py`'s template registry, and
`app/ai/guards.py`'s shared parsing/sentence/traceability/banned-phrase
guards.

Every test uses `MockAIProvider` (`app/ai/mock_provider.py`, already
merged) — its `responses=[...]` sequencing and `raise_on_call` hook, as
the card requires. Zero network calls, zero real provider calls anywhere
in this file. `db` is never actually touched by `app.ai.pipeline.answer`
in any test here — `app.ai.retrieval`'s `fetch_pathway_records` /
`fetch_career_records` / `fetch_claim_record` are monkeypatched at the
name `app.ai.pipeline` imported them under (a plain `object()` stands in
for `db`, and a handful of tests that must prove retrieval never runs at
all monkeypatch those names to a function that raises `AssertionError` if
called). No `make test-db`, no e2e, no `db/migrations` touched.
"""

from __future__ import annotations

from datetime import date

import pytest

import app.ai.pipeline as pipeline
from app.ai.budget import AIRequestBudget
from app.ai.guards import (
    UntraceableRecordValueError,
    assert_no_banned_phrases,
    assert_payload_traceable,
    build_outbound_payload,
    citation_for_record,
    fact_sentence_for_record,
    parse_selection_response,
    parse_verification_response,
    scan_generated_sentences,
)
from app.ai.mock_provider import MockAIProvider
from app.ai.prompts import TEMPLATE_REGISTRY
from app.ai.retrieval import RetrievedRecord
from app.ai.schemas import (
    AIAnswerStatus,
    AIProviderQuota,
    AIProviderTimeout,
    AskRequest,
    OutboundPayload,
    find_banned_phrases,
)
from app.core.config import Settings

TODAY = date(2026, 9, 22)


def _record(
    record_id: str,
    *,
    field: str = "minimum_age",
    value: str | int | float | bool | None = 17,
    source_authority: str | None = "GSEB",
    source_url: str | None = "https://gseb.example.invalid",
    is_stale: bool = False,
) -> RetrievedRecord:
    return RetrievedRecord(
        id=record_id,
        field=field,
        value=value,
        source_authority=source_authority,
        source_url=source_url,
        is_stale=is_stale,
    )


def _settings(*, ai_enabled: bool = True, configured: bool = True) -> Settings:
    """`_env_file=None` bypasses any real `.env` on disk (same idiom as
    `tests/unit/test_ai_adapter.py`), so these assertions hold regardless
    of local developer configuration."""
    return Settings(
        _env_file=None,
        ai_enabled=ai_enabled,
        gemini_api_key="test-only-not-a-real-key" if configured else None,
    )


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs: bool) -> None:
    monkeypatch.setattr(pipeline, "get_settings", lambda: _settings(**kwargs))


def _explode(*args: object, **kwargs: object) -> None:
    raise AssertionError("retrieval must not be called on this path")


def _patch_pathway_records(
    monkeypatch: pytest.MonkeyPatch, records: tuple[RetrievedRecord, ...]
) -> None:
    monkeypatch.setattr(
        pipeline, "fetch_pathway_records", lambda db, pathway_id, *, as_of=None: records
    )


def _patch_claim_record(monkeypatch: pytest.MonkeyPatch, record: RetrievedRecord | None) -> None:
    monkeypatch.setattr(
        pipeline, "fetch_claim_record", lambda db, claim_id, *, as_of=None: record
    )


def _budget(daily_request_budget: int = 10) -> AIRequestBudget:
    return AIRequestBudget(daily_request_budget=daily_request_budget)


def _pathway_request(**overrides: object) -> AskRequest:
    fields: dict[str, object] = {"template_id": "pathway_overview", "pathway_id": "pathway-1"}
    fields.update(overrides)
    return AskRequest(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Step 1 — template validation. Unknown template, or a known template
# missing the one record id it requires, both -> unsupported_template,
# before anything else runs.
# ---------------------------------------------------------------------


def test_unknown_template_id_is_unsupported_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "fetch_pathway_records", _explode)
    monkeypatch.setattr(pipeline, "fetch_career_records", _explode)
    monkeypatch.setattr(pipeline, "fetch_claim_record", _explode)
    provider = MockAIProvider()
    request = AskRequest(template_id="not_a_real_template", pathway_id="pathway-1")

    result = pipeline.answer(object(), request, provider, _budget(), as_of=TODAY)

    assert result.status == AIAnswerStatus.unsupported_template
    assert result.sentences == []
    assert provider.calls == []


def test_known_template_missing_required_id_is_unsupported_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "fetch_pathway_records", _explode)
    provider = MockAIProvider()
    # "pathway_overview" requires pathway_id (app/ai/prompts.py's
    # TEMPLATE_REGISTRY) -- not supplied here.
    request = AskRequest(template_id="pathway_overview")

    result = pipeline.answer(object(), request, provider, _budget(), as_of=TODAY)

    assert result.status == AIAnswerStatus.unsupported_template
    assert provider.calls == []


# ---------------------------------------------------------------------
# Step 2 — AI feature flags. Either false -> ai_unavailable, before any
# retrieval or budget reservation.
# ---------------------------------------------------------------------


def test_ai_disabled_returns_ai_unavailable_before_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=False, configured=True)
    monkeypatch.setattr(pipeline, "fetch_pathway_records", _explode)
    provider = MockAIProvider()
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.ai_unavailable
    assert result.sentences == []
    assert result.citations == []
    assert provider.calls == []
    assert budget.remaining(today=TODAY) == 10  # never touched


def test_ai_not_configured_returns_ai_unavailable_before_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=False)
    monkeypatch.setattr(pipeline, "fetch_pathway_records", _explode)
    provider = MockAIProvider()

    result = pipeline.answer(object(), _pathway_request(), provider, _budget(), as_of=TODAY)

    assert result.status == AIAnswerStatus.ai_unavailable
    assert provider.calls == []


# ---------------------------------------------------------------------
# Step 3 — retrieval. No records -> not_available, provider never called.
# ---------------------------------------------------------------------


def test_no_records_returns_not_available_without_calling_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    _patch_pathway_records(monkeypatch, ())
    provider = MockAIProvider()
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.not_available
    assert result.sentences == []
    assert provider.calls == []
    assert budget.remaining(today=TODAY) == 10  # nothing to spend on


# ---------------------------------------------------------------------
# Step 4 — reserve exactly two calls, both before any provider call. A
# reservation failure -> budget_exhausted, zero provider calls, whatever
# fact cards retrieval already found still attached.
# ---------------------------------------------------------------------


def test_budget_exhaustion_returns_budget_exhausted_with_zero_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider()
    # Only 1 slot available -- the *second* of the two up-front
    # reservations must fail, and NEITHER provider call may have
    # happened by the time that failure is returned.
    budget = _budget(daily_request_budget=1)

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.budget_exhausted
    assert result.sentences == []
    # THE call-count proof this card's completion report asks for:
    # zero provider calls after a failed reservation.
    assert provider.calls == []
    # Deterministic fact cards from retrieval are still attached.
    assert result.citations == [citation_for_record(record)]


# ---------------------------------------------------------------------
# Step 5 — the traceability self-check (OutboundPayload.from_records +
# untraceable_values). Under normal operation this can never fire (see
# app/ai/guards.py's own docstring) -- this proves the GUARD ITSELF
# raises loudly rather than silently dropping a mismatch, per this
# card's own step 5 instruction, by constructing the mismatch directly.
# ---------------------------------------------------------------------


def test_untraceable_record_value_raises_loudly_rather_than_silently_dropping() -> None:
    payload = OutboundPayload.from_records(
        template_id="pathway_overview",
        records={"rec-1": {"minimum_age": "17"}},
        lang="en",
    )
    # A records_map that disagrees with what the payload was built from
    # -- simulating the only way this could ever happen: a future bug
    # that builds the payload from one record set and checks it against
    # a different one.
    mismatched_records_map = {"rec-1": {"minimum_age": "18"}}

    with pytest.raises(UntraceableRecordValueError):
        assert_payload_traceable(payload, mismatched_records_map)


def test_build_outbound_payload_is_traceable_by_construction() -> None:
    """The positive counterpart: under real pipeline usage (payload and
    records_map built together by `build_outbound_payload`), the guard
    never raises."""
    records = (_record("rec-1", field="minimum_age", value=17),)
    payload, records_map = build_outbound_payload("pathway_overview", records, lang="en")
    assert_payload_traceable(payload, records_map)  # must not raise


# ---------------------------------------------------------------------
# Step 6 — send the selection prompt. Any typed provider error ->
# ai_unavailable, deterministic fact cards attached, verification never
# attempted (only 1 provider call total).
# ---------------------------------------------------------------------


def test_provider_error_on_selection_call_returns_ai_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider()
    provider.raise_on_call(1, AIProviderTimeout("simulated timeout"))
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.ai_unavailable
    assert result.sentences == []
    assert result.citations == [citation_for_record(record)]
    # Only the one (failing) call -- verification is never attempted.
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------
# Step 7 — validate the selection response. A malformed line, an
# out-of-context id, or an explicit NOT_GROUNDED all -> whole response
# rejected -> insufficient_information, verification never sent.
# ---------------------------------------------------------------------


def test_selection_format_violation_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["This is a free-text sentence, not a selection line."])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.sentences == []
    assert result.citations == [citation_for_record(record)]
    # No verification call -- nothing valid survived pass one.
    assert len(provider.calls) == 1


def test_selection_not_grounded_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    _patch_pathway_records(monkeypatch, (_record("rec-1"),))
    provider = MockAIProvider(responses=["NOT_GROUNDED"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert len(provider.calls) == 1


def test_selection_citing_an_out_of_context_id_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    _patch_pathway_records(monkeypatch, (_record("rec-1"),))
    provider = MockAIProvider(responses=["[rec-not-in-context]"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert len(provider.calls) == 1


# ---------------------------------------------------------------------
# Step 8 — build and send the verification prompt. A provider error here
# -> ai_unavailable too, but selection_ids (pass one's real result) are
# still on the returned Answer, and exactly 2 calls were made.
# ---------------------------------------------------------------------


def test_provider_error_on_verification_call_returns_ai_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-1]"])
    provider.raise_on_call(2, AIProviderQuota("simulated quota refusal"))
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.ai_unavailable
    assert result.sentences == []
    assert result.selection_ids == ["rec-1"]
    assert result.verification_ids == []
    assert result.citations == [citation_for_record(record)]
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------
# Step 9 — validate the verification response. A format violation, or an
# empty confirmed set, both -> insufficient_information with fact cards
# still attached (never a bare refusal with nothing useful).
# ---------------------------------------------------------------------


def test_verification_format_violation_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-1]", "definitely yes"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.sentences == []
    assert result.selection_ids == ["rec-1"]
    assert result.verification_ids == []
    assert result.citations == [citation_for_record(record)]
    assert len(provider.calls) == 2


def test_verification_out_of_context_id_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    _patch_pathway_records(monkeypatch, (_record("rec-1"),))
    provider = MockAIProvider(responses=["[rec-1]", "YES rec-not-selected"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert len(provider.calls) == 2


def test_verification_empty_intersection_returns_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-1")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-1]", "NO rec-1"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.sentences == []
    assert result.selection_ids == ["rec-1"]
    assert result.verification_ids == []
    # Deterministic fact cards still attached -- never a bare refusal.
    assert result.citations == [citation_for_record(record)]
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------
# Step 10 — freshness. A surviving id backed by a stale record downgrades
# the WHOLE answer to insufficient_information, same all-or-nothing rule
# app/ai/grounding.py documents for its own single-pass equivalent.
# ---------------------------------------------------------------------


def test_stale_surviving_record_downgrades_to_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    stale_record = _record("rec-stale", is_stale=True)
    _patch_pathway_records(monkeypatch, (stale_record,))
    provider = MockAIProvider(responses=["[rec-stale]", "YES rec-stale"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.sentences == []
    assert result.selection_ids == ["rec-stale"]
    assert result.verification_ids == ["rec-stale"]
    assert len(provider.calls) == 2


def test_fresh_surviving_record_is_answered_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check on the boundary: a fresh surviving record is NOT
    downgraded -- the staleness check must not be so aggressive it
    downgrades ordinary fresh content."""
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    fresh_record = _record("rec-fresh", is_stale=False)
    _patch_pathway_records(monkeypatch, (fresh_record,))
    provider = MockAIProvider(responses=["[rec-fresh]", "YES rec-fresh"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.answered
    assert result.sentences != []


# ---------------------------------------------------------------------
# Step 11 — sentences generated entirely by code, never by the provider.
# The positive proof to go with every rejection test above.
# ---------------------------------------------------------------------


def test_answered_sentences_are_generated_entirely_by_code_never_by_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record(
        "rec-real", field="minimum_age", value=17, source_authority="GSEB", is_stale=False
    )
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-real]", "YES rec-real"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.answered
    # Exactly the deterministic template output -- not influenced by
    # anything the provider's response text happened to contain, because
    # the provider's response here contributes nothing but a bare id.
    assert result.sentences == ["According to GSEB: minimum age is 17."]
    assert result.sentences == [fact_sentence_for_record(record)]
    assert result.citations == [citation_for_record(record)]
    # THE call-count proof: exactly two provider calls for a fully
    # answered request.
    assert len(provider.calls) == 2
    assert result.selection_ids == ["rec-real"]
    assert result.verification_ids == ["rec-real"]


def test_answered_response_never_contains_provider_authored_free_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversarial variant: even if the underlying prompt text happened
    to contain a word the provider could have echoed, `.sentences` never
    contains anything but the fixed template output, because the
    provider's response is only ever parsed down to a set of ids
    (`app.ai.guards.parse_selection_response` /
    `parse_verification_response`) before a sentence is ever built."""
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-real", field="minimum_age", value=17, source_authority="GSEB")
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-real]", "YES rec-real"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.answered
    for sentence in result.sentences:
        assert sentence == "According to GSEB: minimum age is 17."


# ---------------------------------------------------------------------
# Step 12 — banned-phrase guard. A hit is a test failure, not a runtime
# path: this proves the guard function itself raises, and that every
# fixed template label in the real registry is clean.
# ---------------------------------------------------------------------


def test_banned_phrase_guard_raises_on_a_hedge_word() -> None:
    with pytest.raises(AssertionError):
        assert_no_banned_phrases("This might be the answer, maybe.")


def test_banned_phrase_guard_is_silent_on_clean_text() -> None:
    assert_no_banned_phrases("What does this pathway cost, broken down by fee component?")


def test_template_registry_labels_contain_no_banned_phrase() -> None:
    for template in TEMPLATE_REGISTRY.values():
        assert find_banned_phrases(template.label) == ()


# ---------------------------------------------------------------------
# Runtime banned-phrase scan (BCI-027) — app.ai.guards.
# scan_generated_sentences, wired between step 11 (sentence generation)
# and step 13 (the final `answered` return). Unlike step 12's
# assert_no_banned_phrases (fixed TEMPLATE_REGISTRY labels, import time,
# raises), this is real per-request control flow over the sentences THIS
# pipeline just generated from a published, reviewer-approved record's
# own value -- and it degrades, never raises.
# ---------------------------------------------------------------------


def test_scan_generated_sentences_is_pure_and_never_raises_on_a_hit() -> None:
    """The exact contract difference from assert_no_banned_phrases this
    card's own text draws: same underlying find_banned_phrases check,
    but reporting, not raising."""
    hits = scan_generated_sentences(["This might be the answer, maybe."])
    # BANNED_PHRASES order (app/ai/schemas.py): "maybe" precedes "might".
    assert hits == ("maybe", "might")


def test_scan_generated_sentences_is_silent_on_clean_text() -> None:
    assert scan_generated_sentences(["According to GSEB: minimum age is 17."]) == ()


def test_scan_generated_sentences_dedupes_a_repeated_hit_across_sentences() -> None:
    hits = scan_generated_sentences(["It might be 17.", "It might also be 18."])
    assert hits == ("might",)


def test_banned_phrase_in_a_claim_value_downgrades_whole_answer_to_insufficient_information(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE proof this card's completion report asks for: a claim value
    deliberately seeded with a banned phrase (simulating a human content
    error at review time, never an AI hallucination -- the provider only
    ever contributes ids, per step 11's own proof above) downgrades the
    WHOLE answer, never a partial redaction of just the offending
    sentence. Two surviving records here -- one clean, one seeded -- and
    BOTH sentences are dropped, not just the bad one."""
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    clean_record = _record("rec-clean", field="minimum_age", value=17)
    # "maybe" is a real BANNED_PHRASES entry (app/ai/schemas.py) -- a
    # reviewer would never have approved this in practice, but this
    # module's own guard makes no assumption maker-checker review is
    # infallible.
    banned_record = _record("rec-banned", field="minimum_age", value="maybe")
    _patch_pathway_records(monkeypatch, (clean_record, banned_record))
    provider = MockAIProvider(
        responses=["[rec-clean]\n[rec-banned]", "YES rec-clean\nYES rec-banned"]
    )
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.insufficient_information
    # Never a partial redaction: sentences is fully empty, not "just the
    # clean one survived".
    assert result.sentences == []
    assert result.selection_ids == ["rec-clean", "rec-banned"]
    assert result.verification_ids == ["rec-clean", "rec-banned"]
    # Fact cards for every retrieved record still attached -- same
    # citations precedent step 10's own staleness downgrade uses, so a
    # caller can see which record blocked the answer.
    assert result.citations == [
        citation_for_record(clean_record),
        citation_for_record(banned_record),
    ]
    assert len(provider.calls) == 2


def test_a_generated_sentence_with_no_banned_phrase_is_answered_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity check on the boundary: an ordinary, clean generated sentence
    is NOT downgraded by this new check -- it must not be so aggressive
    it blocks ordinary content the earlier tests already prove is
    answered."""
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("rec-clean", field="minimum_age", value=17)
    _patch_pathway_records(monkeypatch, (record,))
    provider = MockAIProvider(responses=["[rec-clean]", "YES rec-clean"])
    budget = _budget()

    result = pipeline.answer(object(), _pathway_request(), provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.answered
    assert result.sentences == ["According to GSEB: minimum age is 17."]


# ---------------------------------------------------------------------
# app/ai/guards.py's parsers, tested directly (the pipeline-level tests
# above already exercise them end to end; these pin down the exact
# all-or-nothing contract each one implements).
# ---------------------------------------------------------------------


def test_parse_selection_response_deduplicates_repeated_valid_lines() -> None:
    assert parse_selection_response("[rec-1]\n[rec-1]", {"rec-1"}) == ("rec-1",)


def test_parse_selection_response_rejects_trailing_text_after_bracket() -> None:
    assert parse_selection_response("[rec-1].", {"rec-1"}) == ()


def test_parse_verification_response_rejects_self_contradictory_id() -> None:
    assert parse_verification_response("YES rec-1\nNO rec-1", {"rec-1"}) is None


def test_parse_verification_response_deduplicates_repeated_identical_verdict() -> None:
    assert parse_verification_response("YES rec-1\nYES rec-1", {"rec-1"}) == ("rec-1",)


def test_parse_verification_response_empty_is_not_a_format_violation() -> None:
    # Well-formed (nothing to say) is NOT the same failure class as a
    # malformed line -- see this module's own docstring on the
    # None-vs-empty-tuple distinction.
    assert parse_verification_response("", {"rec-1"}) == ()


# ---------------------------------------------------------------------
# Registry variety: eligibility_gap requires claim_id and is answered
# via fetch_claim_record -- a different dispatch branch than the
# pathway_id templates every test above exercises.
# ---------------------------------------------------------------------


def test_claim_id_template_dispatches_to_fetch_claim_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    record = _record("claim-1", field="minimum_age", value=17)
    _patch_claim_record(monkeypatch, record)
    provider = MockAIProvider(responses=["[claim-1]", "YES claim-1"])
    budget = _budget()
    request = AskRequest(template_id="eligibility_gap", claim_id="claim-1")

    result = pipeline.answer(object(), request, provider, budget, as_of=TODAY)

    assert result.status == AIAnswerStatus.answered
    assert result.sentences == ["According to GSEB: minimum age is 17."]


def test_claim_id_template_with_no_claim_found_is_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, ai_enabled=True, configured=True)
    _patch_claim_record(monkeypatch, None)
    provider = MockAIProvider()
    request = AskRequest(template_id="eligibility_gap", claim_id="claim-missing")

    result = pipeline.answer(object(), request, provider, _budget(), as_of=TODAY)

    assert result.status == AIAnswerStatus.not_available
    assert provider.calls == []
