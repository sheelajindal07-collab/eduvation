"""GET/POST /timeline/view — Career Life Span Calculator (UI-2's split of
the former monolithic `app/web/pages.py`).

Standalone and pathway-independent (app/api/timeline.py's own docstring:
"stages are 'editable milestones' the student adjusts interactively"). A
fixed number of blank stage/parallel-activity rows is this screen's
zero-JS equivalent of "add a row" -- docs/UI.md's "Editable milestones"
is about the numbers per stage being editable, not about an unbounded
list, which would need JavaScript to grow client-side. A row with a
blank name is ignored, same convention on GET (nothing filled in yet)
and POST (a row the student left untouched).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.rules.timeline import ParallelActivity, Stage, TimelineResult, compute_timeline
from app.web.common import _form_str, _int_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

_TIMELINE_STAGE_ROWS = 6
_TIMELINE_PARALLEL_ROWS = 3


def _blank_stage_rows() -> list[dict[str, Any]]:
    return [
        {"name": "", "duration_weeks": "", "required": True, "overlap_weeks_with_previous": ""}
        for _ in range(_TIMELINE_STAGE_ROWS)
    ]


def _blank_parallel_rows() -> list[dict[str, Any]]:
    return [{"name": "", "duration_weeks": ""} for _ in range(_TIMELINE_PARALLEL_ROWS)]


@router.get("/timeline/view")
def timeline_page(request: Request) -> Any:
    return templates.TemplateResponse(
        request,
        "timeline_calculator.html",
        {
            "error": None,
            "result": None,
            "unknown_stage_names": [],
            "stage_rows": _blank_stage_rows(),
            "parallel_rows": _blank_parallel_rows(),
        },
    )


@router.post("/timeline/view")
async def timeline_calculate(request: Request) -> Any:
    """Stateless, same as POST /timeline itself -- no `Depends(get_db_
    client)` here at all, since compute_timeline() takes only what the
    student just typed into this form."""
    form = await request.form()

    stage_rows: list[dict[str, Any]] = []
    stages: list[Stage] = []
    for i in range(1, _TIMELINE_STAGE_ROWS + 1):
        name = _form_str(form, f"stage_name_{i}").strip()
        duration_raw = _form_str(form, f"stage_duration_weeks_{i}")
        overlap_raw = _form_str(form, f"stage_overlap_weeks_with_previous_{i}")
        required = form.get(f"stage_required_{i}") is not None
        stage_rows.append(
            {
                "name": name,
                "duration_weeks": duration_raw,
                "required": required,
                "overlap_weeks_with_previous": overlap_raw,
            }
        )
        if not name:
            continue  # blank rows are ignored
        stages.append(
            Stage(
                name=name,
                duration_weeks=_int_or_none(duration_raw),
                required=required,
                overlap_weeks_with_previous=_int_or_none(overlap_raw) or 0,
            )
        )

    parallel_rows: list[dict[str, Any]] = []
    parallel: list[ParallelActivity] = []
    for i in range(1, _TIMELINE_PARALLEL_ROWS + 1):
        name = _form_str(form, f"parallel_name_{i}").strip()
        duration_raw = _form_str(form, f"parallel_duration_weeks_{i}")
        parallel_rows.append({"name": name, "duration_weeks": duration_raw})
        if not name:
            continue
        parallel.append(ParallelActivity(name=name, duration_weeks=_int_or_none(duration_raw)))

    base_context = {"stage_rows": stage_rows, "parallel_rows": parallel_rows}

    try:
        result: TimelineResult = compute_timeline(stages, parallel)
    except ValueError as exc:
        # An overlap exceeding a stage's own duration -- app/api/
        # timeline.py's own docstring calls this a content-authoring
        # error to surface, not a student input to silently clamp.
        # compute_timeline's message already names the stages and weeks
        # involved in plain language, so it is shown as-is rather than
        # replaced with something vaguer.
        return templates.TemplateResponse(
            request,
            "timeline_calculator.html",
            {**base_context, "error": str(exc), "result": None, "unknown_stage_names": []},
        )

    return templates.TemplateResponse(
        request,
        "timeline_calculator.html",
        {
            **base_context,
            "error": None,
            "result": result,
            "unknown_stage_names": [s.name for s in result.unknown],
        },
    )
