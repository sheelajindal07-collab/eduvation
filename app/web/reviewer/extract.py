"""GET/POST /reviewer/extract, POST /reviewer/extract/claims — AI-assisted
claim extraction drafts (AI-14, tasks/BCI-016.md).

A signed-in reviewer pastes the plain text of an official document, picks
an existing source and the entity (Pathway/Career + id) the document is
about, and gets back zero or more candidate `(field, value, quoted_span)`
proposals from `app/ai/extraction.py`'s two-pass pipeline. Each surviving
proposal renders as its own small, pre-filled form; nothing is written to
the database until a reviewer explicitly submits one of those forms,
which POSTs to `/reviewer/extract/claims` below and calls straight into
`app/api/claims.py`'s own `create_claim` — the exact same function
`POST /claims` uses, with `extracted_by` forced to `"ai"` in code (never
trusted from the form) and `status` left for that route to default to
`draft`, as it already does for every claim. This module adds NO new
database write path; every write still goes through the existing,
already-tested claims API and its existing maker-checker enforcement
(`db/migrations/0003_maker_checker.sql`) — a reviewer must still submit
and get a second reviewer to approve a draft created this way, exactly
like one typed in by hand.

## Why this doesn't POST straight to `/claims` from the browser

`POST /claims` (`app/api/claims.py`) is Bearer-only —
`app.api.deps.require_auth` reads an `Authorization` header, which a
plain, zero-JS HTML `<form method="post">` has no way to attach (see
`app/web/reviewer/auth.py`'s own module docstring, "How the cookie
reaches app/api/claims.py's routes" — the exact same constraint this
whole console was already built around). This module reuses that same,
already-established shape rather than inventing a new one: the pre-filled
form POSTs to a route IN THIS ROUTER, which builds a `CreateClaimRequest`
from the form fields and calls `create_claim(...)` directly with the
cookie-derived `AuthedSession`, the identical pattern
`app/web/reviewer/queue.py`'s submit/approve/reject actions already use
to reach `app/api/claims.py`'s other route functions.

## Reviewer gating — stricter than `/reviewer/queue`, and why

`/reviewer/queue` lets ANY signed-in user load the page and shows an
empty queue for a non-reviewer (RLS quietly filtering out every row —
existing, intentional, documented behaviour). This page is different: it
is a request that would spend AI budget/money for `/reviewer/extract`'s
POST, so both the GET and the POST below actively check reviewer status
before doing anything, rather than silently degrading to "nothing to
show." `db/migrations/0001_init.sql` explicitly forbids reading the
`reviewers` table directly through PostgREST at all ("No policy is added
on `reviewers` itself: nobody reads or writes it directly through the
API; only the `is_reviewer()` security-definer function touches it"), so
`_is_reviewer` below calls that function the one sanctioned way this
codebase already established for reading a database-computed boolean
through PostgREST: an RPC call, mirroring `app/api/explore.py`'s own
`_demo_mode()` helper exactly (same fail-closed-on-any-error shape, same
`result.data is True` reading of a scalar-returning `security definer`
SQL function). No new grant, no new migration — `is_reviewer()` already
carries the default PUBLIC execute privilege `db/migrations/0004_
guardian_consent.sql`'s own comment notes has never been revoked.

A request with no reviewer session cookie at all (guest) gets 404 — the
page does not reveal its own existence to an unauthenticated caller. A
request with a VALID session that is not a reviewer (a signed-in student)
gets 403 — its identity is known, and it is refused. Both `_require_
reviewer` below.

## The pasted text is never logged, never stored beyond the request

No route below ever calls `logger.*` with `pasted_text`, `field`,
`value`, `quoted_span` or any prompt/raw-provider-response text — every
log line here carries only opaque identifiers (a reviewer id, a claim
id, an action name), the same convention
`app/web/reviewer/queue.py`'s `_handle_reviewer_action` already
documents and follows. `pasted_text` lives only in this request's own
local variables; nothing here assigns it to any longer-lived structure,
a file, or a database row (`app/ai/extraction.py` is pure and does the
same).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from supabase import Client

from app.ai.budget import AIBudgetExceededError
from app.ai.extraction import (
    FIXED_SCALAR_TARGET_FIELDS,
    ExtractionProposal,
    ExtractionStatus,
    run_extraction,
)
from app.ai.gemini_provider import GeminiNotConfiguredError, GeminiProvider
from app.ai.schemas import AIProviderError
from app.api.claims import CreateClaimRequest, create_claim
from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.data.models import Source, SourceType
from app.web.templating import templates

from .auth import get_reviewer_session, require_reviewer_origin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviewer", tags=["reviewer-console"], include_in_schema=False)

#: The two entity types any claim in this codebase is ever attached to —
#: same vocabulary `app/web/reviewer/queue.py`'s `_ENTITY_TABLES` and
#: `app/ai/retrieval.py`'s `_KNOWN_ENTITY_TYPES` already use. Kept
#: file-local (not imported from either, both private to their own
#: modules) matching this codebase's established convention of not
#: coupling otherwise-unrelated modules over a two-entry tuple.
ENTITY_TYPES: tuple[str, ...] = ("Pathway", "Career")

# ---------------------------------------------------------------------
# Money-field vocabulary -- mirrors `app/api/claims.py`'s own
# `_MONEY_FIELD_NAMES`/`_is_money_field` exactly (copied, not imported,
# matching this codebase's established file-local-constant convention
# that module's own docstring names, e.g. `_ENTITY_TABLES` in
# `app/web/reviewer/queue.py`). This module needs the same field-kind
# check for a different reason than that one: `CreateClaimRequest.
# currency_matches_field_kind` (SCOPE-13) rejects a money field with no
# currency AND a non-money field WITH one, but this page's proposal
# forms (built from `app/ai/extraction.py`'s `ExtractionProposal`, which
# carries no currency of its own) never collected a currency at all
# before this fix -- every money-field proposal 422'd unconditionally.
# `_DEFAULT_CURRENCY_FOR_MONEY_FIELDS` is this pilot's own scope, not a
# guess: docs/PRODUCT.md scopes BCION Lite to India only, so "INR" is a
# safe, reviewer-editable starting value on the form, never silently
# assumed in code -- the reviewer still explicitly confirms or changes
# it before the value ever reaches `CreateClaimRequest`.
#
# `_is_money_field` below is used ONLY to decide the template's own
# rendering (whether a given proposal's form shows/requires the
# currency input at all) -- it does not gate what
# `reviewer_extract_create_claim` forwards to `CreateClaimRequest`.
# Enforcement stays exactly one place: that model's own
# `currency_matches_field_kind` validator (see that route function's
# docstring for why).
# ---------------------------------------------------------------------

_MONEY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "verified_charges",
        "estimated_additional_expenses_hint",
        "potential_assistance_not_yet_awarded",
    }
)

_FEE_COMPONENT_FIELD_PREFIX = "fee_component:"

_DEFAULT_CURRENCY_FOR_MONEY_FIELDS = "INR"


def _is_money_field(field: str) -> bool:
    return field in _MONEY_FIELD_NAMES or field.startswith(_FEE_COMPONENT_FIELD_PREFIX)


# ---------------------------------------------------------------------
# Fixed error-code vocabulary for `?error=` -- SEC-2's rule, applied here
# too: the query string carries a CODE, never free text (see
# app/web/reviewer/queue.py's own module docstring for the reasoning in
# full; not re-imported, since that dict is private to that module and
# names failures this page can't produce, e.g. self-approval).
# ---------------------------------------------------------------------
_GENERIC_ERROR_CODE = "unknown_error"
_DB_UNAVAILABLE_CODE = "db_unavailable"
_AI_UNAVAILABLE_CODE = "ai_unavailable"
_BUDGET_EXHAUSTED_CODE = "budget_exhausted"

EXTRACT_ERROR_MESSAGES: dict[str, str] = {
    "not_a_reviewer": "Only a reviewer can do this.",
    "source_not_found": (
        "The source you picked no longer exists -- refresh this page and pick another."
    ),
    "invalid_input": (
        "That claim couldn't be created -- check the verifier field (it can't be the "
        'literal "ai"; use your own name or id), the currency field (required on a '
        "money field, e.g. verified_charges, and must be a 3-letter code like INR), "
        "and the other fields, then try again."
    ),
    "could_not_process": (
        "This claim couldn't be created. Try again -- if it keeps happening, report it."
    ),
    _AI_UNAVAILABLE_CODE: (
        "AI-assisted extraction is not available right now. You can still add a claim "
        "manually through the review queue."
    ),
    _BUDGET_EXHAUSTED_CODE: (
        "Today's AI extraction budget is already used up. Try again tomorrow, or add "
        "this claim manually through the review queue."
    ),
    _DB_UNAVAILABLE_CODE: "This page isn't available right now -- please try again shortly.",
    _GENERIC_ERROR_CODE: "Something went wrong and that action didn't go through.",
}
"""code -> the ONLY messages this page will ever render for `?error=` --
identical discipline to `app/web/reviewer/queue.py`'s own
`QUEUE_ERROR_MESSAGES` (an unrecognised code renders the generic
message; the parameter's own text is never reflected)."""

_DETAIL_PREFIX_CODES: tuple[tuple[str, str], ...] = (
    ("Only a reviewer can do this", "not_a_reviewer"),
    ("Referenced source not found", "source_not_found"),
)


def error_code_for_detail(detail: object) -> str:
    """`HTTPException.detail` -> one of `EXTRACT_ERROR_MESSAGES`' codes.
    Identical shape to `app/web/reviewer/queue.py`'s function of the same
    name — see that function's own docstring for why an unrecognised
    message must never itself reach the query string."""
    text = str(detail)
    for prefix, code in _DETAIL_PREFIX_CODES:
        if text.startswith(prefix):
            return code
    return "could_not_process"


def extract_error_message(code: str | None) -> str | None:
    if not code:
        return None
    return EXTRACT_ERROR_MESSAGES.get(code, EXTRACT_ERROR_MESSAGES[_GENERIC_ERROR_CODE])


def _redirect_to_extract_with_error(code: str) -> RedirectResponse:
    if code not in EXTRACT_ERROR_MESSAGES:
        code = _GENERIC_ERROR_CODE
    return RedirectResponse(url=f"/reviewer/extract?error={code}", status_code=303)


# ---------------------------------------------------------------------
# Reviewer gating -- see module docstring's "Reviewer gating" section.
# ---------------------------------------------------------------------


def _is_reviewer(session: AuthedSession) -> bool:
    """Mirrors `app/api/explore.py`'s `_demo_mode()` exactly: an RPC call
    to an existing, already-granted `security definer` SQL function,
    failing closed to `False` on any error (a missing/unreachable
    function must never silently grant reviewer access)."""
    try:
        result = session.client.rpc("is_reviewer", {}).execute()
    except Exception:  # noqa: BLE001 - fail closed, see docstring above.
        return False
    return result.data is True


def _require_reviewer(session: AuthedSession | None) -> AuthedSession:
    """Guest (no session at all) -> 404; signed-in but not a reviewer ->
    403. See module docstring's "Reviewer gating" section for why this
    page does not use `/reviewer/queue`'s redirect-to-sign-in /
    empty-queue pattern."""
    if session is None:
        raise HTTPException(status_code=404)
    if not _is_reviewer(session):
        raise HTTPException(status_code=403, detail="Only a reviewer can do this.")
    return session


def _current_reviewer_id(session: AuthedSession) -> str | None:
    """File-local convention (see `app/api/claims.py`'s `_current_user_id`
    docstring for the same pattern applied elsewhere): resolves the
    caller's own user id from their access token, `None` on any failure
    -- a caller of this function degrades to a token-keyed budget instead
    (see `reviewer_extract_run` below), never to a crash."""
    try:
        user_response = session.client.auth.get_user(jwt=session.access_token)
    except Exception:  # noqa: BLE001 - see docstring above.
        return None
    if user_response is None or user_response.user is None:
        return None
    return user_response.user.id


# ---------------------------------------------------------------------
# Source picker
# ---------------------------------------------------------------------


def _row_to_source(row: dict[str, Any]) -> Source:
    """Identical in shape to `app/web/reviewer/queue.py`'s file-local
    helper of the same name — kept file-local here too, matching this
    codebase's established convention (see that module's own docstring)
    of not coupling otherwise-unrelated route files over a few lines of
    row-mapping."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


def _fetch_sources(db: Client) -> list[Source]:
    """Every existing source, for the picker — `sources` is world-
    readable (`db/migrations/0001_init.sql`: `sources_select_all`), so
    this query itself needs no reviewer check of its own; `_require_
    reviewer` above already gated the page this feeds."""
    result = db.table("sources").select("*").order("authority_name").execute()
    return [_row_to_source(row) for row in cast("list[dict[str, Any]]", result.data)]


# ---------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------


def _render_extract_page(
    request: Request,
    db: Client,
    *,
    error: str | None,
    pasted_text: str = "",
    selected_source_id: str = "",
    selected_entity_type: str = "",
    selected_entity_id: str = "",
    result_status: ExtractionStatus | None = None,
    proposals: tuple[ExtractionProposal, ...] = (),
    status_code: int = 200,
) -> Any:
    try:
        sources = _fetch_sources(db)
    except Exception:
        # Same "degrade to a friendly in-page alert, never an unhandled
        # 500" reasoning as app/web/reviewer/queue.py's reviewer_queue_page.
        logger.warning("Reviewer extract page failed to load sources", exc_info=True)
        return templates.TemplateResponse(
            request,
            "reviewer_extract.html",
            {
                "sources": [],
                "entity_types": ENTITY_TYPES,
                "target_fields": FIXED_SCALAR_TARGET_FIELDS,
                "ai_available": False,
                "error": EXTRACT_ERROR_MESSAGES[_DB_UNAVAILABLE_CODE],
                "pasted_text": pasted_text,
                "selected_source_id": selected_source_id,
                "selected_entity_type": selected_entity_type,
                "selected_entity_id": selected_entity_id,
                "result_status": None,
                "proposals": (),
                "is_money_field": _is_money_field,
                "default_currency": _DEFAULT_CURRENCY_FOR_MONEY_FIELDS,
            },
            status_code=503,
        )
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "reviewer_extract.html",
        {
            "sources": sources,
            "entity_types": ENTITY_TYPES,
            "target_fields": FIXED_SCALAR_TARGET_FIELDS,
            "ai_available": settings.ai_enabled and settings.ai_configured,
            "error": error,
            "pasted_text": pasted_text,
            "selected_source_id": selected_source_id,
            "selected_entity_type": selected_entity_type,
            "selected_entity_id": selected_entity_id,
            "result_status": result_status,
            "proposals": proposals,
            "is_money_field": _is_money_field,
            "default_currency": _DEFAULT_CURRENCY_FOR_MONEY_FIELDS,
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------


@router.get("/extract")
def reviewer_extract_page(
    request: Request,
    error: str | None = Query(default=None),
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    reviewer_session = _require_reviewer(session)
    return _render_extract_page(
        request, reviewer_session.client, error=extract_error_message(error)
    )


@router.post("/extract", dependencies=[Depends(require_reviewer_origin)])
def reviewer_extract_run(
    request: Request,
    pasted_text: str = Form(...),
    source_id: str = Form(...),
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    """Run the two-pass extraction pipeline over `pasted_text` and
    re-render this same page with whatever proposals survived (see
    `app/ai/extraction.py`'s `run_extraction`). Never writes anything —
    see module docstring."""
    reviewer_session = _require_reviewer(session)

    # mypy note: these four fields used to travel as a **common_kwargs
    # dict[str, str] splat into _render_extract_page below. That dict's
    # value type (str) doesn't match every OTHER keyword parameter on
    # that function (result_status/proposals/status_code), so mypy can't
    # prove a **dict[str, str] splat could never supply one of those --
    # spelled out explicitly at each call site instead, which is both
    # the type-safe form and no more verbose in practice.

    settings = get_settings()
    if not (settings.ai_enabled and settings.ai_configured):
        return _render_extract_page(
            request,
            reviewer_session.client,
            error=EXTRACT_ERROR_MESSAGES[_AI_UNAVAILABLE_CODE],
            pasted_text=pasted_text,
            selected_source_id=source_id,
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
        )

    try:
        provider = GeminiProvider()
    except GeminiNotConfiguredError:
        return _render_extract_page(
            request,
            reviewer_session.client,
            error=EXTRACT_ERROR_MESSAGES[_AI_UNAVAILABLE_CODE],
            pasted_text=pasted_text,
            selected_source_id=source_id,
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
        )

    reviewer_id = _current_reviewer_id(reviewer_session) or reviewer_session.access_token
    try:
        result = run_extraction(pasted_text, reviewer_id=reviewer_id, provider=provider)
    except AIBudgetExceededError:
        logger.warning("AI extraction budget exhausted for this reviewer")
        return _render_extract_page(
            request,
            reviewer_session.client,
            error=EXTRACT_ERROR_MESSAGES[_BUDGET_EXHAUSTED_CODE],
            pasted_text=pasted_text,
            selected_source_id=source_id,
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
        )
    except AIProviderError:
        logger.warning("AI extraction provider call failed", exc_info=True)
        return _render_extract_page(
            request,
            reviewer_session.client,
            error=EXTRACT_ERROR_MESSAGES[_AI_UNAVAILABLE_CODE],
            pasted_text=pasted_text,
            selected_source_id=source_id,
            selected_entity_type=entity_type,
            selected_entity_id=entity_id,
        )

    return _render_extract_page(
        request,
        reviewer_session.client,
        error=None,
        result_status=result.status,
        proposals=result.proposals,
        pasted_text=pasted_text,
        selected_source_id=source_id,
        selected_entity_type=entity_type,
        selected_entity_id=entity_id,
    )


@router.post("/extract/claims", dependencies=[Depends(require_reviewer_origin)])
def reviewer_extract_create_claim(
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    field: str = Form(...),
    value: str = Form(...),
    source_id: str = Form(...),
    verification_date: date = Form(...),
    verifier: str = Form(...),
    review_due_date: date = Form(...),
    currency: str | None = Form(default=None),
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    """One surviving proposal's pre-filled form, submitted for real. Calls
    straight into `app/api/claims.py`'s `create_claim` — see module
    docstring's "Why this doesn't POST straight to /claims" section.
    `extracted_by="ai"` is set here, in code, never taken from the form;
    `status` is left unset, so `create_claim` defaults it to `draft`
    exactly as it already does for every claim. This is not a new
    database write path -- it is the existing one, called the same way
    `app/web/reviewer/queue.py`'s action routes already call the other
    `app/api/claims.py` functions.

    `currency` (added for this fix -- see the "Money-field vocabulary"
    comment above `_is_money_field`) is forwarded to `CreateClaimRequest`
    exactly as submitted (normalised below), with no field-kind gating
    of its own here: `CreateClaimRequest.currency_matches_field_kind`
    (SCOPE-13, `app/api/claims.py`) is the one place that rule is
    enforced, and this route must not duplicate or second-guess it --
    the fix is to make this form SATISFY that validator, never to route
    around it (see this module's own fix-round note). In the normal
    template flow the currency input only exists on a money-field
    proposal's own form, so a non-money proposal simply never sends this
    field at all (`currency=None`, which `currency_matches_field_kind`
    already accepts). A hand-crafted POST that smuggles a currency onto
    a non-money field still hits that same validator's existing 422,
    exactly as it did before this fix -- proven by
    `tests/db/test_reviewer_extract.py`'s
    `TestReviewerExtractCreateClaimCurrency` class."""
    reviewer_session = _require_reviewer(session)

    # The template's `<input pattern="[A-Za-z]{3}">` (HTML5 client-side
    # hint only, never trusted as validation) accepts lower case so a
    # reviewer isn't tripped up by shift-lock; normalised to upper case
    # here to match `CreateClaimRequest.currency`'s own strict
    # `CURRENCY_PATTERN` (`^[A-Z]{3}$`) before that model ever sees it.
    normalised_currency = currency.strip().upper() if currency else currency
    try:
        claim_request = CreateClaimRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            value=value,
            source_id=source_id,
            verification_date=verification_date,
            verifier=verifier,
            review_due_date=review_due_date,
            extracted_by="ai",
            currency=normalised_currency,
        )
    except ValidationError:
        return _redirect_to_extract_with_error("invalid_input")

    try:
        create_claim(claim_request, session=reviewer_session)
    except HTTPException as exc:
        logger.warning(
            "Reviewer extract create-claim failed: status=%s", exc.status_code, exc_info=True
        )
        return _redirect_to_extract_with_error(error_code_for_detail(exc.detail))
    except Exception:
        logger.warning("Reviewer extract create-claim failed: db_unavailable", exc_info=True)
        return _redirect_to_extract_with_error(_DB_UNAVAILABLE_CODE)

    return RedirectResponse(url="/reviewer/queue", status_code=303)
