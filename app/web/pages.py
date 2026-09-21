"""Server-rendered HTML pages — the actual clickable journey docs/UI.md
describes (explore -> compare). This is the first real UI this whole
project has had; every route before this session returned JSON only.

Distinct paths from the JSON API (`/explore`, `/compare/view` vs.
`/careers`, `/compare`) rather than content negotiation on the same URL —
keeps the already-tested JSON contract completely untouched, and keeps
this module's only job as "render what the API already computes", never
a second copy of the fetch-and-assemble logic. `app.api.compare
.assemble_comparisons` is the one place that logic lives; both this
module and `app/api/compare.py`'s JSON route call it.
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import Client

from app.api.compare import MAX_PATHWAYS, MIN_PATHWAYS, assemble_comparisons
from app.api.deps import get_db_client
from app.api.eligibility import EligibilityResponse, check_eligibility
from app.db import SupabaseNotConfiguredError
from app.rules.timeline import ParallelActivity, Stage, TimelineResult, compute_timeline

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface
templates = Jinja2Templates(directory="app/web/templates")

# docs/UI.md "difficult states": a plain-language, visible status --
# never a generic error -- for the realistic "Weak connection" case.
# Shared by both routes below so a DB outage degrades the same way on
# both screens rather than inventing two different messages.
_DB_UNAVAILABLE_MESSAGE = (
    "We're having trouble reaching our data right now. Please try again shortly."
)


def _db_client_or_none(
    authorization: str | None = Header(default=None),
) -> Iterator[Client | None]:
    """Same contract as `app.api.deps.get_db_client`, except a Supabase
    misconfiguration (`SupabaseNotConfiguredError`) degrades to `None`
    instead of propagating out of dependency resolution -- which happens
    BEFORE a route function's body ever runs, so a plain try/except
    inside compare_page/requirements_page can't catch it; the route body
    can only react to what its dependency handed it. `get_db_client`'s
    own generator does the real work (bearer-token resolution, and the
    `finally: client.postgrest.aclose()` cleanup app/api/deps.py's
    docstring explains) -- advanced by hand here rather than
    reimplemented, so there is exactly one place either piece of logic
    lives. app/db/client.py's own docstring: "Callers should catch this
    and degrade gracefully" -- this is that catch, for the two pages
    that have a friendly template to fall back to."""
    gen = get_db_client(authorization)
    try:
        client = next(gen)
    except SupabaseNotConfiguredError:
        yield None
        return
    try:
        yield client
    finally:
        next(gen, None)  # resumes get_db_client() past its own `yield`, running its `finally`


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/explore")


@router.get("/explore")
def explore_page(request: Request, db: Client = Depends(get_db_client)) -> Any:
    """docs/UI.md "Career explorer" screen. Same two queries
    `GET /careers` already runs (app/api/explore.py) — kept as a direct
    call here rather than an HTTP round-trip to the JSON endpoint, same
    reasoning as `assemble_comparisons`: one fetch, reused, not
    duplicated or indirected through a second network hop."""
    careers_result = db.table("careers").select("id, name, nco_anchor").execute()
    pathways_result = db.table("pathways").select("id, career_id, name, description").execute()
    careers = cast("list[dict[str, Any]]", careers_result.data)
    pathways = cast("list[dict[str, Any]]", pathways_result.data)

    pathways_by_career: dict[str, list[dict[str, Any]]] = {}
    for pathway in pathways:
        pathways_by_career.setdefault(pathway["career_id"], []).append(pathway)

    careers_with_pathways = [
        {"career": career, "pathways": pathways_by_career.get(career["id"], [])}
        for career in careers
    ]
    return templates.TemplateResponse(
        request, "explore.html", {"careers_with_pathways": careers_with_pathways}
    )


def _looks_like_a_uuid(value: str) -> bool:
    try:
        uuid_module.UUID(value)
    except ValueError:
        return False
    return True


def _int_or_none(raw: str | None) -> int | None:
    """Shared by requirements_page (age) and timeline_calculate (stage/
    parallel-activity durations): not this module's job to validate
    typed input character-by-character -- a missing or unparsable value
    is simply "not provided", never guessed at, silently dropped, or
    (ux-qa-reviewer finding: age used to be a native `int | None` FastAPI
    query param, so a non-numeric value never even reached this
    function -- FastAPI's own request validation rejected it first with
    a raw JSON 422, before a human-clicked-a-page error page could ever
    show) a crash."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _float_or_none(raw: str | None) -> float | None:
    """Same contract as `_int_or_none`, for marks_percentage."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@router.get("/compare/view")
def compare_page(
    request: Request,
    pathway_id: list[str] = Query(default=[]),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """docs/UI.md "Comparison screen". A missing/wrong pathway_id count,
    OR a malformed id (ux-qa-reviewer finding, 2026-09-19: a truncated or
    garbled shared link -- very plausible for this product, sent over
    WhatsApp -- used to reach Postgres raw and crash to a bare 500 with
    no way back), renders the same friendly in-page message with a link
    to Explore (docs/UI.md "difficult states": explain, don't just
    error) rather than either the JSON API's plain 400 or an unhandled
    crash — a human clicked into this page, they didn't send a malformed
    request on purpose.

    A DB that's down or unconfigured (`db is None`, from
    `_db_client_or_none`) degrades to the same friendly template with a
    plain "temporarily unavailable" message, rather than the raw 500
    that used to propagate straight out of `Depends(get_db_client)`."""
    if db is None:
        return templates.TemplateResponse(
            request,
            "compare.html",
            {"error": _DB_UNAVAILABLE_MESSAGE, "comparisons": [], "pathway_names": {}},
        )

    invalid_shape = not all(_looks_like_a_uuid(pid) for pid in pathway_id)
    has_duplicates = len(set(pathway_id)) != len(pathway_id)
    # Security-review finding, 2026-09-20 (LOW): requesting the same
    # pathway_id twice passed the count check and silently rendered the
    # same pathway twice as if it were a real two-way comparison. A
    # human clicked into this page, so this degrades to the same
    # friendly message as a malformed/wrong-count id rather than
    # crashing or quietly showing a meaningless "comparison".
    if invalid_shape or has_duplicates or not (MIN_PATHWAYS <= len(pathway_id) <= MAX_PATHWAYS):
        return templates.TemplateResponse(
            request,
            "compare.html",
            {
                "error": f"Pick {MIN_PATHWAYS} or {MAX_PATHWAYS} pathways to compare.",
                "comparisons": [],
                "pathway_names": {},
            },
        )

    as_of = datetime.now(tz=UTC).date()
    comparisons = assemble_comparisons(db, pathway_id, as_of=as_of)

    names_result = db.table("pathways").select("id, name").in_("id", pathway_id).execute()
    pathway_names = {
        row["id"]: row["name"] for row in cast("list[dict[str, Any]]", names_result.data)
    }

    return templates.TemplateResponse(
        request,
        "compare.html",
        {"error": None, "comparisons": comparisons, "pathway_names": pathway_names},
    )


@router.get("/requirements/view")
def requirements_page(
    request: Request,
    pathway_id: str | None = Query(default=None),
    age: str | None = Query(default=None),
    marks_percentage: str | None = Query(default=None),
    subjects_studied: str | None = Query(
        default=None, description="Comma-separated, e.g. Physics,Chemistry,Biology"
    ),
    domicile_state: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """docs/UI.md "Requirements" screen -- a thin HTML layer over
    GET /eligibility's own `check_eligibility()`, called directly here
    exactly the way compare_page calls `assemble_comparisons()`: one
    fetch/rule-evaluation, reused, never a second copy of the eligibility
    logic or an HTTP round-trip to our own JSON route.

    Missing/malformed pathway_id degrades to the same friendly in-page
    message compare_page already uses for its own malformed-id case
    (entity_id is a `uuid` column -- db/migrations/0001_init.sql -- so an
    unvalidated garbled id would otherwise reach Postgres raw and crash).
    A well-formed but nonexistent pathway_id is NOT specially handled,
    same as compare_page: check_eligibility() simply finds no claims for
    it and returns a vacuous "meets" with no criteria, rendered as the
    same "no requirements published yet" state a real pathway with no
    eligibility claims would show.

    A DB that's down or unconfigured (`db is None`) degrades to the same
    friendly template with a plain "temporarily unavailable" message,
    same as compare_page -- see `_db_client_or_none`.

    `age`/`marks_percentage` are read as raw strings and parsed by hand
    (`_int_or_none`/`_float_or_none`, the same pattern
    `timeline_calculate` below already uses for its own form fields)
    rather than typed as `int | None`/`float | None` query parameters --
    a non-numeric value for either used to be rejected by FastAPI's own
    request validation before this function's body ever ran, surfacing a
    raw JSON 422 for a value a human typed into a page, not a request
    they hand-crafted. An unparseable value is simply "not provided",
    same as an omitted one.

    Every field is omitted by default (age/marks_percentage/
    subjects_studied/domicile_state all None) -- on first load that's
    exactly "pathway_id only", which is the point: it shows what the
    criteria ARE (name, explanation, source) via
    `insufficient_information` outcomes, before the student has entered
    anything. That is this screen's normal starting state, not an error.
    """
    age_value = _int_or_none(age)
    marks_percentage_value = _float_or_none(marks_percentage)

    if db is None:
        return templates.TemplateResponse(
            request,
            "requirements.html",
            {
                "error": _DB_UNAVAILABLE_MESSAGE,
                "pathway_id": pathway_id or "",
                "pathway_name": None,
                "result": None,
                "age": age_value,
                "marks_percentage": marks_percentage_value,
                "subjects_studied": subjects_studied,
                "domicile_state": domicile_state,
            },
        )

    if pathway_id is None or not _looks_like_a_uuid(pathway_id):
        return templates.TemplateResponse(
            request,
            "requirements.html",
            {
                "error": "That link doesn't point to a valid pathway.",
                "pathway_id": pathway_id or "",
                "pathway_name": None,
                "result": None,
                "age": age_value,
                "marks_percentage": marks_percentage_value,
                "subjects_studied": subjects_studied,
                "domicile_state": domicile_state,
            },
        )

    result: EligibilityResponse = check_eligibility(
        pathway_id=pathway_id,
        age=age_value,
        marks_percentage=marks_percentage_value,
        subjects_studied=subjects_studied,
        domicile_state=domicile_state,
        db=db,
    )

    name_result = db.table("pathways").select("id, name").eq("id", pathway_id).execute()
    name_rows = cast("list[dict[str, Any]]", name_result.data)
    pathway_name = name_rows[0]["name"] if name_rows else None

    return templates.TemplateResponse(
        request,
        "requirements.html",
        {
            "error": None,
            "pathway_id": pathway_id,
            "pathway_name": pathway_name,
            "result": result,
            "age": age_value,
            "marks_percentage": marks_percentage_value,
            "subjects_studied": subjects_studied,
            "domicile_state": domicile_state,
        },
    )


# ---------------------------------------------------------------------
# /timeline/view -- Career Life Span Calculator, standalone and
# pathway-independent (app/api/timeline.py's own docstring: "stages are
# 'editable milestones' the student adjusts interactively"). A fixed
# number of blank stage/parallel-activity rows is this screen's zero-JS
# equivalent of "add a row" -- docs/UI.md's "Editable milestones" is
# about the numbers per stage being editable, not about an unbounded
# list, which would need JavaScript to grow client-side. A row with a
# blank name is ignored, same convention on GET (nothing filled in yet)
# and POST (a row the student left untouched).
# ---------------------------------------------------------------------

_TIMELINE_STAGE_ROWS = 6
_TIMELINE_PARALLEL_ROWS = 3


def _blank_stage_rows() -> list[dict[str, Any]]:
    return [
        {"name": "", "duration_weeks": "", "required": True, "overlap_weeks_with_previous": ""}
        for _ in range(_TIMELINE_STAGE_ROWS)
    ]


def _blank_parallel_rows() -> list[dict[str, Any]]:
    return [{"name": "", "duration_weeks": ""} for _ in range(_TIMELINE_PARALLEL_ROWS)]


def _form_str(form: Any, key: str) -> str:
    """`FormData.get` can return `str | UploadFile | None` in general;
    every field on this form is a plain text/number/checkbox input, so
    anything else (or a missing key) is treated as blank rather than
    guessed at."""
    value = form.get(key)
    return value if isinstance(value, str) else ""


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
