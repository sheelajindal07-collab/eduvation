"""Integration tests for GET /ask and GET /ask/view against the real
database (UI-11 / BCI-014) — seeds via the service-role admin client,
reads through a guest's real, RLS-restricted anon client (no Authorization
header), the same convention `tests/db/test_api_explore_compare.py` and
`tests/db/test_web_pages.py` already use.

Neither route is registered on `app.main.app` yet — `app/main.py` is a
frozen, lead-only registry (see `app/api/ask.py`'s own module docstring
for the exact `RouterSlot` lines the lead needs to add) — so, like
`tests/unit/test_web_ask.py`, this module builds its own small
`FastAPI()` app wrapping both routers directly. Unlike that unit-test
module, NOTHING here fakes the database: `get_db_client`/
`_db_client_or_none` are left exactly as `app/api/ask.py`/
`app/web/ask_pages.py` wire them, so every request in this file really
hits the local Supabase stack (`tests/db/conftest.py`'s loopback-only
target guard) and is really subject to RLS — this file's whole point is
proving a DRAFT claim is genuinely invisible to a guest here, not merely
absent from a hand-built fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any, NoReturn

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from supabase import Client

import app.api.ask as ask_module
from app.ai.budget_db import identity_digest
from app.ai.schemas import AIAnswerStatus, AskRequest
from app.ai.schemas import Answer as AIAnswer
from app.api.ask import router as ask_json_router
from app.core.config import Settings
from app.db import get_anon_client
from app.web.ask_pages import router as ask_html_router
from app.web.guest_session import COOKIE_NAME as GUEST_SESSION_COOKIE_NAME
from tests.db.conftest import RUN_ID, _require_live, admit_student, run_name

_FALLBACK_COPY = "You can still compare routes and use the calculators."


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ask_json_router)
    app.include_router(ask_html_router)
    return app


client = TestClient(_make_app())


@pytest.fixture
def seeded_pathway(admin_client: Client, synthetic_source: str) -> Iterator[dict[str, Any]]:
    """A career + one pathway with:
    - a PUBLISHED `entry_requirements` claim (pathway_overview should show it)
    - a PUBLISHED `verified_charges` claim with a currency (cost_breakdown)
    - a PUBLISHED `minimum_age` claim (eligibility_gap)
    - a DRAFT `main_stages` claim on a SYNTHETIC source (must stay
      invisible to a guest -- both because it's a draft and because a
      synthetic source can never back a published claim at all)
    all cleaned up after.
    """
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Ask BCION test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Ask BCION test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_ask_view.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("ASK VIEW TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/ask-view-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    published_claims = (
        admin_client.table("claims")
        .insert(
            [
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "entry_requirements",
                    "value": "Class 12 pass with Physics, Chemistry, Biology",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "verified_charges",
                    "value": 85000,
                    "currency": "INR",
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": "minimum_age",
                    "value": 16,
                    "source_id": official_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                },
            ]
        )
        .execute()
        .data
    )
    draft_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway["id"],
                "field": "main_stages",
                "value": "should never be visible to a guest",
                "source_id": synthetic_source,
                "verification_date": "2026-01-01",
                "verifier": run_name("test-fixture"),
                "status": "draft",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )

    yield {
        "career": career,
        "pathway": pathway,
        "official_source": official_source,
        "published_claims": published_claims,
        "draft_claim": draft_claim,
    }

    claim_ids = [c["id"] for c in published_claims] + [draft_claim["id"]]
    admin_client.table("claims").delete().in_("id", claim_ids).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestAskJsonRouteAgainstTheRealStack:
    def test_guest_sees_the_published_pathway_overview_fact(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["entry_requirements"]["value"]["value"] == (
            "Class 12 pass with Physics, Chemistry, Biology"
        )
        assert fields_by_name["entry_requirements"]["value"]["source_url"] == (
            "https://example.invalid/ask-view-test-source"
        )

    def test_guest_never_sees_the_draft_synthetic_claim(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """RLS-level proof, not just this module's own defensive
        re-filter: a real guest anon client cannot even SELECT the draft
        row, so it can never reach `field_value_for` in the first place."""
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert "main_stages" not in fields_by_name
        assert "Main stages" in body["missing_information"]

    def test_cost_breakdown_shows_the_currency_safe_verified_charges(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "cost_breakdown", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["verified_charges"]["value"]["value"] == 85000
        assert fields_by_name["verified_charges"]["value"]["currency"] == "INR"
        assert fields_by_name["verified_charges"]["value"]["label"] == (
            "checked_against_official_source"
        )

    def test_eligibility_gap_shows_minimum_age_and_lists_the_rest_as_missing(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "eligibility_gap", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        fields_by_name = {c["field"]: c for c in body["fact_cards"]}
        assert fields_by_name["minimum_age"]["value"]["value"] == 16
        assert "Domicile" in body["missing_information"]

    def test_unknown_template_is_a_404_that_never_reflects_the_raw_id(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={
                "template": "not-a-real-template-abc123",
                "pathway_id": seeded_pathway["pathway"]["id"],
            },
        )
        assert response.status_code == 404
        assert "not-a-real-template-abc123" not in response.text

    def test_malformed_pathway_id_is_a_clean_422_not_a_500(self) -> None:
        response = client.get(
            "/ask", params={"template": "cost_breakdown", "pathway_id": "not-a-uuid"}
        )
        assert response.status_code == 422

    def test_ai_disabled_by_default_shows_the_fallback_message(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        body = response.json()
        assert body["ai_enabled"] is False
        assert body["show_fallback"] is True
        assert body["fallback_message"] == _FALLBACK_COPY


class TestAskViewPageAgainstTheRealStack:
    def test_every_entry_point_returns_200_with_fallback_copy_and_cited_records(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        """The three real `_ask.html` call sites -- cost_breakdown/
        pathway_overview (compare.html), eligibility_gap
        (requirements.html) -- each with pathway_id."""
        for template_id in ("cost_breakdown", "pathway_overview", "eligibility_gap"):
            response = client.get(
                "/ask/view",
                params={"template": template_id, "pathway_id": seeded_pathway["pathway"]["id"]},
            )
            assert response.status_code == 200, template_id
            assert _FALLBACK_COPY in response.text, template_id
            assert "https://example.invalid/ask-view-test-source" in response.text, template_id

    def test_guest_never_sees_the_draft_claim_on_the_rendered_page(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask/view",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert "should never be visible to a guest" not in response.text

    def test_unknown_template_is_a_friendly_404_page_not_a_500(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/ask/view",
            params={
                "template": "not-a-real-template-abc123",
                "pathway_id": seeded_pathway["pathway"]["id"],
            },
        )
        assert response.status_code == 404
        assert "not-a-real-template-abc123" not in response.text
        assert "Back to explore" in response.text

    def test_pathway_name_is_shown_for_context(self, seeded_pathway: dict[str, Any]) -> None:
        response = client.get(
            "/ask/view",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert seeded_pathway["pathway"]["name"] in response.text


# BCI-025 -- `next_steps`'s `plan_id` ownership check must be proven against
# the REAL, RLS-scoped `saved_plans` table, exactly like
# `tests/db/test_ask_next_steps.py`'s own `TestNextStepsByPlanId` proves it
# for the JSON route -- a hand-built fake db (tests/unit/test_web_ask.py's
# own `_FakeDbClient`) cannot stand in for real RLS here. `student_a`/
# `student_b` below are the same file-local override
# `tests/db/test_ask_next_steps.py` already establishes: CONSENT-4 (0012)
# means a real `saved_plans` write also needs `is_admitted(auth.uid())`.
@pytest.fixture
def student_a(student_a: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_a
    admit_student(admin_client, user_id)
    return user_id, client_


@pytest.fixture
def student_b(student_b: tuple[str, Client], admin_client: Client) -> tuple[str, Client]:
    user_id, client_ = student_b
    admit_student(admin_client, user_id)
    return user_id, client_


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _access_token(admin_client: Client, user_client: Client, user_id: str) -> str:
    """Mirrors `tests/db/test_ask_next_steps.py`'s own file-local helper of
    the same name -- `_create_test_user` (`tests/db/conftest.py`) already
    signed this client in; this just reads the token back off that
    session rather than signing in a second time."""
    session = user_client.auth.get_session()
    assert session is not None
    return session.access_token


def _save_plan(client_: Client, student_id: str, pathway_id: str) -> str:
    """Mirrors `tests/db/test_ask_next_steps.py`'s own file-local `_save_plan`
    -- a direct, RLS-scoped insert, not a round trip through `POST /plans`
    (this file already exercises `GET /ask/view` over HTTP; seeding via the
    SDK keeps that the one HTTP call under test)."""
    return (
        client_.table("saved_plans")
        .insert({"student_id": student_id, "pathway_id": pathway_id})
        .execute()
        .data[0]["id"]
    )


class TestAskViewNextStepsPlanIdOwnershipAgainstTheRealStack:
    """BCI-025 / AI-18: `plan_id` resolution on `/ask/view` mirrors
    `app.api.ask.ask()`'s own -- a guest's or another student's plan id
    must 404, never leak whose plan it is or which pathway it names."""

    def test_the_owning_student_s_plan_id_resolves_to_their_pathway(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        a_id, a_client = student_a
        token = _access_token(admin_client, a_client, a_id)
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])

        response = client.get(
            "/ask/view",
            params={"template": "next_steps", "plan_id": plan_id},
            headers=_auth(token),
        )
        assert response.status_code == 200
        assert seeded_pathway["pathway"]["name"] in response.text

    def test_a_guest_cannot_resolve_another_identity_s_plan_id(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
    ) -> None:
        """Proof: a plan id belonging to a different identity (a guest,
        here) 404s, matching `GET /ask`'s own behaviour exactly, and never
        reflects that identity's pathway back."""
        a_id, a_client = student_a
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])

        response = client.get("/ask/view", params={"template": "next_steps", "plan_id": plan_id})
        assert response.status_code == 404
        assert seeded_pathway["pathway"]["id"] not in response.text
        assert seeded_pathway["pathway"]["name"] not in response.text

    def test_student_b_cannot_resolve_student_a_s_plan_id(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        admin_client: Client,
    ) -> None:
        """Proof: a plan id belonging to a different identity (student A,
        here) 404s for student B, never leaking student A's pathway."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        plan_id = _save_plan(a_client, a_id, seeded_pathway["pathway"]["id"])
        b_token = _access_token(admin_client, b_client, b_id)

        response = client.get(
            "/ask/view",
            params={"template": "next_steps", "plan_id": plan_id},
            headers=_auth(b_token),
        )
        assert response.status_code == 404
        assert seeded_pathway["pathway"]["id"] not in response.text
        assert seeded_pathway["pathway"]["name"] not in response.text

    def test_a_nonexistent_plan_id_is_a_404_not_a_500(self) -> None:
        response = client.get(
            "/ask/view",
            params={
                "template": "next_steps",
                "plan_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == 404

    def test_a_malformed_plan_id_is_a_404_not_a_500(self) -> None:
        response = client.get(
            "/ask/view", params={"template": "next_steps", "plan_id": "not-a-uuid"}
        )
        assert response.status_code == 404


class TestAskViewWhatChangedClaimIdAgainstTheRealStack:
    """BCI-025 / AI-19: `claim_id` resolution on `/ask/view` bypasses
    `entity_kind_and_id` entirely, exactly like `app.api.ask.ask()`."""

    def test_claim_id_alone_resolves_to_a_200_answered_page(
        self, seeded_pathway: dict[str, Any]
    ) -> None:
        claim_id = seeded_pathway["published_claims"][0]["id"]
        response = client.get(
            "/ask/view", params={"template": "what_changed", "claim_id": claim_id}
        )
        assert response.status_code == 200
        assert "Back to explore" in response.text
        # AI disabled by default (pilot default, unset in this test
        # environment) -- what_changed's own ASK_TEMPLATES entry has
        # fields == () (no fact cards for this template regardless), and
        # what_changed_lines needs the AI layer, which is off.
        assert _FALLBACK_COPY in response.text

    def test_missing_claim_id_degrades_to_the_friendly_invalid_request_page(self) -> None:
        response = client.get("/ask/view", params={"template": "what_changed"})
        assert response.status_code == 200
        assert "Back to explore" in response.text

    def test_malformed_claim_id_degrades_to_the_friendly_invalid_request_page(self) -> None:
        response = client.get(
            "/ask/view", params={"template": "what_changed", "claim_id": "not-a-uuid"}
        )
        assert response.status_code == 200
        assert "Back to explore" in response.text


# =====================================================================
# BCI-026 -- the AI spend budget is per-identity and DATABASE-backed.
#
# Everything above this line proves the deterministic baseline. What is
# proved below is the thing AI-4/0011 was built for and nothing actually
# used until this card: a real request from a real, signed-in account
# reserves against `ai_usage` THROUGH THAT ACCOUNT'S OWN RLS-SCOPED
# CLIENT, leaving a real row behind — and another account's request never
# touches it.
#
# The ONLY fakes here are the AI provider and the pipeline body: nothing
# in this repo ever calls a real model, and `ai_pipeline.answer`'s own
# two-pass behaviour is already covered by tests/unit/test_ai_pipeline.py.
# The fake pipeline below calls `budget.reserve(today=...)` — the exact
# call the real one makes (`app/ai/pipeline.py` step 4) — so the
# reservation path under test is genuinely the real
# `AIRequestBudgetDB` -> `ai_reserve()` -> `ai_usage` one, over the wire,
# against the local stack.
# =====================================================================

_AI_MIGRATION_SKIP_REASON = (
    "db/migrations/0011_ai_usage.sql and/or 0015_ai_identity_binding.sql are not "
    "applied to this stack, so the database-backed AI budget cannot be exercised. "
    "Apply db/migrations/*.sql (db/migrations/README.md); a stale PostgREST schema "
    "cache looks identical and is reloaded by re-running the migrate step."
)


def _unavailable(reason: str) -> NoReturn:
    """Skip — or, under BCION_REQUIRE_LIVE=1, fail. Same rule
    `tests/db/test_ai_usage.py` uses: "green" must never mean "did not
    run"."""
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


