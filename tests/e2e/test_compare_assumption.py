"""UI-6, real-browser proof: editing "Your assumption for extra expenses"
on `/compare/view` and submitting the plain GET form (zero JS) actually
changes the total shown, in a real browser, with no client-side script
involved at all -- `tests/db/test_web_compare_assumption.py` already
proves the same thing at the HTTP-request level; this is the
`tests/e2e/test_start.py`-style sibling that drives an actual page.

Known environment issue (docs/DECISIONS.md's 2026-09-22 A11Y-4 entry,
`STATUS.md`'s own note on the same date): a click that triggers a real
server-side navigation has a reproducible pytest-playwright hang in this
environment, independent of and pre-existing this task's own code. If
this file hits it, the flow is verified by hand instead with a
standalone Playwright script outside pytest (same precedent A11Y-4/SEC-2
already set) rather than patched blind a third time.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Page, expect
from supabase import Client

from tests.db.conftest import run_name


@pytest.fixture
def priced_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """One priced pathway (a published, official, INR `verified_charges`
    claim of 50,000) plus one bare second pathway -- /compare/view needs
    at least two pathway_id values, and the second, unpriced pathway
    proves the override applies uniformly without inventing a total for
    a pathway whose charges are still unpublished (same fixture shape as
    tests/db/test_web_compare_assumption.py's `two_pathways_one_priced`,
    duplicated locally per this directory's own "no cross-test-file
    fixture import" convention -- see tests/e2e/conftest.py's docstring)."""
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("E2E assumption test career")})
        .execute()
        .data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("E2E assumption test pathway (priced)"),
                "description": "Seeded by tests/e2e/test_compare_assumption.py",
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
                "name": run_name("E2E assumption test pathway (bare)"),
                "description": "Seeded by tests/e2e/test_compare_assumption.py",
            }
        )
        .execute()
        .data[0]
    )
    source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("E2E ASSUMPTION TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/e2e-assumption-test-source",
                "source_type": "official",
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

    yield {"career": career, "pathway_a": pathway_a, "pathway_b": pathway_b}

    admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", source["id"]).execute()


class TestCompareAssumptionForm:
    def test_editing_the_assumption_updates_the_total_with_no_js(
        self, page: Page, live_server: str, priced_pathway: dict[str, Any]
    ) -> None:
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        pathway_a_id = priced_pathway["pathway_a"]["id"]
        pathway_b_id = priced_pathway["pathway_b"]["id"]
        page.goto(
            f"{live_server}/compare/view?pathway_id={pathway_a_id}&pathway_id={pathway_b_id}"
        )

        expect(page.locator("h1")).to_have_text("Compare")
        expect(page.get_by_text("₹50,000").first).to_be_visible()

        page.get_by_label("Your assumption for extra expenses").fill("15000")
        page.get_by_role("button", name="Update totals").click()

        page.wait_for_url("**/compare/view*")
        assert "estimated_additional_expenses=15000" in page.url

        expect(page.get_by_text("₹65,000").first).to_be_visible()
        expect(page.get_by_text("not a published or verified figure").first).to_be_visible()
        assert page_errors == []
