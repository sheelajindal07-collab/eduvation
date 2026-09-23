"""QA-7: the full guest journey in one real-browser walk -- quick start,
explore, compare (including UI-6's own cost-assumption editing), a real
official evidence link, requirements, then the timeline calculator --
parametrized over the two viewports the inventory names (a 360x740
phone, a 1280x800 desktop; see `tests/e2e/conftest.py`'s
`viewport_size`/`sized_page` fixtures). Same conventions as
`tests/e2e/test_smoke.py` and `test_start.py`: a real `uvicorn`
subprocess (`live_server`), a real browser, assertions on rendered
content, never just a status code.

Overflow: every page this journey visits asserts no horizontal overflow
(`document.documentElement.scrollWidth <= document.documentElement
.clientWidth`) at BOTH viewports -- this task's own acceptance criteria
names explore, compare, requirements and timeline_calculator explicitly,
so each of those four gets its own clearly labelled assertion below
(never folded into a silent loop over "some pages"); the quick-start
chain and the post-submit re-renders of compare/requirements/timeline
are checked too, since the card's own instruction ("on every page in
that journey") is broader than just those four.

Tap targets: checked ONLY on elements docs/UI.md itself names a size
requirement for -- `.btn-primary`, `.btn-secondary` and `.field-input`
("Every touch target in every state above keeps the 44-48px minimum
already established by ...", docs/UI.md's "States" section) -- never a
blanket check over every clickable element on a page, which docs/UI.md
does not ask for.

Real official source link -- read this before changing the URL below:
this repo's own operating rule for every test author is that a test must
never be pointed at anything but localhost/the local stack, "always, no
exception this file can grant" -- and that holds even though this task's
own acceptance text asks to "confirm it's a real, reachable link" by
opening one. The seeded claim below carries
"https://neet.nta.nic.in/" (the National Testing Agency's real NEET
domain -- the same real, non-placeholder example already used in
`tests/unit/test_models.py`, chosen deliberately instead of yet another
`example.invalid` like every other e2e fixture in this suite) as its
source_url PURELY AS DATA -- exactly like a real published claim would
carry a real government URL in production. Its actual reachability was
confirmed once, by hand, outside this suite, in the session that wrote
this file (`curl -sI https://neet.nta.nic.in/` -> HTTP 200) -- not by
the automated test itself, which never issues a network request to it
and never asks Playwright to navigate the browser there. What the test
below DOES assert, entirely against the already-loaded local page, is
that the rendered link is genuinely that real URL, unmodified, opens in
a new tab, and is visibly not a placeholder -- the strongest check
available without breaking the localhost-only rule. See this session's
own completion report for the same disclosure.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_name

# Confirmed reachable by hand outside this suite (see module docstring):
# `curl -sI https://neet.nta.nic.in/` -> HTTP 200, on the date this file
# was written. Never fetched by the automated test itself.
REAL_OFFICIAL_SOURCE_URL = "https://neet.nta.nic.in/"


def _assert_no_horizontal_overflow(page: Page, screen_name: str) -> None:
    """QA-7's own overflow check: a real horizontal scrollbar/overflow,
    not a cosmetic nit. `page.viewport_size` in the failure message makes
    a failing run's report self-explanatory about which of the two
    viewports (`sized_page` picked one per test run) tripped it."""
    scroll_width, client_width = page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    assert scroll_width <= client_width, (
        f"{screen_name} overflows horizontally at viewport {page.viewport_size}: "
        f"scrollWidth={scroll_width} > clientWidth={client_width}"
    )


def _assert_tap_target_at_least_44px(page: Page, selector: str, element_name: str) -> None:
    """docs/UI.md: '.btn-primary'/'.btn-secondary'/'.field-input' each
    keep a 44-48px touch-target minimum -- called here only for elements
    that actually carry one of those three classes."""
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{element_name} ({selector}) has no visible bounding box to measure"
    assert box["height"] >= 44, (
        f"{element_name} ({selector}) is only {box['height']}px tall at viewport "
        f"{page.viewport_size}, under docs/UI.md's 44px minimum for "
        f".btn-primary/.btn-secondary/.field-input"
    )


@pytest.fixture
def journey_pathways(admin_client: Client) -> Iterator[dict[str, Any]]:
    """One career with three pathways -- the top of this task's own "2-3
    pathways" range, which also exercises compare.html's 3-column grid
    (`md:grid-cols-3`) rather than the 2-column case every other e2e
    fixture in this suite already covers. pathway_a carries a published,
    OFFICIAL `verified_charges` claim (so Compare has a real total for
    UI-6's assumption form to change) and a published `minimum_age`
    claim (so Requirements has a real criterion to check) -- both against
    the SAME real, non-placeholder official source; see this module's own
    docstring for why."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("E2E journey test career")})
        .execute()
        .data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E journey pathway A priced"),
                "description": "Seeded by tests/e2e/test_guest_journey.py",
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
                "name": run_name("E2E journey pathway B"),
                "description": "Seeded by tests/e2e/test_guest_journey.py",
            }
        )
        .execute()
        .data[0]
    )
    pathway_c = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E journey pathway C"),
                "description": "Seeded by tests/e2e/test_guest_journey.py",
            }
        )
        .execute()
        .data[0]
    )
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("E2E JOURNEY REAL OFFICIAL SOURCE"),
                "official_url": REAL_OFFICIAL_SOURCE_URL,
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    charges_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_a["id"],
                "field": "verified_charges",
                "value": 50000,
                "currency": "INR",
                "source_id": source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    age_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_a["id"],
                "field": "minimum_age",
                "value": "17",
                "source_id": source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )

    yield {
        "career": career,
        "pathway_a": pathway_a,
        "pathway_b": pathway_b,
        "pathway_c": pathway_c,
        "source": source,
    }

    admin_client.table("claims").delete().eq("id", charges_claim["id"]).execute()
    admin_client.table("claims").delete().eq("id", age_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_c["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", source["id"]).execute()


class TestGuestJourney:
    def test_quick_start_explore_compare_requirements_timeline_and_a_real_source_link(
        self, sized_page: Page, live_server: str, journey_pathways: dict[str, Any]
    ) -> None:
        page = sized_page
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        pathway_a = journey_pathways["pathway_a"]
        pathway_b = journey_pathways["pathway_b"]
        pathway_c = journey_pathways["pathway_c"]
        source = journey_pathways["source"]

        # -- 1. Quick start (/start) --------------------------------------
        page.goto(f"{live_server}/start")
        expect(page.locator("h1")).to_have_text("What are you studying right now?")
        _assert_no_horizontal_overflow(page, "start (stage question)")
        page.get_by_label("Class 11-12").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/decide*")
        _assert_no_horizontal_overflow(page, "start (decide question)")
        page.get_by_label("Which career path to explore").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/interest*")
        _assert_no_horizontal_overflow(page, "start (interest question)")
        page.get_by_label("Science and technology").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/priority*")
        _assert_no_horizontal_overflow(page, "start (priority question)")
        page.get_by_label("Affordable").check()
        page.get_by_role("button", name="Continue").click()

        page.wait_for_url("**/start/results*")
        expect(page.locator("h1")).to_have_text("Thanks — here's what you told us")
        _assert_no_horizontal_overflow(page, "start (results)")

        # -- 2. Explore (/explore) -- pick all 3 seeded pathways ----------
        page.goto(f"{live_server}/explore")
        expect(page.locator("h1")).to_have_text("Explore")
        _assert_no_horizontal_overflow(page, "explore")
        _assert_tap_target_at_least_44px(
            page, 'button:has-text("Compare selected pathways")', "Explore's Compare button"
        )

        page.locator(f'input[value="{pathway_a["id"]}"]').check()
        page.locator(f'input[value="{pathway_b["id"]}"]').check()
        page.locator(f'input[value="{pathway_c["id"]}"]').check()
        page.get_by_role("button", name="Compare selected pathways").click()

        # -- 3. Compare (/compare/view), including UI-6's own real
        #    cost-assumption-editing feature -----------------------------
        page.wait_for_url("**/compare/view*")
        expect(page.locator("h1")).to_have_text("Compare")
        _assert_no_horizontal_overflow(page, "compare")
        for pathway in (pathway_a, pathway_b, pathway_c):
            expect(
                page.get_by_role("heading", name=pathway["name"])
            ).to_be_visible()
        _assert_tap_target_at_least_44px(
            page, "#estimated_additional_expenses", "Compare's assumption field-input"
        )
        _assert_tap_target_at_least_44px(
            page, 'button:has-text("Update totals")', "Compare's Update totals button"
        )

        expect(page.get_by_text("₹50,000").first).to_be_visible()
        page.get_by_label("Your assumption for extra expenses").fill("15000")
        page.get_by_role("button", name="Update totals").click()

        page.wait_for_url("**/compare/view*")
        assert "estimated_additional_expenses=15000" in page.url
        expect(page.get_by_text("₹65,000").first).to_be_visible()
        expect(page.get_by_text("not a published or verified figure").first).to_be_visible()
        _assert_no_horizontal_overflow(page, "compare (after changing the cost assumption)")

        # -- 4. Requirements (/requirements/view), reached the way a
        #    student actually would -- the real "See requirements for
        #    <pathway>" link Compare renders per-card, not a bare goto ---
        page.get_by_role("link", name=f"See requirements for {pathway_a['name']}").click()
        page.wait_for_url("**/requirements/view*")
        expect(page.locator("h1")).to_have_text("Requirements")
        _assert_no_horizontal_overflow(page, "requirements")
        _assert_tap_target_at_least_44px(page, "#age", "Requirements' age field-input")
        _assert_tap_target_at_least_44px(
            page, 'button:has-text("Check my eligibility")', "Requirements' Check button"
        )

        page.locator("#age").fill("18")
        page.get_by_role("button", name="Check my eligibility").click()
        expect(page.get_by_text("Meets this requirement", exact=False)).to_be_visible()
        _assert_no_horizontal_overflow(page, "requirements (after checking eligibility)")

        # -- 5. Timeline calculator (/timeline/view) -- no screen links
        #    here yet (UI-7's own disclosed gap, STATUS.md 2026-09-21), so
        #    a direct goto, same as tests/e2e/test_smoke.py's own
        #    equivalent test ------------------------------------------------
        page.goto(f"{live_server}/timeline/view")
        expect(page.locator("h1")).to_have_text("Timeline calculator")
        _assert_no_horizontal_overflow(page, "timeline_calculator")
        _assert_tap_target_at_least_44px(
            page, "#stage_name_1", "Timeline's stage-name field-input"
        )
        _assert_tap_target_at_least_44px(
            page, 'button:has-text("Calculate timeline")', "Timeline's Calculate button"
        )

        page.locator("#stage_name_1").fill("Class 12")
        page.locator("#stage_duration_weeks_1").fill("52")
        page.get_by_role("button", name="Calculate timeline").click()

        expect(page.locator("p.text-2xl.font-semibold.text-charcoal")).to_have_text("52 weeks")
        _assert_no_horizontal_overflow(page, "timeline_calculator (after calculating)")

        # -- 6. A real official source link -- see module docstring for
        #    exactly what is and isn't checked here and why. A plain goto
        #    back to Compare (not a click) -- nothing about this step
        #    needs a new click path, only that the evidence link Compare
        #    already rendered for pathway_a's verified_charges claim is
        #    genuinely real, not a placeholder ---------------------------
        page.goto(
            f"{live_server}/compare/view?pathway_id={pathway_a['id']}"
            f"&pathway_id={pathway_b['id']}&pathway_id={pathway_c['id']}"
        )
        source_link = page.get_by_role("link", name=source["authority_name"], exact=False).first
        expect(source_link).to_be_visible()

        href = source_link.get_attribute("href")
        target = source_link.get_attribute("target")
        rel = source_link.get_attribute("rel") or ""
        assert href == REAL_OFFICIAL_SOURCE_URL, (
            f"evidence link href was {href!r}, expected the real seeded "
            f"source URL {REAL_OFFICIAL_SOURCE_URL!r} unmodified"
        )
        assert href is not None and href.startswith("https://")
        assert "example.invalid" not in href
        assert "localhost" not in href
        assert "127.0.0.1" not in href
        assert target == "_blank", "official source links must open in a new tab"
        assert "noopener" in rel and "noreferrer" in rel

        assert page_errors == []
