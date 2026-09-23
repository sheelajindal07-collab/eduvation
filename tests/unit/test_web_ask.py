"""Tests for GET /ask (app/api/ask.py) and GET /ask/view
(app/web/ask_pages.py) -- UI-11 / BCI-014.

Neither route is registered on `app.main.app` yet: `app/main.py` is a
frozen, lead-only registry (see `app/api/ask.py`'s own module docstring
for the exact `RouterSlot` lines the lead needs to add). These tests
build a small standalone `FastAPI()` app wrapping both routers directly
-- the same shape the lead will register -- and override the DB
dependency with an in-memory fake, the same convention
`tests/unit/test_web_timeline_page.py`'s `_FakeDbClient` already uses.
No real database is touched here; the live, DB-backed behaviour (RLS,
real published/draft claims) is proven in `tests/db/test_ask_view.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.schemas import AIAnswerStatus
from app.ai.schemas import Answer as AIAnswer
from app.ai.what_changed import RenderedDiffLine, WhatChangedAnswer
from app.api.ask import router as ask_json_router
from app.api.deps import get_db_client
from app.core.config import get_settings
from app.web import ask_pages as ask_pages_module
from app.web import templating
from app.web.ask_pages import router as ask_html_router
from app.web.common import _db_client_or_none

_ASK_TEMPLATE_PATH = Path("app/web/templates/ask.html")
_FALLBACK_COPY = "You can still compare routes and use the calculators."

_PATHWAY_ID = "11111111-1111-1111-1111-111111111111"
_CAREER_ID = "33333333-3333-3333-3333-333333333333"
_SOURCE_ID = "22222222-2222-2222-2222-222222222222"
_PLAN_ID = "44444444-4444-4444-4444-444444444444"
_CLAIM_ID = "55555555-5555-5555-5555-555555555555"
_FRESH_VERIFICATION_DATE = "2026-09-01"  # well within the 180-day SLA of "today" in tests


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Enough of Supabase's fluent `.select().eq().in_().execute()`
    interface for `app.api.ask.assemble_ask_answer` -- filters are
    accepted and ignored (each fake table below is already exactly the
    rows one test wants back), never real network I/O. Same convention
    as `tests/unit/test_web_timeline_page.py`'s `_FakeQuery`."""

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
        "review_due_date": "2027-01-01",
        "currency": currency,
    }


