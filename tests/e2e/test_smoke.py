"""Real-browser smoke tests (`make test-e2e`).

Deliberately small -- this is NOT a second copy of tests/db/'s
correctness coverage (test_web_pages.py, test_reviewer_console.py
already assert every field/trust-label/access-control detail at the
HTTP-request level, thoroughly). This file's only job is proving the
pages actually render and the zero-JS flows actually work end to end in
a REAL browser against a REAL running server (tests/e2e/conftest.py's
`live_server` fixture) -- something nothing else in this suite does,
since `fastapi.testclient.TestClient` never opens a real socket or runs
a real browser.

Every assertion below is on rendered page content via a Playwright
locator or visible text, never just an HTTP status code -- a passing
TestClient status check would not prove any of this.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_email, run_name


@pytest.fixture
def two_seeded_pathways(admin_client: Client) -> Iterator[dict[str, Any]]:
    """Same seeding shape as tests/db/test_web_pages.py's `two_pathways`
    fixture -- a career with two pathways. No claims needed here: the
    claim-driven trust-labelling on /compare/view already has thorough
    live coverage in tests/db/test_web_pages.py; this directory's job is
    proving the zero-JS explore -> compare journey works in a real
    browser, not re-proving field-level correctness."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("E2E smoke test career")})
        .execute()
        .data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E smoke test pathway A"),
                "description": "Seeded by tests/e2e/test_smoke.py",
            }
        )
        .execute()
        .data[0]
    )
    pathway_b = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E smoke test pathway B"),
                "description": "Seeded by tests/e2e/test_smoke.py",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway_a": pathway_a, "pathway_b": pathway_b}
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


@pytest.fixture
def reviewer_credentials(admin_client: Client) -> Iterator[dict[str, str]]:
    """Same pattern as tests/db/test_reviewer_console.py's fixture of the
    same name -- a real, pre-confirmed reviewer with a KNOWN, randomly
    generated password (unlike tests/db/conftest.py's `reviewer` fixture,
    whose password is never exposed). Needed here because the sign-in
    test below POSTs credentials through the real HTML form, not an API
    token."""
    # QA-3: moved off @example.com to @example.invalid, matching every
    # other real-user fixture in this suite (tests/db/conftest.py's
    # `_create_test_user`) -- RFC 2606 reserves .invalid specifically so
    # a domain like this can never resolve or accept real mail, unlike
    # .com, which merely happens to be unregistered today.
    email = run_email("e2e")
    password = uuid.uuid4().hex
    created = admin_client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    user_id = created.user.id
    admin_client.table("reviewers").insert({"user_id": user_id}).execute()
    yield {"email": email, "password": password, "user_id": user_id}
    admin_client.auth.admin.delete_user(user_id)  # cascades to the reviewers row


@pytest.fixture
def seeded_draft_claim(
    admin_client: Client, synthetic_source: str, reviewer_credentials: dict[str, str]
) -> Iterator[dict[str, Any]]:
    """A draft claim, created by the seeded reviewer, for the queue-
    content assertion below. `synthetic_source` (not an official one) is
    fine here -- this test only checks the claim appears in the queue
    listing, it never approves/publishes it (0001_init.sql's own trigger
    forbids publishing a synthetic-sourced claim; see tests/db/
    test_reviewer_console.py's `official_source` fixture docstring for
    the tests that DO exercise that transition)."""
    claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": str(uuid.uuid4()),
                "field": "verified_charges",
                "value": 424242,
                "source_id": synthetic_source,
                "verification_date": "2026-09-01",
                "verifier": run_name("e2e-smoke-test-fixture"),
                "review_due_date": "2099-01-01",
                "status": "draft",
                "created_by": reviewer_credentials["user_id"],
            }
        )
        .execute()
        .data[0]
    )
    yield claim
    admin_client.table("claims").delete().eq("id", claim["id"]).execute()


