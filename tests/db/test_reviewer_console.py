"""Live end-to-end tests for the reviewer console (`app/web/
reviewer_pages.py`) — the first browser-usable UI on top of
`app/api/claims.py`'s publishing-console API, and the first place this
app has ever had a real, cookie-based browser session at all.

Same seeding pattern as tests/db/test_api_claims.py and
tests/db/test_maker_checker.py: claims are seeded directly via
`admin_client` (service-role, exempt from the `enforce_claims_workflow`
trigger) when a test needs a specific starting status, and via the
real reviewer/second_reviewer clients (going through the trigger for
real) when the test is about a state transition.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from app.web.reviewer_pages import COOKIE_NAME

client = TestClient(app)

TODAY = date.today()
DUE = (TODAY + timedelta(days=365)).isoformat()


@pytest.fixture
def official_source(admin_client: Client) -> Iterator[str]:
    """A real (non-synthetic) source — a synthetic-sourced claim can
    never be published at all (0001_init.sql's own trigger), which
    would make it useless for the approve-transitions-status test below.
    Same local-fixture pattern already used in test_api_claims.py and
    test_maker_checker.py (each file defines its own, per this
    codebase's established convention)."""
    row = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": "REVIEWER CONSOLE TEST OFFICIAL SOURCE",
                "official_url": "https://example.invalid/reviewer-console-test-source",
                "source_type": "official",
            }
        )
        .execute()
    )
    source_id = row.data[0]["id"]
    yield source_id
    admin_client.table("sources").delete().eq("id", source_id).execute()


@pytest.fixture
def reviewer_credentials(admin_client: Client) -> Iterator[dict[str, str]]:
    """A real, pre-confirmed reviewer with a KNOWN password — unlike
    conftest.py's `reviewer` fixture (random password, never exposed,
    fine for tests that only need an already-authenticated client), the
    sign-in tests below need to actually POST credentials through the
    HTML form."""
    email = f"bcion-reviewerconsole-{uuid.uuid4().hex[:12]}@example.com"
    # ux-qa-reviewer finding, 2026-09-21 (LOW, security-adjacent): this
    # used to be a fixed, hardcoded password, unlike every other
    # real-Supabase-Auth-user fixture in this suite (official_source
    # above and conftest.py's student_a/reviewer). Teardown runs on a
    # normal failure but not on a killed process/CI timeout, so a
    # predictable-password account could linger -- randomized the same
    # way, matching the existing convention. Held in-process only, to
    # POST it through the sign-in form below.
    password = uuid.uuid4().hex
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)  # cascades to the reviewers row


def _draft_payload(source_id: str, created_by: str, **overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "entity_type": "Pathway",
        "entity_id": str(uuid.uuid4()),
        "field": "verified_charges",
        "value": 77000,
        "source_id": source_id,
        "verification_date": TODAY.isoformat(),
        "verifier": "reviewer-console-test-fixture",
        "review_due_date": DUE,
        "status": "draft",
        "created_by": created_by,
    }
    payload.update(overrides)
    return payload


