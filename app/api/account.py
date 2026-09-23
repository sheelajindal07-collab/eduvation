"""POST /account/withdraw — CONSENT-10, "withdraw consent": freeze the
caller's own account, revoke its consent, mark it deletion-due.

This is the HTTP surface CONSENT-4 explicitly left out of its own scope
(db/migrations/0013_safeguarding_schema.sql's own module docstring: "never
actual deletion execution ... not this task"). All the real logic —
setting `account_status = 'frozen'`, stamping `deletion_due_at = now() +
30 days`, and appending a `'withdrawn'` row to `consents` — already lives
in `withdraw_account()`, a database function, and stays there: this route
does nothing but call it (as the caller's own identity, via
`require_auth`'s RLS-scoped client — never a service-role/admin client,
and never any id read from a request body) and report the resulting
state. It holds no business logic of its own to keep in sync with the
database's, matching every other route in this codebase
(app/api/plans.py's own docstring: "RLS is the actual enforcement, not
application code").

Once this call succeeds, RLS (already built by CONSENT-4 — `account_
active()`/`is_admitted()` ANDed into `saved_plans`'/`student_profiles`'
policies) blocks every further write for that account, at the database
layer, regardless of this route. Freezing is not deletion: no row in
`auth.users`, `student_accounts`, `saved_plans` or anywhere else is ever
removed here or by `withdraw_account()` itself — actual deletion after the
30-day window is a STAFF RUNBOOK (docs/RUNBOOK-deletion.md), driven by a
future deletion-due list (CONSENT-8, not built here), never an automated
job.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.api.deps import AuthedSession, require_auth

router = APIRouter(prefix="/account", tags=["account"])

# Same two SQLSTATEs app/api/claims.py already distinguishes, for the same
# reasons — see that module's own comments for the full explanation of
# each code.
_RLS_VIOLATION = "42501"
_TRIGGER_RAISED = "P0001"


class WithdrawResponse(BaseModel):
    account_status: str
    deletion_due_at: datetime | None


def _own_account_row(session: AuthedSession) -> dict[str, Any] | None:
    """The caller's own `student_accounts` row, or None if it has none.

    `student_accounts_select_own` (db/migrations/0004_guardian_consent.sql)
    is a plain `auth.uid() = id` policy with no `account_active()`/
    `is_admitted()` gate on it (unlike `saved_plans`/`student_profiles`),
    so this keeps working after a freeze — this route's own read of "did
    the freeze actually happen" would otherwise go blind the moment it
    succeeds. Going through `session.client` (the caller's own RLS-scoped
    client, from `require_auth`) rather than any admin/service-role
    client means this can structurally never return a different
    identity's row.
    """
    result = session.client.table("student_accounts").select(
        "account_status, deletion_due_at"
    ).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    return rows[0] if rows else None


@router.post("/withdraw", response_model=WithdrawResponse)
def withdraw_account(session: AuthedSession = Depends(require_auth)) -> WithdrawResponse:
    """Calls `withdraw_account()` as the signed-in caller's own identity —
    `session.client` carries only that caller's bearer token, and the RPC
    itself resolves `auth.uid()` server-side (it takes no id parameter at
    all), so there is no path to withdraw anyone else's account from this
    route, no matter what a caller sends.

    `withdraw_account()`'s own contract (0013's comment) is "raise rather
    than silently no-op on a second call" — its `returns void` signature
    gives it no other channel to say "nothing happened". Two genuinely
    different situations arrive as the SAME raised message, because the
    function has no way to tell them apart from inside a single UPDATE
    statement:
      1. A real repeat withdrawal (already frozen) — this MUST be
         idempotent from a caller's perspective (this route's own
         contract, not the RPC's): calling withdraw twice must not be an
         error, and must not disturb the existing `deletion_due_at` (the
         RPC's own guard already guarantees the second part; this route
         adds the first).
      2. No `student_accounts` row to freeze at all — a genuine "nothing
         to withdraw" (0013's own comment: "a pre-existing account from
         before" the admission-axis fix, or a row-creation that silently
         failed) — a real error, not success.
    This route tells them apart the only way it safely can: by re-reading
    the caller's OWN row (never another identity's) after the RPC raises,
    since `student_accounts_select_own` stays readable through a freeze
    (see `_own_account_row`).
    """
    try:
        session.client.rpc("withdraw_account", {}).execute()
    except APIError as exc:
        if exc.code == _RLS_VIOLATION:
            # withdraw_account() is granted to `authenticated` only
            # (0013) -- reaching this branch at all would mean
            # `require_auth`'s own bearer-token check somehow let through
            # a token Postgres itself doesn't consider authenticated.
            # Same "clean response over a raw RPC error" convention as
            # app/api/auth.py's redeem_invite().
            raise HTTPException(status_code=401, detail="Sign in required.") from exc
        if exc.code == _TRIGGER_RAISED:
            row = _own_account_row(session)
            if row is not None and row["account_status"] == "frozen":
                # Case 1 above: already withdrawn. Report the existing
                # frozen state as success -- a repeat call is not a
                # caller error, and this changes nothing (the RPC's own
                # guard already refused to touch deletion_due_at or
                # insert a second consents row before raising).
                return WithdrawResponse(
                    account_status=row["account_status"],
                    deletion_due_at=row["deletion_due_at"],
                )
            # Case 2 above: genuinely nothing to withdraw.
            raise HTTPException(
                status_code=404, detail="No account found to withdraw."
            ) from exc
        raise HTTPException(
            status_code=400, detail="Could not withdraw this account."
        ) from exc

    row = _own_account_row(session)
    if row is None:  # pragma: no cover - defensive only, see docstring below
        # withdraw_account() just returned without raising, so its own
        # UPDATE matched a row -- this branch should be unreachable. Kept
        # as a clean 404 rather than an unhandled KeyError/TypeError below
        # in case of an impossible race with the function's own write.
        raise HTTPException(status_code=404, detail="No account found to withdraw.")
    return WithdrawResponse(
        account_status=row["account_status"], deletion_due_at=row["deletion_due_at"]
    )
