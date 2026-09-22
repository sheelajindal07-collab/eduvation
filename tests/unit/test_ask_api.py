"""Tests for AI-7 — wiring `app/ai/pipeline.py` (AI-6, merged) into
GET /ask (`app/api/ask.py`) and GET /ask/view (`app/web/ask_pages.py`)
as an ADDITIVE layer over the UI-11/BCI-014 deterministic baseline.

`tests/unit/test_web_ask.py` (UI-11, not owned by this card) already
covers the deterministic-only behaviour in full; `tests/db/test_ask_view.py`
(also UI-11) proves that same behaviour against the real stack and is run
unmodified as this card's own proof that the baseline is untouched.
`tests/unit/test_ai_pipeline.py` (AI-6, not owned by this card) already
covers `app.ai.pipeline.answer()`'s own two-pass correctness in full.

This file therefore tests exactly the seam AI-7 owns:

- `app.api.ask._pipeline_answer()` in isolation -- the AI feature-flag
  gate, the `GeminiProvider()` construction/`GeminiNotConfiguredError`
  catch, the `AskRequest` built from `entity_kind`/`entity_id`, and the
  process-local `_ai_budget()` singleton -- via direct calls and via
  monkeypatching `app.api.ask.GeminiProvider` / `app.api.ask.ai_pipeline
  .answer` (never the real network, never a real provider call).
- Both routes' own rendering logic -- fact cards are always present,
  `ai_sentences`/`ai_citations` are populated only when the pipeline
  returned `AIAnswerStatus.answered`, and every other status renders
  nothing extra -- via monkeypatching `app.api.ask._pipeline_answer` /
  `app.web.ask_pages._pipeline_answer` directly (a separate name binding
  per module, since `from app.api.ask import _pipeline_answer` copies the
  reference at import time).

No real database, no real provider, no network call anywhere in this
file.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.ask as ask_module
import app.web.ask_pages as ask_pages_module
from app.ai.gemini_provider import GeminiNotConfiguredError
from app.ai.schemas import AIAnswerStatus, AskRequest
from app.ai.schemas import Answer as AIAnswer
from app.api.ask import router as ask_json_router
from app.api.deps import get_db_client
from app.core.config import Settings, get_settings
from app.web.ask_pages import router as ask_html_router
from app.web.common import _db_client_or_none

_PATHWAY_ID = "11111111-1111-1111-1111-111111111111"
_CAREER_ID = "33333333-3333-3333-3333-333333333333"
_SOURCE_ID = "22222222-2222-2222-2222-222222222222"
_FRESH_VERIFICATION_DATE = "2026-09-01"  # well within the 180-day SLA of "today" in tests
_FALLBACK_COPY = "You can still compare routes and use the calculators."


# ---------------------------------------------------------------------
# Fakes -- a minimal in-memory `Client` stand-in for
# `assemble_ask_answer()`'s `.table(...).select().eq().in_().execute()`
# calls, the same convention `tests/unit/test_web_ask.py`'s own
# `_FakeDbClient`/`_FakeQuery` use (duplicated here, not imported, so
# this file stays self-contained -- that module is not owned by this
# card).
# ---------------------------------------------------------------------


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def in_(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._tables.get(name, []))


def _claim_row(
    *,
    field: str,
    value: Any,
    entity_type: str = "Pathway",
    entity_id: str = _PATHWAY_ID,
    status: str = "published",
    verification_date: str = _FRESH_VERIFICATION_DATE,
    source_id: str = _SOURCE_ID,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"claim-{field}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field": field,
        "value": value,
        "source_id": source_id,
        "verification_date": verification_date,
        "verifier": "tester",
        "status": status,
        "review_due_date": "2099-01-01",
        "currency": currency,
    }


def _source_row(source_id: str = _SOURCE_ID) -> dict[str, Any]:
    return {
        "id": source_id,
        "authority_name": "Test Authority",
        "official_url": "https://example.invalid/test-source",
        "source_type": "official",
    }


def _tables_with_one_published_claim(
    *, entity_type: str = "Pathway", entity_id: str = _PATHWAY_ID
) -> dict[str, list[dict[str, Any]]]:
    return {
        "claims": [
            _claim_row(
                field="entry_requirements",
                value="Class 12 pass",
                entity_type=entity_type,
                entity_id=entity_id,
            )
        ],
        "sources": [_source_row()],
    }


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ask_json_router)
    app.include_router(ask_html_router)
    return app


def _client_with_tables(tables: dict[str, list[dict[str, Any]]]) -> TestClient:
    app = _make_app()
    fake_db = _FakeDbClient(tables)
    app.dependency_overrides[get_db_client] = lambda: fake_db
    app.dependency_overrides[_db_client_or_none] = lambda: fake_db
    return TestClient(app)


def _settings(*, ai_enabled: bool = True, configured: bool = True) -> Settings:
    """Same idiom as `tests/unit/test_ai_pipeline.py`'s own `_settings()`
    helper -- `_env_file=None` bypasses any real `.env` on disk."""
    return Settings(
        _env_file=None,
        ai_enabled=ai_enabled,
        gemini_api_key="test-only-not-a-real-key" if configured else None,
    )


def _explode(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("must not be called on this path")


class _FakeGeminiProviderNotConfigured:
    """Stands in for the real `GeminiProvider`, whose own constructor
    raises `GeminiNotConfiguredError` when `GEMINI_API_KEY` is missing --
    this fake raises unconditionally, so a test can exercise the route's
    catch of that error without depending on real Settings plumbing."""

    def __init__(self) -> None:
        raise GeminiNotConfiguredError("GEMINI_API_KEY is not set (test double).")


class _FakeGeminiProviderOK:
    """Constructing this always succeeds and makes no network call.
    `.generate()` is never exercised in tests that use this fake, because
    `app.api.ask.ai_pipeline.answer` is monkeypatched separately in every
    test that uses it -- this class only proves *construction* happened,
    never a real provider call."""

    def generate(self, prompt: str) -> str:  # pragma: no cover - never called
        raise AssertionError("must not be called -- ai_pipeline.answer is monkeypatched")


@pytest.fixture(autouse=True)
def _reset_caches() -> Any:
    """`get_settings()` and `app.api.ask._ai_budget()` are both
    `lru_cache`d process-wide (this card's own module-level singleton
    budget mirrors `get_settings()`'s lifecycle, by design -- see
    `_ai_budget()`'s own docstring) -- clear both around every test so
    one test's settings/budget state can never leak into the next."""
    get_settings.cache_clear()
    ask_module._ai_budget.cache_clear()
    yield
    get_settings.cache_clear()
    ask_module._ai_budget.cache_clear()


# ---------------------------------------------------------------------
# `_pipeline_answer()` in isolation.
# ---------------------------------------------------------------------


class TestPipelineAnswerHelper:
    def test_returns_none_and_never_touches_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "get_settings", lambda: _settings(ai_enabled=False))
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is None

    def test_returns_none_and_never_touches_the_pipeline_when_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=False)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is None

    def test_gemini_not_configured_error_is_caught_as_ai_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE proof this card's completion report asks for:
        `GeminiNotConfiguredError` never escapes `_pipeline_answer()`."""
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)  # must never be reached
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        result = ask_module._pipeline_answer(
            object(),
            template,
            entity_kind="pathway",
            entity_id=_PATHWAY_ID,
            as_of=date(2026, 9, 22),
        )

        assert result is not None
        assert result.status == AIAnswerStatus.ai_unavailable
        assert result.sentences == []
        assert result.citations == []

    def test_builds_a_pathway_id_request_for_a_pathway_entity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["db"] = db
            captured["request"] = request
            captured["provider"] = provider
            captured["budget"] = budget
            captured["as_of"] = as_of
            return AIAnswer(status=AIAnswerStatus.answered, sentences=["s"], citations=[])

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]
        as_of = date(2026, 9, 22)
        db = object()

        result = ask_module._pipeline_answer(
            db, template, entity_kind="pathway", entity_id=_PATHWAY_ID, as_of=as_of
        )

        assert result is not None
        assert result.status == AIAnswerStatus.answered
        request = captured["request"]
        assert isinstance(request, AskRequest)
        assert request.template_id == "pathway_overview"
        assert request.pathway_id == _PATHWAY_ID
        assert request.career_id is None
        assert captured["db"] is db
        assert captured["as_of"] == as_of
        assert isinstance(captured["provider"], _FakeGeminiProviderOK)
        assert captured["budget"] is ask_module._ai_budget()

    def test_builds_a_career_id_request_for_a_career_entity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_answer(
            db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
        ) -> AIAnswer:
            captured["request"] = request
            return AIAnswer(status=AIAnswerStatus.not_available)

        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderOK)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _fake_answer)
        template = ask_module.ASK_TEMPLATES["pathway_overview"]

        ask_module._pipeline_answer(
            object(), template, entity_kind="career", entity_id=_CAREER_ID, as_of=date(2026, 9, 22)
        )

        request = captured["request"]
        assert request.pathway_id is None
        assert request.career_id == _CAREER_ID


class TestAiBudgetSingleton:
    def test_is_shared_across_calls_not_reconstructed_per_call(self) -> None:
        first = ask_module._ai_budget()
        second = ask_module._ai_budget()
        assert first is second


# ---------------------------------------------------------------------
# GET /ask (JSON route) -- fact cards always present; ai_sentences/
# ai_citations additive-only.
# ---------------------------------------------------------------------


class TestAskJsonRouteAiWiring:
    def test_never_calls_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []
        assert any(c["field"] == "entry_requirements" for c in body["fact_cards"])

    def test_answered_renders_ai_sentences_and_citations_alongside_fact_cards(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE proof this card's completion report asks for: AI on +
        pipeline `answered` renders sentences/citations alongside, never
        instead of, the deterministic fact cards."""
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to GSEB: entry requirements is Class 12 pass."],
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": "https://gseb.example.invalid",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_module, "_pipeline_answer", lambda *a, **k: canned)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        # The deterministic fact card is still present -- never replaced.
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["entry_requirements"]["value"]["value"] == "Class 12 pass"
        # The AI content is present ALONGSIDE it.
        assert body["ai_sentences"] == canned.sentences
        assert body["ai_citations"] == canned.citations

    @pytest.mark.parametrize(
        "status",
        [
            AIAnswerStatus.not_available,
            AIAnswerStatus.insufficient_information,
            AIAnswerStatus.ai_unavailable,
            AIAnswerStatus.budget_exhausted,
            AIAnswerStatus.unsupported_template,
        ],
    )
    def test_every_non_answered_status_renders_exactly_what_ai_off_already_rendered(
        self, monkeypatch: pytest.MonkeyPatch, status: AIAnswerStatus
    ) -> None:
        """THE proof this card's completion report asks for: AI on +
        pipeline falling back to any non-`answered` status renders
        exactly what AI-off already rendered -- no blank page, no error,
        no second, conflicting message."""
        tables = _tables_with_one_published_claim()
        baseline = _client_with_tables(tables).get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )
        assert baseline.status_code == 200
        baseline_body = baseline.json()

        canned = AIAnswer(
            status=status,
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": None,
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_module, "_pipeline_answer", lambda *a, **k: canned)
        client = _client_with_tables(tables)

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["fact_cards"] == baseline_body["fact_cards"]
        assert body["missing_information"] == baseline_body["missing_information"]
        assert body["show_fallback"] == baseline_body["show_fallback"]
        assert body["fallback_message"] == baseline_body["fallback_message"]
        # Nothing extra -- even though the canned Answer carries a
        # citation, it must never surface for a non-answered status.
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []

    def test_never_500s_when_gemini_is_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_module, "get_settings", lambda: _settings(ai_enabled=True, configured=True)
        )
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []
        assert any(c["field"] == "entry_requirements" for c in body["fact_cards"])


