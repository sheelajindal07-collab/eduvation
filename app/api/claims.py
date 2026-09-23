"""POST /claims, /claims/{id}/submit, /approve, /reject, /supersede,
GET /claims — the publishing console's HTTP surface (M4, tasks/BCI-005.md
"Not done yet"; docs/DATA.md "Publishing workflow").

Reviewer-only, enforced by RLS and the `enforce_claims_workflow` trigger
(db/migrations/0003_maker_checker.sql) — this route layer does no
additional access-control decision of its own, same "one place access
rules live" principle as every other route in this codebase
(app/api/plans.py's docstring says it plainly: RLS is the actual
enforcement, not application code). What this layer *does* own: setting
`created_by`/`reviewed_by` to the caller's own resolved user id — never a
client-supplied value — which is exactly the gap tasks/BCI-005.md flagged
as a known limitation of the DB layer alone ("created_by/reviewed_by are
not yet forced to equal the authenticated caller... tracked here for
whoever builds the publishing-console API to close").

Every one of these calls will fail with a 403 or 400 until
`db/migrations/0003_maker_checker.sql` is applied to the project (the
INSERT-must-be-draft/self-approval/immutability rules live entirely in
that trigger) — see STATUS.md for whether that's landed yet.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.deps import AuthedSession, require_auth
from app.data.models import CURRENCY_PATTERN

router = APIRouter(prefix="/claims", tags=["claims"])

# ---------------------------------------------------------------------
# SCOPE-13 -- currency required on money fields, forbidden on every other
# field.
#
# No single "the money fields" constant existed anywhere in this codebase
# before this card (checked app/data/models.py and app/rules/cost.py, the
# two places the card pointed at, plus a repo-wide grep) -- the cost
# engine (app/rules/cost.py, app/planning/comparison.py) is generic over
# whatever `FieldValue`s its caller hands it and never names a field by
# string itself except in these three exact places, which this list is
# copied from verbatim rather than inventing anything new:
#   - `app/planning/comparison.py`'s `_verified_charges_field_value`
#     (`_money_field_value("verified_charges", ...)`)
#   - `app/planning/comparison.py`'s `_estimated_additional_expenses_hint`
#     (`field_value_for("estimated_additional_expenses_hint", ...)`, fed
#     straight into `_money_from_field_value`)
#   - `app/planning/comparison.py`'s `assemble_cost_breakdown`
#     (`_money_field_value("potential_assistance_not_yet_awarded", ...)`)
#   - RULES-10's `fee_component:<name>` prefix convention
#     (`app/planning/comparison.py`'s `_FEE_COMPONENT_FIELD_PREFIX`,
#     mirrored -- not re-imported, matching this codebase's own
#     established file-local-constant convention, e.g. `_ENTITY_TABLES` in
#     app/web/reviewer/queue.py) for itemised fee lines.
# Kept file-local rather than moved into app/data/models.py or
# app/rules/cost.py, both outside this card's own file list.
# ---------------------------------------------------------------------

_MONEY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "verified_charges",
        "estimated_additional_expenses_hint",
        "potential_assistance_not_yet_awarded",
    }
)

_FEE_COMPONENT_FIELD_PREFIX = "fee_component:"
"""Mirrors `app/planning/comparison.py`'s own constant of the same name
(RULES-10) -- copied, not imported, per this module's docstring above."""


def _is_money_field(field: str) -> bool:
    return field in _MONEY_FIELD_NAMES or field.startswith(_FEE_COMPONENT_FIELD_PREFIX)


_RLS_VIOLATION = "42501"
_FOREIGN_KEY_VIOLATION = "23503"
_TRIGGER_RAISED = "P0001"
"""Postgres's default SQLSTATE for a plain `raise exception '...'` in
plpgsql with no explicit errcode — every workflow-state-machine and
self-approval message from `enforce_claims_workflow` arrives with this
code. Those messages are already written to be shown to a reviewer (not
internal detail), the same way app/api/auth.py relays Supabase Auth's
own error text directly."""


def _current_user_id(session: AuthedSession) -> str:
    """Identical pattern to app/api/plans.py's private helper of the same
    name — kept file-local rather than shared, matching this codebase's
    existing convention of not coupling otherwise-unrelated route files
    over a two-line helper (see app/api/auth.py's PendingPlan docstring
    for the same reasoning applied elsewhere)."""
    user_response = session.client.auth.get_user(jwt=session.access_token)
    if user_response is None or user_response.user is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user_response.user.id


def _raise_for_claims_error(exc: APIError) -> None:
    """Every route below funnels its Postgres errors through this one
    mapping, so "not a reviewer", "bad workflow transition", and "source
    doesn't exist" always come back as the same status code no matter
    which route triggered them."""
    if exc.code == _RLS_VIOLATION:
        raise HTTPException(
            status_code=403, detail="Only a reviewer can do this."
        ) from exc
    if exc.code == _FOREIGN_KEY_VIOLATION:
        raise HTTPException(status_code=404, detail="Referenced source not found.") from exc
    if exc.code == _TRIGGER_RAISED:
        # The trigger's own message IS the explanation (self-approval,
        # invalid transition, frozen content, ...) -- relay it as-is
        # rather than collapsing every workflow violation into one
        # generic "bad request".
        raise HTTPException(status_code=400, detail=exc.message) from exc
    raise HTTPException(status_code=400, detail="Could not process this claim.") from exc


