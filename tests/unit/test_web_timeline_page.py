"""Tests for GET/POST /timeline/view (app/web/pages.py) via TestClient.

Stateless -- no database involved, same reasoning as
tests/unit/test_api_timeline.py for POST /timeline itself -- this page
just wraps compute_timeline() with an HTML form/response layer, so these
live in tests/unit/, not tests/db/.

RULES-9's GET-only prefill is the one exception: `TestRealPathwayPrefillDegradesGracefully`
below exercises the DB-unavailable and pathway-not-found degradation
paths via a fake client / dependency override, with no real network
I/O -- the actual claim-gated prefill (a published vs. a draft stage
claim) is proven live against the real local stack in
tests/db/test_web_timeline_page.py, per this task's own acceptance
criteria ("proven with a real seeded draft claim against the local DB,
not just a pure unit test").
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from supabase import Client

from app.main import app
from app.web.pages import _db_client_or_none

client = TestClient(app)

_REAL_LOOKING_UUID = "00000000-0000-0000-0000-000000000001"


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Enough of Supabase's fluent `.select().eq().in_().execute()`
    interface for `app.web.timeline_pages._pathway_prefill` -- filters
    are accepted and ignored (each fake table below is already exactly
    the rows one specific test wants back), never real network I/O."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def in_(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        return self

    def execute(self) -> _FakeResult:
        return _FakeResult(self._rows)


class _FakeDbClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self._tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._tables.get(name, []))


class TestTimelinePageGet:
    def test_get_shows_the_empty_form(self) -> None:
        response = client.get("/timeline/view")
        assert response.status_code == 200
        assert "Timeline calculator" in response.text
        assert 'name="stage_name_1"' in response.text
        assert 'name="stage_duration_weeks_1"' in response.text
        # No result section yet -- nothing has been submitted.
        assert "Missing a duration for" not in response.text

    def test_skip_link_is_the_first_focusable_element(self) -> None:
        """A11Y-2 acceptance: the skip link must be the FIRST focusable
        element in rendered HTML order (not just present somewhere in the
        markup) -- base.html renders it on every page, including this
        fully stateless one."""
        response = client.get("/timeline/view")
        assert response.status_code == 200
        focusable = re.findall(
            r"<(?:a|button|input|select|textarea|summary)\b[^>]*>", response.text
        )
        assert focusable, "expected at least one focusable element on the page"
        assert focusable[0].startswith('<a href="#main"')


class TestTimelinePagePost:
    def test_a_few_valid_stages_show_the_correct_total(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "stage_name_2": "Entrance prep",
                "stage_duration_weeks_2": "26",
                "stage_required_2": "on",
            },
        )
        assert response.status_code == 200
        assert "78 weeks" in response.text
        assert "Complete" in response.text
        # Pre-filled for further what-if edits, not cleared out.
        assert 'value="Class 12"' in response.text
        assert 'value="52"' in response.text

    def test_a_stage_left_without_a_duration_is_named_and_incomplete(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "stage_name_2": "Entrance prep (TBD)",
                "stage_duration_weeks_2": "",
                "stage_required_2": "on",
            },
        )
        assert response.status_code == 200
        assert "Total not available yet" in response.text
        assert "Missing a duration for: Entrance prep (TBD)" in response.text
        # The stage the student left blank is still shown pre-filled by
        # name, so they can go straight to filling in its duration.
        assert 'value="Entrance prep (TBD)"' in response.text

    def test_blank_rows_are_ignored_not_treated_as_unknown_stages(self) -> None:
        """Only the row the student actually named counts -- the other
        five blank stage rows and three blank parallel-activity rows
        must not show up as "missing" stages."""
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Degree",
                "stage_duration_weeks_1": "150",
                "stage_required_1": "on",
            },
        )
        assert response.status_code == 200
        assert "150 weeks" in response.text
        assert "Missing a duration for" not in response.text

    def test_overlap_exceeding_stage_duration_shows_a_plain_language_error_not_a_500(
        self,
    ) -> None:
        """app/rules/timeline.py's compute_timeline() raises ValueError
        for this (a content-authoring error, not a student input to
        silently clamp) -- app/api/timeline.py's own JSON route already
        turns that into a 400; this page must turn it into an inline
        message on the same form, never a raw exception or a 500."""
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Stage A",
                "stage_duration_weeks_1": "4",
                "stage_required_1": "on",
                "stage_name_2": "Stage B",
                "stage_duration_weeks_2": "10",
                "stage_required_2": "on",
                "stage_overlap_weeks_with_previous_2": "20",
            },
        )
        assert response.status_code == 200
        assert "overlap" in response.text.lower()
        # Still the same editable form, not a crash page.
        assert 'name="stage_name_1"' in response.text
        assert 'value="Stage A"' in response.text

    def test_overlap_error_alert_has_role_alert(self) -> None:
        """A11Y-2: this screen's hand-rolled `.alert alert--caution` now
        renders through _states.html's `alert()` macro, which must carry
        role="alert" for a user-actionable error like this one."""
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Stage A",
                "stage_duration_weeks_1": "4",
                "stage_required_1": "on",
                "stage_name_2": "Stage B",
                "stage_duration_weeks_2": "10",
                "stage_required_2": "on",
                "stage_overlap_weeks_with_previous_2": "20",
            },
        )
        assert response.status_code == 200
        assert 'role="alert"' in response.text

    def test_parallel_activity_is_shown_but_never_added_to_the_total(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Degree",
                "stage_duration_weeks_1": "100",
                "stage_required_1": "on",
                "parallel_name_1": "Part-time certification",
                "parallel_duration_weeks_1": "40",
            },
        )
        assert response.status_code == 200
        assert "100 weeks" in response.text
        assert 'value="Part-time certification"' in response.text

    def test_negative_duration_shows_a_plain_language_error_not_a_500(self) -> None:
        """RULES-9: app/rules/timeline.py's compute_timeline() raises
        TimelineValidationError for a negative duration -- same "friendly
        message, never a crash" handling as the overlap case above, and
        the SAME `_states.html` `alert()` macro (role="alert")."""
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Broken stage",
                "stage_duration_weeks_1": "-5",
                "stage_required_1": "on",
            },
        )
        assert response.status_code == 200
        assert "negative" in response.text.lower()
        assert 'role="alert"' in response.text
        # Still the same editable form, not a crash page.
        assert 'name="stage_name_1"' in response.text
        assert 'value="Broken stage"' in response.text

    def test_negative_overlap_shows_a_plain_language_error_not_a_500(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "stage_name_2": "Entrance prep",
                "stage_duration_weeks_2": "26",
                "stage_required_2": "on",
                "stage_overlap_weeks_with_previous_2": "-1",
            },
        )
        assert response.status_code == 200
        assert "negative" in response.text.lower()
        assert 'role="alert"' in response.text


class TestStageKindsRenderDistinguishably:
    """UI-7: required vs optional vs user-assumption stages (docs/UI.md
    "Timeline & cost") each get their own text label AND icon, sourced
    from app/rules/timeline.py's `Stage.display_kind` -- never a CSS
    class that happens to carry a different colour alone."""

    def test_required_optional_and_user_assumption_all_render_distinguishably(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "stage_name_2": "Optional bridge course",
                "stage_duration_weeks_2": "10",
                # No stage_required_2 -- an unchecked "Required" box, i.e. optional.
                "action": "revise",  # adds the third kind, a user-assumption row
            },
        )
        assert response.status_code == 200
        # Required: its own CSS class and its own icon.
        assert "stage-kind-badge--required" in response.text
        assert "&#10003;" in response.text
        # Optional: a different class, a different icon, and the capitalised
        # badge text (distinct from the lowercase "(optional)" section heading).
        assert "stage-kind-badge--optional" in response.text
        assert "&#9675;" in response.text
        assert "Optional" in response.text
        # User assumption: the "Revise this scenario" row, a third class and icon.
        assert "stage-kind-badge--user_assumption" in response.text
        assert "&#8776;" in response.text
        assert "Your assumption" in response.text
        assert "Extra attempt 1" in response.text


class TestReviseThisScenario:
    """UI-7: "Revise this scenario" adds an extra attempt/stage and
    recomputes -- never framed as a failure (docs/UI.md "Timeline &
    cost": "A failed attempt offers 'Revise this scenario', not a
    failure badge")."""

    def test_revise_never_uses_failure_language(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "action": "revise",
            },
        )
        assert response.status_code == 200
        assert "Revise this scenario" in response.text
        assert "fail" not in response.text.lower()

    def test_revise_adds_an_extra_attempt_row_live_via_a_real_round_trip(self) -> None:
        """Two real requests through TestClient -- not a unit test on
        compute_timeline() alone -- matching this screen's existing
        pre-fill-and-resubmit loop (GET, then POST, then POST again)."""
        # Step 1: a complete plan, then click "Revise this scenario".
        revise_response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "action": "revise",
            },
        )
        assert revise_response.status_code == 200
        assert 'name="stage_extra_name_1"' in revise_response.text
        assert 'value="Extra attempt 1"' in revise_response.text
        assert 'name="num_extra_rows" value="1"' in revise_response.text

        # Step 2: fill in the new row's duration and recalculate -- the
        # total must include it, live, via the same page.
        calculate_response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "num_extra_rows": "1",
                "stage_extra_name_1": "Extra attempt 1",
                "stage_extra_duration_weeks_1": "10",
                "action": "calculate",
            },
        )
        assert calculate_response.status_code == 200
        assert "62 weeks" in calculate_response.text
        assert "Complete" in calculate_response.text

    def test_revise_button_is_disabled_once_the_maximum_is_reached(self) -> None:
        data = {
            "stage_name_1": "Class 12",
            "stage_duration_weeks_1": "52",
            "stage_required_1": "on",
            "num_extra_rows": "6",  # _TIMELINE_EXTRA_ROWS_MAX
            "action": "revise",
        }
        for i in range(1, 7):
            data[f"stage_extra_name_{i}"] = f"Extra attempt {i}"
            data[f"stage_extra_duration_weeks_{i}"] = "4"
        response = client.post("/timeline/view", data=data)
        assert response.status_code == 200
        # Still only 6 extra rows -- the 7th click was a no-op, not silently
        # accepted -- and the control itself says why (never a colour-only
        # disabled state, per docs/UI.md's State-pattern table).
        assert "Extra attempt 7" not in response.text
        assert "most extra attempts this calculator supports" in response.text


