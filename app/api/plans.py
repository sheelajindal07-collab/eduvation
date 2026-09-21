"""POST/GET/PATCH/DELETE /plans — saved plans (Lite Build Pack §6
"Student work: saved_plans"; docs/UI.md "My Plan").

Every route requires sign-in (`app.api.deps.require_auth`) — a guest has
nothing to save here; a guest's routes live in `guest_plans` behind
`app/web/guest_session.py` instead (AUTH-4). RLS
(db/migrations/0002_saved_plans.sql, tightened by 0004's
`account_active` gate, plus 0010's `plan_actions_own_row`) is the actual
enforcement of "only your own plans"; this route layer does no
additional ownership filtering of its own, same "one place access rules
live" principle as the other routes in this codebase.

AUTH-5 adds: the current-decision flag, the next-actions checklist, and
input bounds on the two free-form fields.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from app.api.deps import AuthedSession, require_auth
from app.planning.actions import is_known_action_key

router = APIRouter(prefix="/plans", tags=["plans"])

# AUTH-5 input bounds. `notes` is the one place a student types free text
# that is stored, so it gets a length ceiling: unbounded text on a
# student-owned row is both a storage problem and, more importantly,
# somewhere a child could paste far more about themselves than this
# product ever asked for (docs/DATA.md "Minimisation").
MAX_NOTES_LENGTH = 2000

# A sanity ceiling on a rupee figure, not a product rule — the same bound
# db/migrations/0009_guest_sessions.sql puts on the guest equivalent, so
# the two paths cannot disagree about what counts as absurd.
MAX_EXPENSES = 100_000_000.0

# Postgres error codes this router distinguishes, rather than collapsing
# every failure into one generic message (security-review finding,
# 2026-09-19: a nonexistent pathway_id and a malformed UUID were both
# previously mislabelled as "already saved").
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_INVALID_UUID_SYNTAX = "22P02"
# "new row violates row-level security policy" — what Postgres raises
# when a WITH CHECK clause refuses a write. Mapped to 404 below, never
# surfaced as its own status: a caller who could tell "refused by RLS"
# apart from "no such row" would have an existence oracle for other
# students' plan ids (caught by tests/db/test_plan_actions.py's
# `test_b_ticking_a_s_plan_gets_404_not_a_row`, which saw a 400 here).
_RLS_VIOLATION = "42501"


def _require_valid_uuid(value: str, *, field_name: str = "plan_id") -> None:
    """Reject a malformed id before it ever reaches a query — without
    this, PATCH/DELETE /plans/<not-a-uuid> fell through to an unhandled
    500 instead of a clean 422 (security-review finding, 2026-09-19)."""
    try:
        uuid_module.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"{field_name!r} is not a valid id."
        ) from exc


class SavePlanRequest(BaseModel):
    pathway_id: str
    estimated_additional_expenses: float | None = Field(
        default=None, ge=0, le=MAX_EXPENSES
    )
    notes: str | None = Field(default=None, max_length=MAX_NOTES_LENGTH)


class UpdatePlanRequest(BaseModel):
    """Every field is optional AND nullable, which are two different
    things here — see `update_plan` below for why that distinction is
    the whole fix."""

    estimated_additional_expenses: float | None = Field(
        default=None, ge=0, le=MAX_EXPENSES
    )
    notes: str | None = Field(default=None, max_length=MAX_NOTES_LENGTH)
    is_current: bool | None = None


class PlanOut(BaseModel):
    id: str
    pathway_id: str
    estimated_additional_expenses: float | None
    notes: str | None
    is_current: bool = False
    """AUTH-5. Defaulted so this still validates against a row read in
    the deploy window before db/migrations/0010_plan_actions.sql is
    applied, where PostgREST omits the column entirely."""
    created_at: datetime
    updated_at: datetime


class PlanActionOut(BaseModel):
    action_key: str
    done: bool
    done_at: datetime | None = None


class TickActionRequest(BaseModel):
    done: bool


def _current_user_id(session: AuthedSession) -> str:
    """Resolve the calling student's id from their own access token via
    a live Supabase Auth check — never decoded/trusted client-side, and
    never the value of any client-supplied field. The token must be
    passed explicitly: see AuthedSession's docstring for why a bare
    `client.auth.get_user()` would not find a session on this client."""
    user_response = session.client.auth.get_user(jwt=session.access_token)
    if user_response is None or user_response.user is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user_response.user.id


@router.post("", response_model=PlanOut, status_code=201)
def save_plan(request: SavePlanRequest, session: AuthedSession = Depends(require_auth)) -> PlanOut:
    _require_valid_uuid(request.pathway_id, field_name="pathway_id")
    student_id = _current_user_id(session)
    try:
        result = (
            session.client.table("saved_plans")
            .insert(
                {
                    "student_id": student_id,
                    "pathway_id": request.pathway_id,
                    "estimated_additional_expenses": request.estimated_additional_expenses,
                    "notes": request.notes,
                }
            )
            .execute()
        )
    except APIError as exc:
        # Distinguished, not collapsed into one message (security-review
        # finding, 2026-09-19): a genuine duplicate, a pathway that
        # doesn't exist, and (belt-and-braces alongside the explicit
        # check above) a malformed id are three different problems.
        if exc.code == _UNIQUE_VIOLATION:
            raise HTTPException(
                status_code=409, detail="This pathway is already in your saved plans."
            ) from exc
        if exc.code == _FOREIGN_KEY_VIOLATION:
            raise HTTPException(status_code=404, detail="Pathway not found.") from exc
        if exc.code == _INVALID_UUID_SYNTAX:
            raise HTTPException(status_code=422, detail="Invalid pathway_id.") from exc
        raise HTTPException(status_code=400, detail="Could not save this plan.") from exc
    row = cast("dict[str, Any]", result.data[0])
    return PlanOut.model_validate(row)


@router.get("", response_model=list[PlanOut])
def list_plans(session: AuthedSession = Depends(require_auth)) -> list[PlanOut]:
    result = session.client.table("saved_plans").select("*").execute()
    rows = cast("list[dict[str, Any]]", result.data)
    return [PlanOut.model_validate(row) for row in rows]


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: str,
    request: UpdatePlanRequest,
    session: AuthedSession = Depends(require_auth),
) -> PlanOut:
    _require_valid_uuid(plan_id)

    # `exclude_unset=True`, NOT the old `if v is not None` filter.
    #
    # The old version dropped every null before building the update, so
    # there was no way to CLEAR a field: `{"notes": null}` was
    # indistinguishable from not mentioning notes at all, and a student
    # who wanted to remove a note they had written simply could not
    # (AUTH-5: "allow clearing notes/expenses", "PATCH can null a
    # field"). `exclude_unset` asks pydantic the right question — which
    # keys did the caller actually send — so an explicit null is kept
    # and an absent key is still left alone, which is what PATCH means.
    updates: dict[str, Any] = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    # Switching the current decision is two statements, and the partial
    # unique index (db/migrations/0010_plan_actions.sql) makes a
    # half-finished switch fail loudly rather than leave two rows
    # flagged current. Clearing first is what makes the common case —
    # "make this one current instead" — work without the caller having
    # to un-set the old one themselves.
    #
    # The clear is scoped by `is_current` only: RLS already restricts it
    # to this student's own rows (saved_plans_own_row, 0002/0004), and
    # adding a student_id filter here would mean trusting a value this
    # layer would have to fetch rather than the policy that is already
    # authoritative.
    #
    # Security review, migration-lane merge (2026-09-21): confirmed live
    # that clearing before checking the target left a caller with ZERO
    # current plans on a 404 (a nonexistent id, a plan raced away in
    # another tab, or one deleted elsewhere) -- two separate requests,
    # not one transaction, so a failure of the second couldn't undo the
    # first. Fixed by checking existence (RLS-scoped, same "not found or
    # not yours" ambiguity as the final 404 below) BEFORE touching
    # anything, so a 404 now genuinely changes nothing.
    if updates.get("is_current") is True:
        exists = (
            session.client.table("saved_plans").select("id").eq("id", plan_id).execute()
        )
        if not cast("list[dict[str, Any]]", exists.data):
            raise HTTPException(status_code=404, detail="Plan not found.")
        session.client.table("saved_plans").update({"is_current": False}).eq(
            "is_current", True
        ).execute()

    result = session.client.table("saved_plans").update(updates).eq("id", plan_id).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        # Either it doesn't exist, or RLS silently filtered a plan that
        # belongs to someone else -- these must look identical to the
        # caller (docs/UI.md "Permission denied: explain the boundary
        # without exposing another user's data").
        raise HTTPException(status_code=404, detail="Plan not found.")
    return PlanOut.model_validate(rows[0])


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: str, session: AuthedSession = Depends(require_auth)) -> None:
    _require_valid_uuid(plan_id)
    result = session.client.table("saved_plans").delete().eq("id", plan_id).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        raise HTTPException(status_code=404, detail="Plan not found.")


# --------------------------------------------------------------------
# Next actions (AUTH-5)
# --------------------------------------------------------------------
# Which actions EXIST is derived from published claims in ordinary code
# (app/planning/actions.py) and never stored. These routes record only
# whether the student has ticked one off, so `plan_actions` holds no
# content that could go stale against the claims it came from.


@router.get("/{plan_id}/actions", response_model=list[PlanActionOut])
def list_plan_actions(
    plan_id: str, session: AuthedSession = Depends(require_auth)
) -> list[PlanActionOut]:
    """The tick state for one plan's actions.

    RLS (`plan_actions_own_row`, db/migrations/0010_plan_actions.sql)
    scopes this to the caller's own plans via the parent row, so another
    student's plan_id simply returns nothing — the same shape as every
    other route here, and indistinguishable from "no actions ticked
    yet", which is deliberate (docs/UI.md: explain the boundary without
    exposing another user's data).
    """
    _require_valid_uuid(plan_id)
    result = (
        session.client.table("plan_actions")
        .select("action_key, done, done_at")
        .eq("plan_id", plan_id)
        .execute()
    )
    rows = cast("list[dict[str, Any]]", result.data)
    return [PlanActionOut.model_validate(row) for row in rows]


@router.put("/{plan_id}/actions/{action_key}", response_model=PlanActionOut)
def tick_plan_action(
    plan_id: str,
    action_key: str,
    request: TickActionRequest,
    session: AuthedSession = Depends(require_auth),
) -> PlanActionOut:
    """Tick or un-tick one action.

    PUT, not POST: ticking an action that is already ticked is the same
    request twice, not a second row — `plan_actions` has a unique
    (plan_id, action_key), and this upserts against it.

    `action_key` is validated against the closed set
    `app/planning/actions.py` can actually produce. The column is plain
    `text` with no enum behind it, so without this a caller could store
    any string at all on a table that is deliberately supposed to hold
    no free text.

    `done_at` is never accepted from the caller — the
    `plan_actions_set_done_at` trigger owns it (0010), so a client
    cannot claim to have done something last week.
    """
    _require_valid_uuid(plan_id)
    if not is_known_action_key(action_key):
        raise HTTPException(status_code=422, detail="Unknown action.")

    try:
        result = (
            session.client.table("plan_actions")
            .upsert(
                {"plan_id": plan_id, "action_key": action_key, "done": request.done},
                on_conflict="plan_id,action_key",
            )
            .execute()
        )
    except APIError as exc:
        # A plan that does not exist (FK) and a plan that belongs to
        # someone else (RLS) are deliberately the same 404 — see
        # `_RLS_VIOLATION` above.
        if exc.code in {_FOREIGN_KEY_VIOLATION, _RLS_VIOLATION}:
            raise HTTPException(status_code=404, detail="Plan not found.") from exc
        if exc.code == _INVALID_UUID_SYNTAX:
            raise HTTPException(status_code=422, detail="Invalid plan_id.") from exc
        raise HTTPException(status_code=400, detail="Could not update this action.") from exc

    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        # RLS refused the write because the plan is not this student's.
        # Same 404 as "no such plan", on purpose.
        raise HTTPException(status_code=404, detail="Plan not found.")
    return PlanActionOut.model_validate(rows[0])
