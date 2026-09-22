"""UI-6: live tests for the "assumption editing" HTML form on
`/compare/view` (docs/UI.md "Timeline & cost": "estimated additional
expenses" is one of three amounts that must always stay visibly
separate). The underlying override mechanism
(`estimated_additional_expenses_override`, threaded through
`app.api.compare.assemble_comparisons`) already has full JSON-route
coverage in `tests/db/test_api_explore_compare.py`'s
`test_net_to_arrange_is_computed_live_and_assumption_is_editable`; this
file is the HTML-route sibling, over the same real database, asserting
on rendered markup rather than a JSON body -- same split as
`tests/db/test_web_pages.py` vs. `tests/db/test_api_explore_compare.py`.

Same seeding pattern as those two files: a service-role admin client
seeds a career/pathway/source/claim, the test reads through the real
FastAPI app as a guest would, and everything is cleaned up afterwards.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from tests.db.conftest import run_name

client = TestClient(app)


@pytest.fixture
def two_pathways_one_priced(admin_client: Client) -> Iterator[dict[str, Any]]:
    """`pathway_priced` has one published, official, INR
    `verified_charges` claim of 50,000 -- big enough that the "your
    assumption" figure this file adds (15,000) can never collide with it
    digit-for-digit. `pathway_bare` has no claims at all, mirroring
    `tests/db/test_web_pages.py`'s `two_pathways` fixture: a real second
    pathway with an unknown total is what proves the override is applied
    uniformly (Lite Build Pack §6: "applied to every pathway in this
    comparison") without ever inventing a total for a pathway whose
    verified charges are still unpublished.
    """
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("UI-6 assumption test career")})
        .execute()
        .data[0]
    )
    pathway_priced = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("UI-6 assumption test pathway (priced)"),
                "description": "Seeded by tests/db/test_web_compare_assumption.py",
            }
        )
        .execute()
        .data[0]
    )
    pathway_bare = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("UI-6 assumption test pathway (bare)"),
                "description": "Seeded by tests/db/test_web_compare_assumption.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("UI-6 ASSUMPTION TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/ui-6-assumption-test-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    published_claim = (
        admin_client.table("claims")
        .insert(
            {
                "entity_type": "Pathway",
                "entity_id": pathway_priced["id"],
                "field": "verified_charges",
                "value": 50000,
                "currency": "INR",
                "source_id": official_source["id"],
                "verification_date": "2026-09-01",
                "verifier": run_name("test-fixture-reviewer"),
                "status": "published",
                "review_due_date": "2099-01-01",
            }
        )
        .execute()
        .data[0]
    )

    yield {"career": career, "pathway_priced": pathway_priced, "pathway_bare": pathway_bare}

    admin_client.table("claims").delete().eq("id", published_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_priced["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_bare["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


def _get(pathway_ids: list[str], **extra: str) -> Any:
    params: dict[str, Any] = {"pathway_id": pathway_ids}
    params.update(extra)
    return client.get("/compare/view", params=params)


def _assumption_input_value(html: str) -> str | None:
    """The `value="..."` currently rendered on the "your assumption"
    number input, read back with a regex rather than an HTML parser --
    same lightweight style `tests/db/test_web_pages.py` already uses
    throughout for asserting on rendered markup. `None` if the input
    itself is missing (should never happen once `error` is falsy)."""
    match = re.search(
        r'id="estimated_additional_expenses"[^>]*?value="([^"]*)"',
        html,
        re.DOTALL,
    )
    return match.group(1) if match else None


class TestAssumptionForm:
    def test_form_is_present_with_hidden_pathway_ids_and_label(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids)
        assert response.status_code == 200
        assert 'method="get"' in response.text
        assert 'action="/compare/view"' in response.text
        assert 'name="estimated_additional_expenses"' in response.text
        assert "Your assumption for extra expenses" in response.text
        for pid in pathway_ids:
            assert f'<input type="hidden" name="pathway_id" value="{pid}" />' in response.text

    def test_recalculation_copy_is_present(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids)
        assert response.status_code == 200
        assert "the total below updates for every pathway shown here" in response.text

    def test_no_override_shows_the_computed_zero_estimate_and_full_net(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        """Baseline, unchanged from before this task: no hint claim, no
        override -> assume zero extra, net_to_arrange equals the raw
        verified charge. The system's own estimate still carries the
        "Estimate" trust badge -- that badge only disappears once a
        STUDENT override is in play (see the override test below)."""
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids)
        assert response.status_code == 200
        assert response.text.count("₹50,000") == 2  # the fee line AND the total
        assert "trust-badge--estimate" in response.text
        assert _assumption_input_value(response.text) == ""

    def test_override_updates_net_to_arrange_for_every_pathway_without_touching_verified_charges(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids, estimated_additional_expenses="15000")
        assert response.status_code == 200
        # Verified charges themselves: unchanged.
        assert "₹50,000" in response.text
        assert "Checked against official source" in response.text
        # The total now reflects verified charges + the student's own
        # 15,000, not the old computed zero:
        assert "₹65,000" in response.text
        assert response.text.count("₹50,000") == 1  # only the fee line now, not also the total
        # The typed-in figure itself, echoed:
        assert "₹15,000" in response.text
        assert _assumption_input_value(response.text) == "15000"

    def test_override_figure_never_carries_an_estimate_or_trust_badge(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        """The core safety property this card exists to prove: a
        student's own typed-in guess must never be dressed up as a
        verified or system-computed fact anywhere it is displayed. Grep
        the actual rendered HTML -- not the template source -- because
        this is exactly the kind of thing a template-reading review can
        miss (docs/CONTRACTS.md's five trust labels are meant to be
        exhaustive about what IS confidently known; this value isn't any
        of them)."""
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids, estimated_additional_expenses="15000")
        assert response.status_code == 200
        assert "trust-badge--estimate" not in response.text
        assert "&#8776;" not in response.text  # the estimate badge's own glyph
        assert "Your assumption" in response.text
        assert "not a published or verified figure" in response.text

    def test_negative_value_is_ignored_not_treated_as_a_negative_cost(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        """A negative "additional expenses" has no real meaning
        (app/web/compare_pages.py's `_safe_estimated_additional_expenses`)
        -- must degrade to "no override", never silently reduce the
        total as though it were a discount, and never a 500."""
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids, estimated_additional_expenses="-5000")
        assert response.status_code == 200
        assert response.text.count("₹50,000") == 2  # same as the no-override baseline
        assert "-5,000" not in response.text
        assert "-₹5,000" not in response.text
        assert _assumption_input_value(response.text) == ""

    def test_garbled_value_is_ignored_not_a_500(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids, estimated_additional_expenses="not-a-number")
        assert response.status_code == 200
        assert response.text.count("₹50,000") == 2
        assert _assumption_input_value(response.text) == ""

    def test_nan_and_infinity_are_ignored_too(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        """Python's own `float()` parses "nan"/"inf" without raising --
        `_safe_estimated_additional_expenses` rejects both explicitly via
        `math.isfinite`, so this is a real, worth-pinning case, not a
        theoretical one."""
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        for garbled in ("nan", "inf", "-inf"):
            response = _get(pathway_ids, estimated_additional_expenses=garbled)
            assert response.status_code == 200
            assert response.text.count("₹50,000") == 2
            assert _assumption_input_value(response.text) == ""

    def test_implausibly_large_value_is_ignored_not_a_garbled_figure(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        """ux-qa-reviewer finding, 2026-09-22: a finite value past
        float64's ~15-17 significant digits of precision was silently
        corrupted by `_safe_estimated_additional_expenses` and then
        confidently displayed as a garbled, wrong rupee figure -- reject
        it the same way as negative/non-finite, well below the precision
        boundary where corruption could occur at all."""
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(
            pathway_ids, estimated_additional_expenses="99999999999999999999999999"
        )
        assert response.status_code == 200
        assert response.text.count("₹50,000") == 2  # same as the no-override baseline
        assert _assumption_input_value(response.text) == ""
        # The garbled figure this bug used to produce -- must never appear.
        assert "10,00,00,00,00,00,00,00" not in response.text

    def test_funding_work_realities_and_alternatives_show_explicit_not_yet_notes(
        self, two_pathways_one_priced: dict[str, Any]
    ) -> None:
        pathway_ids = [
            two_pathways_one_priced["pathway_priced"]["id"],
            two_pathways_one_priced["pathway_bare"]["id"],
        ]
        response = _get(pathway_ids)
        assert response.status_code == 200
        assert "Funding" in response.text
        assert "Work realities" in response.text
        assert "Alternatives if plans change" in response.text
        assert "Funding information" in response.text
        # Jinja autoescapes the apostrophe in "isn't" as &#39; -- match the
        # actual rendered text, not the template source's literal string.
        assert "published for this pathway yet" in response.text
        assert 'role="status"' in response.text
        # One note per field per pathway -- two pathways, three fields:
        assert response.text.count("published for this pathway yet") >= 6
