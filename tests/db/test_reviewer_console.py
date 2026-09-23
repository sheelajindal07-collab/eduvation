"""Live end-to-end tests for the reviewer console (`app/web/reviewer/`)
— the first browser-usable UI on top of `app/api/claims.py`'s
publishing-console API, and the first place this app has ever had a
real, cookie-based browser session at all.

Same seeding pattern as tests/db/test_api_claims.py and
tests/db/test_maker_checker.py: claims are seeded directly via
`admin_client` (service-role, exempt from the `enforce_claims_workflow`
trigger) when a test needs a specific starting status, and via the
real reviewer/second_reviewer clients (going through the trigger for
real) when the test is about a state transition.

SEC-2: every action POST below now sends an `Origin` header, because the
console refuses a cookie-bearing state change that declares no origin at
all (`app/core/csrf.py`). That is not test scaffolding — it is what a
real browser sends, and `app/main.py`'s SEC-1 docstring predicted this
exact suite would need it. `TestReviewerCsrf` is the regression test for
the rule itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from supabase import Client

from app.core.config import Settings, get_settings
from app.core.csrf import CSRF_ERROR_CODE
from app.main import app
from app.web.reviewer import COOKIE_NAME
from app.web.reviewer.queue import QUEUE_ERROR_MESSAGES
from tests.db.conftest import run_email, run_name

client = TestClient(app)

TODAY = date.today()
DUE = (TODAY + timedelta(days=365)).isoformat()

# What a real browser puts on a form POST from this app's own pages.
# `testserver` is TestClient's default Host, so this is genuinely
# same-origin for every request in this file.
SAME_ORIGIN = {"Origin": "http://testserver"}
FOREIGN_ORIGIN = {"Origin": "https://attacker.example.com"}


def signed_out_client() -> TestClient:
    """A client with a genuinely empty cookie jar.

    The module-level `client` is shared by every test in this file and
    httpx persists any `Set-Cookie` it receives, so once ONE test signs
    in successfully, later requests through that client carry
    `bcion_reviewer_session` whether the test meant them to or not. That
    was invisible before SEC-2 (no route cared about a stray cookie) and
    is not any more: a cookie-bearing POST is CSRF-guarded, so a
    leftover session turned "sign in with a wrong password" into a 403
    instead of a 401.

    Every test below whose subject is "a browser that has NOT signed in
    yet" uses this instead — which is also the more faithful model of
    what it claims to be testing.
    """
    return TestClient(app)


def rendered(message: str) -> str:
    """A message as Jinja's autoescaping actually writes it into the
    page — `escape` is markupsafe's, the same function the template
    environment applies, so an apostrophe in the copy (`isn't`) does not
    quietly make a substring assertion unsatisfiable."""
    return str(escape(message))


@contextmanager
def strict_allowed_hosts() -> Iterator[None]:
    """Narrow `ALLOWED_HOSTS` to `testserver` for the duration of a test.

    The app under test boots with development settings, where
    `allowed_hosts_list` is the permissive `["*"]` and every declared
    origin therefore passes — so a cross-origin rejection cannot be
    demonstrated without a real allow-list. Overriding the settings
    dependency (which `require_same_origin` takes via `Depends`
    precisely so this is possible) narrows only the origin check: the
    routers, the session cookie handling and TrustedHostMiddleware all
    stay exactly as the real app builds them.
    """
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, allowed_hosts="testserver"
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


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
                "authority_name": run_name("REVIEWER CONSOLE TEST OFFICIAL SOURCE"),
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
    email = run_email("reviewerconsole", domain="example.com")
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
        "verifier": run_name("reviewer-console-test-fixture"),
        "review_due_date": DUE,
        "status": "draft",
        "created_by": created_by,
    }
    payload.update(overrides)
    return payload


def _row_html(page_text: str, claim_id: str) -> str:
    """SCOPE-13: the single `<section class="card">...</section>` block
    for one claim, isolated out of the full queue page. The queue lists
    every draft/in_review claim in the whole table, not just this test's
    own -- on a shared local stack, other tests (including this file's
    own duplicate-warning tests) or another concurrent session can have
    their own rows sitting in the same queue at the same moment,
    plausible for `has_published_duplicate` specifically since that is
    the exact condition these tests create and remove. Scoping an
    assertion to this row's own block means it can't be satisfied, or
    defeated, by some unrelated claim rendered elsewhere on the page.
    """
    marker = f"/reviewer/claims/{claim_id}/"
    marker_pos = page_text.index(marker)
    start = page_text.rfind('<section class="card">', 0, marker_pos)
    end = page_text.index("</section>", marker_pos)
    return page_text[start:end]


class TestReviewerSignIn:
    """Every test here posts through `signed_out_client()` — see that
    helper for why a shared cookie jar and SEC-2's CSRF guard do not
    mix. Deliberately no `Origin` header on any of them either: a
    sign-in that carries no session cookie must work with no origin
    declared at all, and these tests are where that is proven."""

    def test_valid_credentials_set_a_cookie_and_redirect_to_the_queue(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        response = signed_out_client().post(
            "/reviewer/sign-in",
            data={
                "email": reviewer_credentials["email"],
                "password": reviewer_credentials["password"],
            },
            follow_redirects=False,
        )
        if response.status_code == 429:
            # UI-review finding, 2026-09-21 (FIX 2): authenticate() now
            # propagates Supabase's own real rate-limit status instead of
            # flattening it to a generic 401 -- correct, but it means a
            # request-rate limit the full test suite's own combined
            # sign-in load genuinely triggers is no longer silently
            # masked as a 401. Same tolerance pattern
            # tests/db/test_api_auth.py's TestSignUp already uses for the
            # identical class of flakiness on the sign-up path.
            return
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
        response = signed_out_client().post(
            "/reviewer/sign-in",
            data={"email": reviewer_credentials["email"], "password": "definitely-wrong"},
        )
        if response.status_code == 429:
            # See test_valid_credentials_set_a_cookie_and_redirect_to_the_queue above.
            return
        assert response.status_code == 401
        # Same anti-enumeration wording as app/api/auth.py's sign_in --
        # never a distinguishable error for a bad email vs. bad password.
        assert "Invalid email or password" in response.text
        assert COOKIE_NAME not in response.cookies

    def test_nonexistent_email_gets_the_identical_error_no_enumeration_leak(self) -> None:
        response = signed_out_client().post(
            "/reviewer/sign-in",
            data={"email": "definitely-not-registered@example.com", "password": "whatever123"},
        )
        if response.status_code == 429:
            # See test_valid_credentials_set_a_cookie_and_redirect_to_the_queue above.
            return
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


class TestReviewerQueueMoneyMetadataColumns:
    """SCOPE-13: jurisdiction/academic_cycle/currency are on `ClaimOut`
    now (app/api/claims.py) and rendered as three explicit columns on the
    queue (app/web/templates/reviewer_queue.html) -- proved with a row
    that carries genuinely non-default values for all three, not just the
    'IN' default every claim already has."""

    def test_queue_shows_jurisdiction_cycle_and_currency_for_a_listed_claim(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        claim = (
            admin_client.table("claims")
            .insert(
                _draft_payload(
                    official_source,
                    reviewer_id,
                    jurisdiction="GB",
                    academic_cycle="2026-27",
                    currency="GBP",
                )
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            assert "GB" in response.text
            assert "2026-27" in response.text
            assert "GBP" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_queue_shows_not_available_for_a_claim_with_no_cycle_or_currency(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """A non-money, non-cycle-scoped claim genuinely has neither -- the
        columns must still render (never silently dropped, per this
        card's own non-negotiable), reading 'Not available' rather than a
        blank cell or a missing row."""
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        claim = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id, field="minimum_age", value=16))
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            assert "Jurisdiction" in response.text
            assert "Cycle" in response.text
            assert "Currency" in response.text
            assert response.text.count("Not available") >= 2  # cycle + currency
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()


class TestReviewerQueueDuplicateWarning:
    """SCOPE-13: a read-side-only warning against the existing `claims`
    table -- another PUBLISHED claim for the same entity_type+entity_id+
    field, no new migration. Both directions proved: present when a
    duplicate genuinely exists, absent when it doesn't."""

    def test_a_published_duplicate_shows_a_warning(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())
        draft = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id, entity_id=entity_id))
            .execute()
            .data[0]
        )
        published = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": entity_id,
                    "field": "verified_charges",
                    "value": 50000,
                    "currency": "INR",
                    "source_id": official_source,
                    "verification_date": TODAY.isoformat(),
                    "verifier": run_name("reviewer-console-test-fixture"),
                    "status": "published",
                    "review_due_date": DUE,
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            row = _row_html(response.text, draft["id"])
            assert "already published" in row.lower()
        finally:
            admin_client.table("claims").delete().eq("id", draft["id"]).execute()
            admin_client.table("claims").delete().eq("id", published["id"]).execute()

    def test_no_warning_when_no_published_duplicate_exists(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        claim = (
            admin_client.table("claims")
            .insert(_draft_payload(official_source, reviewer_id))
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            row = _row_html(response.text, claim["id"])
            assert "already published" not in row.lower()
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()

    def test_a_different_field_on_the_same_entity_does_not_trigger_the_warning(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The match is on the full (entity_type, entity_id, field) triple
        -- a published claim on a DIFFERENT field of the same entity must
        not be mistaken for a duplicate of this one."""
        reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        entity_id = str(uuid.uuid4())
        draft = (
            admin_client.table("claims")
            .insert(
                _draft_payload(
                    official_source, reviewer_id, entity_id=entity_id, field="minimum_age",
                    value=16,
                )
            )
            .execute()
            .data[0]
        )
        published = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": entity_id,
                    "field": "verified_charges",
                    "value": 50000,
                    "currency": "INR",
                    "source_id": official_source,
                    "verification_date": TODAY.isoformat(),
                    "verifier": run_name("reviewer-console-test-fixture"),
                    "status": "published",
                    "review_due_date": DUE,
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get("/reviewer/queue", cookies={COOKIE_NAME: token})
            assert response.status_code == 200
            row = _row_html(response.text, draft["id"])
            assert "already published" not in row.lower()
        finally:
            admin_client.table("claims").delete().eq("id", draft["id"]).execute()
            admin_client.table("claims").delete().eq("id", published["id"]).execute()


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
        failure carried as a visible error, and the claim must genuinely
        stay in_review, never published.

        SEC-2 changed what travels in the query string -- a fixed code,
        not the trigger's own prose -- so this now asserts the exact
        code AND that the code's own message is what the page renders."""
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
                headers=SAME_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/reviewer/queue?error=self_approval"

            # Following the redirect renders the error as a visible alert,
            # not a bare JSON body.
            follow_up = client.get(
                response.headers["location"], cookies={COOKIE_NAME: maker_token}
            )
            assert follow_up.status_code == 200
            assert "alert--error" in follow_up.text
            assert rendered(QUEUE_ERROR_MESSAGES["self_approval"]) in follow_up.text

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
                headers=SAME_ORIGIN,
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

    def test_non_reviewer_approve_redirects_to_the_queue_with_the_matching_error_code(
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
        redirects (303) to /reviewer/queue, rendering it there as a
        visible alert.

        SEC-2 deliberately narrowed what that redirect carries. This test
        used to assert the JSON API's own detail TEXT reached the
        redirect URL; it must not any more -- a free-text `?error=`
        parameter is exactly the reflected-content surface SEC-2 removed.
        What replaces it is stronger, not weaker: the failure is
        classified into the CODE that names it (`claim_not_found`, the
        404 an RLS-invisible row produces), and the page renders that
        code's own fixed message. The JSON API's behaviour is unchanged
        and is still asserted below, to prove the two paths still agree
        about WHICH failure this is -- just not about its wording.

        And, as before, the claim itself is genuinely untouched."""
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
            # The JSON API still relays its own detail, unchanged by
            # SEC-2 -- this route is Bearer-only and was never touched.
            assert detail == "Claim not found."

            console_response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: student_token},
                headers=SAME_ORIGIN,
                follow_redirects=False,
            )
            assert console_response.status_code == 303
            # A code naming the same failure -- and nothing else. The
            # query string carries no message, from claims.py or anyone.
            assert console_response.headers["location"] == "/reviewer/queue?error=claim_not_found"

            follow_up = client.get(
                console_response.headers["location"],
                cookies={COOKIE_NAME: student_token},
            )
            assert follow_up.status_code == 200
            assert rendered(QUEUE_ERROR_MESSAGES["claim_not_found"]) in follow_up.text

            # And the claim itself was genuinely never approved.
            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_two_reviewers_racing_the_same_claim_gets_an_actionable_message(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 8): the trigger's own
        message for this exact race ("A published claim cannot be edited
        in place or un-published; supersede it with a new claim
        instead.") tells the reviewer to use a Supersede feature that
        does not exist anywhere in this console. The console must now
        show a different, actionable message instead -- and must NOT
        relay the raw "supersede" instruction, which would point the
        reviewer at a button this UI doesn't have.
        """
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()
        # The checker approves it for real first, through the actual
        # console route -- in_review -> published.
        first_approve = client.post(
            f"/reviewer/claims/{claim_id}/approve",
            cookies={COOKIE_NAME: checker_token},
            headers=SAME_ORIGIN,
            follow_redirects=False,
        )
        assert first_approve.status_code == 303
        assert first_approve.headers["location"] == "/reviewer/queue"

        try:
            # A second, racing approve attempt on the now-published claim
            # (e.g. the checker's own stale queue tab, or a different
            # reviewer who loaded the queue a moment earlier) hits the
            # trigger's "already published" branch.
            response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: checker_token},
                headers=SAME_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 303
            location = response.headers["location"]
            # SEC-2: the code, not the trigger's prose. That the raw
            # "supersede" instruction cannot reach the URL is now
            # structural rather than a translation step -- asserted
            # anyway, because it is the guarantee FIX 8 bought.
            assert location == "/reviewer/queue?error=already_published"
            assert "supersede" not in location.lower()

            follow_up = client.get(location, cookies={COOKIE_NAME: checker_token})
            assert follow_up.status_code == 200
            assert "already published" in follow_up.text.lower()
            assert "supersede" not in follow_up.text.lower()

            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "published"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestReviewerSubmitAction:
    def test_submit_button_transitions_a_draft_to_in_review(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 11): only the
        approve action had a happy-path test -- submit had none at all."""
        maker_id, maker_client = reviewer
        maker_token = maker_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]

        try:
            response = client.post(
                f"/reviewer/claims/{claim_id}/submit",
                cookies={COOKIE_NAME: maker_token},
                headers=SAME_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/reviewer/queue"

            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestReviewerRejectAction:
    def test_reject_button_sends_an_in_review_claim_back_to_draft(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 11): only the
        approve action had a happy-path test -- reject had none at all."""
        maker_id, maker_client = reviewer
        maker_token = maker_client.auth.get_session().access_token

        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()

        try:
            response = client.post(
                f"/reviewer/claims/{claim_id}/reject",
                cookies={COOKIE_NAME: maker_token},
                headers=SAME_ORIGIN,
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/reviewer/queue"

            row = (
                admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
            )
            assert row["status"] == "draft"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestReviewerSignInFormRenders:
    def test_get_sign_in_renders_the_form(self) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 11): no test at all
        covered GET /reviewer/sign-in."""
        response = client.get("/reviewer/sign-in")
        assert response.status_code == 200
        assert "Reviewer sign-in" in response.text
        assert 'name="email"' in response.text
        assert 'name="password"' in response.text


class TestReviewerSignOut:
    def test_sign_out_clears_the_cookie_and_redirects_to_sign_in(self) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 11): no test at all
        covered POST /reviewer/sign-out. Asserts the cookie is genuinely
        cleared (an expired/zeroed Set-Cookie for the same name+path), not
        just that the redirect happens.

        Deliberately sends no `Origin` (SEC-2): sign-out is the one
        cookie-bearing POST in this console that does NOT carry the CSRF
        guard -- see that route's docstring for why -- and this test is
        the thing that would fail if somebody added it without deciding
        to."""
        response = client.post(
            "/reviewer/sign-out",
            cookies={COOKIE_NAME: "some-previous-session-token"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/sign-in"

        set_cookie = response.headers.get("set-cookie", "")
        assert f'{COOKIE_NAME}=""' in set_cookie
        assert "Max-Age=0" in set_cookie
        assert "Path=/reviewer" in set_cookie


class TestReviewerSignInCookieFlags:
    def test_sign_in_cookie_carries_the_expected_security_flags(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        """UI-review finding, 2026-09-21 (MEDIUM, FIX 11): the existing
        cookie-checking test only ever checked the cookie's name/length
        via httpx's cookie-jar abstraction, never httponly/samesite/path
        -- inspected here via the raw Set-Cookie header string, since the
        cookie jar drops those flags.

        SEC-2 required these flags to be VERIFIED UNCHANGED, not
        modified: SameSite=Lax stays the first CSRF defense and the
        origin check is the second, added alongside it. This test is
        that verification, and it is deliberately identical to its
        pre-SEC-2 form. (`Secure` is absent here because APP_ENV is
        `development` on this local stack -- the production half of that
        conditional is asserted in tests/unit/test_csrf.py's
        `TestSessionCookieFlagsUnchangedBySec2`.)"""
        response = signed_out_client().post(
            "/reviewer/sign-in",
            data={
                "email": reviewer_credentials["email"],
                "password": reviewer_credentials["password"],
            },
            follow_redirects=False,
        )
        if response.status_code == 429:
            # See TestReviewerSignIn.test_valid_credentials_set_a_cookie_
            # and_redirect_to_the_queue's identical comment (FIX 2).
            return
        assert response.status_code == 303
        set_cookie = response.headers.get("set-cookie", "")
        assert COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/reviewer" in set_cookie
        assert "Max-Age=" in set_cookie


class TestReviewerCsrf:
    """SEC-2's regression tests, against a real reviewer session and a
    real database.

    The assertion that matters in each rejection case is not the 403 --
    it is the row read back afterwards through the service-role client.
    A CSRF bug is "the claim got published", not "the status code was
    wrong", and a test that only checked the status code would still
    pass if the guard ran AFTER the transition.
    """

    def _in_review_claim(
        self, maker_client: Client, maker_id: str, official_source: str
    ) -> str:
        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id: str = created["id"]
        maker_client.table("claims").update({"status": "in_review"}).eq("id", claim_id).execute()
        return claim_id

    def _status(self, admin_client: Client, claim_id: str) -> str:
        row = admin_client.table("claims").select("status").eq("id", claim_id).execute().data[0]
        return str(row["status"])

    def test_cross_origin_approve_is_refused_and_the_claim_is_untouched(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """THE regression test. A forged cross-site POST that carries the
        reviewer's real session cookie must not publish the claim.

        The second half of the test is the control: the SAME request,
        same cookie, same claim, differing only in the `Origin` header,
        does publish it. Without that, a "403" could just as well mean
        the request was broken in some other way."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token
        claim_id = self._in_review_claim(maker_client, maker_id, official_source)

        try:
            with strict_allowed_hosts():
                forged = client.post(
                    f"/reviewer/claims/{claim_id}/approve",
                    cookies={COOKIE_NAME: checker_token},
                    headers=FOREIGN_ORIGIN,
                    follow_redirects=False,
                )
            assert forged.status_code == 403
            assert forged.json()["detail"]["code"] == CSRF_ERROR_CODE
            assert self._status(admin_client, claim_id) == "in_review"

            with strict_allowed_hosts():
                honest = client.post(
                    f"/reviewer/claims/{claim_id}/approve",
                    cookies={COOKIE_NAME: checker_token},
                    headers=SAME_ORIGIN,
                    follow_redirects=False,
                )
            assert honest.status_code == 303
            assert honest.headers["location"] == "/reviewer/queue"
            assert self._status(admin_client, claim_id) == "published"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_a_cookie_post_with_no_origin_and_no_referer_is_refused(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """Fail closed. Note there is no `strict_allowed_hosts()` here:
        the absent-header case is refused even under development's
        wildcard allow-list, because there is nothing to match."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token
        claim_id = self._in_review_claim(maker_client, maker_id, official_source)

        try:
            response = client.post(
                f"/reviewer/claims/{claim_id}/approve",
                cookies={COOKIE_NAME: checker_token},
                follow_redirects=False,
            )
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == CSRF_ERROR_CODE
            assert self._status(admin_client, claim_id) == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_a_matching_referer_works_when_origin_is_absent(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """The documented fallback, exercised live: a browser that omits
        `Origin` on a same-site form navigation still gets through."""
        maker_id, maker_client = reviewer
        _checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token
        claim_id = self._in_review_claim(maker_client, maker_id, official_source)

        try:
            with strict_allowed_hosts():
                response = client.post(
                    f"/reviewer/claims/{claim_id}/approve",
                    cookies={COOKIE_NAME: checker_token},
                    headers={"Referer": "http://testserver/reviewer/queue"},
                    follow_redirects=False,
                )
            assert response.status_code == 303
            assert response.headers["location"] == "/reviewer/queue"
            assert self._status(admin_client, claim_id) == "published"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_cross_origin_submit_and_reject_are_refused_too(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """Not just approve: a forged `submit` would push someone else's
        draft into the review queue, and a forged `reject` would pull a
        claim back out of it."""
        maker_id, maker_client = reviewer
        maker_token = maker_client.auth.get_session().access_token
        created = (
            maker_client.table("claims").insert(_draft_payload(official_source, maker_id)).execute()
        ).data[0]
        claim_id = created["id"]

        try:
            with strict_allowed_hosts():
                submitted = client.post(
                    f"/reviewer/claims/{claim_id}/submit",
                    cookies={COOKIE_NAME: maker_token},
                    headers=FOREIGN_ORIGIN,
                    follow_redirects=False,
                )
            assert submitted.status_code == 403
            assert self._status(admin_client, claim_id) == "draft"

            # Move it on legitimately, then try to forge the reverse.
            maker_client.table("claims").update({"status": "in_review"}).eq(
                "id", claim_id
            ).execute()
            with strict_allowed_hosts():
                rejected = client.post(
                    f"/reviewer/claims/{claim_id}/reject",
                    cookies={COOKIE_NAME: maker_token},
                    headers=FOREIGN_ORIGIN,
                    follow_redirects=False,
                )
            assert rejected.status_code == 403
            assert self._status(admin_client, claim_id) == "in_review"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()

    def test_sign_in_still_works_from_any_origin(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        """Don't CSRF-gate the login form. The browser posting it has no
        session cookie yet, so even an `Origin` that every action route
        would refuse -- under a strict allow-list, with no `Referer` to
        fall back on -- must still sign the reviewer in."""
        with strict_allowed_hosts():
            response = signed_out_client().post(
                "/reviewer/sign-in",
                data={
                    "email": reviewer_credentials["email"],
                    "password": reviewer_credentials["password"],
                },
                headers=FOREIGN_ORIGIN,
                follow_redirects=False,
            )
        if response.status_code == 429:
            # See TestReviewerSignIn's identical comment (FIX 2).
            return
        assert response.status_code == 303
        assert response.headers["location"] == "/reviewer/queue"
        assert COOKIE_NAME in response.cookies

    def test_an_already_signed_in_session_reposting_sign_in_is_gated(
        self, reviewer_credentials: dict[str, str]
    ) -> None:
        """The other half of that decision, and the reason the guard is
        attached to the sign-in route at all: once a session cookie
        exists, re-posting this form IS a cookie-bearing state change.

        Worth stating because it is the one way SEC-2 could inconvenience
        a real reviewer: a client that sends no `Origin` and still holds
        a session cookie cannot sign in again. The escape hatch is real
        and needs no support call -- `POST /reviewer/sign-out` is
        deliberately not guarded, and `_redirect_to_sign_in` clears the
        cookie on every expired-session bounce, so the cookie-free state
        this test's sibling covers is always reachable."""
        with strict_allowed_hosts():
            response = client.post(
                "/reviewer/sign-in",
                data={
                    "email": reviewer_credentials["email"],
                    "password": reviewer_credentials["password"],
                },
                cookies={COOKIE_NAME: "a-previous-session-token"},
                headers=FOREIGN_ORIGIN,
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == CSRF_ERROR_CODE

    def test_the_bearer_json_api_is_completely_unaffected(
        self,
        admin_client: Client,
        reviewer: tuple[str, Client],
        second_reviewer: tuple[str, Client],
        official_source: str,
    ) -> None:
        """docs/CONTRACTS.md: "the JSON API is Bearer-only; cookies
        belong to the web layer alone". `POST /claims/{id}/approve` sends
        no cookie, carries no origin-check dependency, and must keep
        working with an `Origin` that the console would have refused."""
        maker_id, maker_client = reviewer
        checker_id, checker_client = second_reviewer
        checker_token = checker_client.auth.get_session().access_token
        claim_id = self._in_review_claim(maker_client, maker_id, official_source)

        try:
            with strict_allowed_hosts():
                response = client.post(
                    f"/claims/{claim_id}/approve",
                    headers={
                        "Authorization": f"Bearer {checker_token}",
                        **FOREIGN_ORIGIN,
                    },
                )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "published"
            assert response.json()["reviewed_by"] == checker_id
            assert self._status(admin_client, claim_id) == "published"
        finally:
            admin_client.table("claims").delete().eq("id", claim_id).execute()


class TestReviewerQueueErrorCodes:
    """SEC-2's other half, live: `?error=` is a code looked up in a fixed
    dict, so nothing a stranger writes into that parameter can appear on
    an authenticated page."""

    def test_an_arbitrary_error_parameter_is_never_reflected(
        self, reviewer: tuple[str, Client]
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        hostile = "<script>alert(1)</script>"

        signed_out = signed_out_client().get(
            "/reviewer/queue", params={"error": hostile}, follow_redirects=False
        )
        assert signed_out.status_code == 303  # no session -> sign-in, as always

        response = client.get(
            "/reviewer/queue", params={"error": hostile}, cookies={COOKIE_NAME: token}
        )
        assert response.status_code == 200
        # Neither raw nor merely HTML-escaped: the string never reaches
        # the template at all, so no form of it is in the page.
        assert hostile not in response.text
        assert rendered(hostile) not in response.text
        assert "alert(1)" not in response.text
        # What a reviewer sees instead.
        assert rendered(QUEUE_ERROR_MESSAGES["unknown_error"]) in response.text

    def test_a_phishing_sentence_is_replaced_by_the_generic_message(
        self, reviewer: tuple[str, Client]
    ) -> None:
        """The realistic version of the same attack: no markup at all,
        just believable text in a link sent to a reviewer."""
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token
        hostile = "Your session expired. Call BCION support on 000-000-0000 to restore it."

        response = client.get(
            "/reviewer/queue", params={"error": hostile}, cookies={COOKIE_NAME: token}
        )
        assert response.status_code == 200
        assert "000-000-0000" not in response.text
        assert rendered(QUEUE_ERROR_MESSAGES["unknown_error"]) in response.text

    def test_a_known_code_renders_its_own_fixed_message(
        self, reviewer: tuple[str, Client]
    ) -> None:
        _reviewer_id, reviewer_client = reviewer
        token = reviewer_client.auth.get_session().access_token

        response = client.get(
            "/reviewer/queue", params={"error": "db_unavailable"}, cookies={COOKIE_NAME: token}
        )
        assert response.status_code == 200
        assert rendered(QUEUE_ERROR_MESSAGES["db_unavailable"]) in response.text
        assert "alert--error" in response.text
