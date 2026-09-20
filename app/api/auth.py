"""POST /auth/sign-up, POST /auth/sign-in — thin wrapper over Supabase
Auth, which already underlies every RLS policy in this schema
(`auth.users`, `auth.uid()`).

Real minor accounts stay out of scope here (docs/SECURITY.md: disabled
until the consent and safeguarding workflow is built and reviewed by a
person — tasks/BCI-004.md). This route does not enforce an age check
itself; that gate belongs to a later, deliberately separate task, not a
side effect of shipping sign-up.

Each call gets a fresh client (app/db/client.py) — never shared, never
cached, per the concurrency fix in docs/DECISIONS.md.

**Guest -> account plan migration** (Lite Build Pack §6, docs/UI.md
"Account creation migrates it"): docs/UI.md's "Guest sessions" section
specifies an anonymous SERVER session (random token, no personal
fields, 7-day expiry, "never local storage for a plan"). Nothing here
implements that yet — no session table, no token, no expiry. What
exists instead is simpler: the client holds its own in-progress plan
(however it chooses to -- this route makes no assumption) and hands it
to sign-up as `pending_plan`, so "migration" means "accept the plan the
caller already has in hand and save it as the new account's first
plan," never a session lookup. This is a real, deliberate gap against
the docs/UI.md spec, not a documentation slip — flagged here (and in
STATUS.md) so whoever builds an actual guest-session mechanism doesn't
assume this route already has one to migrate from, and so the "never
local storage" requirement doesn't get silently violated by whatever
the client ends up doing to hold that plan in the meantime.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.db import get_anon_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class PendingPlan(BaseModel):
    """The one plan a guest was looking at right before signing up —
    supplied by the client, which is the only place it existed until
    now. Same shape as app.api.plans.SavePlanRequest, kept as a separate
    model rather than imported to avoid coupling auth.py to plans.py for
    what is otherwise an unrelated route."""

    pathway_id: str
    estimated_additional_expenses: float | None = None
    notes: str | None = None


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    pending_plan: PendingPlan | None = None


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user_id: str
    migrated_plan_id: str | None = None
    """Set when `pending_plan` was supplied and successfully saved.
    `None` with no error raised means either no pending_plan was sent,
    or saving it failed non-fatally — sign-up itself never fails because
    of a plan-save problem (see the handler)."""


def _migrate_pending_plan(
    client: Client, access_token: str, user_id: str, plan: PendingPlan
) -> str | None:
    """Best-effort: save the client's one pending plan as the new
    account's first saved plan. Failure here (e.g. the pathway_id
    doesn't exist, or — unlikely on a brand-new account — a duplicate)
    must never fail the sign-up itself; the account is the important
    part, and the client still has the plan's data locally to retry via
    POST /plans if this doesn't succeed.

    `user_id` must be passed explicitly and set on the insert — RLS's
    `saved_plans_own_row` policy checks `auth.uid() = student_id` via
    `WITH CHECK`, and an insert that omits `student_id` sends it as
    NULL, which never equals `auth.uid()` (caught by actually running
    this against the live project: the first version of this function
    omitted it and every call failed RLS, silently, exactly because of
    the except below — a good reminder that "fails safe" and "fails
    silently wrong" can look identical from the caller's side without a
    live test).

    **The failure is logged, not just swallowed** (security-review
    finding, 2026-09-19): the bug above would have been invisible in
    production with no log line at all — this exception path is the
    only place it could ever have surfaced. `notes` and
    `estimated_additional_expenses` are deliberately excluded from the
    log (student-supplied free text/figures; CLAUDE.md "no student data
    to development agents" and docs/SECURITY.md "no personal data in
    logs" — `user_id` and `pathway_id` are opaque ids already used
    throughout this schema's own RLS policies, not personal data)."""
    client.postgrest.auth(access_token)
    try:
        result = (
            client.table("saved_plans")
            .insert(
                {
                    "student_id": user_id,
                    "pathway_id": plan.pathway_id,
                    "estimated_additional_expenses": plan.estimated_additional_expenses,
                    "notes": plan.notes,
                }
            )
            .execute()
        )
    except Exception:
        logger.warning(
            "Guest->account plan migration failed for user_id=%s pathway_id=%s "
            "(account creation still succeeds; client should retry via POST /plans)",
            user_id,
            plan.pathway_id,
            exc_info=True,
        )
        return None
    rows = cast("list[dict[str, Any]]", result.data)
    return rows[0]["id"] if rows else None


@router.post("/sign-up", response_model=AuthResponse, status_code=201)
def sign_up(request: SignUpRequest) -> AuthResponse:
    client = get_anon_client()
    try:
        try:
            result = client.auth.sign_up({"email": request.email, "password": request.password})
        except AuthApiError as exc:
            # Propagate Supabase Auth's own HTTP status instead of
            # flattening every failure to 400. Matters concretely for
            # rate limiting: Supabase itself returns 429 with
            # exc.code == "over_email_send_rate_limit" (confirmed live,
            # 2026-09-19) — collapsing that to 400 is why
            # tests/db/test_api_auth.py used to have to guess at "was
            # this a rate limit?" by pattern-matching the free-text
            # message, which flaked under the test suite's own load
            # whenever Supabase phrased a different rate-limit variant
            # slightly differently. exc.status is what the provider
            # actually returned, not a guess; exc.message is already
            # safe, user-facing text.
            raise HTTPException(status_code=exc.status, detail=exc.message) from exc
        except Exception as exc:
            # Not a structured Supabase Auth error (network issue,
            # unexpected client-library exception) -- no provider status
            # to propagate, so surface it as a plain 400 same as before.
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if result.session is None or result.user is None:
            # Email confirmation is required by the project's Auth
            # settings — not an error, just no session yet. A
            # pending_plan can't be migrated without a session; the
            # client keeps holding it and retries via POST /plans once
            # the user has confirmed and signed in.
            raise HTTPException(
                status_code=202,
                detail="Account created. Check your email to confirm before signing in.",
            )

        migrated_plan_id = None
        if request.pending_plan is not None:
            migrated_plan_id = _migrate_pending_plan(
                client, result.session.access_token, result.user.id, request.pending_plan
            )

        return AuthResponse(
            access_token=result.session.access_token,
            user_id=result.user.id,
            migrated_plan_id=migrated_plan_id,
        )
    finally:
        # Every get_anon_client()/get_user_scoped_client() call returns a
        # fresh, unshared client (docs/DECISIONS.md's concurrency fix) —
        # each one owns its own httpx connection pool that nothing else
        # closes (data-security-reviewer finding applied here too, see
        # app/api/deps.py's identical pattern for the yield-dependency
        # routes; this route doesn't go through a FastAPI dependency, so
        # it needs its own explicit close).
        client.postgrest.aclose()


@router.post("/sign-in", response_model=AuthResponse)
def sign_in(request: SignInRequest) -> AuthResponse:
    client = get_anon_client()
    try:
        try:
            result = client.auth.sign_in_with_password(
                {"email": request.email, "password": request.password}
            )
        except Exception as exc:
            # Never distinguish "no such email" from "wrong password" —
            # that distinction is an account-enumeration leak.
            raise HTTPException(status_code=401, detail="Invalid email or password.") from exc

        if result.session is None or result.user is None:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        return AuthResponse(access_token=result.session.access_token, user_id=result.user.id)
    finally:
        client.postgrest.aclose()