# ---------------------------------------------------------------------
# GET /ask/view (HTML page) -- same additive wiring, threaded into the
# template context. `app/web/templates/ask.html` is a forbidden file for
# this card and, as of this card, has no markup that reads either
# `ai_sentences` or `ai_citations` -- see `app/web/ask_pages.py`'s own
# module docstring. These tests prove the DATA reaches the template
# context correctly; they do not (and cannot, without touching the
# forbidden template) prove anything is visually rendered from it.
# ---------------------------------------------------------------------


class TestAskViewPageAiWiring:
    def test_never_calls_the_pipeline_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(ask_module, "GeminiProvider", _explode)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert _FALLBACK_COPY in response.text

    def test_answered_passes_ai_sentences_and_citations_into_template_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to GSEB: entry requirements is Class 12 pass."],
            citations=[
                {
                    "record_id": "rec-1",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "GSEB",
                    "source_url": "https://gseb.example.invalid",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)

        original_template_response = ask_pages_module.templates.TemplateResponse
        captured: dict[str, Any] = {}

        def _capture(
            request: Any, name: str, context: Any = None, *args: Any, **kwargs: Any
        ) -> Any:
            captured["context"] = context
            return original_template_response(request, name, context, *args, **kwargs)

        monkeypatch.setattr(ask_pages_module.templates, "TemplateResponse", _capture)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        context = captured["context"]
        assert context["ai_sentences"] == canned.sentences
        assert context["ai_citations"] == canned.citations
        # The deterministic fact card is still in context too -- never
        # replaced (AskFactCard is a dataclass, not a dict -- .field).
        assert any(card.field == "entry_requirements" for card in context["fact_cards"])

    def test_non_answered_status_passes_empty_ai_lists_into_template_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.insufficient_information, citations=[{"record_id": "r"}]
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)

        original_template_response = ask_pages_module.templates.TemplateResponse
        captured: dict[str, Any] = {}

        def _capture(
            request: Any, name: str, context: Any = None, *args: Any, **kwargs: Any
        ) -> Any:
            captured["context"] = context
            return original_template_response(request, name, context, *args, **kwargs)

        monkeypatch.setattr(ask_pages_module.templates, "TemplateResponse", _capture)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        context = captured["context"]
        assert context["ai_sentences"] == []
        assert context["ai_citations"] == []

    def test_never_500s_when_gemini_is_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ai_on_settings = _settings(ai_enabled=True, configured=True)
        monkeypatch.setattr(ask_module, "get_settings", lambda: ai_on_settings)
        monkeypatch.setattr(ask_pages_module, "get_settings", lambda: ai_on_settings)
        monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProviderNotConfigured)
        monkeypatch.setattr(ask_module.ai_pipeline, "answer", _explode)
        client = _client_with_tables(_tables_with_one_published_claim())

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert "Class 12 pass" in response.text
