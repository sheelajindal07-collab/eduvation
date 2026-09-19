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
from pydantic import BaseModel, field_validator

from app.api.deps import AuthedSession, require_auth

router = APIRouter(prefix="/claims", tags=["claims"])

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
    result = session.client.table("claims").select("*").in_("status", statuses).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    return [_to_claim_out(row) for row in rows]
