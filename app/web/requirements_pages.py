"""GET/POST /requirements/view — docs/UI.md "Requirements" screen (UI-2's
split of the former monolithic `app/web/pages.py`).

SEC-5: personal inputs (age, marks_percentage, subjects_studied,
domicile_state) are POST-only, never a query param — docs/CONTRACTS.md's
frozen "Every personal input ... is POST-only" rule, made true for this
screen. GET keeps `pathway_id` only and renders the screen's normal
starting state (every criterion "insufficient_information", the
pathway's name and requirement list, nothing about the student yet).
Submitting the form POSTs `pathway_id` plus whatever personal fields the
student filled in, and the SAME path renders the results directly in its
response — "POST-and-render", not a redirect — so no personal value is
ever carried in a URL, a `Location` header, browser history or a
bookmarked/shared link. Same GET/POST split already used by
app/web/timeline_pages.py's own two routes over one path.
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
    _form_str,
    _int_or_none,
    _looks_like_a_uuid,
    templates,
)

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


def _none_if_blank(raw: str) -> str | None:
    """A submitted-but-empty form field means "not provided" — same
    convention as `app.web.common._int_or_none`/`_float_or_none`, kept
    local here since this one is a plain string, not a number to
    parse."""
    text = raw.strip()
    return text if text else None


def _render_requirements(
    request: Request,
    db: Client | None,
    pathway_id: str | None,
    age: int | None,
    marks_percentage: float | None,
    subjects_studied: str | None,
    domicile_state: str | None,
) -> Any:
    """Shared by GET (pathway_id only) and POST (every field) below --
    the render path is identical either way; only where the input came
    from differs. Same fallbacks the old single GET handler already
    had: a DB that's down or unconfigured, and a missing/malformed
    pathway_id (entity_id is a `uuid` column -- db/migrations/
    0001_init.sql -- so an unvalidated garbled id would otherwise reach
    Postgres raw and crash), both degrade to the same friendly template
    compare_page already uses for its own equivalent cases.
    """
    if db is None:
        return templates.TemplateResponse(
            request,
            "requirements.html",
            {
                "error": _DB_UNAVAILABLE_MESSAGE,
                "pathway_id": pathway_id or "",
                "pathway_name": None,
                "result": None,
                "age": age,
                "marks_percentage": marks_percentage,
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
                "age": age,
                "marks_percentage": marks_percentage,
                "subjects_studied": subjects_studied,
                "domicile_state": domicile_state,
            },
        )

    result: EligibilityResponse = check_eligibility(
        pathway_id, age, marks_percentage, subjects_studied, domicile_state, db
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
            "age": age,
            "marks_percentage": marks_percentage,
            "subjects_studied": subjects_studied,
            "domicile_state": domicile_state,
        },
    )


@router.get("/requirements/view")
def requirements_page(
    request: Request,
    pathway_id: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """`pathway_id` only -- SEC-5: no personal input may ever be a query
    param. Every field is blank on load -- the screen's normal starting
    state, not an error (shows what each requirement IS via
    `insufficient_information` outcomes, before the student has entered
    anything).
    """
    return _render_requirements(request, db, pathway_id, None, None, None, None)


@router.post("/requirements/view")
async def requirements_submit(
    request: Request,
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """POST-and-render (SEC-5): the student's own details never leave
    the request body -- no redirect, so nothing personal ever reaches a
    URL, a `Location` header or browser history. `pathway_id` travels
    as a hidden form field alongside the personal ones here, not as a
    query param, matching app/web/timeline_pages.py's own POST handler
    (`await request.form()` plus the same `_form_str`/`_int_or_none`
    parsing helpers, since a hand-edited/malformed submission must
    degrade the same friendly way an omitted one already does, not
    surface a raw 422).
    """
    form = await request.form()
    pathway_id = _none_if_blank(_form_str(form, "pathway_id"))
    age = _int_or_none(_form_str(form, "age"))
    marks_percentage = _float_or_none(_form_str(form, "marks_percentage"))
    subjects_studied = _none_if_blank(_form_str(form, "subjects_studied"))
    domicile_state = _none_if_blank(_form_str(form, "domicile_state"))
    return _render_requirements(
        request, db, pathway_id, age, marks_percentage, subjects_studied, domicile_state
    )
