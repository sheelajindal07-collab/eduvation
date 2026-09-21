"""GET /requirements/view — docs/UI.md "Requirements" screen (UI-2's
split of the former monolithic `app/web/pages.py`).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.api.eligibility import EligibilityResponse, check_eligibility
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _float_or_none,
    _int_or_none,
    _looks_like_a_uuid,
    templates,
)

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


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
    exactly the way app/web/compare_pages.py's compare_page calls
    `assemble_comparisons()`: one fetch/rule-evaluation, reused, never a
    second copy of the eligibility logic or an HTTP round-trip to our
    own JSON route.

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
    same as compare_page -- see `app.web.common._db_client_or_none`.

    `age`/`marks_percentage` are read as raw strings and parsed by hand
    (`_int_or_none`/`_float_or_none`, the same pattern
    `timeline_calculate` in app/web/timeline_pages.py already uses for
    its own form fields) rather than typed as `int | None`/`float | None`
    query parameters -- a non-numeric value for either used to be
    rejected by FastAPI's own request validation before this function's
    body ever ran, surfacing a raw JSON 422 for a value a human typed
    into a page, not a request they hand-crafted. An unparseable value is
    simply "not provided", same as an omitted one.

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