class _FakeGeminiProvider:
    """Constructing this succeeds and makes no network call. `.generate()`
    is never reached — `ask_module.ai_pipeline.answer` is replaced
    wholesale in every test below."""

    def generate(self, prompt: str) -> str:  # pragma: no cover - never called
        raise AssertionError("must not be called -- ai_pipeline.answer is replaced")


def _ai_on_settings() -> Settings:
    """AI flags on, with a placeholder key so `Settings.ai_configured` is
    true. No real key, and no provider call is ever made."""
    return Settings(_env_file=None, ai_enabled=True, gemini_api_key="test-only-not-a-real-key")


@pytest.fixture
def ai_usage_rows(admin_client: Client) -> Iterator[list[str]]:
    """Identity hashes whose `ai_usage` rows this test wants removed
    afterwards — service role, teardown only (tests/db/conftest.py's
    contract for `admin_client`), never used to make an assertion about
    what a real user may do.

    Deleting them genuinely frees the budget they consumed: every cap in
    0011 is computed from the rows that exist right now.
    """
    hashes: list[str] = []
    yield hashes
    if hashes:
        admin_client.table("ai_usage").delete().in_("identity_hash", hashes).execute()


@pytest.fixture
def ai_enabled_with_a_reserving_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Turn the AI layer on for one test and replace the pipeline with a
    stand-in that makes exactly ONE real reservation against whatever
    budget the route resolved for the caller."""
    captured: dict[str, Any] = {}

    def _reserving_answer(
        db: Any, request: AskRequest, provider: Any, budget: Any, *, as_of: date | None = None
    ) -> AIAnswer:
        captured["budget"] = budget
        captured["request"] = request
        budget.reserve(today=as_of)
        return AIAnswer(status=AIAnswerStatus.not_available)

    settings = _ai_on_settings()
    monkeypatch.setattr(ask_module, "get_settings", lambda: settings)
    monkeypatch.setattr(ask_module, "GeminiProvider", _FakeGeminiProvider)
    monkeypatch.setattr(ask_module.ai_pipeline, "answer", _reserving_answer)
    return captured


@pytest.fixture(scope="module")
def ai_migrations_applied() -> None:
    """Deliberately NOT autouse: the deterministic UI-11/BCI-025 tests
    above must not start depending on 0011/0015. Only the BCI-026 class
    below requests it."""
    anon = get_anon_client()
    for marker in ("ai_usage_schema_version", "ai_identity_binding_schema_version"):
        try:
            anon.rpc(marker, {}).execute()
        except Exception:  # noqa: BLE001 — any error here means "not applied yet"
            _unavailable(_AI_MIGRATION_SKIP_REASON)


def _usage_rows_for(admin_client: Client, identity_hash: str) -> list[dict[str, Any]]:
    """Read the ledger with the service role. Teardown/inspection only —
    `ai_usage_select_own` deliberately lets NO caller read another
    identity's rows, which is exactly why an assertion about "B's request
    never touched A" has to be made from outside RLS."""
    result = (
        admin_client.table("ai_usage").select("*").eq("identity_hash", identity_hash).execute()
    )
    return list(result.data or [])


