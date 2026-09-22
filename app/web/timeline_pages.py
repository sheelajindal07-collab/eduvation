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

UI-7 added `pathway_id`/`pathway_name`, an OPTIONAL pair of query params
(GET) / hidden fields (POST), as DISPLAY-ONLY context with no database
lookup at all, and flagged wiring a real prefill as a follow-up. RULES-9
is that follow-up, for GET only:

- `GET /timeline/view?pathway_id=<uuid>` now has a real
  `Depends(_db_client_or_none)` and, when the id is a well-formed UUID
  and the database is reachable, fetches that pathway's real name and
  its published timeline-stage claims
  (`app/planning/timeline_assembly.py`'s `stages_from_claims`), then
  pre-fills the calculator's stage rows with them. The fetched pathway
  name wins over a same-named query param (a query param can be
  spoofed/stale; the database is the source of truth once it is
  reachable) — the query param remains the ONLY source when the id
  isn't a real UUID, the pathway row doesn't exist, or the database is
  unavailable, so every one of UI-7's own display-only-context tests
  (which never configure a database) keeps passing unchanged. A DB
  outage degrades to the same friendly `_DB_UNAVAILABLE_MESSAGE` every
  other screen in this codebase already shows
  (`app/db/client.py`'s `SupabaseNotConfiguredError` — caught one layer
  up, inside `_db_client_or_none` itself, per its own docstring) rather
  than a 500 — the calculator itself still renders, blank, so a student
  can keep using it even while the lookup is down. Prefill is capped at
  `_TIMELINE_STAGE_ROWS`, the same bounded-rows architecture this screen
  already uses everywhere else on this page.
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

POST stays exactly as stateless as it always was: NO `Depends(
get_db_client)` here at all, since `compute_timeline()` takes only what
the student's own form submission carries (a stage list seeded from a
GET prefill or typed by hand, either way already in the request body).
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.api.eligibility import today_ist
from app.data.models import Claim, ClaimStatus, Source, SourceType
from app.planning.timeline_assembly import stages_from_claims
from app.rules.timeline import (
    ParallelActivity,
    Stage,
    TimelineResult,
    TimelineValidationError,
    compute_timeline,
)
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _form_str,
    _int_or_none,
    _looks_like_a_uuid,
)
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