class CreateClaimRequest(BaseModel):
    entity_type: str
    entity_id: str
    field: str
    value: str | int | float | bool | None
    source_id: str
    verification_date: date
    verifier: str
    review_due_date: date
    extracted_by: Literal["human", "ai"] = "human"
    """Matches the DB's own CHECK constraint (0001_init.sql) — validated
    here too so an invalid value is a clean 422 from pydantic rather than
    a raw Postgres constraint-violation error relayed to the caller."""
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)
    """SCOPE-13 / docs/CONTRACTS.md "Money and currency": ISO 4217,
    uppercase (same shape `app/data/models.py`'s `Claim.currency` and
    `db/migrations/0008_jurisdiction_currency.sql`'s CHECK constraint
    already require) -- REQUIRED on a money field (`_is_money_field`)
    and FORBIDDEN on every other field, enforced below. A money-valued
    claim with no currency is exactly the state
    `app/planning/comparison.py`'s `_money_field_value` already treats as
    `not_available` once published -- refusing it at write time (422)
    catches the mistake before a reviewer ever approves a fee nobody can
    actually read, instead of a confidently-badged number the arithmetic
    layer silently discards."""

    @model_validator(mode="after")
    def currency_matches_field_kind(self) -> CreateClaimRequest:
        """SCOPE-13's own two rules, both server-side (never a
        form/template-only check, per this card's named risk): a money
        field submitted with no currency, and a non-money field submitted
        WITH one, are both a 422 -- pydantic's own `ValueError`, not a
        raw Postgres constraint failure, so the caller (the JSON API
        directly, or `app/web/reviewer/extract.py`'s
        `reviewer_extract_create_claim`, which already turns any
        `ValidationError` from constructing this exact model into a
        styled console alert rather than a stack trace) gets a clean,
        honest error either way."""
        is_money = _is_money_field(self.field)
        if is_money and self.currency is None:
            raise ValueError(
                f"'{self.field}' is a money field and must be submitted with a currency "
                "(ISO 4217, e.g. 'INR') -- docs/CONTRACTS.md \"Money and currency\"."
            )
        if not is_money and self.currency is not None:
            raise ValueError(
                f"'{self.field}' is not a money field and must not carry a currency -- "
                "only verified_charges, estimated_additional_expenses_hint, "
                "potential_assistance_not_yet_awarded and fee_component:<name> take one."
            )
        return self

    @field_validator("verifier")
    @classmethod
    def verifier_must_be_a_person(cls, v: str) -> str:
        # docs/DATA.md, Claim.verifier: "a person's identifier — never
        # 'ai'" (see extracted_by for how AI-authored drafts are actually
        # flagged). A literal "ai" here is a caller bug worth rejecting
        # up front, not a valid identifier that happens to look odd.
        if v.strip().lower() == "ai":
            raise ValueError(
                "verifier must be a person's identifier, never the literal 'ai' "
                "-- use extracted_by='ai' to flag an AI-authored draft instead."
            )
        return v


class SupersedeRequest(BaseModel):
    new_claim_id: str
    """An existing claim (created via a normal POST /claims call) that
    replaces this one. Its own status is this route's business —
    superseding the old claim does not require the new one to already be
    published; the new claim goes through its own draft/submit/approve
    cycle independently. See module docstring."""


class ClaimOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    field: str
    value: str | int | float | bool | None
    source_id: str
    verification_date: date
    verifier: str
    status: str
    review_due_date: date
    superseded_by: str | None
    created_by: str | None
    reviewed_by: str | None
    extracted_by: str
    jurisdiction: str
    """SCOPE-13: db/migrations/0008_jurisdiction_currency.sql column,
    never surfaced on this response shape before this card -- defaults to
    'IN' at the database layer, so every existing row (published before
    this column existed) still round-trips here."""
    academic_cycle: str | None
    """SCOPE-13: as above -- nullable, a text label (`docs/CONTRACTS.md`
    "Duration, dates, cycle, DOB"), not a date."""
    currency: str | None
    """SCOPE-13: as above -- see `CreateClaimRequest.currency`'s own
    docstring for why this is `None` for a non-money claim and a required
    ISO 4217 code for a money one."""


def _to_claim_out(row: dict[str, Any]) -> ClaimOut:
    return ClaimOut.model_validate(row)


