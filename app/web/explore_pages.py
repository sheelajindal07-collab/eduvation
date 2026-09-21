"""GET / and GET /explore — docs/UI.md "Career explorer" screen (UI-2's
split of the former monolithic `app/web/pages.py`).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from supabase import Client

from app.api.deps import get_db_client
from app.web.common import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/explore")


@router.get("/explore")
def explore_page(request: Request, db: Client = Depends(get_db_client)) -> Any:
    """docs/UI.md "Career explorer" screen. Same two queries
    `GET /careers` already runs (app/api/explore.py) — kept as a direct
    call here rather than an HTTP round-trip to the JSON endpoint, same
    reasoning as `assemble_comparisons` in app/web/compare_pages.py: one
    fetch, reused, not duplicated or indirected through a second network
    hop."""
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