class TestReviewerSignIn:
    def test_valid_credentials_set_a_cookie_and_redirect_to_the_queue(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        response = client.post(
            "/reviewer/sign-in",
            data={
                "email": reviewer_credentials["email"],
                "password": reviewer_credentials["password"],
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/queue"
        assert COOKIE_NAME in response.cookies
        # A real access token, not a placeholder -- same sanity check
        # tests/db/test_api_auth.py already applies to the JSON route's
        # own access_token.
        assert len(response.cookies[COOKIE_NAME]) > 20

    def test_wrong_password_rerenders_the_form_with_an_error_and_sets_no_cookie(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        response = client.post(
            "/reviewer/sign-in",
            data={"email": reviewer_credentials["email"], "password": "definitely-wrong"},
        )
        assert response.status_code == 401
        # Same anti-enumeration wording as app/api/auth.py's sign_in --
        # never a distinguishable error for a bad email vs. bad password.
        assert "Invalid email or password" in response.text
        assert COOKIE_NAME not in response.cookies

    def test_nonexistent_email_gets_the_identical_error_no_enumeration_leak(self) -> None:
        response = client.post(
            "/reviewer/sign-in",
            data={"email": "definitely-not-registered@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.text
        assert COOKIE_NAME not in response.cookies


class TestReviewerQueueAuth:
    def test_queue_without_a_cookie_redirects_to_sign_in_not_a_401(self) -> None:
        """A human clicked/bookmarked a link -- must be a friendly
        redirect, not the JSON API's bare 401 (task requirement,
        matching app/web/pages.py's existing 'explain, don't error'
        pattern for a malformed /compare/view link)."""
        response = client.get("/reviewer/queue", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_queue_with_an_invalid_cookie_also_redirects_not_a_401(self) -> None:
        response = client.get(
            "/reviewer/queue",
            cookies={COOKIE_NAME: "not-a-real-token"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

    def test_queue_with_a_valid_reviewer_cookie_shows_a_seeded_draft_claim(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        claim = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id, value=91234))
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            assert claim["id"] in response.text  # in the row's form action URLs
            assert "91234" in response.text
            assert "Draft" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_non_reviewer_cookie_shows_an_empty_queue_not_an_error(
        self, admin_client: Client, reviewer: tuple[str, Client], student_a: tuple[str, Client]
    ) -> None:
        """Existing, intentional behaviour (RLS + list_claims' own
        docstring): a signed-in non-reviewer gets an empty queue, never
        an error that would reveal drafts exist at all. This route adds
        no separate reviewer-check of its own on top of that."""
        _reviewer_id, _reviewer_client = reviewer  # ensures at least one reviewer exists
        _student_id, student_client = student_a
        token = student_client.auth.get_session().access_token
        response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
        assert response.status_code == 200
        assert "Nothing waiting on review" in response.text


class TestReviewerApproveAction:
    def test_self_approval_redirects_to_the_queue_with_a_visible_error(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """UI-review finding, 2026-09-21 (HIGH, FIX 1): "a solo reviewer
        testing their own submitted draft (the first thing anyone would
        try) hits this via self-approval immediately" -- reproduced live
        here. Before the fix, the trigger's self-approval rejection
        (0003_maker_checker.sql's `enforce_claims_workflow`) surfaced as
        FastAPI's raw default JSON error body with no way back to the
        queue. It must now redirect (303) to /reviewer/queue with the
        trigger's own message carried as a visible error, and the claim
        must genuinely stay in_review, never published."""
        maker_id, maker_client = reviewer
        maker_token = maker_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()

        try:
            response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: maker_token},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"].startswith("/reviewer/queue?error=")

            # Following the redirect renders the error as a visible alert,
            # not a bare JSON body.
            follow_up = client.get(
                response.headers["location"], cookies={COOKIE_NAME: maker_token}
            )
            assert follow_up.status_code == 200
            assert "alert--error" in follow_up.text

            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_approve_button_actually_transitions_the_claim_to_published(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]
        # draft -> in_review, via the maker's own real client (any
        # reviewer may submit any draft, same rule claims.py's
        # submit_claim docstring states) -- exercises the real trigger,
        # not a service-role bypass.
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()

        try:
            response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: checker_token},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/reviewer/queue"

            # Verified independently via the admin (service-role) client
            # -- not just trusting the redirect happened.
            row = (
                admin_client.table("claims")
                .select("status, reviewed_by, created_by")
                .eq("id", claim_id)
                .execute()
                .data[0]
            )
            assert row["status"] == "published"
            assert row["reviewed_by"] == checker_id
            assert row["created_by"] == maker_id
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_non_reviewer_approve_redirects_to_the_queue_with_the_json_apis_own_error(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        official_source: str,
    ) -> None:
        """UI-review finding, 2026-09-21 (HIGH, FIX 1): the console used to
        let whatever HTTPException claims.py's approve_claim() raised
        (self-approval, an invalid workflow transition, or -- this exact
        case -- the 404 a non-reviewer's now-invisible-under-RLS row
        produces) surface as FastAPI's raw default JSON error body, with
        no way back to the queue. It now catches that exception and
        redirects (303) to /reviewer/queue with the same detail message
        carried as a query param, rendered there as a visible alert. This
        supersedes the previous version of this test, which asserted the
        console's raw status code matched the JSON API's and was
        deliberately never 303 -- that was correct for the old,
        unhandled-exception behaviour, but the whole point of the fix is
        that a failure now DOES redirect (303), just with the error made
        visible rather than silently dropped or (as before the fix) shown
        as a bare JSON body. What still must hold, and is asserted below:
        the JSON API's own detail text for this exact failure reaches the
        redirect target, and the claim itself is genuinely untouched --
        not that the two routes' status codes match byte-for-byte."""
        maker_id, maker_client = reviewer
        _student_id, student_client = student_a
        student_token = student_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()

        try:
            json_response = client.post(
                f"/claims/{claim_id}/approve",
                headers={"Authorization": f"Bearer {student_token}"},
            )
            assert json_response.status_code not in (200, 201)  # genuinely rejected
            detail = json_response.json()["detail"]

            console_response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: student_token},
                follow_redirects=False,
            )
            assert console_response.status_code == 303
            location = console_response.headers["location"]
            assert location.startswith("/reviewer/queue?error=")
            # The JSON API's own detail text for this exact failure reaches
            # the redirect target -- not a generic or blank message.
            assert quote(detail) in location

            # And the claim itself was genuinely never approved.
            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()