class TestTotalStaysUnknownAfterRevise:
    """UI-7 safety property (app/rules/timeline.py's core invariant,
    preserved through the new "Revise this scenario" control): adding an
    attempt must never let a stale, now-incomplete total keep showing as
    if it were still confident."""

    def test_total_goes_back_to_unknown_the_moment_an_unfilled_attempt_is_added(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "action": "revise",
            },
        )
        assert response.status_code == 200
        assert "Total not available yet" in response.text
        assert "Missing a duration for: Extra attempt 1" in response.text


class TestPathwayNameContext:
    """UI-7: `pathway_id`/`pathway_name` are an optional pair -- display
    context by default. RULES-9 adds a real database lookup on GET, but
    ONLY for a well-formed UUID `pathway_id` -- every test in this class
    uses the non-UUID `"abc-123"`, so no lookup is attempted and these
    stay exactly the display-only-context assertions UI-7 wrote (no
    Supabase configured in this test environment either, so `db` here
    is always `None` regardless). Standalone mode (neither given) must
    keep working exactly as before."""

    def test_pathway_name_shown_when_pathway_id_given(self) -> None:
        response = client.get(
            "/timeline/view", params={"pathway_id": "abc-123", "pathway_name": "B.Tech (CSE)"}
        )
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert "B.Tech (CSE)" in response.text
        assert 'value="abc-123"' in response.text  # carried as a hidden field


