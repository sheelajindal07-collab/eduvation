"""GET /reviewer/queue, POST /reviewer/claims/{id}/{submit,approve,reject} —
the queue listing and claim-action routes for the reviewer console.

SEC-2 changed two things here. Every action route now carries
`require_reviewer_origin` (app/core/csrf.py, built in auth.py): a
cookie-bearing POST whose `Origin` — or `Referer`, when the browser omits
`Origin` — does not name an `ALLOWED_HOSTS` host is a 403 before the
route body, the session lookup or the database is reached. And the
`?error=` query parameter is now a fixed CODE from `QUEUE_ERROR_MESSAGES`
below, never a free-text message: see `_redirect_to_queue_with_error`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from supabase import Client

from app.api.claims import ClaimOut, approve_claim, list_claims, reject_claim, submit_claim
from app.api.deps import AuthedSession
from app.data.models import Source, SourceType
from app.web.templating import templates

from .auth import _redirect_to_sign_in, get_reviewer_session, require_reviewer_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviewer", tags=["reviewer-console"], include_in_schema=False)

# ------------------------------------------------------------------
# SEC-2 -- the fixed error-code vocabulary for ?error=
# ------------------------------------------------------------------
# Until SEC-2 this router URL-encoded the failure's own free-text message
# into `/reviewer/queue?error=<message>` and `reviewer_queue_page`
# rendered whatever came back. Jinja's autoescaping meant an attacker
# could not inject markup, but ANY string a stranger put in that query
# parameter was still reproduced verbatim inside the console's own error
# alert -- a ready-made text-injection/phishing surface ("your session
# expired, call this number") on an authenticated page, and a way to
# reflect content the server never wrote.
#
# The wire format is now a short CODE from this dict and nothing else.
# The code is the contract, the message is not (docs/CONTRACTS.md's own
# error-shape rule, applied to a redirect instead of a JSON body). An
# unrecognised code -- including anything hand-typed into the address bar
# -- renders `_GENERIC_ERROR_MESSAGE`, never itself.
_DB_UNAVAILABLE_CODE = "db_unavailable"
_GENERIC_ERROR_CODE = "unknown_error"

QUEUE_ERROR_MESSAGES: dict[str, str] = {
    # UI-review finding, 2026-09-21 (MEDIUM, FIX 8), preserved verbatim:
    # the trigger's own message for "two reviewers raced the same claim"
    # (0003_maker_checker.sql, the `old.status = 'published'` branch)
    # tells the reviewer to "supersede it with a new claim instead" -- a
    # feature this console does not implement. This console-side wording
    # replaces it; claims.py's actual error text is untouched.
    "already_published": (
        "This claim was already published -- most likely by another reviewer "
        "moments ago. Refresh the queue to see its current status; correcting "
        "a published claim needs a new claim, which this console doesn't "
        "support yet."
    ),
    "already_superseded": (
        "This claim has been superseded and is final -- it can't be changed. "
        "Refresh the queue to see what's still waiting on you."
    ),
    "self_approval": (
        "You can't approve a claim you created yourself. A second reviewer has "
        "to approve it (maker-checker) -- submit it for review and leave it for "
        "a colleague."
    ),
    "invalid_transition": (
        "That action doesn't apply to this claim's current status -- most likely "
        "someone else moved it while this page was open. Refresh the queue and "
        "try again."
    ),
    "not_a_reviewer": "Only a reviewer can do this.",
    "claim_not_found": (
        "That claim isn't in your queue any more -- it may have been withdrawn, "
        "or it may never have been yours to review. Refresh the queue."
    ),
    "source_not_found": (
        "The source this claim cites no longer exists, so it can't be moved on. "
        "Recreate the source, or raise a fresh claim against an existing one."
    ),
    "sign_in_required": "Your session has ended. Sign in again to continue reviewing.",
    "could_not_process": (
        "This claim couldn't be processed. Refresh the queue -- if it keeps "
        "happening, report it with the claim's details."
    ),
    # UI-review finding, 2026-09-21 (HIGH, FIX 1): shown when the DB
    # itself is unreachable (Supabase down, a network issue -- a raw
    # httpx/postgrest exception, not the postgrest.exceptions.APIError
    # create_claim/_transition already catch), or when app/db/client.py's
    # SupabaseNotConfiguredError propagates. Every route below degrades
    # to this same friendly, in-page message rather than an unhandled 500
    # with no BCION styling.
    _DB_UNAVAILABLE_CODE: (
        "The review queue isn't available right now -- please try again shortly."
    ),
    _GENERIC_ERROR_CODE: (
        "Something went wrong and that action didn't go through. Refresh the "
        "queue to see the claim's current status."
    ),
}
"""code -> the ONLY messages this page will ever render for `?error=`."""

_DB_UNAVAILABLE_MESSAGE = QUEUE_ERROR_MESSAGES[_DB_UNAVAILABLE_CODE]
_GENERIC_ERROR_MESSAGE = QUEUE_ERROR_MESSAGES[_GENERIC_ERROR_CODE]

# Detail-text prefix -> code. Prefixes, not exact strings, because two of
# `enforce_claims_workflow`'s messages interpolate the offending status
# (`... -- not directly to %.`), so their tails vary at runtime. Order
# matters only in that the first match wins; the prefixes are disjoint.
#
# Sources of every entry, checked against the code rather than guessed:
# app/api/claims.py's `_raise_for_claims_error` (RLS 42501 -> "Only a
# reviewer...", FK 23503 -> "Referenced source...", trigger P0001 ->
# the trigger's own message, anything else -> "Could not process..."),
# `_transition`'s 404 "Claim not found.", `_current_user_id`'s 401 "Sign
# in required.", and db/migrations/0003_maker_checker.sql's own `raise
# exception` texts. Entries marked UNREACHABLE are mapped anyway so that
# a future console route (supersede, a claims form) cannot silently fall
# through to the generic message.
_DETAIL_PREFIX_CODES: tuple[tuple[str, str], ...] = (
    ("The author of a claim cannot approve their own claim", "self_approval"),
    ("A published claim cannot be edited in place or un-published", "already_published"),
    ("A superseded claim is final", "already_superseded"),
    ("A draft may only stay draft or move to in_review", "invalid_transition"),
    # UNREACHABLE today: this console only ever writes draft/in_review/
    # published, which are exactly the three this branch permits.
    ("An in_review claim may only go back to draft", "invalid_transition"),
    # UNREACHABLE today: approve_claim always sets reviewed_by.
    ("A claim cannot be published without a recorded reviewer", "invalid_transition"),
    # UNREACHABLE today: no supersede route in this console.
    ("Superseding a published claim may only change status", "invalid_transition"),
    # UNREACHABLE today: this console never inserts a claim.
    ("A claim must be inserted as draft", "invalid_transition"),
    ("Only a reviewer can do this", "not_a_reviewer"),
    ("Referenced source not found", "source_not_found"),
    ("Claim not found", "claim_not_found"),
    ("Sign in required", "sign_in_required"),
    ("Could not process this claim", "could_not_process"),
)


def error_code_for_detail(detail: object) -> str:
    """`HTTPException.detail` -> one of `QUEUE_ERROR_MESSAGES`' codes.

    Anything unrecognised becomes `_GENERIC_ERROR_CODE`: a message this
    console has never seen must not be forwarded to the browser, because
    the whole point of the code vocabulary is that the query string
    carries no server-authored (or attacker-authored) prose at all.
    """
    text = str(detail)
    for prefix, code in _DETAIL_PREFIX_CODES:
        if text.startswith(prefix):
            return code
    return _GENERIC_ERROR_CODE


def queue_error_message(code: str | None) -> str | None:
    """`?error=` -> the ONE message the queue page may render for it.

    The whole point of SEC-2's half of this change: the caller's string
    is used as a dict KEY and never as content. An unknown code — a
    typo, a stale bookmark, `<script>alert(1)</script>`, a phishing
    sentence someone put in a link they sent a reviewer — renders the
    generic message, so nothing a stranger writes can appear inside this
    console's own error alert.
    """
    if not code:
        return None
    return QUEUE_ERROR_MESSAGES.get(code, _GENERIC_ERROR_MESSAGE)


def _redirect_to_queue_with_error(code: str) -> RedirectResponse:
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
    POST-then-redirect shape: 303 back to the queue, with the failure
    identified so `reviewer_queue_page` can show it as a visible alert
    instead of silently dropping it.

    SEC-2: what travels in the query string is a CODE, not the message.
    The membership check below means an unknown code can never even be
    emitted -- there is no path from a caller's string to the URL."""
    if code not in QUEUE_ERROR_MESSAGES:
        code = _GENERIC_ERROR_CODE
    return RedirectResponse(url=f"/reviewer/queue?error={code}", status_code=303)


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

    `error`, when present, is a short CODE naming which action below
    failed (see `_redirect_to_queue_with_error`). SEC-2: it is looked up
    in `QUEUE_ERROR_MESSAGES` and only the message found there is
    rendered — an unrecognised code (a typo, a stale bookmark, or a
    hand-crafted link someone was sent) falls back to
    `_GENERIC_ERROR_MESSAGE`. The parameter's own text is never passed to
    the template, so nothing a stranger puts in the URL can appear on
    this page.
    """
    error_message = queue_error_message(error)
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
        request, "reviewer_queue.html", {"claims": rows, "error": error_message}
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
        return _redirect_to_queue_with_error(error_code_for_detail(exc.detail))
    except Exception:
        logger.warning(
            "Reviewer action failed: action=%s claim_id=%s status=db_unavailable",
            action_name,
            claim_id,
            exc_info=True,
        )
        return _redirect_to_queue_with_error(_DB_UNAVAILABLE_CODE)
    return RedirectResponse(url="/reviewer/queue", status_code=303)


# SEC-2: `dependencies=[Depends(require_reviewer_origin)]` on all three
# action routes below. Route-level dependencies are solved BEFORE the
# endpoint's own parameters, so a request whose origin can't be verified
# is a 403 before `get_reviewer_session` opens a client, before
# claims.py's transition runs, and therefore before any claim's status
# could possibly change -- which is the guarantee that matters here, not
# the status code. tests/db/test_reviewer_console.py asserts exactly
# that: rejected AND the row untouched, read back independently.
@router.post("/claims/{claim_id}/submit", dependencies=[Depends(require_reviewer_origin)])
def reviewer_submit_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "submit", claim_id, lambda: submit_claim(claim_id, session=session)
    )


@router.post("/claims/{claim_id}/approve", dependencies=[Depends(require_reviewer_origin)])
def reviewer_approve_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "approve", claim_id, lambda: approve_claim(claim_id, session=session)
    )


@router.post("/claims/{claim_id}/reject", dependencies=[Depends(require_reviewer_origin)])
def reviewer_reject_claim(
    claim_id: str, session: AuthedSession | None = Depends(get_reviewer_session)
) -> Any:
    if session is None:
        return _redirect_to_sign_in()
    return _handle_reviewer_action(
        "reject", claim_id, lambda: reject_claim(claim_id, session=session)
    )