class TestAccountReservationsReallyReachAiUsage:
    """This card's own required proof: a real row exists after a real
    request, and a different account's identity is never touched by it."""

    @pytest.fixture(autouse=True)
    def _gate(self, ai_migrations_applied: None) -> None:
        return None

    def test_a_signed_in_student_s_request_writes_a_real_ai_usage_row(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        admin_client: Client,
        ai_usage_rows: list[str],
        ai_enabled_with_a_reserving_pipeline: dict[str, Any],
    ) -> None:
        a_id, a_client = student_a
        token = _access_token(admin_client, a_client, a_id)
        a_hash = identity_digest(a_id)
        ai_usage_rows.append(a_hash)
        assert _usage_rows_for(admin_client, a_hash) == []

        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
            headers=_auth(token),
        )

        assert response.status_code == 200
        # The deterministic baseline is untouched by any of this.
        fields_by_name = {c["field"]: c for c in response.json()["fact_cards"]}
        assert "entry_requirements" in fields_by_name

        rows = _usage_rows_for(admin_client, a_hash)
        assert len(rows) == 1, "exactly one reservation should have been written"
        row = rows[0]
        assert row["identity_kind"] == "account"
        assert row["template_id"] == "pathway_overview"
        assert row["calls_reserved"] == 1
        assert row["status"] == "reserved"
        # And no prompt/answer text anywhere in the ledger, ever (0011).
        assert "prompt" not in row
        assert "answer" not in row

        # The identity the route resolved really is the DB-backed one.
        budget = ai_enabled_with_a_reserving_pipeline["budget"]
        assert budget.inner.identity_kind == "account"
        assert budget.inner.identity_hash == a_hash

    def test_one_account_s_request_never_touches_another_account_s_identity(
        self,
        seeded_pathway: dict[str, Any],
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        admin_client: Client,
        ai_usage_rows: list[str],
        ai_enabled_with_a_reserving_pipeline: dict[str, Any],
    ) -> None:
        """CLAUDE.md: cross-user access is tested every time auth changes.
        Before this card there was ONE process-wide counter for everybody;
        this is the assertion that says that is over."""
        a_id, a_client = student_a
        b_id, b_client = student_b
        a_hash, b_hash = identity_digest(a_id), identity_digest(b_id)
        ai_usage_rows.extend([a_hash, b_hash])

        a_response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
            headers=_auth(_access_token(admin_client, a_client, a_id)),
        )
        assert a_response.status_code == 200
        assert len(_usage_rows_for(admin_client, a_hash)) == 1
        assert _usage_rows_for(admin_client, b_hash) == []

        b_response = client.get(
            "/ask",
            params={"template": "cost_breakdown", "pathway_id": seeded_pathway["pathway"]["id"]},
            headers=_auth(_access_token(admin_client, b_client, b_id)),
        )
        assert b_response.status_code == 200

        a_rows = _usage_rows_for(admin_client, a_hash)
        b_rows = _usage_rows_for(admin_client, b_hash)
        # B spent B's budget, not A's: A still has exactly the one row
        # from A's own request, and B's row carries B's own template.
        assert len(a_rows) == 1
        assert a_rows[0]["template_id"] == "pathway_overview"
        assert len(b_rows) == 1
        assert b_rows[0]["template_id"] == "cost_breakdown"
        assert a_rows[0]["id"] != b_rows[0]["id"]

    def test_a_guest_with_a_session_cookie_reserves_under_its_own_guest_identity(
        self,
        seeded_pathway: dict[str, Any],
        admin_client: Client,
        ai_usage_rows: list[str],
        ai_enabled_with_a_reserving_pipeline: dict[str, Any],
    ) -> None:
        """The guest half of the same wiring, against the real stack.

        The cookie value is an opaque token the route never validates —
        deliberately: `app/web/guest_session.py`'s `ensure_session`
        docstring says probing whether a token is live would turn every
        page load into a token oracle, and `ai_reserve` hashes whatever
        it is given for a guest (0015 leaves the guest path unbound,
        because possessing the token IS the credential). So a token
        string is exactly as much as this path ever has.
        """
        guest_token = f"bci026-guest-{RUN_ID}"
        guest_hash = identity_digest(guest_token)
        ai_usage_rows.append(guest_hash)
        guest_client = TestClient(_make_app())
        guest_client.cookies.set(GUEST_SESSION_COOKIE_NAME, guest_token)

        response = guest_client.get(
            "/ask",
            params={"template": "eligibility_gap", "pathway_id": seeded_pathway["pathway"]["id"]},
        )

        assert response.status_code == 200
        rows = _usage_rows_for(admin_client, guest_hash)
        assert len(rows) == 1
        assert rows[0]["identity_kind"] == "guest"
        assert rows[0]["template_id"] == "eligibility_gap"

    def test_a_session_less_guest_writes_no_ledger_row_at_all(
        self,
        seeded_pathway: dict[str, Any],
        admin_client: Client,
        ai_enabled_with_a_reserving_pipeline: dict[str, Any],
    ) -> None:
        """The documented judgment call, proved live: no bearer token and
        no cookie means the process-local in-memory budget, so nothing is
        minted and nothing is written — and, in particular, this GET
        route creates no `guest_sessions` row."""
        before = (
            admin_client.table("guest_sessions").select("id", count="exact").execute().count
        )

        response = client.get(
            "/ask",
            params={"template": "pathway_overview", "pathway_id": seeded_pathway["pathway"]["id"]},
        )

        assert response.status_code == 200
        assert "set-cookie" not in {key.lower() for key in response.headers}
        budget = ai_enabled_with_a_reserving_pipeline["budget"]
        assert budget is ask_module._ai_budget()
        after = (
            admin_client.table("guest_sessions").select("id", count="exact").execute().count
        )
        assert after == before
