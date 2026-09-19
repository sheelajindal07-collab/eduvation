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

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import Client

from app.api.compare import MAX_PATHWAYS, MIN_PATHWAYS, assemble_comparisons
from app.api.deps import get_db_client

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface
templates = Jinja2Templates(directory="app/web/templates")


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


@router.get("/compare/view")
def compare_page(
    request: Request,
    pathway_id: list[str] = Query(default=[]),
    db: Client = Depends(get_db_client),
) -> Any:
    """docs/UI.md "Comparison screen". A missing/wrong pathway_id count
    renders a friendly in-page message with a way back to Explore
    (docs/UI.md "difficult states": explain, don't just error) rather
    than the JSON API's plain 400 — a human clicked into this page, they
    didn't send a malformed request on purpose."""
    if not (MIN_PATHWAYS <= len(pathway_id) <= MAX_PATHWAYS):
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
