"""Integration tests for GET/POST /reviewer/extract and POST
/reviewer/extract/claims against the real database (AI-14, BCI-016).

Neither route is registered on `app.main.app` yet -- `app/main.py` and
`app/web/reviewer/__init__.py` are both frozen/forbidden to this card
(see `app/web/reviewer/extract.py`'s own module docstring for the exact
lines the lead needs to add) -- so, like `tests/db/test_ask_view.py`,
this module builds its own small `FastAPI()` app wrapping the router
directly. `Client`/RLS/the real `is_reviewer()` function are all exactly
what `app/web/reviewer/extract.py` wires them to -- nothing here fakes
the database, the same "this file's whole point is proving it live"
reasoning `test_ask_view.py`'s own module docstring gives.

This file never sets `GEMINI_API_KEY`/`AI_ENABLED` -- `settings.
ai_configured` is `False` on this stack exactly as it is in every other
test run in this repo, so every AI-gated path below degrades to the
existing "AI unavailable" fallback without ever calling a live provider.
`app/ai/extraction.py`'s own two-pass pipeline is covered by
`tests/unit/test_ai_extraction.py`'s `MockAIProvider`-based suite
instead — this file only proves the parts that need a real database:
reviewer gating, the source picker, and the create-claim path (which has
no AI dependency at all: it is a plain form -> `create_claim()` call).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from supabase import Client

from app.web.reviewer import COOKIE_NAME
from app.web.reviewer.extract import router as extract_router
from tests.db.conftest import run_name

# What a real browser puts on a form POST from this app's own pages —
# identical convention to tests/db/test_reviewer_console.py's own
# SAME_ORIGIN constant.
SAME_ORIGIN = {"Origin": "http://testserver"}

TODAY = date.today()
DUE = (TODAY + timedelta(days=365)).isoformat()


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(extract_router)
    return app


client = TestClient(_make_app())


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    """A real (non-synthetic) source — same local-fixture pattern
    `tests/db/test_reviewer_console.py`'s own `official_source` fixture
    already uses (each file defines its own, per this codebase's
    established convention)."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("AI EXTRACTION TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/ai-extraction-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id: str = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _create_claim_payload(entity_id: str, source_id: str, **overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "entity_type": "Pathway",
        "entity_id": entity_id,
        "field": "minimum_age",
        "value": "16",
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": run_name("ai-extraction-console-test"),
        "review_due_date": DUE,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------
# Reviewer gating — stricter than /reviewer/queue's redirect/empty-queue
# pattern (see app/web/reviewer/extract.py's own module docstring).
# ---------------------------------------------------------------------


class TestReviewerExtractAuth:
    def test_guest_with_no_cookie_gets_404(self) -> None:
        response = client.get("/reviewer/extract")
        assert response.status_code == 404

    def test_invalid_cookie_also_gets_404(self) -> None:
        response = client.get("/reviewer/extract", cookies={COOKIE_NAME: "not-a-real-token"})
        assert response.status_code == 404

    def test_signed_in_non_reviewer_gets_403(self, student_a: tuple[str, Client]) -> None:
        _student_id, student_client = student_a
        token = student_client.auth.get_session().access_token
        response = client.get("/reviewer/extract", cookies={COOKIE_NAME: token})
        assert response.status_code == 403

    def test_signed_in_reviewer_can_load_the_page_with_the_source_picker(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.get("/reviewer/extract", cookies={COOKIE_NAME: token})
        assert response.status_code == 200
        assert 'name="pasted_text"' in response.text
        assert 'name="source_id"' in response.text
        assert 'name="entity_type"' in response.text
        assert 'name="entity_id"' in response.text
        assert official_source in response.text  # the picker lists it as an <option>

    def test_guest_post_to_extract_gets_404(self, official_source: str) -> None:
        response = client.post(
            "/reviewer/extract",
            headers=SAME_ORIGIN,
            data={
                "pasted_text": "The minimum age for admission is 16 years.",
                "source_id": official_source,
                "entity_type": "Pathway",
                "entity_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 404

    def test_non_reviewer_post_to_extract_gets_403(
        self, student_a: tuple[str, Client], official_source: str
    ) -> None:
        _student_id, student_client = student_a
        token = student_client.auth.get_session().access_token
        response = client.post(
            "/reviewer/extract",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data={
                "pasted_text": "The minimum age for admission is 16 years.",
                "source_id": official_source,
                "entity_type": "Pathway",
                "entity_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 403

    def test_guest_cannot_reach_the_create_claim_route(self, official_source: str) -> None:
        response = client.post(
            "/reviewer/extract/claims",
            headers=SAME_ORIGIN,
            data=_create_claim_payload(str(uuid.uuid4()), official_source),
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------
# AI-off degrade — this stack never sets GEMINI_API_KEY, so every POST
# /reviewer/extract below must degrade gracefully and create nothing.
# ---------------------------------------------------------------------


class TestReviewerExtractRunWithAiUnavailable:
    def test_post_with_ai_unavailable_shows_a_friendly_message_and_writes_nothing(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data={
                "pasted_text": "The minimum age for admission is 16 years.",
                "source_id": official_source,
                "entity_type": "Pathway",
                "entity_id": entity_id,
            },
        )
        assert response.status_code == 200
        assert "not available" in response.text.lower()

        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []


class TestReviewerExtractCsrf:
    def test_post_to_extract_without_origin_or_referer_is_refused(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/reviewer/extract",
            cookies={COOKIE_NAME: token},
            data={
                "pasted_text": "x",
                "source_id": official_source,
                "entity_type": "Pathway",
                "entity_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 403

    def test_post_to_create_claim_without_origin_or_referer_is_refused(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())
        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            data=_create_claim_payload(entity_id, official_source),
        )
        assert response.status_code == 403
        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []


# ---------------------------------------------------------------------
# The create-claim route — no AI dependency at all, so this is fully
# exercisable live even with AI off. Proves: the existing POST /claims
# write path (create_claim) is genuinely reused, extracted_by is always
# "ai" regardless of what the form tries to send, status always defaults
# to draft, and ordinary CreateClaimRequest validation still applies.
# ---------------------------------------------------------------------


class TestReviewerExtractCreateClaim:
    def test_submitting_a_prefilled_form_creates_an_ai_extracted_draft_claim(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data=_create_claim_payload(entity_id, official_source),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/queue"

        try:
            rows = (
                admin_client.table("claims")
                .select("*")
                .eq("entity_id", entity_id)
                .execute()
                .data
            )
            assert len(rows) == 1
            row = rows[0]
            assert row["status"] == "draft"
            assert row["extracted_by"] == "ai"
            assert row["field"] == "minimum_age"
            assert str(row["value"]) == "16"
            assert row["source_id"] == official_source
        finally:
            admin_client.table("claims").delete().eq("entity_id", entity_id).execute()

    def test_extracted_by_and_status_cannot_be_overridden_by_the_form(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """The route declares no `extracted_by`/`status` form parameters at
        all, so even a hand-crafted POST that includes them has no effect
        -- `extracted_by` is always forced to `"ai"` in code, and `status`
        is always left to `create_claim`'s own `draft` default."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data=_create_claim_payload(
                entity_id, official_source, extracted_by="human", status="published"
            ),
            follow_redirects=False,
        )
        assert response.status_code == 303

        try:
            row = (
                admin_client.table("claims")
                .select("*")
                .eq("entity_id", entity_id)
                .execute()
                .data[0]
            )
            assert row["extracted_by"] == "ai"
            assert row["status"] == "draft"
        finally:
            admin_client.table("claims").delete().eq("entity_id", entity_id).execute()

    def test_verifier_literal_ai_is_refused_and_creates_nothing(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data=_create_claim_payload(entity_id, official_source, verifier="ai"),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/extract?error=invalid_input"

        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []

    def test_nonexistent_source_id_is_refused_with_a_friendly_redirect(
        self, admin_client: Client, reviewer: tuple[str, Client]
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data=_create_claim_payload(entity_id, str(uuid.uuid4())),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/extract?error=source_not_found"

        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []

    def test_non_reviewer_cannot_create_a_claim_via_this_route(
        self, admin_client: Client, student_a: tuple[str, Client], official_source: str
    ) -> None:
        _student_id, student_client = student_a
        token = student_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())

        response = client.post(
            "/reviewer/extract/claims",
            cookies={COOKIE_NAME: token},
            headers=SAME_ORIGIN,
            data=_create_claim_payload(entity_id, official_source),
        )
        assert response.status_code == 403

        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []


# ---------------------------------------------------------------------
# Completion-report proof: a direct attempt to publish an
# extracted_by="ai" draft (bypassing the reviewer console/this card's
# code entirely) is refused by the EXISTING database rule
# (db/migrations/0003_maker_checker.sql's enforce_claims_workflow), not
# by anything app/web/reviewer/extract.py or app/ai/extraction.py adds.
# This test never imports either module and never goes through the
# console's routes at all -- it inserts straight through a real
# reviewer's own RLS-scoped client, exactly the shape a hand-crafted
# request bypassing this whole UI would take.
# ---------------------------------------------------------------------


class TestDirectPublishBypassRefusedByTheDatabase:
    def test_ai_extracted_claim_cannot_be_inserted_as_published_directly(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        entity_id = str(uuid.uuid4())
        payload = {
            "entity_type": "Pathway",
            "entity_id": entity_id,
            "field": "minimum_age",
            "value": 16,
            "source_id": official_source,
            "verification_date": TODAY.isoformat(),
            "verifier": run_name("direct-publish-bypass-test"),
            "review_due_date": DUE,
            "status": "published",  # attempting to skip draft/in_review entirely
            "created_by": reviewer_id,
            "extracted_by": "ai",
        }

        with pytest.raises(APIError) as excinfo:
            reviewer_client.table("claims").insert(payload).execute()
        assert "must be inserted as draft" in str(excinfo.value)

        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []
