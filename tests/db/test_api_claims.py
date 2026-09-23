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
from tests.db.conftest import run_name

client = TestClient(app)

TODAY = date.today()
DUE = (TODAY + timedelta(days=365)).isoformat()


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("API TEST OFFICIAL SOURCE (claims)"),
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
        "verifier": run_name("test-fixture-reviewer"),
        "review_due_date": DUE,
        # SCOPE-13: "verified_charges" is a money field -- every existing
        # test in this file that doesn't care about currency needs a
        # valid one here now, or the new validator's own 422 would fail
        # every one of them for an unrelated reason.
        "currency": "INR",
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
        # SCOPE-13: jurisdiction/academic_cycle/currency now round-trip on
        # ClaimOut -- jurisdiction defaults 'IN' at the DB layer even
        # though this payload never sets it; currency is exactly what the
        # request sent; academic_cycle is genuinely absent here.
        assert body["jurisdiction"] == "IN"
        assert body["academic_cycle"] is None
        assert body["currency"] == "INR"
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


class TestCurrencyValidation:
    """SCOPE-13: currency required on money fields, forbidden on every
    other field -- enforced by `app/api/claims.py`'s own pydantic
    validator on `CreateClaimRequest`, not a form/template-only check, so
    every case here is a clean 422 (pydantic's own shape), never a raw
    Postgres error and never a 201 that silently wrote a bad row."""

    def test_a_money_field_with_no_currency_is_rejected(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims",
            json=_create_payload(official_source, currency=None),
            headers=_auth(token),
        )
        assert response.status_code == 422
        # Nothing was written -- a 422 must mean no row, not a bad one.
        rows = (
            admin_client.table("claims")
            .select("id")
            .eq("entity_id", "11111111-1111-1111-1111-111111111111")
            .eq("field", "verified_charges")
            .execute()
            .data
        )
        assert rows == []

    def test_a_fee_component_field_with_no_currency_is_also_rejected(
        self, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """The `fee_component:<name>` prefix convention (RULES-10) counts
        as a money field too, not just the three fixed scalar names."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims",
            json=_create_payload(
                official_source, field="fee_component:tuition", currency=None
            ),
            headers=_auth(token),
        )
        assert response.status_code == 422

    def test_a_non_money_field_with_a_currency_is_rejected(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        """`minimum_age` is a real, existing eligibility field
        (`app/ai/retrieval.py`'s `GENERIC_ELIGIBILITY_FIELDS`) that carries
        no money at all -- a currency on it is not a harmless extra, it is
        a claim about a fact that has no currency to state."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = "22222222-2222-2222-2222-222222222222"
        response = client.post(
            "/claims",
            json=_create_payload(
                official_source, entity_id=entity_id, field="minimum_age", value=16
            ),
            headers=_auth(token),
        )
        assert response.status_code == 422
        rows = (
            admin_client.table("claims").select("id").eq("entity_id", entity_id).execute().data
        )
        assert rows == []

    def test_a_non_money_field_with_no_currency_still_succeeds(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = "33333333-3333-3333-3333-333333333333"
        response = client.post(
            "/claims",
            json=_create_payload(
                official_source,
                entity_id=entity_id,
                field="minimum_age",
                value=16,
                currency=None,
            ),
            headers=_auth(token),
        )
        assert response.status_code == 201
        admin_client.table("claims").delete().eq("id", response.json()["id"]).execute()

    def test_a_money_field_with_a_valid_currency_still_succeeds(
        self, admin_client: Client, reviewer: tuple[str, Client], official_source: str
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        response = client.post(
            "/claims", json=_create_payload(official_source), headers=_auth(token)
        )
        assert response.status_code == 201
        body = response.json()
        assert body["currency"] == "INR"
        admin_client.table("claims").delete().eq("id", body["id"]).execute()


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
            # old["id"]'s superseded_by references new["id"] -- must
            # delete the referencing row first, or the FK constraint
            # blocks deleting the still-referenced replacement (Postgres
            # default: NO ACTION, not CASCADE). Same bug, same fix, as
            # tests/db/test_maker_checker.py's equivalent test.
            admin_client.table("claims").delete().eq("id", old["id"]).execute()
            admin_client.table("claims").delete().eq("id", new["id"]).execute()


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
