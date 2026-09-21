"""Tests for app/ai/ — the M5 grounded-AI adapter (Lite Build Pack §9).

CLAUDE.md's non-negotiable is the thing under test: "AI never invents
facts... No record -> answer is 'not verified'." These tests exist to
make that a demonstrated property of the code, not an assertion taken on
faith — in particular the adversarial cases construct a provider that
actively tries to produce an ungrounded answer and assert the grounding
layer catches it, rather than only ever exercising the happy path.

Uses `MockAIProvider` throughout. No network call, no live Gemini API key
is read or used anywhere in this file.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.ai.adapter import AIProvider
from app.ai.budget import AIBudgetExceededError, AIRequestBudget
from app.ai.gemini_provider import GeminiNotConfiguredError, GeminiProvider
from app.ai.grounding import (
    AIAnswerStatus,
    answer_question,
)
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from app.data.models import Claim, ClaimStatus, Source, SourceType

TODAY = date(2026, 9, 21)

OFFICIAL_SOURCE = Source(
    id="src-official-1",
    authority_name="GSEB",
    official_url="https://gseb.example.invalid",
    source_type=SourceType.official,
)
SYNTHETIC_SOURCE = Source(
    id="src-synthetic-1",
    authority_name="TEST FIXTURE — not a real authority",
    official_url="https://example.invalid/not-real",
    source_type=SourceType.synthetic,
)
SOURCES_BY_ID = {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE, SYNTHETIC_SOURCE.id: SYNTHETIC_SOURCE}


def _claim(
    claim_id: str,
    *,
    status: ClaimStatus,
    source_id: str = OFFICIAL_SOURCE.id,
    field_name: str = "minimum_age",
    value: str | int | float | bool | None = 17,
    verification_date: date = date(2026, 6, 1),
    review_due_date: date = date(2027, 6, 1),
) -> Claim:
    return Claim(
        id=claim_id,
        entity_type="Pathway",
        entity_id="pathway-1",
        field=field_name,
        value=value,
        source_id=source_id,
        verification_date=verification_date,
        verifier="test-reviewer",
        status=status,
        review_due_date=review_due_date,
        extracted_by="human",
    )


def _budget(daily_request_budget: int = 10) -> AIRequestBudget:
    return AIRequestBudget(daily_request_budget=daily_request_budget)


# ---------------------------------------------------------------------
# Defensive re-filter: draft / in_review / superseded / synthetic-sourced
# claims must never be used as grounding material, even when present in
# the input list.
# ---------------------------------------------------------------------


def test_unpublished_and_synthetic_claims_are_never_used_as_grounding_material() -> None:
    published_claim = _claim("claim-published", status=ClaimStatus.published, value=17)
    draft_claim = _claim("claim-draft", status=ClaimStatus.draft, value="DRAFT-LEAK")
    in_review_claim = _claim("claim-in-review", status=ClaimStatus.in_review, value="REVIEW-LEAK")
    superseded_claim = _claim("claim-superseded", status=ClaimStatus.superseded, value="STALE-LEAK")
    synthetic_but_published_claim = _claim(
        "claim-synthetic",
        status=ClaimStatus.published,
        source_id=SYNTHETIC_SOURCE.id,
        value="SYNTHETIC-LEAK",
    )
    provider = MockAIProvider()
    budget = _budget()

    result = answer_question(
        "What is the minimum age?",
        [
            published_claim,
            draft_claim,
            in_review_claim,
            superseded_claim,
            synthetic_but_published_claim,
        ],
        SOURCES_BY_ID,
        provider=provider,
        budget=budget,
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.answered
    assert result.text is not None
    cited_ids = {c.claim_id for c in result.citations}
    assert cited_ids == {"claim-published"}
    # The new staleness fields (fresh here: verified 2026-06-01, ~112 days
    # before TODAY, under the 180-day SLA) must reach the Citation too.
    (citation,) = result.citations
    assert citation.is_stale is False
    assert citation.review_due_date == date(2027, 6, 1)
    # The fact-bearing sentence is code-generated from the real claim's
    # own data -- it must state the real value (17), never one of the
    # excluded claims' fabricated leak markers.
    assert "17" in result.text

    # The excluded claims' ids/values must never even have reached the
    # provider — the defensive filter runs before the prompt is built,
    # not just before the response is trusted.
    assert len(provider.calls) == 1
    sent_prompt = provider.calls[0]
    for excluded_id in (
        "claim-draft",
        "claim-in-review",
        "claim-superseded",
        "claim-synthetic",
    ):
        assert excluded_id not in sent_prompt
    for leaked_value in ("DRAFT-LEAK", "REVIEW-LEAK", "STALE-LEAK", "SYNTHETIC-LEAK"):
        assert leaked_value not in sent_prompt
        assert result.text is not None and leaked_value not in result.text


# ---------------------------------------------------------------------
# No usable grounding material -> "not_available", never a fabricated
# answer, and the provider/budget are never touched.
# ---------------------------------------------------------------------


def test_no_relevant_claims_produces_not_available_without_calling_provider() -> None:
    provider = MockAIProvider()
    budget = _budget(daily_request_budget=1)

    result = answer_question(
        "What is the fee for a pathway nobody has published anything about?",
        [],
        SOURCES_BY_ID,
        provider=provider,
        budget=budget,
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.not_available
    assert result.text is None
    assert result.citations == ()
    # Nothing to ground an answer on -> the provider must never be
    # called, and the budget must not be spent on it.
    assert provider.calls == []
    assert budget.remaining(today=TODAY) == 1


def test_only_unpublished_claims_also_produces_not_available() -> None:
    """Same as above, but via the defensive filter rather than an empty
    input list — a caller that (incorrectly) passes only draft claims
    must get the same safe outcome as passing nothing at all."""
    provider = MockAIProvider()
    budget = _budget()

    result = answer_question(
        "What is the minimum age?",
        [_claim("claim-draft-only", status=ClaimStatus.draft)],
        SOURCES_BY_ID,
        provider=provider,
        budget=budget,
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.not_available
    assert result.text is None
    assert provider.calls == []


# ---------------------------------------------------------------------
# Adversarial: a provider that actively tries to fabricate an answer.
# The grounding-validation mechanism must catch and reject it, not just
# pass the happy path. Under the new selection-only contract (see
# app/ai/grounding.py's module docstring), a valid response line is
# nothing but "[<claim_id>]" -- so every one of these tries a different
# way to sneak free text, a bad id, or both, into the response.
# ---------------------------------------------------------------------


def test_response_citing_a_claim_outside_the_given_context_is_rejected() -> None:
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(canned_response="[claim-not-in-context]")
    budget = _budget()

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=budget,
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None
    assert result.citations == ()
    assert result.rejection_reason is not None
    assert "claim-not-in-context" in result.rejection_reason
    # The provider WAS called (there was grounding material to try with);
    # the rejection has to come from validating its response, not from
    # short-circuiting before the call.
    assert len(adversarial_provider.calls) == 1


def test_response_with_untagged_free_text_is_rejected() -> None:
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(
        canned_response="The minimum age requirement is seventeen years old."
    )

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None


def test_response_with_one_bad_citation_rejects_the_whole_response_not_just_that_line() -> None:
    """All-or-nothing: a response that mixes one valid citation with one
    fabricated one must be rejected entirely, not silently trimmed down
    to "the good line" — a provider that fabricates part of a response
    cannot be trusted for the rest of it either."""
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(canned_response="[claim-real]\n[claim-fabricated]")

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None
    assert result.citations == ()


def test_provider_declining_via_not_grounded_token_yields_insufficient_information() -> None:
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    declining_provider = MockAIProvider(canned_response="NOT_GROUNDED")

    result = answer_question(
        "What is the capital of France?",
        [real_claim],
        SOURCES_BY_ID,
        provider=declining_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None


def test_response_smuggling_fabricated_sentence_onto_a_valid_citation_line_is_rejected() -> None:
    """THE critical finding this task exists to fix, reproduced exactly:
    a response that cites a genuinely real, in-context claim_id, but
    appends a fabricated fact-bearing sentence on the same line --
    including a fabricated numeric value for the SAME field the real
    claim carries (age 10 vs. the real 17), a fabricated hidden fee, and
    a "guarantees admission" promise CLAUDE.md separately forbids as a
    category. Under the old design this passed (the tag was real, so the
    citation-tag check alone approved it) and the fabricated sentence
    reached `.text` verbatim. Under the new selection-only contract, ANY
    text after the closing bracket makes the line fail the exact
    `[<claim_id>]` match, so the whole response is rejected outright --
    the fabricated sentence can never reach `.text` because `.text` is
    never built from anything the provider wrote in the first place."""
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(
        canned_response=(
            "[claim-real] The minimum age is actually 10, and a hidden "
            "capitation fee of Rs 50,000 is required, and this pathway "
            "guarantees admission."
        )
    )

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None
    assert result.citations == ()  # nothing survived at all -- no partial credit
    assert result.rejection_reason is not None


def test_response_with_extra_free_text_line_alongside_valid_citation_is_rejected() -> None:
    """A "framing" line was considered as an allowed exception (a short
    connective phrase with no digits/dates/claim content) and deliberately
    rejected as a design -- see app/ai/grounding.py's module docstring,
    "Why no free text at all". This proves the implementation actually
    matches that decision: an entirely innocuous-looking, digit-free line
    with no relation to any claim's content still gets the WHOLE response
    rejected, because the boundary is "no model-authored text", not "no
    text that looks suspicious"."""
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(
        canned_response="Here is what's confirmed:\n[claim-real]"
    )

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None
    assert result.citations == ()


