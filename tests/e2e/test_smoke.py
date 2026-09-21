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


@pytest.fixture
def two_seeded_pathways(admin_client: Client) -> Iterator[dict[str, Any]]:
    """Same seeding shape as tests/db/test_web_pages.py's `two_pathways`
    fixture -- a career with two pathways. No claims needed here: the
    claim-driven trust-labelling on /compare/view already has thorough
    live coverage in tests/db/test_web_pages.py; this directory's job is
    proving the zero-JS explore -> compare journey works in a real
    browser, not re-proving field-level correctness."""
    career = (
        admin_client.table("careers").insert({"name": "E2E smoke test career"}).execute().data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": "E2E smoke test pathway A",
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
                "name": "E2E smoke test pathway B",
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
    email = f"bcion-e2e-{uuid.uuid4().hex[:12]}@example.com"
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
                "verifier": "e2e-smoke-test-fixture",
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
        expect(page.get_by_text(two_seeded_pathways["pathway_a"]["name"])).to_be_visible()
        expect(page.get_by_text(two_seeded_pathways["pathway_b"]["name"])).to_be_visible()
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


class TestRequirementsAndTimelinePagesNotBuiltYet:
    """docs' own backlog (tasks/BCI-006.md "Not done yet") describes a
    Requirements screen (built from `GET /eligibility`) and a Timeline/
    cost-calculator screen (built from `POST /timeline`) -- but as of
    this task, NEITHER has an actual route. `app/web/pages.py` registers
    only `/`, `/explore` and `/compare/view` (confirmed by reading that
    file and app/main.py's router list, and cross-checked against every
    other active worktree this session -- no /requirements/view or
    /timeline/view exists anywhere yet, in this repo or in flight
    elsewhere). This task is test-infrastructure-only (no app/ or
    template changes), so these routes are not built here either.

    Writing a "smoke test" against a route that 404s on every single run
    would not be a genuine test -- it would always fail for a reason
    that has nothing to do with what this file exists to catch. Skipped
    instead, with a reason a human can act on, rather than either faked
    or silently dropped (CLAUDE.md: "never claim a test passed without
    having run it" cuts the other way too -- never claim one is testing
    something it structurally cannot). The underlying JSON APIs these
    pages would render are already fully live-tested:
    tests/db/test_api_eligibility.py and tests/unit/test_api_timeline.py.
    Un-skip and fill these in once app/web/pages.py actually grows the
    routes.
    """

    @pytest.mark.skip(
        reason="/requirements/view does not exist yet -- no route registered in "
        "app/web/pages.py as of this task. See this class's docstring."
    )
    def test_requirements_view_loads_and_shows_the_criteria_list(
        self, page: Page, live_server: str
    ) -> None:
        raise NotImplementedError

    @pytest.mark.skip(
        reason="/timeline/view does not exist yet -- no route registered in "
        "app/web/pages.py as of this task. See this class's docstring."
    )
    def test_timeline_view_computes_a_total_from_one_filled_stage(
        self, page: Page, live_server: str
    ) -> None:
        raise NotImplementedError


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
