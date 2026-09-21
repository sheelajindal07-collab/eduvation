"""Live end-to-end tests for the actual clickable UI (app/web/) — the
first real user-facing screens this whole project has had. Same seeding
pattern as tests/db/test_api_explore_compare.py; the difference here is
asserting on rendered HTML content instead of a JSON body.
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

# QA-3: these two literals are asserted verbatim further down (not read
# back off the fixture's own returned dict, unlike every career/pathway
# name in this file), so each is tagged exactly once, here, and reused —
# never re-typed — everywhere it must match.
_SOME_COLLEGE_NAME = run_name("Some College (web UI test)")
_REQUIREMENTS_SOURCE_NAME = run_name("WEB UI REQUIREMENTS TEST SOURCE (fixture)")


@pytest.fixture
def two_pathways(
    admin_client: Client, synthetic_source: str
) -> Iterator[dict[str, Any]]:
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Web UI test career")})
        .execute()
        .data[0]
    )
    pathway_a = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Web UI test pathway A"),
                "description": "Seeded by tests/db/test_web_pages.py",
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
                "name": run_name("Web UI test pathway B"),
                "description": "Seeded by tests/db/test_web_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": run_name("WEB UI TEST OFFICIAL SOURCE"),
                "official_url": "https://example.invalid/web-ui-test-source",
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
                "entity_id": pathway_a["id"],
                "field": "verified_charges",
                "value": 85000,
                # SCOPE-4: an ordinary Indian fee states its currency. A
                # money claim with a null currency renders not_available
                # (docs/CONTRACTS.md), which is its own test below rather
                # than an accident of this shared fixture.
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

    yield {"career": career, "pathway_a": pathway_a, "pathway_b": pathway_b}

    admin_client.table("claims").delete().eq("id", published_claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_a["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway_b["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestExplorePage:
    def test_home_redirects_to_explore(self) -> None:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/explore"

    def test_static_css_is_served(self) -> None:
        response = client.get("/static/css/app.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_explore_lists_seeded_career_and_pathways(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get("/explore")
        assert response.status_code == 200
        assert two_pathways["career"]["name"] in response.text
        assert two_pathways["pathway_a"]["name"] in response.text
        assert two_pathways["pathway_b"]["name"] in response.text

    def test_skip_link_is_the_first_focusable_element(self) -> None:
        """A11Y-2 acceptance: the skip link must be the FIRST focusable
        element in rendered HTML order (not just present somewhere in the
        markup) -- a keyboard/screen-reader user's very first Tab must
        reach it before the header wordmark, session state or nav.
        Works regardless of whether any careers are seeded -- base.html's
        skip link renders on every page."""
        response = client.get("/explore")
        assert response.status_code == 200
        focusable = re.findall(
            r"<(?:a|button|input|select|textarea|summary)\b[^>]*>", response.text
        )
        assert focusable, "expected at least one focusable element on the page"
        assert focusable[0].startswith('<a href="#main"')

    def test_no_careers_shows_the_empty_state_with_role_status(self) -> None:
        """A11Y-2: explore.html's own empty copy ("No careers published
        yet...") now renders through _states.html's `empty_state()`
        macro, which the task requires to carry role="status"
        (informational -- nothing failed), never role="alert". Forced via
        a dependency override rather than relying on the shared local
        stack actually having zero careers -- never guaranteed, since
        STATUS.md notes this repo is sometimes run by more than one
        concurrent session."""
        from app.api.deps import get_db_client

        class _EmptyResult:
            data: list[Any] = []

        class _EmptyQuery:
            def execute(self) -> _EmptyResult:
                return _EmptyResult()

        class _EmptyTable:
            def select(self, *args: Any, **kwargs: Any) -> _EmptyQuery:
                return _EmptyQuery()

        class _EmptyDbClient:
            def table(self, name: str) -> _EmptyTable:
                return _EmptyTable()

        def _override() -> Iterator[Any]:
            yield _EmptyDbClient()

        app.dependency_overrides[get_db_client] = _override
        try:
            response = client.get("/explore")
        finally:
            app.dependency_overrides.pop(get_db_client, None)
        assert response.status_code == 200
        assert "No careers published yet" in response.text
        assert 'role="status"' in response.text
        assert "<script" not in response.text

    def test_explore_script_is_external_not_inline_and_selection_count_is_live(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """A11Y-2: explore.html's compare-selection progressive
        enhancement moved out of an inline <script> into
        app/static/js/explore-select.js (a pre-existing flagged
        CSP-tightening follow-up -- app/main.py's own comment on
        `_CONTENT_SECURITY_POLICY` names this exact script). Every
        <script> tag left on this page must be external (a `src`
        attribute, no inline body); `#selection-count` is now a live
        region so a screen-reader user hears the count change too, not
        only a sighted one."""
        response = client.get("/explore")
        assert response.status_code == 200
        script_bodies = re.findall(r"<script\b[^>]*>(.*?)</script>", response.text, re.DOTALL)
        assert script_bodies, "expected at least one <script> tag once careers are seeded"
        for body in script_bodies:
            assert body.strip() == "", "a <script> tag on this page has an inline body"
        assert '<script src="/static/js/explore-select.js">' in response.text
        assert 'id="selection-count"' in response.text
        assert 'aria-live="polite"' in response.text


class TestComparePage:
    def test_wrong_pathway_count_shows_a_friendly_message_not_a_bare_error(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view", params={"pathway_id": [two_pathways["pathway_a"]["id"]]}
        )
        assert response.status_code == 200
        assert "Pick 2 or 3 pathways" in response.text
        assert "Back to explore" in response.text

    def test_wrong_pathway_count_error_alert_has_role_alert(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """A11Y-2: the hand-rolled `.alert alert--caution` on this screen
        now renders through _states.html's `alert()` macro, which must
        carry role="alert" for a user-actionable error like this one
        (docs/UI.md State-pattern table)."""
        response = client.get(
            "/compare/view", params={"pathway_id": [two_pathways["pathway_a"]["id"]]}
        )
        assert response.status_code == 200
        assert 'role="alert"' in response.text

    def test_malformed_pathway_id_shows_the_friendly_message_not_a_500(self) -> None:
        """ux-qa-reviewer finding, 2026-09-19: a truncated/garbled shared
        link (very plausible for this product -- sent over WhatsApp) used
        to reach Postgres raw and crash to a bare, unstyled 500 with no
        way back."""
        response = client.get(
            "/compare/view", params={"pathway_id": ["not-a-uuid", "also-bad"]}
        )
        assert response.status_code == 200
        assert "Pick 2 or 3 pathways" in response.text

    def test_nonexistent_pathway_id_gives_a_friendly_heading_not_the_raw_uuid(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    "00000000-0000-0000-0000-000000000000",
                ]
            },
        )
        assert response.status_code == 200
        assert "This pathway" in response.text
        assert "00000000-0000-0000-0000-000000000000" not in response.text

    def test_compare_shows_both_pathway_names_and_trust_labels(
        self, two_pathways: dict[str, Any]
    ) -> None:
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert response.status_code == 200
        assert two_pathways["pathway_a"]["name"] in response.text
        assert two_pathways["pathway_b"]["name"] in response.text
        # Pathway A's published official claim:
        assert "Checked against official source" in response.text
        assert "₹85,000" in response.text
        # Pathway B has no claims at all -- every field must degrade to
        # "not available", never a blank or a crash (docs/UI.md: "name
        # the missing requirement/information, never guess").
        assert "Not available" in response.text

    def test_an_inr_fee_renders_exactly_as_it_always_did(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """SCOPE-4's "don't break the common case" check: the ordinary
        Indian pathway still shows a rupee sign and the same figures,
        now produced by `format_money` instead of a literal `&#8377;` in
        the template. The net total is the fee plus a zero assumption, so
        it renders identically to the fee itself."""
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert response.status_code == 200
        # The fee line AND the "what you'd need to arrange" total:
        assert response.text.count("₹85,000") == 2
        assert "What you'd need to arrange" in response.text
        # The estimate line, zero, still in rupees for an INR pathway:
        assert "₹0" in response.text

    def test_a_foreign_currency_fee_is_never_shown_as_rupees(
        self, admin_client: Client, two_pathways: dict[str, Any]
    ) -> None:
        """SCOPE-4, the riskiest display bug this screen can have: a fee
        published in pounds rendered with a rupee sign in front of it.
        `compare.html`/`_trust_badge.html` used to write `&#8377;`
        literally, in front of whatever number they were handed."""
        gbp_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": run_name("WEB UI TEST OFFICIAL SOURCE (GBP)"),
                    "official_url": "https://example.invalid/web-ui-test-source-gbp",
                    "source_type": "official",
                }
            )
            .execute()
            .data[0]
        )
        gbp_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": two_pathways["pathway_b"]["id"],
                    "field": "verified_charges",
                    "value": 9500,
                    "currency": "GBP",
                    "jurisdiction": "GB",
                    "source_id": gbp_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare/view",
                params={
                    "pathway_id": [
                        two_pathways["pathway_a"]["id"],
                        two_pathways["pathway_b"]["id"],
                    ]
                },
            )
            assert response.status_code == 200
            assert "GBP 9,500" in response.text
            # The pound figure never appears with a rupee sign in front,
            # and no template writes a currency symbol of its own:
            assert "₹9,500" not in response.text
            assert "&#8377;" not in response.text
        finally:
            admin_client.table("claims").delete().eq("id", gbp_claim["id"]).execute()
            admin_client.table("sources").delete().eq("id", gbp_source["id"]).execute()

    def test_closing_prompt_is_present(self, two_pathways: dict[str, Any]) -> None:
        """docs/UI.md's exact required closing prompt for this screen."""
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert "Which option would you like to investigate further?" in response.text

    def test_compare_links_to_requirements_for_each_compared_pathway(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """A student finishing a 3-way comparison must be able to keep
        going on any of the compared pathways, not just backtrack to
        Explore."""
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert response.status_code == 200
        assert (
            f'/requirements/view?pathway_id={two_pathways["pathway_a"]["id"]}'
            in response.text
        )
        assert (
            f'/requirements/view?pathway_id={two_pathways["pathway_b"]["id"]}'
            in response.text
        )

    def test_compare_page_header_links_to_the_timeline_calculator(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """The Timeline calculator is pathway-independent and must be
        reachable from every screen via base.html's global header link,
        including Compare."""
        response = client.get(
            "/compare/view",
            params={
                "pathway_id": [
                    two_pathways["pathway_a"]["id"],
                    two_pathways["pathway_b"]["id"],
                ]
            },
        )
        assert response.status_code == 200
        assert 'href="/timeline/view"' in response.text
        assert "Timeline calculator" in response.text

    def test_evidence_link_names_the_actual_source_and_varies_by_trust_label(
        self, admin_client: Client, two_pathways: dict[str, Any]
    ) -> None:
        """ux-qa-reviewer finding, 2026-09-19: the evidence link used to
        say "Official source" for every field regardless of its actual
        trust label -- an institution-reported or needs-rechecking field
        showed a badge saying "not independently confirmed"/"overdue"
        directly next to a link claiming to be official, contradicting
        the badge on the same line."""
        institution_source = (
            admin_client.table("sources")
            .insert(
                {
                    "authority_name": _SOME_COLLEGE_NAME,
                    "official_url": "https://example.invalid/institution-web-test",
                    "source_type": "institution_self_declared",
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
                    "entity_id": two_pathways["pathway_b"]["id"],
                    "field": "location",
                    "value": "Ahmedabad",
                    "source_id": institution_source["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare/view",
                params={
                    "pathway_id": [
                        two_pathways["pathway_a"]["id"],
                        two_pathways["pathway_b"]["id"],
                    ]
                },
            )
            assert response.status_code == 200
            assert _SOME_COLLEGE_NAME in response.text
            assert "(institution-reported)" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", claim["id"]).execute()
            admin_client.table("sources").delete().eq("id", institution_source["id"]).execute()

    def test_draft_claim_value_never_appears_in_the_rendered_html(
        self,
        admin_client: Client,
        synthetic_source: str,
        two_pathways: dict[str, Any],
    ) -> None:
        """Security-review finding, 2026-09-20 (MEDIUM, test coverage):
        tests/db/test_api_explore_compare.py has this exact live
        regression for the JSON route, but /compare/view (the HTML
        route) shares the same underlying assemble_comparisons() and had
        no equivalent -- it could silently diverge if a future change to
        app/web/pages.py stopped delegating to it for some field. Seeds
        a draft claim with a distinctive, greppable value and asserts it
        does not appear anywhere in the response text (not a JSON field
        -- the actual rendered HTML a browser would show)."""
        distinctive_value = "DRAFT-VALUE-MUST-NEVER-RENDER-8f31c2"
        draft_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": two_pathways["pathway_b"]["id"],
                    "field": "main_stages",
                    "value": distinctive_value,
                    "source_id": synthetic_source,
                    "verification_date": "2026-01-01",
                    "verifier": run_name("test-fixture"),
                    "status": "draft",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/compare/view",
                params={
                    "pathway_id": [
                        two_pathways["pathway_a"]["id"],
                        two_pathways["pathway_b"]["id"],
                    ]
                },
            )
            assert response.status_code == 200
            assert distinctive_value not in response.text
        finally:
            admin_client.table("claims").delete().eq("id", draft_claim["id"]).execute()


@pytest.fixture
def requirements_pathway(
    admin_client: Client,
) -> Iterator[dict[str, Any]]:
    """Same shape as tests/db/test_api_eligibility.py's `eligibility_
    pathway` fixture: a real pathway with four published eligibility
    claims (minimum_age=17, minimum_marks_percentage=50,
    required_subjects=Physics,Chemistry,Biology) plus a source, so
    /requirements/view has real criteria (with real evidence) to render,
    not just the vacuous "meets" of a claims-free pathway."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _REQUIREMENTS_SOURCE_NAME,
                "official_url": "https://example.invalid/requirements-web-ui-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("Requirements web UI test career (SYNTHETIC)")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("Requirements web UI test pathway (SYNTHETIC)"),
                "description": "Seeded by tests/db/test_web_pages.py",
            }
        )
        .execute()
        .data[0]
    )
    claim_specs = [
        ("minimum_age", "17"),
        ("minimum_marks_percentage", "50"),
        ("required_subjects", "Physics,Chemistry,Biology"),
    ]
    claims = []
    for field, value in claim_specs:
        claims.append(
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": pathway["id"],
                    "field": field,
                    "value": value,
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

    yield {"career": career, "pathway": pathway, "source": official_source}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestRequirementsPage:
    """Live regression tests for GET /requirements/view -- the HTML page
    wrapping GET /eligibility's own check_eligibility(), same wrapping
    relationship /compare/view has with assemble_comparisons()."""

    def test_no_student_inputs_shows_the_criteria_list_without_crashing(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        """On first load (pathway_id only), this is the screen's normal
        starting state -- every criterion needing student input shows
        as "insufficient_information"/"Not yet known", which is correct
        and expected, not an error."""
        response = client.get(
            "/requirements/view",
            params={"pathway_id": requirements_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert "Minimum age" in response.text
        assert "Minimum marks percentage" in response.text
        assert "Required subjects" in response.text
        assert "Not yet known" in response.text
        assert _REQUIREMENTS_SOURCE_NAME in response.text

    def test_get_ignores_a_personal_field_smuggled_into_the_query_string(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        """SEC-5: GET /requirements/view only ever declares pathway_id --
        age/marks_percentage/subjects_studied tacked onto the query
        string anyway (a hand-edited or legacy shared link) have no
        route parameter to bind to and are never read into the
        eligibility check."""
        response = client.get(
            "/requirements/view",
            params={
                "pathway_id": requirements_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology,English",
            },
        )
        assert response.status_code == 200
        assert "Not yet known" in response.text
        assert "You meet the published requirements" not in response.text

    def test_matching_student_inputs_shows_meets(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        # SEC-5: age/marks_percentage/subjects_studied are personal
        # inputs, POST-only -- the form now submits as a plain
        # x-www-form-urlencoded POST (same as the real zero-JS <form>),
        # never a query string.
        response = client.post(
            "/requirements/view",
            data={
                "pathway_id": requirements_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 72,
                "subjects_studied": "Physics,Chemistry,Biology,English",
            },
        )
        assert response.status_code == 200
        assert "You meet the published requirements" in response.text
        assert "Meets this requirement" in response.text
        assert "verified 2026-09-01" in response.text
        # POST-and-render: no redirect, so the URL a browser would end up
        # on is still exactly the POST target, never carrying "age=18" or
        # any other personal value.
        assert str(response.url).endswith("/requirements/view")
        assert "age" not in str(response.url)

    def test_non_matching_student_input_shows_does_not_meet(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        response = client.post(
            "/requirements/view",
            data={
                "pathway_id": requirements_pathway["pathway"]["id"],
                "age": 18,
                "marks_percentage": 30,  # below the published 50% minimum
                "subjects_studied": "Physics,Chemistry,Biology",
            },
        )
        assert response.status_code == 200
        # Jinja autoescapes the apostrophe to &#39; in rendered HTML (this
        # is correct, safe output -- the assertion matches what a
        # browser actually receives, not a raw literal apostrophe).
        assert "At least one published requirement isn&#39;t met" in response.text
        assert "Does not meet this requirement" in response.text

    def test_missing_pathway_id_degrades_to_a_friendly_message_not_a_crash(self) -> None:
        response = client.get("/requirements/view")
        assert response.status_code == 200
        # Jinja autoescapes the apostrophe to &#39; -- see comment above.
        assert "doesn&#39;t point to a valid pathway" in response.text
        assert "Back to explore" in response.text

    def test_malformed_pathway_id_degrades_to_a_friendly_message_not_a_500(self) -> None:
        """Same class of bug already fixed for /compare/view: entity_id
        is a `uuid` column (db/migrations/0001_init.sql), so an
        unvalidated garbled id would otherwise reach Postgres raw and
        crash to a bare 500."""
        response = client.get(
            "/requirements/view", params={"pathway_id": "not-a-uuid-at-all"}
        )
        assert response.status_code == 200
        assert "doesn&#39;t point to a valid pathway" in response.text

    def test_missing_pathway_id_error_alert_has_role_alert(self) -> None:
        """A11Y-2: same role="alert" requirement as compare.html's
        equivalent error alert, now that both render through the same
        shared `alert()` macro."""
        response = client.get("/requirements/view")
        assert response.status_code == 200
        assert 'role="alert"' in response.text

    def test_no_published_requirements_shows_the_empty_state_with_role_status(
        self, two_pathways: dict[str, Any]
    ) -> None:
        """A11Y-2: requirements.html's own empty copy ("No published
        eligibility requirements yet for this pathway") now renders
        through _states.html's `empty_state()` macro, which must carry
        role="status" (informational -- nothing failed), not
        role="alert". `two_pathways["pathway_b"]` has zero claims of any
        kind (the fixture's only claim is on pathway_a), so this
        pathway's criteria list is deterministically empty regardless of
        anything else in the shared local stack."""
        response = client.get(
            "/requirements/view",
            params={"pathway_id": two_pathways["pathway_b"]["id"]},
        )
        assert response.status_code == 200
        assert "No published eligibility requirements yet for this pathway." in response.text
        assert 'role="status"' in response.text

    def test_criteria_show_trust_label_alongside_the_eligibility_outcome(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        """FIX 2: a criterion's outcome (does the STUDENT's input meet
        it) and the underlying claim's trust label (should the FACT
        itself be trusted) are two different questions -- both must be
        visible, not just the outcome. The fixture's claims are a fresh
        official-source publication, so every criterion's trust label is
        "checked_against_official_source"."""
        response = client.get(
            "/requirements/view",
            params={"pathway_id": requirements_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert "Checked against official source" in response.text
        # Still shown alongside the eligibility outcome, not replacing it:
        assert "Not yet known" in response.text

    def test_domicile_criterion_display_name_is_not_the_awkward_generic_one(
        self, admin_client: Client, requirements_pathway: dict[str, Any]
    ) -> None:
        """FIX 8: 'domicile_in' must render as 'Domicile', not the
        generic name.replace('_', ' ')|capitalize result 'Domicile in'."""
        domicile_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": requirements_pathway["pathway"]["id"],
                    "field": "domicile_states",
                    "value": "Gujarat",
                    "source_id": requirements_pathway["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.get(
                "/requirements/view",
                params={"pathway_id": requirements_pathway["pathway"]["id"]},
            )
            assert response.status_code == 200
            assert re.search(r"<h2[^>]*>\s*Domicile\s*</h2>", response.text)
            assert "Domicile in" not in response.text
        finally:
            admin_client.table("claims").delete().eq("id", domicile_claim["id"]).execute()

    def test_domicile_case_mismatch_still_meets_not_a_hard_rejection(
        self, admin_client: Client, requirements_pathway: dict[str, Any]
    ) -> None:
        """FIX 4 (part B): a plausible case mismatch ('gujarat' vs the
        published 'Gujarat') must not silently produce a hard
        does_not_meet -- still true after SCOPE-5 replaced the free-text
        input with a <select> (a raw POST can still submit any string,
        not only one of the select's own option values, so the server
        side tolerance this test pins down still matters)."""
        domicile_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": requirements_pathway["pathway"]["id"],
                    "field": "domicile_states",
                    "value": "Gujarat",
                    "source_id": requirements_pathway["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.post(
                "/requirements/view",
                data={
                    "pathway_id": requirements_pathway["pathway"]["id"],
                    "age": 18,
                    "marks_percentage": 72,
                    "subjects_studied": "Physics,Chemistry,Biology,English",
                    "domicile_state": "gujarat",
                },
            )
            assert response.status_code == 200
            assert "You meet the published requirements" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", domicile_claim["id"]).execute()

    def test_domicile_select_code_value_matches_a_published_name(
        self, admin_client: Client, requirements_pathway: dict[str, Any]
    ) -> None:
        """SCOPE-5: the actual value a real browser submits from the new
        <select> is a canonical ISO code (e.g. 'IN-GJ'), not the display
        name -- this must still match a claim published as the plain
        state name via app.data.jurisdictions' code resolution."""
        domicile_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": requirements_pathway["pathway"]["id"],
                    "field": "domicile_states",
                    "value": "Gujarat",
                    "source_id": requirements_pathway["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.post(
                "/requirements/view",
                data={
                    "pathway_id": requirements_pathway["pathway"]["id"],
                    "age": 18,
                    "marks_percentage": 72,
                    "subjects_studied": "Physics,Chemistry,Biology,English",
                    "domicile_state": "IN-GJ",
                },
            )
            assert response.status_code == 200
            assert "You meet the published requirements" in response.text
        finally:
            admin_client.table("claims").delete().eq("id", domicile_claim["id"]).execute()

    def test_unrecognised_domicile_shows_not_yet_known_not_a_rejection(
        self, admin_client: Client, requirements_pathway: dict[str, Any]
    ) -> None:
        """SCOPE-5's core safety rule at the whole-page level: an
        unrecognised domicile value (bypassing the <select> via a raw
        POST) must render as unknown, never as a rejection."""
        domicile_claim = (
            admin_client.table("claims")
            .insert(
                {
                    "entity_type": "Pathway",
                    "entity_id": requirements_pathway["pathway"]["id"],
                    "field": "domicile_states",
                    "value": "Gujarat",
                    "source_id": requirements_pathway["source"]["id"],
                    "verification_date": "2026-09-01",
                    "verifier": run_name("test-fixture-reviewer"),
                    "status": "published",
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        try:
            response = client.post(
                "/requirements/view",
                data={
                    "pathway_id": requirements_pathway["pathway"]["id"],
                    "domicile_state": "Narnia",
                },
            )
            assert response.status_code == 200
            assert "Not yet known" in response.text
            assert "At least one published requirement isn&#39;t met" not in response.text
        finally:
            admin_client.table("claims").delete().eq("id", domicile_claim["id"]).execute()

    def test_domicile_hint_is_present_matching_subjects_studied_treatment(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        """FIX 4 (part A): domicile_state gets a hint, same treatment
        subjects_studied already has. SCOPE-5: the field is now a plain,
        zero-JS <select> over app/data/jurisdictions.py's canonical
        state/UT + pilot-country list, not a free-text input with a
        placeholder -- a <select> has no placeholder attribute, so this
        checks the select itself renders with a real option instead.
        Needs a well-formed pathway_id -- the form only renders on the
        "else" (non-error) branch of the page."""
        response = client.get(
            "/requirements/view",
            params={"pathway_id": requirements_pathway["pathway"]["id"]},
        )
        assert response.status_code == 200
        assert '<select class="field-input" id="domicile_state" name="domicile_state">' in (
            response.text
        )
        assert '<option value="IN-GJ"' in response.text
        assert "Your state of domicile" in response.text

    def test_malformed_age_and_marks_percentage_degrade_not_a_422(
        self, requirements_pathway: dict[str, Any]
    ) -> None:
        """FIX 5: a garbled age/marks_percentage from a hand-edited or
        malfunctioning client must degrade the same friendly way an
        omitted one already does, not surface a raw 422 -- true whether
        the value arrives via a query param (the old GET form) or, now
        (SEC-5), a POST body field."""
        response = client.post(
            "/requirements/view",
            data={
                "pathway_id": requirements_pathway["pathway"]["id"],
                "age": "not-a-number",
                "marks_percentage": "also-not-a-number",
                "subjects_studied": "Physics,Chemistry,Biology",
            },
        )
        assert response.status_code == 200
        # age/marks_percentage are treated as not provided -- their
        # criteria are still "insufficient_information", not an error
        # and not silently treated as some default value.
        assert "Not yet known" in response.text


class TestDbUnavailableDegradesGracefully:
    """FIX 6: app/db/client.py's SupabaseNotConfiguredError docstring
    says callers should catch it and degrade gracefully -- neither
    compare_page nor requirements_page did. Simulated here via a
    dependency override (app.web.pages._db_client_or_none) rather than
    actually unsetting the live project's config, since these two live
    tests share a TestClient/app with every other test in this module."""

    def test_compare_page_shows_a_friendly_message_not_a_500(self) -> None:
        from app.web.pages import _db_client_or_none

        def _unavailable() -> Iterator[Client | None]:
            yield None

        app.dependency_overrides[_db_client_or_none] = _unavailable
        try:
            response = client.get(
                "/compare/view",
                params={
                    "pathway_id": [
                        "00000000-0000-0000-0000-000000000001",
                        "00000000-0000-0000-0000-000000000002",
                    ]
                },
            )
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert "trouble reaching our data" in response.text
        assert "try again shortly" in response.text

    def test_requirements_page_shows_a_friendly_message_not_a_500(self) -> None:
        from app.web.pages import _db_client_or_none

        def _unavailable() -> Iterator[Client | None]:
            yield None

        app.dependency_overrides[_db_client_or_none] = _unavailable
        try:
            response = client.get(
                "/requirements/view",
                params={"pathway_id": "00000000-0000-0000-0000-000000000001"},
            )
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert "trouble reaching our data" in response.text
        assert "try again shortly" in response.text