def test_response_with_trailing_punctuation_after_citation_bracket_is_rejected() -> None:
    """Even trivial trailing content -- a single period -- after the
    closing bracket invalidates the line. The format is exact, not
    "close enough", precisely so there is no fuzzy boundary an attacker
    could probe for a gap in."""
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    adversarial_provider = MockAIProvider(canned_response="[claim-real].")

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=adversarial_provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None


def test_answered_response_text_is_generated_entirely_by_code_never_by_the_provider() -> None:
    """The positive proof to go with the negative ones above: given a
    validly-formatted selection, the resulting `.text` is EXACTLY the
    template output `app/ai/grounding.py`'s own `_fact_sentence()`
    produces from the real claim's own data -- not whatever the
    provider's prompt/response happened to contain, and not influenced by
    the provider's response in any way beyond which claim_id was picked."""
    real_claim = _claim(
        "claim-real",
        status=ClaimStatus.published,
        field_name="minimum_age",
        value=17,
    )
    provider = MockAIProvider(canned_response="[claim-real]")

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.answered
    assert result.text == "According to GSEB (verified 2026-06-01): minimum age is 17."
    (citation,) = result.citations
    assert citation.claim_id == "claim-real"
    assert citation.value == 17
    assert citation.is_stale is False


def test_response_with_duplicate_citation_lines_is_deduplicated() -> None:
    real_claim = _claim("claim-real", status=ClaimStatus.published, value=17)
    provider = MockAIProvider(canned_response="[claim-real]\n[claim-real]")

    result = answer_question(
        "What is the minimum age?",
        [real_claim],
        SOURCES_BY_ID,
        provider=provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.answered
    assert len(result.citations) == 1
    assert result.text == "According to GSEB (verified 2026-06-01): minimum age is 17."


# ---------------------------------------------------------------------
# Freshness/SLA staleness (the MEDIUM finding): a published, non-synthetic
# claim that is badly overdue for review must not produce a
# full-confidence "answered" response the same way a fresh claim does,
# and the staleness information must reach the caller rather than being
# silently lost.
# ---------------------------------------------------------------------


def test_stale_claim_citation_is_rejected_but_staleness_info_reaches_the_citation() -> None:
    stale_claim = _claim(
        "claim-stale",
        status=ClaimStatus.published,
        value=17,
        verification_date=date(2020, 1, 1),  # far past the 180-day SLA as of TODAY
        review_due_date=date(2021, 1, 1),
    )
    provider = MockAIProvider(canned_response="[claim-stale]")

    result = answer_question(
        "What is the minimum age?",
        [stale_claim],
        SOURCES_BY_ID,
        provider=provider,
        budget=_budget(),
        as_of=TODAY,
    )

    # Not a full-confidence "answered" response, unlike the fresh-claim case.
    assert result.status == AIAnswerStatus.insufficient_information
    assert result.text is None
    # Unlike a fabrication rejection, staleness info is NOT lost -- a
    # future caller can see exactly which claim blocked the answer.
    assert len(result.citations) == 1
    (citation,) = result.citations
    assert citation.claim_id == "claim-stale"
    assert citation.is_stale is True
    assert citation.review_due_date == date(2021, 1, 1)
    assert result.rejection_reason is not None
    assert "claim-stale" in result.rejection_reason


def test_fresh_claim_just_inside_the_sla_is_answered_normally() -> None:
    """Sanity check on the boundary: a claim verified well within the
    freshness SLA is NOT treated as stale, and produces a normal
    full-confidence answer -- the staleness check must not be so
    aggressive it downgrades ordinary fresh content."""
    fresh_claim = _claim(
        "claim-fresh",
        status=ClaimStatus.published,
        value=17,
        verification_date=TODAY - timedelta(days=10),
        review_due_date=TODAY + timedelta(days=170),
    )
    provider = MockAIProvider(canned_response="[claim-fresh]")

    result = answer_question(
        "What is the minimum age?",
        [fresh_claim],
        SOURCES_BY_ID,
        provider=provider,
        budget=_budget(),
        as_of=TODAY,
    )

    assert result.status == AIAnswerStatus.answered
    assert result.text is not None
    (citation,) = result.citations
    assert citation.is_stale is False


# ---------------------------------------------------------------------
# Spend cap: refuses a call once the budget is exhausted, with a clear
# error, and never lets the provider run once it does.
# ---------------------------------------------------------------------


def test_budget_exhaustion_refuses_further_calls_with_a_clear_error() -> None:
    provider = MockAIProvider()
    budget = _budget(daily_request_budget=1)
    claim = _claim("claim-1", status=ClaimStatus.published, value=17)

    first = answer_question(
        "What is the minimum age?",
        [claim],
        SOURCES_BY_ID,
        provider=provider,
        budget=budget,
        as_of=TODAY,
    )
    assert first.status == AIAnswerStatus.answered
    assert len(provider.calls) == 1

    with pytest.raises(AIBudgetExceededError):
        answer_question(
            "What is the minimum age?",
            [claim],
            SOURCES_BY_ID,
            provider=provider,
            budget=budget,
            as_of=TODAY,
        )

    # The refusal must happen BEFORE the provider is invoked again — no
    # second call recorded.
    assert len(provider.calls) == 1


def test_budget_reserve_raises_directly_once_exhausted() -> None:
    budget = AIRequestBudget(daily_request_budget=2)
    budget.reserve(today=TODAY)
    budget.reserve(today=TODAY)
    assert budget.remaining(today=TODAY) == 0
    with pytest.raises(AIBudgetExceededError):
        budget.reserve(today=TODAY)


def test_budget_resets_on_a_new_day() -> None:
    budget = AIRequestBudget(daily_request_budget=1)
    budget.reserve(today=date(2026, 9, 21))
    assert budget.remaining(today=date(2026, 9, 21)) == 0
    assert budget.remaining(today=date(2026, 9, 22)) == 1
    budget.reserve(today=date(2026, 9, 22))  # does not raise: new day, fresh budget


# ---------------------------------------------------------------------
# GeminiProvider must never be silently constructible without a
# configured API key.
# ---------------------------------------------------------------------


def test_gemini_provider_is_not_constructible_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.ai.gemini_provider as gemini_provider_module

    # `_env_file=None` bypasses any real .env on disk (same idiom as
    # tests/unit/test_health.py) so this assertion holds regardless of
    # local developer configuration.
    monkeypatch.setattr(
        gemini_provider_module,
        "get_settings",
        lambda: Settings(_env_file=None),
    )

    with pytest.raises(GeminiNotConfiguredError):
        GeminiProvider()


def test_gemini_provider_constructs_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flip side of the gate above: a configured key must let the
    object actually construct (still makes no network call — building a
    `genai.Client` does not itself contact the API)."""
    import app.ai.gemini_provider as gemini_provider_module

    monkeypatch.setattr(
        gemini_provider_module,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key="test-only-not-a-real-key"),
    )

    provider = GeminiProvider()
    assert isinstance(provider, AIProvider)


# ---------------------------------------------------------------------
# Sanity: the mock and Gemini providers both satisfy the AIProvider
# Protocol shape the grounding layer depends on.
# ---------------------------------------------------------------------


def test_mock_provider_satisfies_the_ai_provider_protocol() -> None:
    assert isinstance(MockAIProvider(), AIProvider)
