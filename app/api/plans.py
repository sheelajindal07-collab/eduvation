"""POST/GET/PATCH/DELETE /plans — saved plans (Lite Build Pack §6
"Student work: saved_plans"; docs/UI.md "My Plan").

Every route requires sign-in (`app.api.deps.require_user_client`) — a
guest has nothing to save. RLS (db/migrations/0002_saved_plans.sql,
identical pattern to student_profiles) is the actual enforcement of
"only your own plans"; this route layer does no additional ownership
filtering of its own, same "one place access rules live" principle as
the other routes in this codebase.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.api.deps import AuthedSession, require_auth

router = APIRouter(prefix="/plans", tags=["plans"])

# Postgres error codes this router distinguishes, rather than collapsing
# every failure into one generic message (security-review finding,
# 2026-09-19: a nonexistent pathway_id and a malformed UUID were both
# previously mislabelled as "already saved").
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_INVALID_UUID_SYNTAX = "22P02"


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
    estimated_additional_expenses: float | None = None
    notes: str | None = None


class UpdatePlanRequest(BaseModel):
    estimated_additional_expenses: float | None = None
    notes: str | None = None


class PlanOut(BaseModel):
    id: str
    pathway_id: str
    estimated_additional_expenses: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


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
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
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
