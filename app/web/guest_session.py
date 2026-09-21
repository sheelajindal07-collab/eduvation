"""Guest server sessions — the cookie half of AUTH-4.

docs/CONTRACTS.md, "Settled — guest state": "A guest *plan* uses a
server-side guest session (opaque id, httponly cookie) over
`guest_sessions`/`guest_plans`, merged into the account at sign-up by a
one-way, idempotent definer function. No birth year is stored for a
guest."

**What this module is not.** It holds no access rules. Everything that
decides which rows a caller may see lives in
`db/migrations/0009_guest_sessions.sql` — deny-all RLS on both tables
plus four SECURITY DEFINER functions that resolve the caller's session
from the token before touching anything. This module carries the token
between the browser and those functions and does nothing else, so there
is exactly one place the isolation rule lives.

**The token.** 256 bits of randomness, generated inside Postgres by
`create_guest_session()` and returned exactly once. The database keeps
only its SHA-256 hash, so the value in the cookie is the only copy that
exists anywhere. This module never writes it to a log, never puts it in
a URL or a query parameter, and never hands it to a template.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from fastapi import Request, Response
from supabase import Client

from app.core.config import get_settings

COOKIE_NAME = "bcion_guest_session"
"""Sits beside `bcion_student_session` and `bcion_reviewer_session`
(docs/CONTRACTS.md, "Error shape, sessions, guest state, flags")."""

COOKIE_PATH = "/"

COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
"""7 days, matching `guest_sessions.expires_at`'s own default exactly.

Kept deliberately in step with the database, not merely near it: if the
cookie outlived the row, a returning guest would present a token that
silently resolves to nothing and see an empty plan with no explanation.
The database remains the authority — `guest_session_id()` filters on
`expires_at` regardless of what any cookie claims — so a tampered
`Max-Age` buys a caller nothing."""

MAX_PLANS_PER_SESSION = 10
"""Mirrors the `guest_plans_enforce_limit` trigger. Duplicated here only
so the web layer can show a useful message before attempting a write
that the database would refuse anyway; the trigger is the enforcement."""


@dataclass(frozen=True)
class GuestPlan:
    """One saved route, as `list_guest_plans` returns it. Note what is
    absent: no notes, no free text of any kind. The table has no such
    column (see 0009's own comment on why)."""

    id: str
    pathway_id: str
    estimated_additional_expenses: float | None
    created_at: str


def token_from_request(request: Request) -> str | None:
    """The raw token this browser presented, or None.

    An empty cookie is treated as no cookie: a browser that has been
    handed `bcion_guest_session=` should start a fresh session rather
    than send an empty string into the token lookup.
    """
    value = request.cookies.get(COOKIE_NAME)
    return value.strip() or None if value else None


def set_session_cookie(response: Response, token: str) -> None:
    """Attach a freshly-created session token to the response.

    `httponly` so no script can read it — this token is the ONLY thing
    standing between one guest's saved routes and another's.
    `samesite="lax"` so it is not sent on a cross-site POST, which is the
    CSRF defence for the zero-JS save forms, exactly as
    app/web/reviewer_pages.py documents for the reviewer cookie.
    `secure` only in production, mirroring that same module and
    app/main.py's `docs_url` conditional, so plain http still works for
    local development.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=(get_settings().app_env == "production"),
        max_age=COOKIE_MAX_AGE_SECONDS,
        path=COOKIE_PATH,
    )


def clear_session_cookie(response: Response) -> None:
    """Forget this browser's guest session.

    Used on the shared-device path and after AUTH-7's sign-up merge. The
    server-side row is left to expire (or to be removed by the next
    `create_guest_session()` purge) rather than deleted here — this
    function is reached from a response-building path that may not have a
    database handle, and an orphaned row with no live token is inert.
    """
    response.delete_cookie(key=COOKIE_NAME, path=COOKIE_PATH)


def create_session(db: Client) -> str:
    """Start a guest session and return its raw token.

    The token exists in exactly two places after this returns: this
    value, and the cookie the caller puts it in. The database has only
    its hash.
    """
    result = db.rpc("create_guest_session", {}).execute()
    token = result.data
    if not isinstance(token, str) or not token:
        raise RuntimeError(
            "create_guest_session() returned no token — is "
            "db/migrations/0009_guest_sessions.sql applied?"
        )
    return token


def ensure_session(request: Request, response: Response, db: Client) -> str:
    """The token for this browser, creating a session if it has none.

    A cookie that no longer resolves server-side (expired, purged, or
    simply wrong) is NOT detected here: this returns the presented token
    as-is, and the RPCs answer "no plans" for it. Probing whether a token
    is live, just to decide whether to mint a new one, would turn every
    page load into a token oracle for no gain — a guest with a dead
    cookie sees an empty plan, which is the truth.
    """
    existing = token_from_request(request)
    if existing is not None:
        return existing
    token = create_session(db)
    set_session_cookie(response, token)
    return token


def list_plans(db: Client, token: str) -> list[GuestPlan]:
    """This session's saved routes, oldest first. Unknown or expired
    token gives an empty list — never an error, never another session's
    rows."""
    result = db.rpc("list_guest_plans", {"p_token": token}).execute()
    rows = cast("list[dict[str, Any]]", result.data or [])
    return [
        GuestPlan(
            id=row["id"],
            pathway_id=row["pathway_id"],
            estimated_additional_expenses=row["estimated_additional_expenses"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def save_plan(
    db: Client,
    token: str,
    pathway_id: str,
    estimated_additional_expenses: float | None = None,
) -> bool:
    """Save or refresh one route. False means the token did not resolve
    to a live session — an ordinary state after seven days, which the
    caller should surface as "your saved routes have expired", never as
    a failure."""
    result = db.rpc(
        "save_guest_plan",
        {
            "p_token": token,
            "p_pathway_id": pathway_id,
            "p_estimated_additional_expenses": estimated_additional_expenses,
        },
    ).execute()
    return result.data is True


def delete_plan(db: Client, token: str, plan_id: str) -> bool:
    """Remove one route. False when nothing matched — which covers both
    "no such plan" and "that plan belongs to someone else", deliberately
    indistinguishable to the caller."""
    result = db.rpc(
        "delete_guest_plan", {"p_token": token, "p_plan_id": plan_id}
    ).execute()
    return result.data is True
