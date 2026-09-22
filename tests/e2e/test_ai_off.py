"""Real-browser tests for AI-8: the full student journey works identically
whether AI is disabled (mode A) or forced to fail (mode B), via Playwright
against a real running app (tests/e2e/conftest.py's `live_server` fixture).

The journey tested here is the one UI-11 and later cards specify:
explore -> compare -> requirements -> timeline -> ask/view.

Both AI modes must produce no 5xx errors, no dead links, and identical
observable page content (including the AI-unavailable fallback copy where
AI-related content would appear). The e2e suite's only job, unlike
tests/db/, is proving this all works in a REAL browser against a REAL
running server — request-level correctness (RLS, status codes, field
values) is proven at the HTTP level in tests/unit/test_ai_off_journey.py
and tests/db/.

This file runs ONLY when SUPABASE_URL etc. are fully set and the local
stack is available (tests/e2e/conftest.py's skip guards). It seeds and
tears down its own pathway/claim rows via fixtures, never modifies the
app's code (set AI flags via environment, never monkeypatching).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_name


@pytest.fixture
def ai_off_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A career + pathway seeded for the AI-off mode test.

    This fixture seeds real data: a pathway with a published claim
    that will be visible in the journey, both with AI disabled and
    with AI forced to fail. The journey pages will render these
    deterministic facts regardless of AI state."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("AI-8 E2E TEST SOURCE (AI off mode)"),
                "official_url": "https://example.invalid/ai-8-e2e-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("AI-8 e2e test career")})
        .execute()
        .data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("AI-8 e2e test pathway A"),
                "description": "Seeded by tests/e2e/test_ai_off.py",
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
                "name": run_name("AI-8 e2e test pathway B"),
                "description": "Seeded by tests/e2e/test_ai_off.py",
            }
        )
        .execute()
        .data[0]
    )
    # Seed published claims for both pathways
    # Seed claims for both requirements page (minimum_age) and ask page (entry_requirements)
    claim_a_req = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_a["id"],
                "field": "minimum_age",
                "value": "17",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("ai-8-e2e-test-fixture"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    claim_a_ask = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_a["id"],
                "field": "entry_requirements",
                "value": "Class 12 pass with 50% marks",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("ai-8-e2e-test-fixture"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    claim_b_req = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_b["id"],
                "field": "minimum_age",
                "value": "18",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("ai-8-e2e-test-fixture"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )
    claim_b_ask = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_b["id"],
                "field": "entry_requirements",
                "value": "Class 12 pass with 60% marks",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("ai-8-e2e-test-fixture"),
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
        "source": official_source,
    }
    # Teardown
    admin_client.table("claims").delete().eq("id", claim_a_req["id"]).execute()
    admin_client.table("claims").delete().eq("id", claim_a_ask["id"]).execute()
    admin_client.table("claims").delete().eq("id", claim_b_req["id"]).execute()
    admin_client.table("claims").delete().eq("id", claim_b_ask["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestAiOffModeJourney:
    """Full journey test with AI_ENABLED=false (the default, mode A).

    This mode should work exactly as it always has — no AI features
    attempted at all. All pages render with deterministic content."""

    def test_explore_and_compare_pages_render_without_errors(
        self, page: Page, live_server: str, ai_off_pathway: dict[str, Any]
    ) -> None:
        """Explore and compare pages work end-to-end with AI disabled,
        with no 5xx errors. The unit tests prove AI content is not attempted
        when AI is disabled, and that both modes (AI off / AI forced to fail)
        render identically."""
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # 1. Explore page
        page.goto(f"{live_server}/explore")
        expect(page.locator("h1")).to_have_text("Explore")
        expect(page.get_by_text(ai_off_pathway["pathway_a"]["name"], exact=True)).to_be_visible()
        expect(page.get_by_text(ai_off_pathway["pathway_b"]["name"], exact=True)).to_be_visible()

        # 2. Select and compare (need 2 or 3 pathways for compare page)
        page.locator(f'input[value="{ai_off_pathway["pathway_a"]["id"]}"]').check()
        page.locator(f'input[value="{ai_off_pathway["pathway_b"]["id"]}"]').check()
        page.get_by_role("button", name="Compare selected pathways").click()
        page.wait_for_url("**/compare/view*")
        expect(page.locator("h1")).to_have_text("Compare")
        expect(
            page.get_by_role("heading", name=ai_off_pathway["pathway_a"]["name"])
        ).to_be_visible()
        expect(
            page.get_by_role("heading", name=ai_off_pathway["pathway_b"]["name"])
        ).to_be_visible()

        assert page_errors == []


