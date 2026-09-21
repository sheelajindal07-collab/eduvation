"""Tests for GET/POST /timeline/view (app/web/pages.py) via TestClient.

Stateless -- no database involved, same reasoning as
tests/unit/test_api_timeline.py for POST /timeline itself -- this page
just wraps compute_timeline() with an HTML form/response layer, so these
live in tests/unit/, not tests/db/.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestTimelinePageGet:
    def test_get_shows_the_empty_form(self) -> None:
        response = client.get("/timeline/view")
        assert response.status_code == 200
        assert "Timeline calculator" in response.text
        assert 'name="stage_name_1"' in response.text
        assert 'name="stage_duration_weeks_1"' in response.text
        # No result section yet -- nothing has been submitted.
        assert "Missing a duration for" not in response.text


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
