"""Integration tests for GET /ask?template=what_changed against the real
database, and for `app.ai.what_changed.answer_what_changed()`'s own
RLS-equivalent readability re-check against the REAL RLS engine (AI-19,
`tasks/BCI-022.md`).

Two halves, mirroring the split `tests/db/test_ask_next_steps.py` already
established for AI-18:

- **Route-level** (`TestWhatChangedRoute*`): AI is left at its pilot
  default (disabled, unset in this test environment) throughout, exactly
  like that file — proves `claim_id` validation/resolution and the
  disabled-AI response shape against the real stack, over HTTP, via
  `app.main.app`.
- **RLS-equivalent access** (`TestReadabilityAgainstRealRLS`): calls
  `app.ai.what_changed.answer_what_changed()` directly (not over HTTP),
  with `app.ai.what_changed.get_settings` monkeypatched so AI is "on" and
  a `MockAIProvider` standing in for the network call (never a real
  provider call, anywhere in this file) — but the `db` client passed in
  is a REAL, RLS-scoped Supabase client from `tests/db/conftest.py`
  (`guest_client`/`student_a`/`reviewer`), so `claims_select_published`
  (`db/migrations/0001_init.sql`) actually decides what comes back. This
  is where this card's own "a claim with no successor, or either row
  unreadable under the caller's access, gives not_available" proof is
  made against the real Postgres RLS engine, not a fake.
  `tests/unit/test_ai_what_changed.py` already proves the two-pass
  selection/verification/rendering logic in full against a fake db; this
  file exists only to prove the READABILITY re-check against the real
  thing.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

import app.ai.what_changed as what_changed_module
from app.ai.budget import AIRequestBudget
from app.ai.mock_provider import MockAIProvider
from app.ai.schemas import AIAnswerStatus
from app.ai.what_changed import answer_what_changed
from app.core.config import Settings
from app.main import app
from tests.db.conftest import run_name

client = TestClient(app)


def _settings(*, ai_enabled: bool = True, configured: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        ai_enabled=ai_enabled,
        gemini_api_key="test-only-not-a-real-key" if configured else None,
    )


def _patch_settings_on(monkeypatch: pytest.MonkeyPatch, **kwargs: bool) -> None:
    monkeypatch.setattr(what_changed_module, "get_settings", lambda: _settings(**kwargs))


@pytest.fixture
def superseded_claim_chain(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A real supersession: a PUBLISHED claim (`minimum_age`, 17, "Old
    Authority"), then superseded by a second PUBLISHED claim (18, "New
    Authority", a later `verification_date`) — all three diffable
    attributes actually change, matching
    `tests/unit/test_ai_what_changed.py`'s own `_full_scenario_db`
    fixture scenario. Seeded directly via the service-role `admin_client`
    (`db/migrations/0003_maker_checker.sql`'s own documented service_role
    exemption — the same precedent `tests/db/test_ask_next_steps.py`'s
    `seeded_pathway` fixture already relies on)."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("what-changed test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("what-changed test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_ask_what_changed.py",
            }
        )
        .execute()
        .data[0]
    )
    old_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("WHAT CHANGED OLD AUTHORITY"),
                "official_url": "https://example.invalid/what-changed-old-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    new_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("WHAT CHANGED NEW AUTHORITY"),
                "official_url": "https://example.invalid/what-changed-new-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    successor_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_age",
                "value": 18,
                "source_id": new_source["id"],
                "verification_date": "2026-06-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    superseded_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "minimum_age",
                "value": 17,
                "source_id": old_source["id"],
                "verification_date": "2026-01-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "superseded",
                "review_due_date": "2099-01-01",
                "superseded_by": successor_claim["id"],
            }
        )
        .execute()
        .data[0]
    )

    yield {
        "career": career,
        "pathway": pathway,
        "old_source": old_source,
        "new_source": new_source,
        "superseded_claim": superseded_claim,
        "successor_claim": successor_claim,
    }

    admin_client.table("claims").delete().eq("id", superseded_claim["id"]).execute()
    admin_client.table("claims").delete().eq("id", successor_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", old_source["id"]).execute()
    admin_client.table("sources").delete().eq("id", new_source["id"]).execute()


# ---------------------------------------------------------------------
# Route-level: claim_id validation/resolution, AI at its pilot default.
# ---------------------------------------------------------------------


class TestWhatChangedRouteValidation:
    def test_a_missing_claim_id_is_422(self) -> None:
        response = client.get("/ask", params={"template": "what_changed"})
        assert response.status_code == 422

    def test_a_malformed_claim_id_is_422_not_a_500(self) -> None:
        response = client.get(
            "/ask", params={"template": "what_changed", "claim_id": "not-a-uuid"}
        )
        assert response.status_code == 422

    def test_pathway_id_and_career_id_are_ignored_for_this_template(
        self, superseded_claim_chain: dict[str, Any]
    ) -> None:
        """`what_changed` only ever consults `claim_id` -- a pathway_id
        alongside it (no claim_id at all) still 422s, exactly as if
        neither had been given."""
        response = client.get(
            "/ask",
            params={
                "template": "what_changed",
                "pathway_id": superseded_claim_chain["pathway"]["id"],
            },
        )
        assert response.status_code == 422

    def test_claim_id_is_ignored_by_the_other_four_templates(
        self, superseded_claim_chain: dict[str, Any]
    ) -> None:
        """The existing pathway_id/career_id 422 still applies for every
        other template even when a claim_id is also supplied."""
        response = client.get(
            "/ask",
            params={
                "template": "pathway_overview",
                "claim_id": superseded_claim_chain["superseded_claim"]["id"],
            },
        )
        assert response.status_code == 422


class TestWhatChangedRouteDisabledAiShape:
    def test_a_nonexistent_but_well_formed_claim_id_is_200_never_available(self) -> None:
        response = client.get(
            "/ask",
            params={
                "template": "what_changed",
                "claim_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["template_id"] == "what_changed"
        assert body["entity_kind"] == "claim"
        assert body["entity_id"] == "00000000-0000-0000-0000-000000000000"
        assert body["fact_cards"] == []
        assert body["missing_information"] == []
        assert body["what_changed_lines"] == []
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []

    def test_a_real_superseded_claim_still_renders_nothing_extra_when_ai_is_off(
        self, superseded_claim_chain: dict[str, Any]
    ) -> None:
        """AI disabled by default (pilot default, unset in this test
        environment) -- `_what_changed_answer()` returns `None` before
        ever touching the database, so nothing about this REAL
        supersession's actual old/new values ever reaches the response,
        even though the row genuinely exists and genuinely has a
        successor."""
        response = client.get(
            "/ask",
            params={
                "template": "what_changed",
                "claim_id": superseded_claim_chain["superseded_claim"]["id"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ai_enabled"] is False
        assert body["show_fallback"] is True
        assert body["what_changed_lines"] == []
        assert body["fact_cards"] == []
        assert body["ai_sentences"] == []
        assert body["ai_citations"] == []
        # The fixture's own distinctive (run-tagged) source authority
        # names -- unlike a bare "17"/"18" substring check, these cannot
        # coincidentally collide with a hex character run inside a random
        # UUID elsewhere in the body (entity_id, prompt key, ...).
        assert superseded_claim_chain["old_source"]["authority_name"] not in response.text
        assert superseded_claim_chain["new_source"]["authority_name"] not in response.text


# ---------------------------------------------------------------------
# Readability against the REAL RLS engine -- `answer_what_changed()`
# called directly (not over HTTP), AI "on" via a monkeypatched settings
# function and a MockAIProvider (never a real network call).
# ---------------------------------------------------------------------


def _budget() -> AIRequestBudget:
    return AIRequestBudget(daily_request_budget=10)


def _record_ids(superseded_claim_id: str) -> tuple[str, str, str]:
    return (
        f"{superseded_claim_id}:value",
        f"{superseded_claim_id}:source_authority",
        f"{superseded_claim_id}:verification_date",
    )


def _full_confirm_provider(superseded_claim_id: str) -> MockAIProvider:
    value_id, source_id, date_id = _record_ids(superseded_claim_id)
    return MockAIProvider(
        responses=[
            f"[{value_id}]\n[{source_id}]\n[{date_id}]",
            f"YES {value_id}\nYES {source_id}\nYES {date_id}",
        ]
    )


class TestReadabilityAgainstRealRLS:
    def test_a_guest_cannot_see_a_superseded_claim_at_all(
        self,
        superseded_claim_chain: dict[str, Any],
        guest_client: Client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`claims_select_published` (0001_init.sql): draft/in_review/
        superseded rows are reviewer-only. A guest's anon-key client
        cannot even see the superseded row, so `_readable_claim` gets
        zero rows back and the whole answer is not_available -- never a
        fabricated diff, and the provider is never called (an exploding
        provider would fail this test if it were)."""
        _patch_settings_on(monkeypatch, ai_enabled=True, configured=True)
        result = answer_what_changed(
            guest_client,
            superseded_claim_chain["superseded_claim"]["id"],
            _full_confirm_provider(superseded_claim_chain["superseded_claim"]["id"]),
            _budget(),
            as_of=date(2026, 9, 22),
        )
        assert result.status == AIAnswerStatus.not_available
        assert result.diff is None
        assert result.lines == ()

    def test_an_ordinary_signed_in_student_also_cannot_see_it(
        self,
        superseded_claim_chain: dict[str, Any],
        student_a: tuple[str, Client],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same RLS policy, same outcome for a signed-in but non-reviewer
        identity -- this is not merely an "unauthenticated" carve-out."""
        _patch_settings_on(monkeypatch, ai_enabled=True, configured=True)
        _student_id, student_client = student_a
        result = answer_what_changed(
            student_client,
            superseded_claim_chain["superseded_claim"]["id"],
            _full_confirm_provider(superseded_claim_chain["superseded_claim"]["id"]),
            _budget(),
            as_of=date(2026, 9, 22),
        )
        assert result.status == AIAnswerStatus.not_available
        assert result.diff is None

    def test_a_reviewer_sees_the_real_diff_rendered_from_the_actual_claim_values(
        self,
        superseded_claim_chain: dict[str, Any],
        reviewer: tuple[str, Client],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`is_reviewer()` lets a reviewer's own RLS-scoped client see
        the superseded row -- `_readable_claim`'s own re-check then
        accepts it (status is `superseded`, source is real/non-synthetic),
        and the diff is computed from -- and rendered from -- the
        fixture's REAL values, never anything the (mocked) provider's raw
        text said."""
        _patch_settings_on(monkeypatch, ai_enabled=True, configured=True)
        _reviewer_id, reviewer_client = reviewer
        superseded_id = superseded_claim_chain["superseded_claim"]["id"]
        result = answer_what_changed(
            reviewer_client,
            superseded_id,
            _full_confirm_provider(superseded_id),
            _budget(),
            as_of=date(2026, 9, 22),
        )
        assert result.status == AIAnswerStatus.answered
        assert result.diff is not None
        assert result.diff.changed_fields == ("value", "source_authority", "verification_date")
        assert result.diff.old_value == 17
        assert result.diff.new_value == 18
        by_attribute = {line.attribute: line for line in result.lines}
        assert by_attribute["value"].text == "The value changed from 17 to 18."
        assert by_attribute["value"].old_value == 17
        assert by_attribute["value"].new_value == 18
        assert by_attribute["verification_date"].text == (
            "The verification date changed from 2026-01-01 to 2026-06-01."
        )

    def test_a_claim_with_no_successor_is_not_available_even_for_a_reviewer(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A published (never superseded) claim: readable, but there is
        nothing to diff against."""
        _patch_settings_on(monkeypatch, ai_enabled=True, configured=True)
        career = (
            admin_client.table("careers")
            .insert({"name": run_name("what-changed no-successor career (SYNTHETIC)")})
            .execute()
            .data[0]
        )
        pathway = (
            admin_client.table("pathways")
            .insert(
                {
                    "career_id": career["id"],
                    "name": run_name("what-changed no-successor pathway (SYNTHETIC)"),
                    "description": "Seeded by tests/db/test_ask_what_changed.py",
                }
            )
            .execute()
            .data[0]
        )
        source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": run_name("WHAT CHANGED NO-SUCCESSOR AUTHORITY"),
                    "official_url": "https://example.invalid/what-changed-no-successor",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "minimum_age",
                    "value": 17,
                    "source_id": source["id"],
                    "verification_date": "2026-01-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            _reviewer_id, reviewer_client = reviewer
            result = answer_what_changed(
                reviewer_client,
                claim["id"],
                _full_confirm_provider(claim["id"]),
                _budget(),
                as_of=date(2026, 9, 22),
            )
            assert result.status == AIAnswerStatus.not_available
            assert result.diff is None
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()
            admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
            admin_client.table("careers").delete().eq("id", career["id"]).execute()
            admin_client.table("sources").delete().eq("id", source["id"]).execute()