def _official_source_row(source_id: str = _SOURCE_ID) -> dict[str, Any]:
    return {
        "id": source_id,
        "authority_name": "Test Authority",
        "official_url": "https://example.invalid/test-source",
        "source_type": "official",
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


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    """`get_settings()` is `lru_cache`d process-wide -- clear it around
    every test so one test's `monkeypatch.setenv` can't leak into the
    next (same reasoning `tests/db/conftest.py`'s own env loader uses)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestNoInputElementAnywhereInAskHtml:
    """This card's own requirement: "No <input>, <textarea>, or
    contenteditable element anywhere in ask.html -- write a grep-based
    test that asserts this mechanically, not just by inspection." A raw
    text scan of the file on disk, not a rendered-output scan, so this
    still catches a stray element even in a branch no fixture here
    happens to render."""

    def test_no_input_textarea_or_contenteditable(self) -> None:
        source = _ASK_TEMPLATE_PATH.read_text(encoding="utf-8")
        assert re.search(r"<input\b", source, re.IGNORECASE) is None
        assert re.search(r"<textarea\b", source, re.IGNORECASE) is None
        assert re.search(r"contenteditable", source, re.IGNORECASE) is None


class TestAskBcionMacroRendersAWorkingLinkInEveryMode:
    """`_ask.html`'s `ask_bcion` macro -- the three real call sites
    (`compare.html` x2, `requirements.html` x1) all call it exactly like
    this: a template id, a pathway_id, no `label`, no explicit
    `ai_enabled`. This card's own text: "render a working link to
    /ask?template=... in every mode"."""

    def _render(self, source: str) -> str:
        return templating.templates.env.from_string(source).render()

    def test_default_call_shape_renders_a_link_to_ask_view(self) -> None:
        rendered = self._render(
            '{% from "_ask.html" import ask_bcion %}'
            f'{{{{ ask_bcion("cost_breakdown", pathway_id="{_PATHWAY_ID}") }}}}'
        )
        assert "<a" in rendered
        assert f"/ask/view?template=cost_breakdown&amp;pathway_id={_PATHWAY_ID}" in rendered
        assert "<input" not in rendered.lower()

    def test_renders_the_same_link_when_ai_enabled_is_explicitly_false(self) -> None:
        rendered = self._render(
            '{% from "_ask.html" import ask_bcion %}'
            f'{{{{ ask_bcion("eligibility_gap", pathway_id="{_PATHWAY_ID}", ai_enabled=false) }}}}'
        )
        assert f"/ask/view?template=eligibility_gap&amp;pathway_id={_PATHWAY_ID}" in rendered

    def test_renders_the_same_link_when_ai_enabled_is_true(self) -> None:
        """Unlike `_components.html`'s `ask_bcion_entry` (hidden when AI
        is off), this per-fact macro never hides -- and, symmetrically,
        never depends on AI being ON either."""
        rendered = self._render(
            '{% from "_ask.html" import ask_bcion %}'
            f'{{{{ ask_bcion("pathway_overview", pathway_id="{_PATHWAY_ID}", ai_enabled=true) }}}}'
        )
        assert f"/ask/view?template=pathway_overview&amp;pathway_id={_PATHWAY_ID}" in rendered

    def test_career_id_travels_instead_of_pathway_id(self) -> None:
        rendered = self._render(
            '{% from "_ask.html" import ask_bcion %}'
            f'{{{{ ask_bcion("pathway_overview", career_id="{_CAREER_ID}") }}}}'
        )
        assert f"career_id={_CAREER_ID}" in rendered
        assert "pathway_id=" not in rendered

    def test_no_template_id_renders_nothing(self) -> None:
        rendered = self._render('{% from "_ask.html" import ask_bcion %}{{ ask_bcion(none) }}')
        assert rendered.strip() == ""


class TestAskJsonRoute:
    def test_unknown_template_returns_404_and_never_reflects_the_raw_id(self) -> None:
        client = _client_with_tables({})
        response = client.get(
            "/ask", params={"template": "totally-bogus-template-xyz", "pathway_id": _PATHWAY_ID}
        )
        assert response.status_code == 404
        assert "totally-bogus-template-xyz" not in response.text

    def test_neither_pathway_nor_career_id_is_422(self) -> None:
        client = _client_with_tables({})
        response = client.get("/ask", params={"template": "cost_breakdown"})
        assert response.status_code == 422

    def test_both_pathway_and_career_id_is_422(self) -> None:
        client = _client_with_tables({})
        response = client.get(
            "/ask",
            params={
                "template": "cost_breakdown",
                "pathway_id": _PATHWAY_ID,
                "career_id": _CAREER_ID,
            },
        )
        assert response.status_code == 422

    def test_malformed_pathway_id_is_422(self) -> None:
        client = _client_with_tables({})
        response = client.get(
            "/ask", params={"template": "cost_breakdown", "pathway_id": "not-a-uuid"}
        )
        assert response.status_code == 422

    def test_ai_disabled_shows_fallback_alongside_available_fact_cards(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AI_ENABLED", "false")
        tables = {
            "claims": [_claim_row(field="entry_requirements", value="Class 12 pass")],
            "sources": [_official_source_row()],
        }
        client = _client_with_tables(tables)
        response = client.get(
            "/ask", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ai_enabled"] is False
        assert body["show_fallback"] is True
        assert body["fallback_message"] == _FALLBACK_COPY
        assert body["fact_cards"] == [
            {
                "field": "entry_requirements",
                "field_label": "Entry requirements",
                "value": {
                    "value": "Class 12 pass",
                    "label": "checked_against_official_source",
                    "source_url": "https://example.invalid/test-source",
                    "verification_date": _FRESH_VERIFICATION_DATE,
                    "source_authority": "Test Authority",
                    "currency": None,
                    "is_sample": False,
                },
            }
        ]
        # main_stages/time_range/location have no published claim at all.
        assert set(body["missing_information"]) == {"Main stages", "Time", "Location"}

    def test_nothing_published_shows_fallback_with_no_fact_cards(self) -> None:
        client = _client_with_tables({"claims": [], "sources": []})
        response = client.get(
            "/ask", params={"template": "eligibility_gap", "pathway_id": _PATHWAY_ID}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["show_fallback"] is True
        assert body["fact_cards"] == []
        assert len(body["missing_information"]) == 5  # every GENERIC_CRITERION_FIELDS entry

    def test_cost_breakdown_uses_the_currency_safe_assembly(self) -> None:
        """A money claim with a null currency must render not_available,
        never a bare rupee-assumed number (SCOPE-4) -- proves this
        template really goes through `assemble_cost_breakdown`, not a
        bare `field_value_for`."""
        tables = {
            "claims": [
                _claim_row(field="verified_charges", value=125000, currency=None),
            ],
            "sources": [_official_source_row()],
        }
        client = _client_with_tables(tables)
        response = client.get(
            "/ask", params={"template": "cost_breakdown", "pathway_id": _PATHWAY_ID}
        )
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert "verified_charges" not in fields_by_name
        assert "Verified charges" in body["missing_information"]
        # estimated_additional_expenses is always at least an estimate
        # (assemble_cost_breakdown never labels it not_available).
        assert "estimated_additional_expenses" in fields_by_name

    def test_career_id_looks_up_career_entity_claims(self) -> None:
        tables = {
            "claims": [
                _claim_row(
                    field="entry_requirements",
                    value="Some career fact",
                    entity_type="Career",
                    entity_id=_CAREER_ID,
                )
            ],
            "sources": [_official_source_row()],
        }
        client = _client_with_tables(tables)
        response = client.get(
            "/ask", params={"template": "pathway_overview", "career_id": _CAREER_ID}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["entity_kind"] == "career"
        assert body["fact_cards"][0]["field"] == "entry_requirements"


class TestAskViewPage:
    def test_unknown_template_returns_404_html_and_never_reflects_the_raw_id(self) -> None:
        client = _client_with_tables({})
        response = client.get(
            "/ask/view",
            params={"template": "totally-bogus-template-xyz", "pathway_id": _PATHWAY_ID},
        )
        assert response.status_code == 404
        assert "totally-bogus-template-xyz" not in response.text
        assert "500" not in response.text  # never renders as a server error

    def test_invalid_request_degrades_to_a_friendly_200_page(self) -> None:
        client = _client_with_tables({})
        response = client.get("/ask/view", params={"template": "cost_breakdown"})
        assert response.status_code == 200
        assert "Back to explore" in response.text

    def test_every_entry_point_returns_200_with_fallback_copy_and_cited_records_when_ai_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The three real call sites: cost_breakdown/pathway_overview
        (compare.html), eligibility_gap (requirements.html) -- each with
        pathway_id, matching the shape those templates actually use."""
        monkeypatch.setenv("AI_ENABLED", "false")
        tables = {
            "claims": [
                _claim_row(field="entry_requirements", value="Class 12 pass"),
                _claim_row(field="verified_charges", value=125000, currency="INR"),
                _claim_row(field="minimum_age", value=16),
            ],
            "sources": [_official_source_row()],
            "pathways": [{"id": _PATHWAY_ID, "name": "Test Pathway"}],
        }
        client = _client_with_tables(tables)
        for template_id in ("cost_breakdown", "pathway_overview", "eligibility_gap"):
            response = client.get(
                "/ask/view", params={"template": template_id, "pathway_id": _PATHWAY_ID}
            )
            assert response.status_code == 200, template_id
            assert _FALLBACK_COPY in response.text, template_id
            assert "https://example.invalid/test-source" in response.text, template_id

    def test_db_unavailable_degrades_to_a_friendly_message_not_a_crash(self) -> None:
        app = _make_app()
        app.dependency_overrides[_db_client_or_none] = lambda: None
        client = TestClient(app)
        response = client.get(
            "/ask/view", params={"template": "cost_breakdown", "pathway_id": _PATHWAY_ID}
        )
        assert response.status_code == 200
        assert "trouble reaching our data" in response.text

    def test_missing_information_is_listed_by_display_label(self) -> None:
        tables = {"claims": [], "sources": []}
        client = _client_with_tables(tables)
        response = client.get(
            "/ask/view", params={"template": "eligibility_gap", "pathway_id": _PATHWAY_ID}
        )
        assert response.status_code == 200
        assert "Minimum age" in response.text
        assert "Domicile" in response.text


class TestAskViewRendersAiSentencesAndCitations:
    """BCI-025: `ai_sentences`/`ai_citations` were already threaded into
    this page's template context (AI-7) but `ask.html` had no markup that
    read either key -- this proves the actual rendered HTML now carries
    the AI's own sentence text and its citation's source authority/link,
    alongside the fact cards, never instead of them."""

    def test_answered_sentences_and_citations_render_alongside_fact_cards(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to Test Authority: entry requirements is Class 12 pass."],
            citations=[
                {
                    "record_id": "claim-entry_requirements",
                    "field": "entry_requirements",
                    "value": "Class 12 pass",
                    "source_authority": "Test Authority",
                    "source_url": "https://example.invalid/ai-sentence-source",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)
        tables = {
            "claims": [_claim_row(field="entry_requirements", value="Class 12 pass")],
            "sources": [_official_source_row()],
            "pathways": [{"id": _PATHWAY_ID, "name": "Test Pathway"}],
        }
        client = _client_with_tables(tables)

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert "According to Test Authority: entry requirements is Class 12 pass." in (
            response.text
        )
        assert "https://example.invalid/ai-sentence-source" in response.text
        # Alongside, never instead of -- the deterministic fact card (its own,
        # DIFFERENT source URL) is still present too.
        assert "https://example.invalid/test-source" in response.text

    def test_no_ai_sections_render_when_ai_never_answered(self) -> None:
        """AI is left at its pilot default (disabled) -- `_pipeline_answer`
        is never even called, so `ai_sentences`/`next_step_actions`/
        `what_changed_lines` are all empty and none of the new sections'
        markup appears; only the one fact card's `<section class="card">`
        renders."""
        tables = {
            "claims": [_claim_row(field="entry_requirements", value="Class 12 pass")],
            "sources": [_official_source_row()],
            "pathways": [{"id": _PATHWAY_ID, "name": "Test Pathway"}],
        }
        client = _client_with_tables(tables)

        response = client.get(
            "/ask/view", params={"template": "pathway_overview", "pathway_id": _PATHWAY_ID}
        )

        assert response.status_code == 200
        assert response.text.count('<section class="card">') == 1  # the fact card only
        assert '<li class="card">' not in response.text  # no actions, no diff lines


class TestAskViewNextStepsResolvesPlanIdAndRendersActions:
    """BCI-025: mirrors `app.api.ask.ask()`'s own `plan_id` resolution
    (AI-18) -- a `next_steps` request naming a `plan_id`, with neither
    `pathway_id` nor `career_id`, must resolve to that plan's pathway and
    render the derived next-step actions, each with its own citation
    link, alongside the (deliberately always-empty, `ASK_TEMPLATES
    ["next_steps"].fields == ()`) fact cards."""

    def test_plan_id_alone_resolves_and_renders_next_step_actions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = AIAnswer(
            status=AIAnswerStatus.answered,
            sentences=["According to Test Authority: application window is 1 March 2027."],
            citations=[
                {
                    "record_id": "claim-application_window",
                    "field": "application_window",
                    "value": "1 March 2027",
                    "source_authority": "Test Authority",
                    "source_url": "https://example.invalid/next-step-source",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_pages_module, "_pipeline_answer", lambda *a, **k: canned)
        tables = {
            "saved_plans": [{"id": _PLAN_ID, "pathway_id": _PATHWAY_ID}],
            "pathways": [{"id": _PATHWAY_ID, "name": "Test Pathway"}],
            "claims": [],
            "sources": [],
        }
        client = _client_with_tables(tables)

        response = client.get(
            "/ask/view", params={"template": "next_steps", "plan_id": _PLAN_ID}
        )

        assert response.status_code == 200
        assert "Register before 1 March 2027." in response.text
        assert "https://example.invalid/next-step-source" in response.text
        # claim_id is an id, never rendered directly.
        assert "claim-application_window" not in response.text

    def test_a_plan_id_that_does_not_resolve_is_a_404_matching_the_json_route(self) -> None:
        """No `saved_plans` row at all for this id (a guest, another
        identity's plan, or a plan that simply does not exist --
        `_pathway_id_for_plan` treats all three identically, deliberately
        never distinguishing "no such plan" from "not yours"). This route
        does not catch `_pathway_id_for_plan`'s `HTTPException(404,
        "Plan not found.")` -- it propagates unmodified, exactly like
        `app.api.ask.ask()`'s own behaviour. Real, RLS-backed proof that a
        guest/another student specifically cannot resolve someone else's
        plan id lives in `tests/db/test_ask_view.py`
        (`TestAskViewNextStepsPlanIdOwnershipAgainstTheRealStack`)."""
        tables = {"saved_plans": [], "pathways": [], "claims": [], "sources": []}
        client = _client_with_tables(tables)

        response = client.get(
            "/ask/view", params={"template": "next_steps", "plan_id": _PLAN_ID}
        )

        assert response.status_code == 404
        assert "Plan not found." in response.text


class TestAskViewWhatChangedResolvesClaimIdAndRendersDiffLines:
    """BCI-025: mirrors `app.api.ask.ask()`'s own `claim_id` resolution
    (AI-19) -- `what_changed` bypasses `entity_kind_and_id` entirely and
    resolves directly by `claim_id`."""

    def test_claim_id_alone_resolves_and_renders_what_changed_lines(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = WhatChangedAnswer(
            status=AIAnswerStatus.answered,
            lines=(
                RenderedDiffLine(
                    attribute="value",
                    old_value=80000,
                    new_value=90000,
                    text="The verified charges changed from 80000 to 90000.",
                ),
            ),
            citations=[
                {
                    "record_id": f"{_CLAIM_ID}:value",
                    "field": "value",
                    "value": 90000,
                    "source_authority": "Test Authority",
                    "source_url": "https://example.invalid/what-changed-source",
                    "is_stale": False,
                }
            ],
        )
        monkeypatch.setattr(ask_pages_module, "_what_changed_answer", lambda *a, **k: canned)
        # Empty -- claim_id resolution bypasses entity_kind_and_id entirely
        # and never queries pathways/careers for a name (entity_kind ==
        # "claim"), and what_changed's own ASK_TEMPLATES.fields == () means
        # assemble_ask_answer's claims/sources lookups never produce a fact
        # card either way.
        tables: dict[str, list[dict[str, Any]]] = {"claims": [], "sources": []}
        client = _client_with_tables(tables)

        response = client.get(
            "/ask/view", params={"template": "what_changed", "claim_id": _CLAIM_ID}
        )

        assert response.status_code == 200
        assert "The verified charges changed from 80000 to 90000." in response.text
        assert "https://example.invalid/what-changed-source" in response.text

    def test_missing_claim_id_degrades_to_the_friendly_invalid_request_page(self) -> None:
        client = _client_with_tables({})
        response = client.get("/ask/view", params={"template": "what_changed"})
        assert response.status_code == 200
        assert "Back to explore" in response.text

    def test_malformed_claim_id_degrades_to_the_friendly_invalid_request_page(self) -> None:
        client = _client_with_tables({})
        response = client.get(
            "/ask/view", params={"template": "what_changed", "claim_id": "not-a-uuid"}
        )
        assert response.status_code == 200
        assert "Back to explore" in response.text
