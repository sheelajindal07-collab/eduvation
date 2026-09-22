"""GET /explore — docs/UI.md "Career explorer" screen (UI-2's split of
the former monolithic `app/web/pages.py`).

UI-3: `GET /` used to live here as a bare redirect to `/explore`. It is
now its own screen (`app/web/landing_pages.py`, "Find your next step"),
so this module goes back to owning exactly the one route its docstring
already named alongside the redirect -- `/explore` itself, unchanged.

A11Y-3: `Depends(get_db_client)` used to raise hard (`SupabaseNotConfiguredError`
propagating straight out of dependency resolution) whenever Supabase
wasn't configured or reachable -- the same class of bug FIX 6 already
fixed for `/compare/view` and `/requirements/view`. This screen now uses
`app/web/common.py`'s `_db_client_or_none` and the same
`_DB_UNAVAILABLE_MESSAGE` friendly alert those two screens already show,
rather than inventing a new message.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.web.common import _DB_UNAVAILABLE_MESSAGE, _db_client_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


@router.get("/explore")
def explore_page(request: Request, db: Client | None = Depends(_db_client_or_none)) -> Any:
    """docs/UI.md "Career explorer" screen. Same two queries
    `GET /careers` already runs (app/api/explore.py) — kept as a direct
    call here rather than an HTTP round-trip to the JSON endpoint, same
    reasoning as `assemble_comparisons` in app/web/compare_pages.py: one
    fetch, reused, not duplicated or indirected through a second network
    hop.

    A DB that's down or unconfigured (`db is None`, from
    `_db_client_or_none`) degrades to the same friendly template with a
    plain "temporarily unavailable" message, rather than a raw 500."""
    if db is None:
        return templates.TemplateResponse(
            request,
            "explore.html",
            {"error": _DB_UNAVAILABLE_MESSAGE, "careers_with_pathways": []},
        )

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
        request, "explore.html", {"error": None, "careers_with_pathways": careers_with_pathways}
    )