class TestExploreAndCompareJourney:
    def test_explore_loads_and_shows_a_seeded_pathway(
        self, page: Page, live_server: str, two_seeded_pathways: dict[str, Any]
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{live_server}/explore")

        expect(page.locator("h1")).to_have_text("Explore")
        # exact=True: each pathway card also carries a "See requirements
        # for <name>" link (app/web/templates/explore.html) whose text
        # contains the pathway name as a substring -- a non-exact match
        # is ambiguous between the two.
        expect(
            page.get_by_text(two_seeded_pathways["pathway_a"]["name"], exact=True)
        ).to_be_visible()
        expect(
            page.get_by_text(two_seeded_pathways["pathway_b"]["name"], exact=True)
        ).to_be_visible()
        assert page_errors == []

    def test_selecting_two_pathways_and_submitting_reaches_compare_view(
        self, page: Page, live_server: str, two_seeded_pathways: dict[str, Any]
    ) -> None:
        """The zero-JS journey app/web/templates/explore.html describes:
        plain checkboxes in a plain `<form method="get">`, no script
        required to select pathways and submit -- the inline `<script>`
        on that page is progressive enhancement only (a live selection
        counter/cap), not the mechanism itself."""
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{live_server}/explore")
        page.locator(f'input[value="{two_seeded_pathways["pathway_a"]["id"]}"]').check()
        page.locator(f'input[value="{two_seeded_pathways["pathway_b"]["id"]}"]').check()
        page.get_by_role("button", name="Compare selected pathways").click()

        page.wait_for_url("**/compare/view*")
        expect(page.locator("h1")).to_have_text("Compare")
        expect(
            page.get_by_role("heading", name=two_seeded_pathways["pathway_a"]["name"])
        ).to_be_visible()
        expect(
            page.get_by_role("heading", name=two_seeded_pathways["pathway_b"]["name"])
        ).to_be_visible()
        expect(
            page.get_by_text("Which option would you like to investigate further?")
        ).to_be_visible()
        assert page_errors == []


@pytest.fixture
def eligibility_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A career + pathway with one published minimum_age=17 claim on a
    real official source -- mirrors tests/db/test_api_eligibility.py's
    fixture of the same name, kept minimal since this suite's job is
    proving the page renders in a real browser, not re-proving every
    criterion/outcome combination (already thorough at the HTTP level
    in tests/db/test_web_pages.py's TestRequirementsPage)."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("E2E TEST ELIGIBILITY SOURCE (fixture)"),
                "official_url": "https://example.invalid/e2e-eligibility-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("E2E eligibility test career")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E eligibility test pathway"),
                "description": "Seeded by tests/e2e/test_smoke.py",
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
                "value": "17",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("e2e-smoke-test-fixture"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    yield {"career": career, "pathway": pathway, "claim": claim}
    admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestRequirementsAndTimelineJourney:
    """/requirements/view and /timeline/view landed after this suite's
    first version (which correctly skipped them -- see git history for
    that commit's reasoning). Un-skipped and filled in now that both
    routes are real (app/web/pages.py's requirements_page/timeline_page).
    """

    def test_requirements_view_loads_and_shows_the_criteria_list(
        self, page: Page, live_server: str, eligibility_pathway: dict[str, Any]
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{live_server}/requirements/view?pathway_id={eligibility_pathway['pathway']['id']}")

        expect(page.locator("h1")).to_have_text("Requirements")
        expect(page.get_by_text("Minimum age", exact=False)).to_be_visible()

        # Fill in a matching age and resubmit via the plain GET form --
        # the zero-JS "shareable URL" journey this page is built around.
        page.locator("#age").fill("18")
        page.get_by_role("button", name="Check my eligibility").click()
        page.wait_for_url("**/requirements/view*age=18*")
        expect(page.get_by_text("Meets this requirement", exact=False)).to_be_visible()
        assert page_errors == []

    def test_timeline_view_computes_a_total_from_one_filled_stage(
        self, page: Page, live_server: str
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{live_server}/timeline/view")
        expect(page.locator("h1")).to_have_text("Timeline calculator")

        page.locator("#stage_name_1").fill("Class 12")
        page.locator("#stage_duration_weeks_1").fill("52")
        page.get_by_role("button", name="Calculate timeline").click()

        expect(page.get_by_text("52 weeks")).to_be_visible()
        # The form re-renders pre-filled with what was submitted, not
        # blank -- the whole point of this screen's "edit and resubmit"
        # loop (docs/UI.md "assumptions editable without re-entering").
        expect(page.locator("#stage_name_1")).to_have_value("Class 12")
        assert page_errors == []


class TestReviewerConsoleZeroJsJourney:
    def test_sign_in_with_seeded_credentials_reaches_the_queue(
        self, page: Page, live_server: str, reviewer_credentials: dict[str, str]
    ) -> None:
        page.goto(f"{live_server}/reviewer/sign-in")
        page.locator("#email").fill(reviewer_credentials["email"])
        page.locator("#password").fill(reviewer_credentials["password"])
        page.get_by_role("button", name="Sign in").click()

        page.wait_for_url("**/reviewer/queue")
        expect(page.locator("h1")).to_have_text("Review queue")

    def test_queue_shows_a_seeded_draft_claim(
        self,
        page: Page,
        live_server: str,
        reviewer_credentials: dict[str, str],
        seeded_draft_claim: dict[str, Any],
    ) -> None:
        page.goto(f"{live_server}/reviewer/sign-in")
        page.locator("#email").fill(reviewer_credentials["email"])
        page.locator("#password").fill(reviewer_credentials["password"])
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/reviewer/queue")

        # Scoped to this claim's own card (not a bare page-wide text
        # search) so this stays correct even if another concurrent
        # session's own draft claims are sitting in the same live
        # queue -- docs/DECISIONS.md and STATUS.md both note this repo
        # is sometimes worked by more than one session at once.
        card = page.locator("section").filter(has_text="424242")
        expect(card).to_be_visible()
        expect(card.get_by_text("Draft", exact=False)).to_be_visible()
        expect(
            card.locator(f'form[action="/reviewer/claims/{seeded_draft_claim["id"]}/submit"]')
        ).to_be_visible()
