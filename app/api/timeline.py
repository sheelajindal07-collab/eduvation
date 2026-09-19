"""POST /timeline — Career Life Span Calculator (Lite Build Pack §6,
docs/UI.md "Editable milestones").

Unlike /eligibility, this route does NOT look criteria up from stored
claims — stages are "editable milestones" the student adjusts
interactively (docs/UI.md: "assumptions editable without re-entering the
profile"), so the client sends the stage list it currently has (seeded
from a pathway's claims elsewhere, or edited by the student) and gets
back the computed total. Stateless: no database access in this route at
all, which is also why its tests live in tests/unit/, not tests/db/.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.rules.timeline import (
    ParallelActivity,
    Stage,
    TimelineResult,
    compute_timeline,
)

router = APIRouter(tags=["timeline"])


class StageIn(BaseModel):
    name: str
    duration_weeks: int | None = None
    required: bool = True
    overlap_weeks_with_previous: int = 0
    source_claim_id: str | None = None


class ParallelActivityIn(BaseModel):
    name: str
    duration_weeks: int | None = None
    source_claim_id: str | None = None


class TimelineRequest(BaseModel):
    stages: list[StageIn]
    parallel_activities: list[ParallelActivityIn] = []


class StageOut(BaseModel):
    name: str
    duration_weeks: int | None
    required: bool
    overlap_weeks_with_previous: int
    source_claim_id: str | None


class ParallelActivityOut(BaseModel):
    name: str
    duration_weeks: int | None
    source_claim_id: str | None


class TimelineResponse(BaseModel):
    stages: list[StageOut]
    parallel_activities: list[ParallelActivityOut]
    total_weeks: int | None
    complete: bool
    unknown_stage_names: list[str]
    """Names of stages with no duration yet — surfaced explicitly so the
    UI can prompt for them by name (docs/UI.md: "name the missing
    requirement, never guess"), same spirit as the eligibility route."""


def _to_response(result: TimelineResult) -> TimelineResponse:
    return TimelineResponse(
        stages=[
            StageOut(
                name=s.name,
                duration_weeks=s.duration_weeks,
                required=s.required,
                overlap_weeks_with_previous=s.overlap_weeks_with_previous,
                source_claim_id=s.source_claim_id,
            )
            for s in result.stages
        ],
        parallel_activities=[
            ParallelActivityOut(
                name=p.name, duration_weeks=p.duration_weeks, source_claim_id=p.source_claim_id
            )
            for p in result.parallel_activities
        ],
        total_weeks=result.total_weeks,
        complete=result.complete,
        unknown_stage_names=[s.name for s in result.unknown],
    )


@router.post("/timeline", response_model=TimelineResponse)
def compute_timeline_route(request: TimelineRequest) -> TimelineResponse:
    stages = [
        Stage(
            name=s.name,
            duration_weeks=s.duration_weeks,
            required=s.required,
            overlap_weeks_with_previous=s.overlap_weeks_with_previous,
            source_claim_id=s.source_claim_id,
        )
        for s in request.stages
    ]
    parallel = [
        ParallelActivity(
            name=p.name, duration_weeks=p.duration_weeks, source_claim_id=p.source_claim_id
        )
        for p in request.parallel_activities
    ]
    try:
        result = compute_timeline(stages, parallel)
    except ValueError as exc:
        # An overlap exceeding a stage's own duration is a content-
        # authoring error (app/rules/timeline.py's own docstring), not a
        # student input to silently clamp — surfaced as 400, not 500 or
        # a quietly-wrong total.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(result)
