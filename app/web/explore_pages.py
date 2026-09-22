"""GET /explore — docs/UI.md "Career explorer" screen (UI-2's split of
the former monolithic `app/web/pages.py`).

UI-3: `GET /` used to live here as a bare redirect to `/explore`. It is
now its own screen (`app/web/landing_pages.py`, "Find your next step"),
so this module goes back to owning exactly the one route its docstring
already named alongside the redirect -- `/explore` itself, unchanged.

SCOPE-6: adds a zero-JS jurisdiction filter (`?region=india` /
`?region=abroad`, plain links, no script) that groups
`pathways.jurisdiction` into "India" vs "Abroad", plus a "not verified
yet" panel (`_not_verified.html`) for whichever group(s) currently have
no published, non-synthetic claim at all
(`app/planning/coverage.py`'s `covered_jurisdictions`). This is purely
additive to the page's existing content -- pathway/career names were
already world-readable before this card (no claim-status gate on those
two tables at all, db/migrations/0001_init.sql), so filtering/grouping
them by jurisdiction leaks nothing that was not already public; only a
claim's own VALUE is gated, and this screen has never shown one.

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

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.data.models import DEFAULT_JURISDICTION
from app.planning.coverage import covered_jurisdictions_or_none
from app.web.common import _DB_UNAVAILABLE_MESSAGE, _db_client_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


def _is_india(jurisdiction: str) -> bool:
    """True for India itself (`"IN"`) or any of its states/UTs
    (`"IN-XX"`) -- `pathways.jurisdiction`'s own shape
    (db/migrations/0008_jurisdiction_currency.sql:
    `^[A-Z]{2}(-[A-Z0-9]{1,3})?$`) makes this a plain prefix check, not a
    lookup: every non-Indian jurisdiction in this pilot is a bare
    two-letter country code with no `-` at all (app/data/jurisdictions.py's
    `PILOT_COUNTRIES`)."""
    return jurisdiction == "IN" or jurisdiction.startswith("IN-")


_VALID_REGIONS = frozenset({"india", "abroad"})


def _jurisdiction_of(pathway: dict[str, Any]) -> str:
    """`pathway["jurisdiction"]`, defaulting to `DEFAULT_JURISDICTION`
    both when the column is entirely absent (the pre-migration-0008
    deploy window, see the `*` select above) and when it is present but
    `None` -- `.get(key, default)` alone only covers the first case, not
    a row that has the key with a null value; this covers both the same
    way `app/api/explore.py`'s own `PathwaySummary` default already does
    at the model layer."""
    return pathway.get("jurisdiction") or DEFAULT_JURISDICTION


@router.get("/explore")
def explore_page(
    request: Request,
    region: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """docs/UI.md "Career explorer" screen. Same two queries
    `GET /careers` already runs (app/api/explore.py) — kept as a direct
    call here rather than an HTTP round-trip to the JSON endpoint, same
    reasoning as `assemble_comparisons` in app/web/compare_pages.py: one
    fetch, reused, not duplicated or indirected through a second network
    hop.

    SCOPE-6: `region` is a plain GET query param (`"india"` / `"abroad"`,
    anything else -- including absent -- means "show both"), read by a
    zero-JS `<a href="...">` link on the page itself, never a script.

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
    # `*` rather than a column list (matches app/api/explore.py's own
    # `GET /careers`): naming `jurisdiction` explicitly would 400 in the
    # deploy window where this code is live but db/migrations/
    # 0008_jurisdiction_currency.sql has not been applied yet -- PostgREST
    # rejects a select for a column that does not exist. With `*` the
    # column is simply absent from an old row and `_jurisdiction_of`
    # below covers it. `pathways` is world-readable and holds no personal
    # data, so there is nothing a column list was protecting.
    pathways_result = db.table("pathways").select("*").execute()
    careers = cast("list[dict[str, Any]]", careers_result.data)
    pathways = cast("list[dict[str, Any]]", pathways_result.data)

    region_normalised = region.strip().lower() if region else None
    show_india = region_normalised != "abroad"
    show_abroad = region_normalised != "india"

    # `_or_none`: a public page must never 500 just because this
    # derivation's own query failed (see covered_jurisdictions_or_none's
    # own docstring) -- `None` means "could not tell", handled below by
    # simply not flagging anything as unverified for this request, never
    # by guessing.
    covered = covered_jurisdictions_or_none(db)

    def _careers_with_pathways(
        matching: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Same shape the page always rendered -- a list of {career,
        pathways} -- but scoped to only the careers that have at least
        one pathway in this group, so a career whose only pathways are
        in the OTHER group doesn't show an empty "no pathways published"
        card here (that message stays reserved for a career that
        genuinely has none published anywhere, in the no-filter/both-
        groups case below)."""
        by_career: dict[str, list[dict[str, Any]]] = {}
        for pathway in matching:
            by_career.setdefault(pathway["career_id"], []).append(pathway)
        return [
            {"career": career, "pathways": by_career[career["id"]]}
            for career in careers
            if career["id"] in by_career
        ]

    india_pathways = [p for p in pathways if _is_india(_jurisdiction_of(p))]
    abroad_pathways = [p for p in pathways if not _is_india(_jurisdiction_of(p))]

    india_group = _careers_with_pathways(india_pathways) if show_india else None
    abroad_group = _careers_with_pathways(abroad_pathways) if show_abroad else None

    # SCOPE-6: "not verified yet" for a shown group whose pathways carry
    # NO covered jurisdiction at all -- informational only, additive to
    # whatever pathway/career listing already rendered (see module
    # docstring: nothing claim-backed is shown on this screen to leak).
    india_not_verified = (
        show_india
        and covered is not None
        and bool(india_pathways)
        and not any(_jurisdiction_of(p) in covered for p in india_pathways)
    )
    abroad_not_verified = (
        show_abroad
        and covered is not None
        and bool(abroad_pathways)
        and not any(_jurisdiction_of(p) in covered for p in abroad_pathways)
    )

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "error": None,
            "region": region_normalised if region_normalised in _VALID_REGIONS else None,
            "show_india": show_india,
            "show_abroad": show_abroad,
            "india_group": india_group,
            "abroad_group": abroad_group,
            "india_not_verified": india_not_verified,
            "abroad_not_verified": abroad_not_verified,
            "india_place_name": "India",
            "abroad_place_name": "Abroad",
            # Kept for the "no careers published at all yet" empty state,
            # which is unrelated to the region filter.
            "careers_with_pathways": _careers_with_pathways(pathways),
        },
    )