class TestRealPathwayPrefillDegradesGracefully:
    """RULES-9: `GET /timeline/view?pathway_id=<uuid>` now has a real
    `Depends(_db_client_or_none)`. Both paths here are forced via a
    dependency override / fake client -- no real network I/O -- so they
    run in tests/unit rather than tests/db."""

    def test_db_unavailable_shows_the_friendly_message_and_still_renders_the_form(
        self,
    ) -> None:
        def _unavailable() -> Iterator[Client | None]:
            yield None

        app.dependency_overrides[_db_client_or_none] = _unavailable
        try:
            response = client.get(
                "/timeline/view",
                params={"pathway_id": _REAL_LOOKING_UUID, "pathway_name": "B.Tech (CSE)"},
            )
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert "trouble reaching our data" in response.text
        assert "try again shortly" in response.text
        # The calculator itself still renders, blank, zero-JS -- a
        # student can keep using it even while the lookup is down.
        assert 'name="stage_name_1"' in response.text
        assert "<script" not in response.text

    def test_pathway_not_found_falls_back_to_the_query_param_name(self) -> None:
        """A stale or mistyped link (a well-formed UUID that matches no
        row) must not blank out a `pathway_name` the caller already
        supplied -- same "degrade to what was already there" convention
        as UI-7's own not-a-UUID case."""

        def _empty_db() -> Iterator[Client | None]:
            yield _FakeDbClient({"pathways": [], "claims": [], "sources": []})  # type: ignore[arg-type]

        app.dependency_overrides[_db_client_or_none] = _empty_db
        try:
            response = client.get(
                "/timeline/view",
                params={"pathway_id": _REAL_LOOKING_UUID, "pathway_name": "B.Tech (CSE)"},
            )
        finally:
            app.dependency_overrides.pop(_db_client_or_none, None)
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert "B.Tech (CSE)" in response.text
        assert response.text.count('name="stage_name_1"') == 1  # still the blank calculator

    def test_pathway_id_without_a_name_falls_back_to_a_generic_label(self) -> None:
        response = client.get("/timeline/view", params={"pathway_id": "abc-123"})
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert "this pathway" in response.text

    def test_standalone_mode_is_unaffected_when_no_pathway_id_is_given(self) -> None:
        response = client.get("/timeline/view")
        assert response.status_code == 200
        assert "A standalone what-if calculator" in response.text
        assert "Planning around" not in response.text

    def test_pathway_context_persists_across_a_post_round_trip(self) -> None:
        response = client.post(
            "/timeline/view",
            data={
                "pathway_id": "abc-123",
                "pathway_name": "B.Tech (CSE)",
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "action": "calculate",
            },
        )
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert "B.Tech (CSE)" in response.text
