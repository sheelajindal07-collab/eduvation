"""GET/POST /requirements/view — docs/UI.md "Requirements" screen (UI-2's
split of the former monolithic `app/web/pages.py`).

SEC-5: personal inputs (age, marks_percentage, subjects_studied,
domicile_state, date_of_birth) are POST-only, never a query param —
docs/CONTRACTS.md's frozen "Every personal input ... is POST-only" rule,
made true for this screen. GET keeps `pathway_id` only and renders the
screen's normal starting state (every criterion "insufficient_information",
the pathway's name and requirement list, nothing about the student yet).
Submitting the form POSTs `pathway_id` plus whatever personal fields the
student filled in, and the SAME path renders the results directly in its
response — "POST-and-render", not a redirect — so no personal value is
ever carried in a URL, a `Location` header, browser history or a
bookmarked/shared link. Same GET/POST split already used by
app/web/timeline_pages.py's own two routes over one path.

RULES-16: `date_of_birth` gets the same treatment as every other personal
field above (POST body only), plus three stricter guarantees
docs/CONTRACTS.md "Duration, dates, cycle, DOB" spells out for it by name
and this module's own CLAUDE.md treats as absolute: it is never written
anywhere (no cookie, no session, no database row from this route — it is
forwarded straight to `check_eligibility`'s keyword-only `date_of_birth`
argument and nowhere else), never logged (no `logging` call exists in
this module, and none may be added that takes this value or any request
form data), and never echoed into a link (this screen is POST-and-render,
so the only place it can appear at all is back inside the resubmittable
form's own `value="..."` attribute — never a `href`, a `Location` header
or a query string). A malformed value (garbage text, a future date, an
implausibly old one) degrades to a friendly in-page message via
`_parse_date_of_birth` below, the same "never a raw 422" convention
`_int_or_none`/`_float_or_none` already established for `age`/
`marks_percentage` on this exact screen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.api.eligibility import (
    MAX_AGE_YEARS,
    EligibilityResponse,
    check_eligibility,
    today_ist,
)
from app.data.jurisdictions import ALL_JURISDICTIONS
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _float_or_none,
    _form_str,
    _int_or_none,
    _looks_like_a_uuid,
)
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


def _none_if_blank(raw: str) -> str | None:
    """A submitted-but-empty form field (e.g. SCOPE-5's domicile
    `<select>` left on its blank default option, or a text field
    submitted empty) means "not provided" — same convention as
    `app.web.common._int_or_none`/`_float_or_none`, kept local here
    since this one is a plain string, not a number to parse."""
    text = raw.strip()
    return text if text else None


def _parse_date_of_birth(raw: str) -> tuple[date | None, str | None]:
    """A submitted `date_of_birth` -> `(parsed value, friendly error)`.

    Same bounds as `app.api.eligibility.EligibilityCheckRequest`'s own
    `date_of_birth` validator (read, not modified, per this task's
    scope) — a future date, garbage text, or a date implying an age over
    `MAX_AGE_YEARS` — but degrades to a friendly in-page message instead
    of that route's clean 422, matching `_int_or_none`/`_float_or_none`'s
    own "never surface a raw validation error to a human-clicked-a-page
    request" convention for `age`/`marks_percentage` on this same screen.
    A blank submission is "not provided", not an error, same as those two.
    """
    text = raw.strip()
    if not text:
        return None, None
    try:
        value = date.fromisoformat(text)
    except ValueError:
        return None, "That date of birth doesn't look valid. Please enter a real date."
    today = today_ist()
    if value > today:
        return None, "Date of birth can't be in the future."
    if value.year < today.year - MAX_AGE_YEARS:
        return None, "That date of birth looks too far in the past. Please check it."
    return value, None


def _render_requirements(
    request: Request,
    db: Client | None,
    pathway_id: str | None,
    age: int | None,
    marks_percentage: float | None,
    subjects_studied: str | None,
    domicile_state: str | None,
    *,
    date_of_birth: date | None = None,
    dob_error: str | None = None,
) -> Any:
    """Shared by GET (pathway_id only) and POST (every field) below --
    the render path is identical either way; only where the input came
    from differs. Same fallbacks the old single GET handler already
    had: a DB that's down or unconfigured, and a missing/malformed
    pathway_id (entity_id is a `uuid` column -- db/migrations/
    0001_init.sql -- so an unvalidated garbled id would otherwise reach
    Postgres raw and crash), both degrade to the same friendly template
    compare_page already uses for its own equivalent cases.

    `date_of_birth` (RULES-16) is forwarded to `check_eligibility`'s own
    keyword-only argument of the same name and to nowhere else -- see
    this module's own docstring for the exact never-stored/never-logged/
    never-in-a-link guarantees that make it different from every field
    above it. `dob_error` is a friendly message for a value
    `_parse_date_of_birth` rejected (GET never has one, since GET has no
    date_of_birth input at all).
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
                "date_of_birth": date_of_birth,
                "dob_error": dob_error,
                "jurisdictions": ALL_JURISDICTIONS,
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
                "date_of_birth": date_of_birth,
                "dob_error": dob_error,
                "jurisdictions": ALL_JURISDICTIONS,
            },
        )

    result: EligibilityResponse = check_eligibility(
        pathway_id,
        age,
        marks_percentage,
        subjects_studied,
        domicile_state,
        db,
        date_of_birth=date_of_birth,
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
            "date_of_birth": date_of_birth,
            "dob_error": dob_error,
            "jurisdictions": ALL_JURISDICTIONS,
            "today_iso": today_ist().isoformat(),
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
    anything). `date_of_birth` is no exception: this route has no such
    query parameter to bind to, so nothing a hand-edited link tacks on
    can ever reach `check_eligibility`.
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

    `date_of_birth` (RULES-16) gets its own parser, `_parse_date_of_birth`,
    rather than `_int_or_none`'s shape: a malformed date still needs a
    friendly message (`dob_error`) rather than silently becoming "not
    provided" the way a malformed age does, since a future or wildly
    implausible date is worth telling the student about, not just
    dropping.
    """
    form = await request.form()
    pathway_id = _none_if_blank(_form_str(form, "pathway_id"))
    age = _int_or_none(_form_str(form, "age"))
    marks_percentage = _float_or_none(_form_str(form, "marks_percentage"))
    subjects_studied = _none_if_blank(_form_str(form, "subjects_studied"))
    domicile_state = _none_if_blank(_form_str(form, "domicile_state"))
    date_of_birth, dob_error = _parse_date_of_birth(_form_str(form, "date_of_birth"))
    return _render_requirements(
        request,
        db,
        pathway_id,
        age,
        marks_percentage,
        subjects_studied,
        domicile_state,
        date_of_birth=date_of_birth,
        dob_error=dob_error,
    )
