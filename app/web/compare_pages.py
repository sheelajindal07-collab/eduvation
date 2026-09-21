"""GET /compare/view — docs/UI.md "Comparison screen" (UI-2's split of
the former monolithic `app/web/pages.py`).

Distinct path from the JSON API (`/compare/view` vs. `/compare`) rather
than content negotiation on the same URL — keeps the already-tested JSON
contract completely untouched, and keeps this module's only job as
"render what the API already computes", never a second copy of the
fetch-and-assemble logic. `app.api.compare.assemble_comparisons` is the
one place that logic lives; both this module and `app/api/compare.py`'s
JSON route call it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.api.compare import MAX_PATHWAYS, MIN_PATHWAYS, assemble_comparisons
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _looks_like_a_uuid,
    templates,
)

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


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
