"""GET /compare/view — docs/UI.md "Comparison screen" (UI-2's split of
the former monolithic `app/web/pages.py`).

Distinct path from the JSON API (`/compare/view` vs. `/compare`) rather
than content negotiation on the same URL — keeps the already-tested JSON
contract completely untouched, and keeps this module's only job as
"render what the API already computes", never a second copy of the
fetch-and-assemble logic. `app.api.compare.assemble_comparisons` is the
one place that logic lives; both this module and `app/api/compare.py`'s
JSON route call it.

UI-6 ("assumption editing", Lite Build Pack §6): the override mechanism
itself — `estimated_additional_expenses_override`, threaded through
`assemble_comparisons()` — already existed and is already covered by
`tests/db/test_api_explore_compare.py` for the JSON route. What this task
adds is purely the HTML side: reading the same query param here (with a
parser suited to a human-clicked page rather than the JSON route's own
FastAPI-level `float | None` 422) and the `compare.html` form that sets
it. See `_safe_estimated_additional_expenses` below and
`tests/db/test_web_compare_assumption.py`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.api.compare import MAX_PATHWAYS, MIN_PATHWAYS, assemble_comparisons
from app.rules.cost import to_whole_rupees
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _float_or_none,
    _looks_like_a_uuid,
)
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

# ux-qa-reviewer finding, 2026-09-22: a finite but implausibly large typed
# value (e.g. 26 nines) survives `math.isfinite` but loses precision past
# float64's ~15-17 significant digits, then redisplays as a garbled, wrong
# rupee figure with full confidence -- the single most safety-critical
# number on this screen. Chosen well below that precision boundary (no
# rounding risk at all) and far above any plausible one-time expense a
# student would type (hostel deposit, exam fees, relocation) -- this is a
# sanity ceiling, not a claim about what expenses can cost.
_MAX_PLAUSIBLE_ADDITIONAL_EXPENSES_RUPEES = 100_000_000  # ₹10 crore


def _safe_estimated_additional_expenses(raw: str | None) -> int | None:
    """The `estimated_additional_expenses` query param, parsed for THIS
    HTML page only -- distinct from `app/api/compare.py`'s JSON route,
    which types the same param as `float | None = Query(...)` and lets
    FastAPI's own request validation return a raw 422 for anything that
    doesn't parse. A human reaches this page by clicking a link (possibly
    a truncated/hand-edited one shared over WhatsApp -- the same class of
    problem `_looks_like_a_uuid`'s callers already guard `pathway_id`
    against), so a bad value here must degrade to "no override" -- the
    same friendly compare screen, using each pathway's own computed
    estimate -- rather than a 422 JSON error page or an uncaught 500.

    Reuses `app/web/common.py`'s `_float_or_none` for the actual string
    parsing (the same "missing or unparsable -> None" contract every
    other optional numeric field on these HTML pages already follows --
    see `app/web/requirements_pages.py`'s `marks_percentage`), then
    applies two more checks specific to a money amount:

    "Garbled" -- anything `_float_or_none` itself already rejects (a
    blank string, non-numeric text, ...) -- plus the two values Python's
    `float()` parses successfully but which are not a usable amount:
    `nan` and `inf`/`-inf` (`math.isfinite` rejects both).

    "Negative" -- parses fine but is treated as invalid too, not as a
    negative expense: `app/rules/cost.py`'s cost arithmetic has no notion
    of a negative "additional expenses" figure, and letting one through
    would silently shrink `net_to_arrange` as though it were a discount
    the site invented, rather than the student's own stated assumption.
    Falling back to "no override" (the pathway's own computed estimate)
    reads to the student as "that entry wasn't used" on the next render,
    which is honest; silently clamping a mistyped negative to zero would
    instead look like the site had decided their expenses really are
    zero, a fact it has no basis to assert.

    Rounded to a whole rupee via `app/rules/cost.py`'s `to_whole_rupees`
    -- the same round-half-to-even rule this app's `Money` type applies
    to every other amount (RULES-10), reused here rather than
    reimplemented. Returning `int` (not `float`) also keeps a whole-
    number entry redisplaying in the form's own `value="..."` as
    `"15000"`, never `"15000.0"` -- the exact trailing-`.0` "reads like a
    display bug" class of defect ux-qa-reviewer already flagged once for
    this same screen's cost line (2026-09-19).

    "Implausibly large" -- anything above
    `_MAX_PLAUSIBLE_ADDITIONAL_EXPENSES_RUPEES` is also treated as
    invalid, same as negative: a value that big is either a mistake
    (an extra digit, a pasted id) or an attempt to see the site fabricate
    a number, and letting it through risks exactly what it did before
    this check existed -- float64 precision loss past ~15-17 significant
    digits silently corrupting the value into a garbled, wrong-but-
    confident rupee figure on the one number this screen exists to get
    right (ux-qa-reviewer finding, 2026-09-22).
    """
    value = _float_or_none(raw)
    if (
        value is None
        or not math.isfinite(value)
        or value < 0
        or value > _MAX_PLAUSIBLE_ADDITIONAL_EXPENSES_RUPEES
    ):
        return None
    return to_whole_rupees(value)


@router.get("/compare/view")
def compare_page(
    request: Request,
    pathway_id: list[str] = Query(default=[]),
    estimated_additional_expenses: str | None = Query(
        default=None,
        description=(
            "The student's own per-request assumption override (Lite Build "
            "Pack §6 'assumption editing') -- see "
            "_safe_estimated_additional_expenses for the parsing/validation "
            "this HTML page applies before the value ever reaches "
            "assemble_comparisons(). Typed str, not float, so a garbled "
            "value degrades to 'no override' here instead of the JSON "
            "route's own FastAPI-level 422."
        ),
    ),
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
    that used to propagate straight out of `Depends(get_db_client)`.

    UI-6: `estimated_additional_expenses` is parsed once, here, via
    `_safe_estimated_additional_expenses` -- a garbled or negative value
    becomes `None` (no override; each pathway falls back to its own
    computed estimate) rather than a 422 or a 500. The parsed value (not
    the raw string) is carried into every branch's template context under
    the same name, so `compare.html`'s own form re-displays exactly what
    was actually used -- blank again after an invalid entry, the same
    "not provided" redisplay `app/web/requirements_pages.py` already uses
    for `age`/`marks_percentage`."""
    override = _safe_estimated_additional_expenses(estimated_additional_expenses)

    if db is None:
        return templates.TemplateResponse(
            request,
            "compare.html",
            {
                "error": _DB_UNAVAILABLE_MESSAGE,
                "comparisons": [],
                "pathway_names": {},
                "estimated_additional_expenses": override,
            },
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
                "estimated_additional_expenses": override,
            },
        )

    as_of = datetime.now(tz=UTC).date()
    comparisons = assemble_comparisons(
        db, pathway_id, as_of=as_of, estimated_additional_expenses_override=override
    )

    names_result = db.table("pathways").select("id, name").in_("id", pathway_id).execute()
    pathway_names = {
        row["id"]: row["name"] for row in cast("list[dict[str, Any]]", names_result.data)
    }

    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "error": None,
            "comparisons": comparisons,
            "pathway_names": pathway_names,
            "estimated_additional_expenses": override,
        },
    )
