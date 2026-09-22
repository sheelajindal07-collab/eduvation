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

from app.api.ask import router as ask_json_router
from app.api.deps import get_db_client
from app.core.config import get_settings
from app.web import templating
from app.web.ask_pages import router as ask_html_router
from app.web.common import _db_client_or_none

_ASK_TEMPLATE_PATH = Path("app/web/templates/ask.html")
_FALLBACK_COPY = "You can still compare routes and use the calculators."

_PATHWAY_ID = "11111111-1111-1111-1111-111111111111"
_CAREER_ID = "33333333-3333-3333-3333-333333333333"
_SOURCE_ID = "22222222-2222-2222-2222-222222222222"
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
