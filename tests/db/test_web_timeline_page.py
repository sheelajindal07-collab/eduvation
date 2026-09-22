"""Live end-to-end tests for RULES-9's `GET /timeline/view?pathway_id=`
prefill -- same seeding pattern as tests/db/test_web_pages.py. The one
property that specifically needs a REAL local Postgres round-trip (not
just a pure unit test over hand-built `Claim` objects, which
tests/unit/test_timeline_assembly.py already covers) is: a genuinely
seeded, genuinely DRAFT `stage:<n>:duration_weeks` claim -- written and
read back through Postgres/PostgREST/RLS exactly like a real reviewer's
draft would be -- must still leave its stage visible with an unknown
duration, and the calculator's own total must go to "unknown" the
moment that stage is part of the plan.
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

_SOURCE_NAME = run_name("RULES-9 TIMELINE PREFILL SOURCE (fixture)")


@pytest.fixture
def timeline_pathway(admin_client: Client) -> Iterator[dict[str, Any]]:
    """A real pathway with two published `stage:*:name` claims: stage 1
    is fully published (name + duration), stage 2's `name` is published
    but its `duration_weeks` is left in `draft` -- the exact "we know
    the stage exists, we don't yet know how long it takes" case this
    task's convention exists for."""
    official_source = (
        admin_client.table("sources")
        .insert(
            {
                "authority_name": _SOURCE_NAME,
                "official_url": "https://example.invalid/rules-9-timeline-prefill-source",
                "source_type": "official",
            }
        )
        .execute()
        .data[0]
    )
    career = (
        admin_client.table("careers")
        .insert({"name": run_name("RULES-9 timeline prefill career")})
        .execute()
        .data[0]
    )
    pathway = (
        admin_client.table("pathways")
        .insert(
            {
                "career_id": career["id"],
                "name": run_name("RULES-9 timeline prefill pathway"),
                "description": "Seeded by tests/db/test_web_timeline_page.py",
            }
        )
        .execute()
        .data[0]
    )

    def _insert_claim(field: str, value: Any, status: str) -> dict[str, Any]:
        row: dict[str, Any] = (
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
                    "status": status,
                    "review_due_date": "2099-01-01",
                }
            )
            .execute()
            .data[0]
        )
        return row

    claims = [
        _insert_claim("stage:1:name", "Class 12", "published"),
        _insert_claim("stage:1:duration_weeks", 52, "published"),
        _insert_claim("stage:2:name", "Bachelor's degree", "published"),
        # The one claim this fixture exists for: a real DRAFT row.
        _insert_claim("stage:2:duration_weeks", 208, "draft"),
    ]

    yield {"career": career, "pathway": pathway, "source": official_source}

    for claim in claims:
        admin_client.table("claims").delete().eq("id", claim["id"]).execute()
    admin_client.table("pathways").delete().eq("id", pathway["id"]).execute()
    admin_client.table("careers").delete().eq("id", career["id"]).execute()
    admin_client.table("sources").delete().eq("id", official_source["id"]).execute()


class TestTimelinePrefillFromRealPathway:
    def test_get_prefills_stage_rows_and_the_real_pathway_name(
        self, timeline_pathway: dict[str, Any]
    ) -> None:
        response = client.get(
            "/timeline/view", params={"pathway_id": timeline_pathway["pathway"]["id"]}
        )
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert timeline_pathway["pathway"]["name"] in response.text
        assert 'value="Class 12"' in response.text
        assert re.search(r'id="stage_duration_weeks_1"[^>]*value="52"', response.text)
        # Jinja autoescapes the apostrophe to &#39; in rendered HTML (see
        # tests/db/test_web_pages.py's identical comment on the same
        # class of assertion).
        assert "value=\"Bachelor&#39;s degree\"" in response.text
        assert "<script" not in response.text

    def test_the_draft_durations_input_is_left_blank_not_the_literal_none(
        self, timeline_pathway: dict[str, Any]
    ) -> None:
        """The safety-critical part: stage 2's NAME is published (so the
        student sees the stage exists) but its DURATION claim is still
        `draft` -- the duration input must render blank, never the
        literal string "None"."""
        response = client.get(
            "/timeline/view", params={"pathway_id": timeline_pathway["pathway"]["id"]}
        )
        assert response.status_code == 200
        assert re.search(r'id="stage_duration_weeks_2"[^>]*value=""', response.text)
        assert "None" not in response.text

    def test_a_query_param_pathway_name_is_overridden_by_the_real_fetched_name(
        self, timeline_pathway: dict[str, Any]
    ) -> None:
        """RULES-9: once the database is reachable and the id is real,
        the fetched name wins over a (possibly stale/spoofed) query
        param -- unlike the not-found/unreachable cases, which still
        fall back to whatever the caller supplied."""
        response = client.get(
            "/timeline/view",
            params={
                "pathway_id": timeline_pathway["pathway"]["id"],
                "pathway_name": "A completely different, made-up name",
            },
        )
        assert response.status_code == 200
        assert timeline_pathway["pathway"]["name"] in response.text
        assert "A completely different, made-up name" not in response.text

    def test_calculating_the_prefilled_plan_immediately_shows_total_unavailable(
        self, timeline_pathway: dict[str, Any]
    ) -> None:
        """End-to-end proof of this codebase's core rule, through a real
        seeded draft claim: a stage with an unknown duration makes the
        WHOLE total unavailable, never a partial/confident-looking
        number that quietly excludes stage 2. Submits exactly the values
        GET just prefilled -- simulating a student clicking "Calculate
        timeline" immediately, without editing anything."""
        response = client.post(
            "/timeline/view",
            data={
                "pathway_id": timeline_pathway["pathway"]["id"],
                "pathway_name": timeline_pathway["pathway"]["name"],
                "stage_name_1": "Class 12",
                "stage_duration_weeks_1": "52",
                "stage_required_1": "on",
                "stage_name_2": "Bachelor's degree",
                "stage_duration_weeks_2": "",
                "stage_required_2": "on",
                "action": "calculate",
            },
        )
        assert response.status_code == 200
        assert "Total not available yet" in response.text
        assert "Missing a duration for: Bachelor&#39;s degree" in response.text

    def test_nonexistent_pathway_id_falls_back_to_the_generic_label_not_a_500(self) -> None:
        response = client.get(
            "/timeline/view",
            params={"pathway_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert response.status_code == 200
        assert "Planning around" in response.text
        assert "this pathway" in response.text
        # Still the blank, standalone-shaped calculator -- nothing to prefill.
        assert 'name="stage_name_1"' in response.text
