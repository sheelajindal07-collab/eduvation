"""GET /reviewer/queue, POST /reviewer/claims/{id}/{submit,approve,reject} —
the queue listing and claim-action routes for the reviewer console.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from supabase import Client

from app.api.claims import ClaimOut, approve_claim, list_claims, reject_claim, submit_claim
from app.api.deps import AuthedSession
from app.data.models import Source, SourceType
from app.web.templating import templates

from .auth import _redirect_to_sign_in, get_reviewer_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviewer", tags=["reviewer-console"], include_in_schema=False)

# UI-review finding, 2026-09-21 (HIGH, FIX 1): shown when the DB itself is
# unreachable (Supabase down, a network issue -- a raw httpx/postgrest
# exception, not the postgrest.exceptions.APIError create_claim/
# _transition already catch, since postgrest's own execute() has no
# try/except around the network call), or when app/db/client.py's
# SupabaseNotConfiguredError propagates. Every route below degrades to
# this same friendly, in-page message rather than an unhandled 500 with
# no BCION styling.
_DB_UNAVAILABLE_MESSAGE = (
    "The review queue isn't available right now -- please try again shortly."
)

# UI-review finding, 2026-09-21 (MEDIUM, FIX 8): the trigger's own
# message for "two reviewers raced the same claim" (0003_maker_checker
# .sql's enforce_claims_workflow, the `old.status = 'published'` branch)
# tells the reviewer to "supersede it with a new claim instead" -- a
# feature this console does not implement (only submit/approve/reject
# are wired up here; see this module's own docstring). Left as the raw
# trigger text, a reviewer hitting this race would be pointed at a
# button that exists nowhere in this UI. Building the full Supersede UI
# is out of scope here (task's own instruction) -- this is a minimal,
# console-side translation of that one message, not a new backend
# behaviour; claims.py's actual error is untouched, and every OTHER
# HTTPException detail (self-approval, an invalid transition, the 404 a
# non-reviewer's now-invisible-under-RLS row produces, ...) still passes
# through _redirect_to_queue_with_error unchanged.
_ALREADY_PUBLISHED_TRIGGER_MESSAGE = (
    "A published claim cannot be edited in place or un-published; "
    "supersede it with a new claim instead."
)
_ALREADY_PUBLISHED_CONSOLE_MESSAGE = (
    "This claim was already published -- most likely by another reviewer "
    "moments ago. Refresh the queue to see its current status; correcting "
    "a published claim needs a new claim, which this console doesn't "
    "support yet."
)


def _console_error_detail(detail: object) -> str:
    """Translate one specific trigger message into something actionable
    inside THIS console (see the module-level comment above). Everything
    else is relayed as-is, unchanged from before."""
    if detail == _ALREADY_PUBLISHED_TRIGGER_MESSAGE:
        return _ALREADY_PUBLISHED_CONSOLE_MESSAGE
    return str(detail)


def _redirect_to_queue_with_error(detail: object) -> RedirectResponse:
    """UI-review finding, 2026-09-21 (HIGH): the three action routes below
    used to call straight into claims.py's submit_claim/approve_claim/
    reject_claim with no error handling, so any HTTPException it raised
    (self-approval, an invalid workflow transition, or the 400 two
    reviewers racing on the same claim produces -- the normal case
    maker-checker exists for; NOT a 404 -- that's a distinct case, a
    non-reviewer's own now-invisible-under-RLS row) surfaced as FastAPI's
    raw default JSON error body, with no way back to the queue. Same
    "explain, don't just error" reasoning as `app/web/pages.py`'s
    `compare_page` (a human clicked a button, they didn't send a
    malformed request on purpose) adapted to this router's
    POST-then-redirect shape: 303 back to the queue, with the failure's
    own detail message (translated by `_console_error_detail` for the
    one case above that would otherwise point at a nonexistent feature)
    carried as a query param so `reviewer_queue_page` can show it as a
    visible alert instead of silently dropping it."""
    message = _console_error_detail(detail)
    return RedirectResponse(url=f"/reviewer/queue?error={quote(message)}", status_code=303)


def _row_to_source(row: dict[str, Any]) -> Source:
    """Identical to app/api/compare.py's and app/api/eligibility.py's
    helpers of the same name — kept file-local, matching this
    codebase's convention of not coupling otherwise-unrelated route
    files over a few lines (see those modules' own docstrings)."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


def _safe_source_url(source: Source | None) -> str | None:
    """Identical safety check to app/api/eligibility.py's helper of the
    same name (security-review finding, 2026-09-20): Source.official_url
    is reviewer-write-only, but nothing validates its scheme before it
    would reach an href -- a non-http(s) scheme degrades to None (the
    same "unavailable" pattern used elsewhere) rather than ever being
    rendered as a clickable link."""
    if source is None:
        return None
    if source.official_url.startswith(("http://", "https://")):
        return source.official_url
    return None


@dataclass(frozen=True)
class ReviewQueueRow:
    """One claim plus everything reviewer_queue.html needs to show it
    resolved to something a reviewer can actually act on -- the entity's
    human-readable name and the source's authority/official link, never
    just the bare ids (UI-review finding, 2026-09-21, HIGH, FIX 4). Same
    "join the ids for display" pattern already established by
    app/web/pages.py's compare_page (pathway id -> name) and
    app/api/eligibility.py's check_eligibility (source id -> authority/
    url)."""

    claim: ClaimOut
    entity_name: str | None
    source: Source | None
    source_url: str | None


_ENTITY_TABLES = {"Pathway": "pathways", "Career": "careers"}
"""entity_type -> table name, for the two entity types any route in this
codebase currently joins against (db/migrations/0001_init.sql has no
exams/institutions/scholarships table yet). Any other entity_type
gracefully falls back to `entity_name=None` in `_resolve_queue_rows`,
which the template shows as the raw id instead of crashing -- adding a
new entity type here (once its table exists) is the only change needed
to resolve it too."""


def _resolve_queue_rows(db: Client, claims: list[ClaimOut]) -> list[ReviewQueueRow]:
    """Resolve every claim's entity_id and source_id for display, in
    len(_ENTITY_TABLES) + 1 queries total (not one per claim/row) — same
    batching shape as app/api/compare.py's assemble_comparisons.

    ux-qa-reviewer finding, 2026-09-21: this used to resolve
    entity_type == "Pathway" only, leaving a real, reachable entity type
    (Career, e.g. a claim on `careers.nco_anchor`) showing a bare UUID.
    Generalised to loop over every entity type this codebase has a table
    for, rather than special-casing one.
    """
    entity_names: dict[str, str] = {}
    for entity_type, table in _ENTITY_TABLES.items():
        ids = {c.entity_id for c in claims if c.entity_type == entity_type}
        if not ids:
            continue
        names_result = db.table(table).select("id, name").in_("id", list(ids)).execute()
        for row in cast("list[dict[str, Any]]", names_result.data):
            entity_names[row["id"]] = row["name"]

    source_ids = {c.source_id for c in claims}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        sources_by_id = {
            row["id"]: _row_to_source(row)
            for row in cast("list[dict[str, Any]]", sources_result.data)
        }

    rows = []
    for c in claims:
        entity_name = entity_names.get(c.entity_id) if c.entity_type in _ENTITY_TABLES else None
        source = sources_by_id.get(c.source_id)
        rows.append(
            ReviewQueueRow(
                claim=c,
                entity_name=entity_name,
                source=source,
                source_url=_safe_source_url(source),
            )
        )
    return rows


@router.get("/queue")
def reviewer_queue_page(
    request: Request,
    error: str | None = Query(default=None),
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    """Lists what needs a reviewer's attention, via the exact same
    `list_claims` function `GET /claims` (the JSON API) already calls —
    same default `["draft", "in_review"]` status filter, same RLS: a
    signed-in non-reviewer gets an empty queue here too, not an error
    (existing, intentional behaviour — see claims.py's own docstring).

    `error`, when present, is the detail message from an action route
    below that failed (see `_redirect_to_queue_with_error`) — rendered by
    the template as a visible alert, not silently dropped.
    """
    if session is None:
        return _redirect_to_sign_in()
    try:
        claims = list_claims(status=["draft", "in_review"], session=session)
        rows = _resolve_queue_rows(session.client, claims)
    except Exception:
        # UI-review finding, 2026-09-21 (HIGH, FIX 1): list_claims (and
        # the entity/source resolution above it) had NO exception
        # handling at all on this path -- a DB-unavailable condition
        # (Supabase down, a network issue) raises a raw httpx/postgrest
        # exception, not even a postgrest.exceptions.APIError, and used
        # to crash this route to an unhandled 500 with no BCION styling.
        # Degrades to the same friendly in-page alert every other
        # failure on this page already uses, rather than propagating.
        logger.warning("Reviewer queue page failed to load the queue", exc_info=True)
        return templates.TemplateResponse(
            request,
            "reviewer_queue.html",
            {"claims": [], "error": _DB_UNAVAILABLE_MESSAGE},
            status_code=503,
        )
    return templates.TemplateResponse(
        request, "reviewer_queue.html", {"claims": rows, "error": error}
    )


def _handle_reviewer_action(
    action_name: str, claim_id: str, action: Callable[[], ClaimOut]
) -> RedirectResponse:
    """Shared shape for the three action routes below (UI-review finding,
    2026-09-21): run the claims.py transition, turn any `HTTPException`
    it raises into a visible queue-page alert (as before), and ALSO
    catch the broader DB-unavailable case (FIX 1) the same way -- a raw
    httpx/postgrest connection failure used to have NO handling at all
    on this path and would crash straight to an unhandled 500, unlike
    the `HTTPException` case already handled. One shared pattern across
    all three routes rather than four slightly-different ones (this
    function plus `reviewer_queue_page`'s own try/except).

    Every failure is logged (FIX 5, following `_migrate_pending_plan`'s
    convention in app/api/auth.py: opaque identifiers only -- claim_id
    and the resulting status -- never the claim's own value/notes/free
    text) so an operator has something to grep for when a reviewer hits
    an unexpected failure.
    """
    try:
        action()
    except HTTPException as exc:
        logger.warning(
            "Reviewer action failed: action=%s claim_id=%s status=%s",
            action_name,
            claim_id,
            exc.status_code,
            exc_info=True,
        )
        return _redirect_to_queue_with_error(exc.detail)
    except Exception:
        logger.warning(
            "Reviewer action failed: action=%s claim_id=%s status=db_unavailable",
            action_name,
            claim_id,
            exc_info=True,
        )
        return _redirect_to_queue_with_error(_DB_UNAVAILABLE_MESSAGE)
    return RedirectResponse(url="/reviewer/queue", status_code=303)


@router.post("/claims/{claim_id}/submit")
def reviewer_submit_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "submit", claim_id, lambda: submit_claim(claim_id, session=session)
    )


@router.post("/claims/{claim_id}/approve")
def reviewer_approve_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "approve", claim_id, lambda: approve_claim(claim_id, session=session)
    )


@router.post("/claims/{claim_id}/reject")
def reviewer_reject_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "reject", claim_id, lambda: reject_claim(claim_id, session=session)
    )
