"""Live end-to-end tests for the publishing-console HTTP surface
(app/api/claims.py) — the same properties tests/db/test_maker_checker.py
already proves at the trigger level, now proven through the actual
running API a reviewer would call.

Skips (via tests/db/conftest.py's existing pattern) until
db/migrations/0003_maker_checker.sql is applied — every one of these
routes depends on that trigger existing.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app

client = TestClient(app)

TODAY = date.today()
DUE = (TODAY + timedelta(days=365)).isoformat()


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": "API TEST OFFICIAL SOURCE (claims)",
                "official_url": "https://example.invalid/claims-api-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


def _create_payload(source_id: str, **overrides: object) -> dict:
    payload = {
        "entity_type": "Pathway",
        "entity_id": "11111111-1111-1111-1111-111111111111",
        "field": "verified_charges",
        "value": 42000,
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": "test-fixture-reviewer",
        "review_due_date": DUE,
    }
    payload.update(overrides)
    return payload


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCreateClaim:
    def test_reviewer_can_create_a_draft(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        try:
            assert body["value"] == 42000
        finally:
            admin_client.table("claims").delete().eq("id", body["id"]).execute()

    def test_non_reviewer_cannot_create_a_claim(
        self, admin_client: Client, student_a: tuple[str, Client], official_source: str
    ) -> None:
        _student_id, student_client = student_a
        token = student_client.auth.get_session().access_token
        response = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        )
        assert response.status_code == 403

    def test_guest_cannot_create_a_claim(self, official_source: str) -> None:
        response = client.post("/claims", json=_create_payload(official_source))
        assert response.status_code == 401

    def test_literal_verifier_ai_is_rejected(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims",
            json=_create_payload(official_source, verifier="AI"),
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_invalid_extracted_by_is_rejected(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims",
            json=_create_payload(official_source, extracted_by="robot"),
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_nonexistent_source_gives_a_clean_404(
        self, reviewer: tuple[str, Client]
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims",
            json=_create_payload("00000000-0000-0000-0000-000000000000"),
            headers=_auth(token),
        )
        assert response.status_code == 404


class TestFullWorkflowThroughTheRealAPI:
    def test_two_distinct_reviewers_take_a_claim_from_draft_to_published(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        maker_token = maker_client.auth.get_session().access_token
        checker_token = checker_client.auth.get_session().access_token

        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(maker_token)
        )
        assert created.status_code == 201
        claim_id = created.json()["id"]

        try:
            submitted = client.post(f"/claims/{claim_id}/submit", headers=_auth(maker_token))
            assert submitted.status_code == 200
            assert submitted.json()["status"] == "in_review"

            approved = client.post(f"/claims/{claim_id}/approve", headers=_auth(checker_token))
            assert approved.status_code == 200
            body = approved.json()
            assert body["status"] == "published"
            assert body["reviewed_by"] == checker_id
            assert body["created_by"] == maker_id
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_author_cannot_approve_their_own_claim_through_the_api(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token

        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        )
        claim_id = created.json()["id"]
        try:
            client.post(f"/claims/{claim_id}/submit", headers=_auth(token))
            response = client.post(f"/claims/{claim_id}/approve", headers=_auth(token))
            assert response.status_code == 400
            assert "cannot approve their own" in response.json()["detail"].lower()
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_draft_cannot_skip_straight_to_published_through_the_api(
        self, reviewer: tuple[str, Client], official_source: str, admin_client: Client
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        )
        claim_id = created.json()["id"]
        try:
            # approve without submit first -- still in_review-required
            response = client.post(f"/claims/{claim_id}/approve", headers=_auth(token))
            assert response.status_code == 400
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_reject_sends_a_claim_back_to_draft(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        maker_token = maker_client.auth.get_session().access_token
        checker_token = checker_client.auth.get_session().access_token

        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(maker_token)
        )
        claim_id = created.json()["id"]
        try:
            client.post(f"/claims/{claim_id}/submit", headers=_auth(maker_token))
            rejected = client.post(f"/claims/{claim_id}/reject", headers=_auth(checker_token))
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "draft"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_correction_via_supersede_through_the_api(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        maker_token = maker_client.auth.get_session().access_token
        checker_token = checker_client.auth.get_session().access_token

        old = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(maker_token)
        ).json()
        client.post(f"/claims/{old['id']}/submit", headers=_auth(maker_token))
        client.post(f"/claims/{old['id']}/approve", headers=_auth(checker_token))

        new = client.post(
            "/claims",
            json=_create_payload(official_source, value=99000),
            headers=_auth(maker_token),
        ).json()

        try:
            superseded = client.post(
                f"/claims/{old['id']}/supersede",
                json={"new_claim_id": new["id"]},
                headers=_auth(checker_token),
            )
            assert superseded.status_code == 200
            body = superseded.json()
            assert body["status"] == "superseded"
            assert body["superseded_by"] == new["id"]
            assert body["value"] == 42000  # old claim's own value is untouched
        finally:
            admin_client.table("claims").delete().eq("id", new["id"]).execute()
            admin_client.table("claims").delete().eq("id", old["id"]).execute()


class TestListClaims:
    def test_reviewer_sees_drafts_by_default(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        ).json()
        try:
            response = client.get("/claims", headers=_auth(token))
            assert response.status_code == 200
            ids = {c["id"] for c in response.json()}
            assert created["id"] in ids
        finally:
            admin_client.table("claims").delete().eq("id", created["id"]).execute()

    def test_non_reviewer_sees_no_drafts(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        _student_id, student_client = student_a
        reviewer_token = reviewer_client.auth.get_session().access_token
        student_token = student_client.auth.get_session().access_token
        created = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(reviewer_token)
        ).json()
        try:
            response = client.get("/claims", headers=_auth(student_token))
            assert response.status_code == 200
            ids = {c["id"] for c in response.json()}
            assert created["id"] not in ids
        finally:
            admin_client.table("claims").delete().eq("id", created["id"]).execute()
