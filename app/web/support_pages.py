"""GET /reviewer/support — CONSENT-8: the staff-only safeguarding queue.

A NEW router, deliberately not folded into `app/web/reviewer/` (the card's
own instruction): that package's routes are gated on `is_reviewer()` (a
content reviewer, via `app/api/claims.py`'s RLS-scoped queries) — this
route is gated on a DIFFERENT, narrower role, `is_safeguarding_staff()`
(`db/migrations/0013_safeguarding_schema.sql`), and CLAUDE.md/docs/CONSENT.md
section 6 are explicit that the two must never be conflated: "students AND
content reviewers read ZERO rows of safeguarding_flags."

## Session mechanism — reused, not reimplemented
`get_reviewer_session` (`app/web/reviewer/auth.py`) is reused AS-IS: the
same sign-in form, the same cookie, the same `AuthedSession` shape. Nothing
about SIGNING IN is specific to safeguarding staff — the same person who
runs a content review could separately be a safeguarding-staff member, or
not, and the cookie alone answers neither question. What is specific to
this route is the extra `is_safeguarding_staff()` RPC check below, done
BEFORE any query against `safeguarding_flags` — this route adds its own
access-control decision on top of `get_reviewer_session`, unlike every
route in `app/web/reviewer/queue.py` (which relies on RLS alone, see that
module's own docstring) — because RLS alone is not the whole story here:
docs/UI.md's difficult-state table names "Permission denied — explain the
boundary without exposing another user's data" as its own distinct state
from "Empty (no results for this user/filter)", and the task is explicit
that a signed-in non-staff visitor (a content reviewer very much included)
"must see nothing here, not even an empty authorized page." Relying on RLS
alone would give exactly the wrong one of those two states: RLS already
filters `safeguarding_flags` to zero rows for a non-staff caller
(`db/migrations/0013_safeguarding_schema.sql`'s own `safeguarding_flags_
select_staff` policy), which is indistinguishable, on this page, from "you
are staff and there is nothing overdue right now" — the empty-but-
authorized-looking page the task says must never be shown to a non-staff
visitor. So this route checks staff-ness explicitly and returns the
CORRECT difficult state (403, "Permission denied") instead of silently
falling through to the wrong one (200, "Empty").

## Frozen accounts — disclosed gap, not a silent drop
The card asks this page to also list `student_accounts` rows with
`account_status = 'frozen'` and their `deletion_due_at`. `student_accounts`
has exactly two RLS policies today
(`db/migrations/0004_guardian_consent.sql`): `student_accounts_select_own`
and `student_accounts_insert_own`, both scoped to `auth.uid() = id` — there
is no policy, and no `SECURITY DEFINER` function analogous to
`is_safeguarding_staff()`, that lets ANY signed-in session (staff included)
read another user's `student_accounts` row. Building one is a migration
(a new RLS policy or a narrow definer function mirroring `is_safeguarding_
staff()`'s own "answers only what the caller is entitled to see" shape) —
squarely migration-owner work, not this file's. Rather than fabricate a
service-role bypass here (this app's app/db/client.py exposes no
service-role client to any route for exactly this reason — see that
module's own two-function contract: anon and user-scoped only — and every
other console route in this codebase relies on RLS as "the real
enforcement", never an app-level workaround) or silently drop the section,
this page renders it as CLAUDE.md's own required difficult state: "a
missing section says 'Not available', never dropped silently." See this
task's own completion report for the proposed migration text.

## Acknowledge — same disclosed gap
`safeguarding_flags` (0013) has no acknowledged/status column and
deliberately NO update policy for anyone ("Phase-2's detection logic ...
will need its own write path ... when it exists" — that module's own
comment). There is nothing in today's schema an "acknowledge" action could
durably write to. Rather than wire a button that always fails (or, worse,
silently succeeds without persisting anything — CLAUDE.md's "Save failed:
keep the draft visible; never say 'Saved'" difficult state applies exactly
here, and a fake acknowledgment would be the safeguarding-specific version
of "said Saved and wasn't"), no acknowledge control is rendered at all —
same precedent as `docs/UI.md`'s own `reminder_opt_in()`, which "renders
nothing without an `action_url`."
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import AuthedSession
from app.web.reviewer.auth import COOKIE_NAME, COOKIE_PATH, get_reviewer_session
from app.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviewer", tags=["safeguarding-support"], include_in_schema=False)

OVERDUE_AFTER = timedelta(hours=24)
"""The task's own threshold: "visually highlights any flag older than 24
hours." A named constant, not a magic literal, so the unit test
(`tests/unit/test_flag_overdue.py`) and this module agree on one number."""


def is_flag_overdue(created_at: datetime, now: datetime | None = None) -> bool:
    """Pure, unit-testable: strictly more than 24 hours old.

    `now` defaults to the real current time; a test passes an explicit
    value so "deliberately timestamped >24h old" / "deliberately
    timestamped recent" (the task's own acceptance wording) never depends
    on wall-clock timing. A naive `created_at` (should not happen —
    `safeguarding_flags.created_at` is `timestamptz` — but defensive
    against a hand-built test value) is treated as UTC rather than raising.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    resolved_now = now if now is not None else datetime.now(UTC)
    return (resolved_now - created_at) > OVERDUE_AFTER


