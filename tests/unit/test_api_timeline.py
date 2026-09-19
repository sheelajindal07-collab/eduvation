"""Tests for POST /timeline (app/api/timeline.py) via TestClient.

Stateless — no database involved — so these live in tests/unit/, not
tests/db/, and exercise the real HTTP layer over app/rules/timeline.py
(already unit-tested directly in tests/unit/test_timeline.py). The point
here is the wiring: request parsing, response shape, and the
ValueError -> HTTP 400 boundary, not re-proving the engine's own logic.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestTimelineEndpointHappyPath:
    def test_sequential_stages_sum(self) -> None:
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {"name": "Class 12", "duration_weeks": 52},
                    {"name": "Entrance prep", "duration_weeks": 26},
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] == 78
        assert body["complete"] is True
        assert body["unknown_stage_names"] == []

    def test_overlap_is_subtracted(self) -> None:
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {"name": "Final semester", "duration_weeks": 20},
                    {
                        "name": "Internship",
                        "duration_weeks": 12,
                        "overlap_weeks_with_previous": 8,
                    },
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] == 20 + 12 - 8

    def test_empty_stages_list(self) -> None:
        response = client.post("/timeline", json={"stages": []})
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] is None
        assert body["complete"] is False


class TestTimelineEndpointUnknownDuration:
    def test_unknown_stage_gives_none_total_and_names_it(self) -> None:
        """The core safety property, exercised through the actual HTTP
        response shape: an unknown stage must be nameable by the client,
        not just silently absent from the total."""
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {"name": "Class 12", "duration_weeks": 52},
                    {"name": "Entrance prep (TBD)", "duration_weeks": None},
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] is None
        assert body["complete"] is False
        assert "Entrance prep (TBD)" in body["unknown_stage_names"]

    def test_duration_field_can_be_omitted_entirely(self) -> None:
        """duration_weeks defaults to None when omitted, not a validation
        error — matches how a client editing a partially-filled form
        would actually send the request."""
        response = client.post("/timeline", json={"stages": [{"name": "Unplanned stage"}]})
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] is None


class TestTimelineEndpointOverlapValidation:
    def test_overlap_exceeding_stage_duration_returns_400_not_500(self) -> None:
        """A content-authoring error (Build Pack: overlap must not
        exceed either adjacent stage) must surface as a clean 400 with
        an explanation, never a raw 500 or a silently wrong total."""
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {"name": "Stage A", "duration_weeks": 4},
                    {"name": "Stage B", "duration_weeks": 10, "overlap_weeks_with_previous": 20},
                ]
            },
        )
        assert response.status_code == 400
        assert "overlap" in response.json()["detail"].lower()

    def test_overlap_on_first_stage_returns_400(self) -> None:
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {"name": "Only stage", "duration_weeks": 10, "overlap_weeks_with_previous": 2}
                ]
            },
        )
        assert response.status_code == 400


class TestParallelActivities:
    def test_parallel_activity_visible_but_excluded_from_total(self) -> None:
        response = client.post(
            "/timeline",
            json={
                "stages": [{"name": "Degree", "duration_weeks": 100}],
                "parallel_activities": [
                    {"name": "Part-time certification", "duration_weeks": 40}
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_weeks"] == 100
        assert len(body["parallel_activities"]) == 1
        assert body["parallel_activities"][0]["name"] == "Part-time certification"


class TestSourceClaimIdRoundTrips:
    def test_source_claim_id_passed_through_unchanged(self) -> None:
        """A stage seeded from a real claim keeps its citation through
        the calculator round-trip — the UI needs this to show "Report an
        issue" against the right claim (docs/UI.md)."""
        response = client.post(
            "/timeline",
            json={
                "stages": [
                    {
                        "name": "MBBS",
                        "duration_weeks": 286,
                        "source_claim_id": "claim-abc-123",
                    }
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["stages"][0]["source_claim_id"] == "claim-abc-123"
