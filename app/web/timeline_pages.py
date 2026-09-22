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

UI-7 adds two things, both still zero-JS and still with no `Depends(
get_db_client)` anywhere in this module (no data dependency -- the
"extra attempt" rows below are exactly as self-contained as the fixed
stage rows they sit alongside):

- `pathway_id`/`pathway_name`, an OPTIONAL pair of query params (GET) /
  hidden fields (POST) a future linking screen can pass so this page
  shows which pathway the student was exploring. Display-only -- never
  looked up from the database here, and never required: with neither
  present this page is exactly the standalone calculator it always was
  (`pathway_id is None` is the "standalone" case every existing test
  exercises).
- "Revise this scenario" (docs/UI.md "Timeline & cost": "A failed
  attempt offers 'Revise this scenario', not a failure badge") -- a
  second submit button, `name="action" value="revise"`, that appends one
  more "extra attempt" stage row bounded by `_TIMELINE_EXTRA_ROWS_MAX`
  the same way the fixed rows above are bounded by
  `_TIMELINE_STAGE_ROWS`. The new row is already named ("Extra attempt
  N") but has no duration yet, so `compute_timeline`'s own existing
  "any unknown duration makes the total unknown" rule (app/rules/
  timeline.py) already makes the total honestly go back to "unknown"
  the moment it's added -- nothing extra to implement or to break here.
  Every extra-attempt stage is tagged `kind="user_assumption"`
  (app/rules/timeline.py's `Stage.kind`), the third of the three kinds
  `timeline_calculator.html` now shows distinguishably alongside
  "required" and "optional".
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.rules.timeline import ParallelActivity, Stage, TimelineResult, compute_timeline
from app.web.common import _form_str, _int_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

_TIMELINE_STAGE_ROWS = 6
_TIMELINE_PARALLEL_ROWS = 3
_TIMELINE_EXTRA_ROWS_MAX = 6
"""Cap on "Revise this scenario" clicks per request, same reasoning as
`_TIMELINE_STAGE_ROWS` itself: a bounded, server-rendered number of rows
is this screen's zero-JS equivalent of "add a row" -- an unbounded list
would need JavaScript to grow client-side."""


def _blank_stage_rows() -> list[dict[str, Any]]:
    return [
        {"name": "", "duration_weeks": "", "required": True, "overlap_weeks_with_previous": ""}
        for _ in range(_TIMELINE_STAGE_ROWS)
    ]


def _blank_parallel_rows() -> list[dict[str, Any]]:
    return [{"name": "", "duration_weeks": ""} for _ in range(_TIMELINE_PARALLEL_ROWS)]


@router.get("/timeline/view")
def timeline_page(
    request: Request,
    pathway_id: str | None = Query(default=None),
    pathway_name: str | None = Query(default=None),
) -> Any:
    return templates.TemplateResponse(
        request,
        "timeline_calculator.html",
        {
            "error": None,
            "result": None,
            "unknown_stage_names": [],
            "stage_rows": _blank_stage_rows(),
            "parallel_rows": _blank_parallel_rows(),
            "extra_rows": [],
            "num_extra_rows": 0,
            "max_extra_rows": _TIMELINE_EXTRA_ROWS_MAX,
            "pathway_id": (pathway_id or "").strip() or None,
            "pathway_name": (pathway_name or "").strip() or None,
        },
    )


@router.post("/timeline/view")
async def timeline_calculate(request: Request) -> Any:
    """Stateless, same as POST /timeline itself -- no `Depends(get_db_
    client)` here at all, since compute_timeline() takes only what the
    student just typed into this form."""
    form = await request.form()

    # `name="action" value="calculate"|"revise"` -- two submit buttons on
    # one form (docs/UI.md "one primary action per screen": "Calculate
    # timeline" stays primary, "Revise this scenario" is secondary).
    # Anything else (a hand-edited submission, an old test with no
    # `action` field at all) behaves exactly like "calculate" always
    # did -- this field is additive, not a new requirement.
    action = _form_str(form, "action").strip() or "calculate"
    pathway_id = _form_str(form, "pathway_id").strip() or None
    pathway_name = _form_str(form, "pathway_name").strip() or None

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
                kind="required" if required else "optional",
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

    # "Extra attempt" rows -- UI-7's "Revise this scenario". Bounded the
    # same way the fixed stage rows above are (`_TIMELINE_EXTRA_ROWS_MAX`
    # instead of `_TIMELINE_STAGE_ROWS`), and read/echoed the same way:
    # a blank name is ignored, a filled one becomes a real Stage.
    num_extra_rows = _int_or_none(_form_str(form, "num_extra_rows")) or 0
    num_extra_rows = max(0, min(num_extra_rows, _TIMELINE_EXTRA_ROWS_MAX))

    extra_rows: list[dict[str, Any]] = []
    for i in range(1, num_extra_rows + 1):
        name = _form_str(form, f"stage_extra_name_{i}").strip()
        duration_raw = _form_str(form, f"stage_extra_duration_weeks_{i}")
        extra_rows.append({"name": name, "duration_weeks": duration_raw})
        if not name:
            continue
        stages.append(
            Stage(name=name, duration_weeks=_int_or_none(duration_raw), kind="user_assumption")
        )

    if action == "revise" and num_extra_rows < _TIMELINE_EXTRA_ROWS_MAX:
        # Never framed as a failure (docs/UI.md "Timeline & cost"): an
        # extra attempt, a gap year, another try at an entrance exam is
        # a normal, expected part of planning, not a setback. The new
        # row is already named -- so it is a real stage, not a row the
        # "blank rows are ignored" convention above would skip -- but
        # has no duration yet, so the total correctly goes back to
        # "unknown" via compute_timeline's own existing rule the moment
        # it appears, exactly like any other stage the student hasn't
        # filled in yet.
        num_extra_rows += 1
        new_name = f"Extra attempt {num_extra_rows}"
        extra_rows.append({"name": new_name, "duration_weeks": ""})
        stages.append(Stage(name=new_name, duration_weeks=None, kind="user_assumption"))

    base_context = {
        "stage_rows": stage_rows,
        "parallel_rows": parallel_rows,
        "extra_rows": extra_rows,
        "num_extra_rows": num_extra_rows,
        "max_extra_rows": _TIMELINE_EXTRA_ROWS_MAX,
        "pathway_id": pathway_id,
        "pathway_name": pathway_name,
    }

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