@router.post("", response_model=ClaimOut, status_code=201)
def create_claim(
    request: CreateClaimRequest, session: AuthedSession = Depends(require_auth)
) -> ClaimOut:
    """Step 1, "Draft" (docs/DATA.md). `status` is never accepted from the
    caller — always inserted as `draft`, both because that's the only
    correct starting state and because the trigger would reject anything
    else anyway; setting it explicitly here means a reviewer sees a clean
    422-shaped validation story instead of a raw trigger error for a
    field this route already knows the right value for."""
    created_by = _current_user_id(session)
    try:
        result = (
            session.client.table("claims")
            .insert(
                {
                    "entity_type": request.entity_type,
                    "entity_id": request.entity_id,
                    "field": request.field,
                    "value": request.value,
                    "source_id": request.source_id,
                    "verification_date": request.verification_date.isoformat(),
                    "verifier": request.verifier,
                    "review_due_date": request.review_due_date.isoformat(),
                    "extracted_by": request.extracted_by,
                    "status": "draft",
                    "created_by": created_by,
                    "currency": request.currency,
                }
            )
            .execute()
        )
    except APIError as exc:
        _raise_for_claims_error(exc)
        raise  # unreachable -- _raise_for_claims_error always raises
    return _to_claim_out(cast("dict[str, Any]", result.data[0]))


def _transition(
    session: AuthedSession, claim_id: str, updates: dict[str, Any]
) -> ClaimOut:
    try:
        result = (
            session.client.table("claims").update(updates).eq("id", claim_id).execute()
        )
    except APIError as exc:
        _raise_for_claims_error(exc)
        raise  # unreachable
    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        # Either the claim doesn't exist, or RLS filtered it out (a
        # non-reviewer can't even see a draft) -- these must look
        # identical to the caller, same reasoning as app/api/plans.py's
        # update_plan (docs/UI.md "Permission denied: explain the
        # boundary without exposing another user's data").
        raise HTTPException(status_code=404, detail="Claim not found.")
    return _to_claim_out(rows[0])


@router.post("/{claim_id}/submit", response_model=ClaimOut)
def submit_claim(claim_id: str, session: AuthedSession = Depends(require_auth)) -> ClaimOut:
    """Step 2a, "Review" begins: draft -> in_review. Any reviewer may
    submit any draft (the docs don't restrict this to the draft's own
    author, and a small pilot reviewer pool doesn't need that
    restriction) — the trigger still refuses anything but a
    draft-or-in_review claim."""
    return _transition(session, claim_id, {"status": "in_review"})


@router.post("/{claim_id}/reject", response_model=ClaimOut)
def reject_claim(claim_id: str, session: AuthedSession = Depends(require_auth)) -> ClaimOut:
    """Step 2b, sent back for revision: in_review -> draft. No reason
    field exists in the schema yet to persist a rejection note — a known
    gap, not silently assumed away (there is nowhere to put it)."""
    return _transition(session, claim_id, {"status": "draft"})


@router.post("/{claim_id}/approve", response_model=ClaimOut)
def approve_claim(claim_id: str, session: AuthedSession = Depends(require_auth)) -> ClaimOut:
    """Step 3, "Publish": in_review -> published. `reviewed_by` is set
    here, to the caller's own resolved id — never client-supplied. If
    that id equals the claim's `created_by`, the trigger rejects this
    with the self-approval message (the actual guarantee this whole
    slice exists for), which `_raise_for_claims_error` relays as-is."""
    reviewed_by = _current_user_id(session)
    return _transition(session, claim_id, {"status": "published", "reviewed_by": reviewed_by})


@router.post("/{claim_id}/supersede", response_model=ClaimOut)
def supersede_claim(
    claim_id: str, request: SupersedeRequest, session: AuthedSession = Depends(require_auth)
) -> ClaimOut:
    """Step 4, "Correction": published -> superseded, pointing at a
    replacement claim. The trigger separately guarantees no other field
    on this row can change in the same update — a correction always
    means a new claim, never a rewritten old one."""
    return _transition(
        session, claim_id, {"status": "superseded", "superseded_by": request.new_claim_id}
    )


@router.get("", response_model=list[ClaimOut])
def list_claims(
    status: list[str] | None = Query(default=None, alias="status"),
    session: AuthedSession = Depends(require_auth),
) -> list[ClaimOut]:
    """The review queue: what needs a reviewer's attention. Defaults to
    draft/in_review (the actual "needs action" set) rather than
    everything, since `published`/`superseded` claims are the ones a
    reviewer is least likely to be asking for here — pass
    `?status=published` explicitly to see those instead. RLS still
    decides what's actually visible: a non-reviewer gets an empty list
    for anything but published, never an error that would reveal drafts
    exist at all."""
    statuses = status or ["draft", "in_review"]
    # UI-review finding, 2026-09-21 (FIX 10, MEDIUM): no ORDER BY at all
    # means Postgres gives no ordering guarantee -- the queue's row order
    # could shift between requests as the table grows. Most-overdue-first
    # (review_due_date ascending) is the most useful default for a
    # reviewer actually working the queue, not just a tie-breaker for
    # determinism's own sake. Existing tests only assert set/dict
    # membership over the response, never a specific order, so this is
    # additive, not breaking.
    result = (
        session.client.table("claims")
        .select("*")
        .in_("status", statuses)
        .order("review_due_date")
        .execute()
    )
    rows = cast("list[dict[str, Any]]", result.data)
    return [_to_claim_out(row) for row in rows]
