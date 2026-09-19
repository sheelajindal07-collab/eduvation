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

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import AuthedSession, require_auth

router = APIRouter(prefix="/plans", tags=["plans"])


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
    except Exception as exc:
        # Most likely the (student_id, pathway_id) unique constraint —
        # this pathway is already saved. A clean 409, not a raw 500.
        raise HTTPException(
            status_code=409, detail="This pathway is already in your saved plans."
        ) from exc
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
    result = session.client.table("saved_plans").delete().eq("id", plan_id).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        raise HTTPException(status_code=404, detail="Plan not found.")
