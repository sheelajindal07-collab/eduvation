"""Real-browser smoke test for the landing page and the `/start`
quick-start chain (UI-3), same conventions as tests/e2e/test_smoke.py:
a real `uvicorn` subprocess (`live_server`), a real browser, assertions
on rendered content -- never just a status code.

Like the rest of this directory, every test here is skipped (with a
clear reason, `tests/e2e/conftest.py`'s own
`pytest_collection_modifyitems`) when no local Supabase stack is
configured. None of the assertions below actually need a database row
(the whole point of `/start` is that it needs none), but the directory-
wide skip still applies, so this can only run against a real live
server + local stack.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_name


@pytest.fixture
def one_seeded_career(admin_client: Client) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("E2E start-flow test career")})
        .execute()
        .data[0]
    )
    yield career
    admin_client.table("careers").delete().eq("id", career["id"]).execute()


class TestLandingPage:
    def test_landing_page_offers_three_starting_choices_with_no_js(
        self, page: Page, live_server: str
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(live_server)

        expect(page.locator("h1")).to_have_text("Find your next step")
        expect(page.get_by_role("link", name="Start")).to_be_visible()
        expect(page.get_by_role("link", name="Browse Explore")).to_be_visible()
        assert page_errors == []

    def test_career_in_mind_link_jumps_straight_to_its_explore_anchor(
        self, page: Page, live_server: str, one_seeded_career: dict[str, Any]
    ) -> None:
        page.goto(live_server)
        page.get_by_role("link", name=one_seeded_career["name"]).click()

        page.wait_for_url("**/explore*")
        expect(page.locator(f'#career-{one_seeded_career["id"]}')).to_be_visible()


class TestStartFlow:
    def test_answering_every_question_reaches_the_results_summary(
        self, page: Page, live_server: str
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(f"{live_server}/start")
        expect(page.locator("h1")).to_have_text("What are you studying right now?")
        page.get_by_label("Class 8-10").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/decide*")
        page.get_by_label("Which career path to explore").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/interest*")
        page.get_by_label("Science and technology").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/priority*")
        page.get_by_label("Affordable").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/results*")
        expect(page.locator("h1")).to_have_text("Thanks — here's what you told us")
        expect(page.get_by_text("Class 8-10")).to_be_visible()
        expect(page.get_by_text("Which career path to explore")).to_be_visible()
        expect(page.get_by_text("Affordable")).to_be_visible()
        assert page_errors == []

    def test_skipping_every_question_still_reaches_a_plain_summary(
        self, page: Page, live_server: str
    ) -> None:
        page.goto(f"{live_server}/start")
        for _ in range(4):
            page.get_by_role("link", name="Skip this question").click()

        page.wait_for_url("**/start/results*")
        expect(page.get_by_text("You skipped every question")).to_be_visible()

    def test_back_button_preserves_the_first_answer(self, page: Page, live_server: str) -> None:
        page.goto(f"{live_server}/start")
        page.get_by_label("Class 11-12").check()
        page.get_by_role("button", name="Continue").click()
        page.wait_for_url("**/start/decide*")

        page.get_by_label("Not sure yet").check()
        page.get_by_role("button", name="Continue").click()
        page.wait_for_url("**/start/interest*")

        page.go_back()
        page.wait_for_url("**/start/decide*")
        assert "stage=senior_secondary" in page.url
        expect(page.locator('input[name="stage"][type="hidden"]')).to_have_value(
            "senior_secondary"
        )