class SafeguardingFlagRow(BaseModel):
    """One `safeguarding_flags` row, exactly as the task specifies:
    "timestamp, the student's OPAQUE id only -- never an email or name,
    category, status." There is no separate `status` column in 0013 (see
    this module's own docstring, "Acknowledge" section) — the row's
    workflow status is always "open" today, since nothing can move it to
    anything else yet; this model carries no status field rather than
    inventing one no column backs.
    """

    id: str
    student_id: str
    category: str
    created_at: datetime


def _redirect_to_sign_in() -> RedirectResponse:
    """Same shape as `app/web/reviewer/auth.py`'s own helper of this name
    (not imported directly — that name is soft-private to the reviewer
    package's own sibling modules; this router lives outside it) — a
    stale/invalid cookie must not loop a visitor between this page and
    sign-in."""
    response = RedirectResponse(url="/reviewer/sign-in", status_code=303)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return response


@router.get("/support")
def support_queue_page(
    request: Request,
    session: AuthedSession | None = Depends(get_reviewer_session),
) -> Any:
    """Staff-only. See this module's docstring for the full reasoning
    behind every branch below."""
    if session is None:
        return _redirect_to_sign_in()

    try:
        is_staff = bool(session.client.rpc("is_safeguarding_staff", {}).execute().data)
    except Exception:
        # DB/network unavailable — a distinct case from "signed in but not
        # staff" (which is not an error at all, see below). Matches
        # app/web/reviewer/queue.py's own degrade-gracefully pattern for
        # this failure class.
        logger.warning(
            "Support queue: could not check safeguarding-staff status", exc_info=True
        )
        return templates.TemplateResponse(
            request,
            "reviewer_support.html",
            {"unavailable": True},
            status_code=503,
        )

    if not is_staff:
        # See this module's docstring, "Session mechanism" section: this
        # is the one deliberate access-control decision this router makes
        # for itself, precisely because RLS alone would produce the WRONG
        # difficult state (an empty-but-authorized page) for this case.
        # app/web/errors.py's global handler renders the one fixed
        # "Permission denied" copy every other HTML route in this app
        # already uses for this state — this route makes no separate
        # rendering decision of its own.
        raise HTTPException(status_code=403, detail="Not authorized.")

    try:
        flags_result = (
            session.client.table("safeguarding_flags")
            .select("id, student_id, category, created_at")
            .order("created_at")
            .execute()
        )
        flags = [
            SafeguardingFlagRow.model_validate(row)
            for row in cast("list[dict[str, Any]]", flags_result.data)
        ]
    except Exception:
        logger.warning("Support queue: could not load safeguarding_flags", exc_info=True)
        return templates.TemplateResponse(
            request,
            "reviewer_support.html",
            {"unavailable": True},
            status_code=503,
        )

    now = datetime.now(UTC)
    flag_rows = [
        {"flag": flag, "overdue": is_flag_overdue(flag.created_at, now)} for flag in flags
    ]

    return templates.TemplateResponse(
        request,
        "reviewer_support.html",
        {
            "unavailable": False,
            "flags": flag_rows,
            # See this module's own docstring, "Frozen accounts" section:
            # a real, disclosed gap, not an oversight — `student_accounts`
            # has no policy letting any signed-in session read another
            # user's row, staff included.
            "frozen_accounts_available": False,
        },
    )
