"""The guardian-consent gate: age computation, creating a pending
consent request, and enforcing it at sign-in. Backs
`db/migrations/0004_guardian_consent.sql`; see that file's own
docstring for the schema/RLS reasoning this module relies on.

Used by `app/api/auth.py`'s `sign_up()` (creates the request immediately
when a session is available) and `authenticate()` (the actual
enforcement point — see `enforce_guardian_consent_gate`'s docstring for
exactly where and why).

## Where "under 18" is decided, and the one deliberately-trusted source
`date_of_birth` is self-declared by the student at sign-up — docs/
SECURITY.md is explicit that Lite collects no identity documents, so
there is no stronger verification available at this pilot's scale. Once
written to `student_accounts` (own-row RLS, no UPDATE policy — see the
migration), that record is the durable source of truth for every sign-in
after the first: `enforce_guardian_consent_gate` below only ever
consults Supabase's own `user_metadata` (the value passed at sign-up,
also self-declared but additionally writable by the account holder
through Supabase's own profile-update API, outside this app's control)
to bootstrap the FIRST `student_accounts` row, never again afterward.
This closes the obvious bypass ("declare truthfully as a minor, then
edit your own metadata to look 18+ before ever signing in again") for
every account that has already had its `student_accounts` row created.

**Named, accepted residual gap** (documented rather than silently
assumed away, per this project's own convention): a minor who discovers
Supabase's own update-profile API independently (this app never exposes
the anon/publishable key or that API to a browser client itself — every
Supabase call in this codebase happens server-side) and rewrites their
`date_of_birth` metadata BEFORE their very first successful sign-in could
avoid ever getting a `student_accounts` row created at all. This is a
narrower version of the same "self-declared age, no identity documents"
limitation docs/SECURITY.md already accepts pilot-wide, not a new one
introduced here.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from typing import Any, cast

from fastapi import HTTPException
from postgrest.exceptions import APIError
from supabase import Client
from supabase_auth.types import Session, User

from app.core.config import get_settings
from app.db import get_anon_client
from app.notifications.guardian_consent_email import build_guardian_consent_email
from app.notifications.sender import EmailSender

logger = logging.getLogger(__name__)

# Named assumption (task instructions / STATUS.md): no age threshold is
# stated anywhere in docs/SECURITY.md, docs/BCION-Lite-Build-Pack.md or
# the DPR. 18 — India's legal majority age (Indian Majority Act, 1875) —
# is used as the default minor/adult cutoff. Flag to the owner if a
# different threshold is ever wanted; this is the one place to change it.
MINOR_AGE_THRESHOLD_YEARS = 18

# Named assumption, matches db/migrations/0004_guardian_consent.sql's
# `guardian_consents.expires_at` column default — kept here too because
# the guardian-facing email text (build_guardian_consent_email) needs the
# number, and the two are documented as intentionally identical rather
# than independently chosen.
GUARDIAN_CONSENT_EXPIRY_HOURS = 72

_UNIQUE_VIOLATION = "23505"  # Postgres error code, same constant plans.py uses


def compute_age(date_of_birth: date, *, as_of: date) -> int:
    """Whole years of age as of `as_of` — ordinary arithmetic, not a
    library dependency, matching CLAUDE.md's "ordinary code for facts,
    rules and arithmetic" (the same reasoning app/rules/ already applies
    to eligibility/cost/timeline)."""
    years = as_of.year - date_of_birth.year
    had_birthday_yet = (as_of.month, as_of.day) >= (date_of_birth.month, date_of_birth.day)
    if not had_birthday_yet:
        years -= 1
    return years


def is_minor(date_of_birth: date, *, as_of: date) -> bool:
    return compute_age(date_of_birth, as_of=as_of) < MINOR_AGE_THRESHOLD_YEARS


@lru_cache(maxsize=1)
def guardian_consent_schema_is_live() -> bool:
    """Whether BOTH `db/migrations/0004_guardian_consent.sql` AND
    `db/migrations/0005_guardian_consent_request_rpc.sql` have been
    applied to the connected Supabase project yet — probed once per
    process via each migration's own marker function (mirrors
    `tests/db/conftest.py`'s `_maker_checker_migration_applied()`
    exactly, and cached the same way `app.core.config.get_settings()`
    is: this is not expected to flip true mid-process, only across a
    restart after the owner applies each one).

    **Why BOTH, not just 0004** (adversarial review, 2026-09-21,
    MEDIUM, closing a gap found the moment 0005 existed but 0004 was
    already live somewhere real): `create_guardian_consent_request`
    below calls 0005's `create_guardian_consent_request` RPC
    unconditionally whenever this function reports `True`. If only
    0004's marker were checked, applying 0004 alone (a real, live
    sequence — 0004 was applied to production before 0005 even
    existed) would make this report `True` while the RPC 0005 defines
    still doesn't exist, and the very first self-declared-minor
    sign-up/sign-in would 500 on `could not find function
    create_guardian_consent_request` — the identical class of bug this
    whole 0005 migration exists to close, just relocated. Requiring
    both markers means the gate correctly stays "not enforceable yet"
    (safe, same fail-closed 503 as before 0004 existed at all) for the
    entire window between the owner applying 0004 and applying 0005,
    rather than silently trading one crash for another.

    **Why this exists at all**: until the owner actually runs these
    migrations (same manual step as 0001-0003 — see db/migrations/
    README.md), `student_accounts`/`guardian_consents` (0004) or the
    RPC (0005) do not exist. Without this check, EVERY sign-in — not
    just a self-declared minor's — would 500 the moment
    `enforce_guardian_consent_gate` tried to query a table or call a
    function that doesn't exist yet, which would be a severe
    regression for the adult accounts this task explicitly must not
    regress. This check lets the gate degrade to "not enforceable yet"
    (the same baseline STATUS.md already documents: sign-up with no
    age/consent gate) instead, while everything else in the app keeps
    working. See STATUS.md for the exact owner action needed."""
    try:
        client = get_anon_client()
        client.rpc("guardian_consent_schema_version", {}).execute()
        client.rpc("guardian_consent_request_rpc_schema_version", {}).execute()
        return True
    except Exception:  # noqa: BLE001 — any error here means "not ready yet"
        return False


def _confirm_url(token: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/consent/confirm?token={token}"


def create_guardian_consent_request(
    client: Client,
    *,
    student_id: str,
    date_of_birth: date,
    guardian_email: str,
    sender: EmailSender,
) -> None:
    """Creates the `student_accounts` row (status
    `pending_guardian_consent`) and the `guardian_consents` row, then
    emails the guardian via `sender`. `client` must already be scoped to
    `student_id`'s own session (`client.postgrest.auth(access_token)`).

    Delegates both inserts to the `create_guardian_consent_request` SQL
    function (`db/migrations/0005_guardian_consent_request_rpc.sql`)
    rather than doing them as two plain `client.table(...).insert(...)`
    calls. **Why an RPC, not a direct insert:** supabase-py's
    `.insert().execute()` defaults to `Prefer: return=representation`,
    asking PostgREST to return the inserted row via `INSERT ...
    RETURNING`. Postgres applies a table's SELECT policies to rows
    returned this way, not just the INSERT policy's WITH CHECK to the
    write itself — and `guardian_consents` deliberately has NO SELECT
    policy at all, for anyone (see db/migrations/0004_guardian_consent.sql's
    module-level design note: the token is a bearer credential that must
    never be readable through the normal API, not even by the owning
    student). That combination meant the direct-insert form used to fail
    outright with "new row violates row-level security policy for table
    guardian_consents" — a real, previously-live bug that broke the
    guardian-consent gate for every self-declared minor. The RPC does the
    insert and reads back the value INSERT itself produced in the same
    statement, server-side, as the function owner — no RETURNING-through-
    REST round trip, so no SELECT policy is ever needed. See the
    migration's own module-level comment for the full explanation.

    The RPC determines the calling student from `auth.uid()` internally
    (there is no `student_id` parameter to send it — `student_id` is kept
    on THIS function's own signature only for logging and because
    existing callers pass it).

    Idempotent against a concurrent duplicate call (two sign-in requests
    racing the same lazy-create path) and against a genuinely
    still-pending request from earlier — but **only the
    `guardian_consents` insert's own outcome decides the return value**
    (adversarial review, 2026-09-21, MEDIUM, correcting an earlier,
    inaccurate version of this docstring that claimed a
    `student_accounts` conflict alone also produced `NULL`): the RPC's
    `student_accounts` insert uses `ON CONFLICT (id) DO NOTHING` and
    always proceeds regardless of whether that row already existed;
    only the SEPARATE `ON CONFLICT (student_id) WHERE status='pending'
    DO NOTHING` on `guardian_consents` determines whether `NULL` comes
    back. So a `student_accounts` row already existing (e.g. from an
    earlier call) but no currently-*pending* `guardian_consents` row
    (e.g. a prior request expired) still produces a real, fresh token —
    not `NULL`. Both of today's callers (`app.api.auth.sign_up` and
    this module's own `enforce_guardian_consent_gate`) only ever reach
    this function when no `student_accounts` row exists yet, so that
    combination is unreachable today, but a future "resend the
    guardian email" feature would hit it and must not assume `NULL`
    means "nothing happened" — "already existed, not an error, no
    second email sent" is enforced database-side rather than by
    catching a unique-violation exception here, but specifically for
    the `guardian_consents` row, not the account row.

    **The `token` itself is never chosen here** (adversarial review,
    2026-09-21, closing a complete bypass — see the migration's own
    docstring): a BEFORE INSERT trigger on `guardian_consents`
    unconditionally server-generates `token` and `expires_at`, silently
    overwriting anything this call sends. The confirmation email is built
    from the token the RPC reports was actually written — never from a
    value generated in this process — the same "read back what the
    database actually did" pattern `app.api.auth._migrate_pending_plan`
    already uses for a saved plan's generated id.
    """
    result = client.rpc(
        "create_guardian_consent_request",
        {
            "p_date_of_birth": date_of_birth.isoformat(),
            "p_guardian_email": guardian_email,
        },
    ).execute()
    token = cast("str | None", result.data)

    if token is None:
        logger.info(
            "guardian_consents row for student_id=%s already existed "
            "(concurrent creation, or a still-pending request from "
            "earlier) — not an error, no second email sent.",
            student_id,
        )
        return

    subject, body = build_guardian_consent_email(
        confirm_url=_confirm_url(token), expiry_hours=GUARDIAN_CONSENT_EXPIRY_HOURS
    )
    sender.send(to=guardian_email, subject=subject, body=body)


_PENDING_MESSAGE = (
    "This account is waiting on a guardian's confirmation before it can "
    "be used. Ask your guardian to check the email you gave at sign-up "
    "and click the confirmation link."
)
_PENDING_NO_GUARDIAN_EMAIL_MESSAGE = (
    "This account cannot be activated: no guardian email is on file. "
    "Contact support to add one."
)


def enforce_guardian_consent_gate(
    client: Client, session: Session, user: User, *, sender: EmailSender
) -> None:
    """The actual enforcement point (docs/SECURITY.md: "enforced
    server-side, not by a button"). Called from `app.api.auth.
    authenticate()` — the ONE function both `POST /auth/sign-in` and
    `POST /reviewer/sign-in` (app/web/reviewer_pages.py) call to turn a
    verified password into a usable session — so both entry points get
    this for free, with no second implementation to keep in sync.

    Why sign-in, not a per-route dependency check: every authenticated
    route in this codebase (`app.api.deps.require_auth`,
    `app.web.reviewer_pages.get_reviewer_session`) requires an access
    token, and the ONLY way this app's own code hands one out is
    `authenticate()` — there is no separate token-refresh/minting path.
    Blocking here means a student with the right password but no
    guardian confirmation yet never receives a token this app considers
    valid in the first place; nothing downstream needs its own copy of
    this check. (A pre-existing, deliberately-scoped gap: this app
    cannot prevent Supabase itself from having already handed the
    browser a raw JWT if `client.auth.sign_up()`/`sign_in_with_password`
    returned a session object before this check ran — this function is
    called before that object is ever put in an HTTP response, so it
    never reaches a client from THIS app's own responses either way.)

    Raises `HTTPException(403, ...)` — never lets a pending account's
    caller receive the `Session` — for every case except "genuinely
    active" (an explicit `active` row, or no row at all: a legacy
    account created before this feature shipped, or an adult, for whom
    account_status is never stored at all — see
    create_guardian_consent_request's caller in app/api/auth.py). Never
    raises for a caller this module cannot even identify as a
    self-declared minor (no `date_of_birth` in `user_metadata`) — that is
    "no regression for adults" by construction, not a special case.
    """
    if not guardian_consent_schema_is_live():
        return

    client.postgrest.auth(session.access_token)

    existing = (
        client.table("student_accounts")
        .select("account_status")
        .eq("id", user.id)
        .execute()
    )
    rows = cast("list[dict[str, Any]]", existing.data)
    if rows:
        status = rows[0]["account_status"]
        if status == "active":
            return
        raise HTTPException(status_code=403, detail=_PENDING_MESSAGE)

    # No student_accounts row yet. Either this account predates the
    # feature (no date_of_birth was ever collected — treat as active, no
    # regression), or Supabase's own email-confirmation setting withheld
    # a session at sign-up time (app.api.auth.sign_up's Case B) and this
    # is the first successful sign-in since — bootstrap from the
    # durably-stored sign-up metadata now that a session finally exists.
    metadata = user.user_metadata or {}
    dob_raw = metadata.get("date_of_birth")
    if not dob_raw:
        return

    try:
        date_of_birth = date.fromisoformat(dob_raw)
    except (TypeError, ValueError):
        logger.warning(
            "Unparseable date_of_birth in user_metadata for user_id=%s: %r — "
            "treating as adult (no gate) rather than guessing.",
            user.id,
            dob_raw,
        )
        return

    if not is_minor(date_of_birth, as_of=date.today()):
        return

    guardian_email = metadata.get("guardian_email")
    if not guardian_email:
        # Should be unreachable via this app's own POST /auth/sign-up
        # (which requires guardian_email whenever date_of_birth implies
        # a minor — see app.api.auth.SignUpRequest), so this only fires
        # for an account created some other way (e.g. directly against
        # Supabase's own Auth API). Fail closed: record the account as
        # pending anyway rather than let it through with no gate at all,
        # even though there is no address to notify.
        logger.error(
            "user_id=%s is under %s with no guardian_email in user_metadata "
            "— account created outside app/api/auth.py's own sign-up route? "
            "Recording as pending_guardian_consent with no consent request "
            "(nothing to email).",
            user.id,
            MINOR_AGE_THRESHOLD_YEARS,
        )
        try:
            client.table("student_accounts").insert(
                {
                    "id": user.id,
                    "date_of_birth": date_of_birth.isoformat(),
                    "account_status": "pending_guardian_consent",
                }
            ).execute()
        except APIError as exc:
            if exc.code != _UNIQUE_VIOLATION:
                raise
        raise HTTPException(status_code=403, detail=_PENDING_NO_GUARDIAN_EMAIL_MESSAGE)

    create_guardian_consent_request(
        client,
        student_id=user.id,
        date_of_birth=date_of_birth,
        guardian_email=guardian_email,
        sender=sender,
    )
    raise HTTPException(status_code=403, detail=_PENDING_MESSAGE)