def _row_to_source(row: dict[str, Any]) -> Source:
    """Identical to app/api/compare.py's/app/api/eligibility.py's helper
    of the same name -- kept file-local rather than shared, matching this
    codebase's convention of not coupling otherwise-unrelated route files
    over a few lines."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """Identical to app/api/compare.py's/app/api/eligibility.py's helper
    of the same name -- same file-local convention as `_row_to_source`
    above. Needed to call app/planning/timeline_assembly.py's
    `stages_from_claims()`, which (via `field_value_for`) takes real
    `Claim`/`Source` objects, not the raw row dicts PostgREST returns."""
    return Claim(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        field=row["field"],
        value=row["value"],
        source_id=row["source_id"],
        verification_date=row["verification_date"],
        verifier=row["verifier"],
        status=ClaimStatus(row["status"]),
        review_due_date=row["review_due_date"],
        superseded_by=row.get("superseded_by"),
        approved_draft_version=row.get("approved_draft_version"),
        extracted_by=row.get("extracted_by", "human"),
    )


def _stage_rows_from_stages(stages: list[Stage]) -> list[dict[str, Any]]:
    """`Stage` objects (already gated/assembled by `stages_from_claims`)
    -> this screen's editable-row shape, the same dict shape
    `_blank_stage_rows()` and the POST handler's own echo both use.
    Capped at `_TIMELINE_STAGE_ROWS` -- the same bounded-rows cap this
    screen already applies to parallel activities and extra attempts;
    a pathway publishing more stages than that shows only the first
    `_TIMELINE_STAGE_ROWS`, in order.

    `duration_weeks` renders as `""` (never the string `"None"`) when
    `stages_from_claims` reports it unknown, matching the blank-row
    default -- the input is left empty for the student to fill in, not
    shown as a confusing literal "None".
    """
    rows = [
        {
            "name": stage.name,
            "duration_weeks": stage.duration_weeks if stage.duration_weeks is not None else "",
            "required": stage.required,
            "overlap_weeks_with_previous": stage.overlap_weeks_with_previous,
        }
        for stage in stages[:_TIMELINE_STAGE_ROWS]
    ]
    rows.extend(
        {"name": "", "duration_weeks": "", "required": True, "overlap_weeks_with_previous": ""}
        for _ in range(_TIMELINE_STAGE_ROWS - len(rows))
    )
    return rows


def _pathway_prefill(
    db: Client, pathway_id: str, *, as_of: date
) -> tuple[str | None, list[Stage]]:
    """`(pathway_name, published stages)` for a real pathway id, or
    `(None, [])` when the pathway itself has no row (a stale or
    mistyped link) -- the caller falls back to the query-param name (or
    the generic "this pathway" label) exactly as it did before this
    task, so a not-found id degrades the same friendly way it always
    has. Any OTHER database error is left to propagate, matching
    app/web/compare_pages.py's/app/web/requirements_pages.py's own
    scope: only `SupabaseNotConfiguredError` (handled one layer up, by
    `_db_client_or_none`) has an established "degrade, don't crash"
    convention in this codebase; a query that fails for some other
    reason is exactly as unexpected here as it would be on those two
    screens.
    """
    name_result = db.table("pathways").select("id, name").eq("id", pathway_id).execute()
    name_rows = cast("list[dict[str, Any]]", name_result.data)
    if not name_rows:
        return None, []
    pathway_name = name_rows[0]["name"]

    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .eq("entity_id", pathway_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)
    claims_by_field = {row["field"]: _row_to_claim(row) for row in claim_rows}

    source_ids = {row["source_id"] for row in claim_rows}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    stages = stages_from_claims(claims_by_field, sources_by_id, as_of=as_of)
    return pathway_name, stages


@router.get("/timeline/view")
def timeline_page(
    request: Request,
    pathway_id: str | None = Query(default=None),
    pathway_name: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    pathway_id = (pathway_id or "").strip() or None
    pathway_name = (pathway_name or "").strip() or None
    stage_rows = _blank_stage_rows()
    error = None

    if pathway_id is not None:
        if db is None:
            # Same friendly degradation every other screen already has
            # for an unconfigured/unreachable Supabase project -- the
            # calculator below still renders and still works, blank.
            error = _DB_UNAVAILABLE_MESSAGE
        elif _looks_like_a_uuid(pathway_id):
            fetched_name, stages = _pathway_prefill(db, pathway_id, as_of=today_ist())
            if fetched_name is not None:
                pathway_name = fetched_name
            if stages:
                stage_rows = _stage_rows_from_stages(stages)
        # A non-UUID pathway_id (e.g. a hand-typed or legacy link) is
        # left exactly as UI-7 treated it: display-only context, no
        # lookup attempted -- there is no real pathway id to query.

    return templates.TemplateResponse(
        request,
        "timeline_calculator.html",
        {
            "error": error,
            "result": None,
            "unknown_stage_names": [],
            "stage_rows": stage_rows,
            "parallel_rows": _blank_parallel_rows(),
            "extra_rows": [],
            "num_extra_rows": 0,
            "max_extra_rows": _TIMELINE_EXTRA_ROWS_MAX,
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
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
    except TimelineValidationError as exc:
        # An overlap exceeding a stage's own duration, or a negative
        # duration/overlap (RULES-9) -- app/api/timeline.py's own
        # docstring calls this a content-authoring error to surface, not
        # a student input to silently clamp. compute_timeline's message
        # already names the stages and weeks involved in plain language,
        # so it is shown as-is (through _states.html's `alert()` macro,
        # already wired into this template) rather than replaced with
        # something vaguer.
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
