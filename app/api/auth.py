"""POST /auth/sign-up, POST /auth/sign-in — thin wrapper over Supabase
Auth, which already underlies every RLS policy in this schema
(`auth.users`, `auth.uid()`).

**Guardian-consent gate (this task, closing the gap the paragraph below
used to describe):** `SignUpRequest.date_of_birth` is required; an
under-18 sign-up requires `guardian_email` too (400 without it), creates
the account as `pending_guardian_consent` rather than immediately usable,
and emails the guardian a confirmation link via the pluggable
`EmailSender` (`app/notifications/`) — see `app/api/guardian_consent.py`
for the actual age/token/enforcement logic, and
`db/migrations/0004_guardian_consent.sql` for the schema/RLS it relies
on. `authenticate()` below (shared by this route and the reviewer
console's sign-in, `app/web/reviewer_pages.py`) is where a pending
account is actually blocked from getting a usable session — see that
function's own docstring, and `app.api.guardian_consent.
enforce_guardian_consent_gate`'s, for exactly where and why.
**Real email delivery is not wired to a real provider** — see
`app/notifications/logging_sender.py`; the gate's database state is
real, but nobody's inbox is reached yet.

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
from datetime import UTC, date, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from supabase import Client
from supabase_auth.errors import AuthApiError
from supabase_auth.types import Session

from app.api.guardian_consent import (
    MINOR_AGE_THRESHOLD_YEARS,
    create_guardian_consent_request,
    enforce_guardian_consent_gate,
    guardian_consent_schema_is_live,
    is_minor,
)
from app.db import get_anon_client
from app.notifications.factory import get_email_sender

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
    date_of_birth: date
    # Required whenever date_of_birth implies under-18 — checked in
    # sign_up() itself (a Pydantic model can't see MINOR_AGE_THRESHOLD_
    # YEARS from here without importing app.api.guardian_consent into a
    # request model, which would be an odd layering), not by making this
    # field itself conditionally-typed.
    guardian_email: EmailStr | None = None
    pending_plan: PendingPlan | None = None

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("date_of_birth cannot be in the future.")
        return value


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    # Optional (was required before this task): a sign-up response for a
    # pending-guardian-consent account carries NO access token at all —
    # see sign_up() below. A sign-in response always has one; the gate
    # (authenticate()) raises rather than returning a Session for a
    # pending account, so sign_in() itself never constructs an
    # AuthResponse with access_token=None.
    access_token: str | None = None
    user_id: str
    # "active" | "pending_guardian_consent" — a plain str, not the
    # account_status enum type db/migrations/0004_guardian_consent.sql
    # defines, so this response model has no dependency on that schema
    # module beyond the two string values themselves.
    account_status: str = "active"
    migrated_plan_id: str | None = None
    """Set when `pending_plan` was supplied and successfully saved.
    `None` with no error raised means either no pending_plan was sent,
    or saving it failed non-fatally — sign-up itself never fails because
    of a plan-save problem (see the handler)."""
    message: str | None = None
    """Set on a pending-guardian-consent sign-up response, to make the
    "not immediately usable" state visible to a caller that only reads
    the 2xx body rather than distinguishing status codes (task
    requirement: "the response should clearly indicate the account is
    pending guardian confirmation, not immediately usable -- do not
    silently let the student in")."""


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


def _normalize_email_for_self_check(email: str) -> str:
    """Normalize an email for the guardian_email-vs-own-email self-check
    below — NOT a general-purpose email canonicalizer, and deliberately
    narrower than one: lowercase, strip surrounding whitespace, and drop
    a `local+tag@domain` sub-address tag, because that's the one bypass
    an adversarial live check actually demonstrated (see the comment on
    that check). No dot-stripping — see the same comment for why that
    would trade a real bypass for a false-positive rejection of a
    genuinely different guardian on non-Gmail providers."""
    local, _, domain = email.strip().casefold().partition("@")
    local = local.partition("+")[0]
    return f"{local}@{domain}"


@router.post("/sign-up", response_model=AuthResponse, status_code=201)
def sign_up(request: SignUpRequest) -> AuthResponse:
    today = datetime.now(tz=UTC).date()
    minor = is_minor(request.date_of_birth, as_of=today)
    if minor and request.guardian_email is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"guardian_email is required for a student under "
                f"{MINOR_AGE_THRESHOLD_YEARS} (named assumption — India's legal "
                "majority age, Indian Majority Act 1875; see docs/SECURITY.md "
                "'Consent & safeguarding')."
            ),
        )
    # Adversarial review, 2026-09-21 (HIGH, then a second-pass MEDIUM):
    # nothing previously stopped a self-declared minor from entering
    # their OWN sign-up email as guardian_email. Not exploitable TODAY —
    # no real email provider is configured
    # (app/notifications/logging_sender.py) — but the moment one is, a
    # minor could receive their own "guardian confirmation" email and
    # self-confirm instantly, a complete, trivial defeat of the whole
    # mechanism triggered by nothing more than an owner action this app
    # cannot see coming.
    #
    # A first version compared case-insensitively but exact-match, which
    # a live adversarial re-check defeated trivially: most providers
    # (Gmail, Outlook/M365, ProtonMail, FastMail — RFC 5233 "Sieve
    # Subaddress") deliver `local+anything@domain` to the same inbox as
    # `local@domain`, so `name+guardian@gmail.com` sailed straight past
    # an exact-match check while still reaching the student's own inbox.
    # `_normalize_email_for_self_check` strips a `+...` suffix from the
    # local part before comparing. Deliberately NOT stripping dots too
    # (Gmail treats `r.kumar@gmail.com`/`rkumar@gmail.com` as identical,
    # but most OTHER providers, including Outlook, do not — two genuinely
    # different people can differ only by a dot on those providers, and
    # blanket dot-stripping would wrongly reject a real, different
    # guardian's address as "the same email", the opposite failure mode
    # from the one this check exists to catch).
    if (
        minor
        and request.guardian_email is not None
        and _normalize_email_for_self_check(request.guardian_email)
        == _normalize_email_for_self_check(request.email)
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "guardian_email cannot be the same as the student's own "
                "sign-up email — a minor's guardian must be a different "
                "person who can actually confirm this account (see "
                "docs/SECURITY.md 'Consent & safeguarding')."
            ),
        )
    if minor and not guardian_consent_schema_is_live():
        # Fail CLOSED, before Supabase's own auth.users row is even
        # created: db/migrations/0004_guardian_consent.sql (own-row RLS
        # tables this whole gate depends on) is not applied to this
        # project yet (see db/migrations/README.md / STATUS.md for the
        # owner action needed). Letting a self-declared minor's sign-up
        # through as immediately-usable here — the only alternative,
        # since there is nowhere yet to record "pending" — would be
        # exactly the CLAUDE.md non-negotiable this whole task exists to
        # close. Refusing outright (no account created at all) is the
        # safe failure mode; an 18+ sign-up is completely unaffected by
        # this check (never reaches it).
        raise HTTPException(
            status_code=503,
            detail=(
                "Guardian consent is required for this account and is not yet "
                "available. Please try again later."
            ),
        )

    try:
        client = get_anon_client()
    except Exception as exc:
        # UI-review finding, 2026-09-21 (HIGH, FIX 3): this used to
        # construct the client BEFORE any try block, so
        # app/db/client.py's SupabaseNotConfiguredError (whose own
        # docstring asks every caller to catch it and degrade
        # gracefully) -- or any other construction-time failure --
        # propagated as an unhandled 500 instead of a clean response.
        # This is a JSON API route, so "gracefully" means a clean error
        # response, not a page redirect (that's reviewer_sign_in_submit's
        # job, fixed the same way below).
        raise HTTPException(
            status_code=503,
            detail="Sign-up isn't available right now. Please try again shortly.",
        ) from exc
    try:
        try:
            # date_of_birth/guardian_email travel in Supabase's own
            # `options.data` (-> auth.users.raw_user_meta_data), so they
            # are durably recorded by Supabase itself regardless of
            # whether a session comes back below (see the `result.session
            # is None` branch) — app.api.guardian_consent.
            # enforce_guardian_consent_gate reads them back from there to
            # bootstrap the pending-consent request on this student's
            # first successful sign-in, if it wasn't already created here.
            result = client.auth.sign_up(
                {
                    "email": request.email,
                    "password": request.password,
                    "options": {
                        "data": {
                            "date_of_birth": request.date_of_birth.isoformat(),
                            "guardian_email": request.guardian_email,
                        }
                    },
                }
            )
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

        if result.user is None:
            raise HTTPException(status_code=400, detail="Sign-up failed.")
        user_id = result.user.id

        if result.session is None:
            # Email confirmation is required by the project's Auth
            # settings — not an error, just no session yet. Unchanged
            # from before this task for an 18+ signup (still a plain
            # 202); a pending_plan can't be migrated without a session
            # either way (pre-existing gap, see _migrate_pending_plan's
            # own docstring). For a self-declared minor, the guardian-
            # consent request itself ALSO can't be created without a
            # session (own-row RLS — see app.api.guardian_consent's
            # module docstring) — nothing is lost, though: the metadata
            # above durably holds date_of_birth/guardian_email, and
            # authenticate() creates the request on this student's first
            # successful sign-in instead.
            if minor:
                return AuthResponse(
                    access_token=None,
                    user_id=user_id,
                    account_status="pending_guardian_consent",
                    message=(
                        "Account created. Check your email to confirm it first. "
                        "Because this account is for a student under "
                        f"{MINOR_AGE_THRESHOLD_YEARS}, your guardian will also need "
                        "to confirm a separate email before this account can sign in."
                    ),
                )
            raise HTTPException(
                status_code=202,
                detail="Account created. Check your email to confirm before signing in.",
            )

        client.postgrest.auth(result.session.access_token)

        if minor:
            assert request.guardian_email is not None  # enforced above
            create_guardian_consent_request(
                client,
                student_id=user_id,
                date_of_birth=request.date_of_birth,
                guardian_email=request.guardian_email,
                sender=get_email_sender(),
            )
            return AuthResponse(
                access_token=None,
                user_id=user_id,
                account_status="pending_guardian_consent",
                message=(
                    f"Account created. A confirmation link has been emailed to "
                    f"{request.guardian_email}. This account cannot sign in until "
                    "your guardian confirms."
                ),
            )

        migrated_plan_id = None
        if request.pending_plan is not None:
            migrated_plan_id = _migrate_pending_plan(
                client, result.session.access_token, user_id, request.pending_plan
            )

        return AuthResponse(
            access_token=result.session.access_token,
            user_id=user_id,
            account_status="active",
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


# UI-review finding, 2026-09-21 (HIGH, FIX 2): Supabase's own structured
# rate-limit errors (429, exc.code in this set) used to be flattened by
# authenticate()'s bare `except Exception` into the same generic 401 as
# a wrong password -- indistinguishable, unloggable, unfixable from the
# caller's side. This is an explicit allowlist, not "propagate any
# AuthApiError's real status" -- deliberately narrow, so the
# anti-enumeration guarantee below stays exactly as strong as before for
# every OTHER structured error (most importantly "invalid_credentials",
# Supabase's own code for both "no such email" and "wrong password"):
# only a provider-level signal that has nothing to do with whether THIS
# email/password pair is valid is ever allowed to escape the generic
# 401. See sign_up()'s own AuthApiError handling for the pattern this
# mirrors.
_RATE_LIMIT_ERROR_CODES = frozenset({"over_request_rate_limit", "over_email_send_rate_limit"})


def authenticate(client: Client, email: str, password: str) -> Session:
    """The one place this app calls Supabase Auth's
    `sign_in_with_password` — shared by this route and by the reviewer
    console's cookie-based session (`app/web/reviewer_pages.py`), so
    neither caller reimplements the actual auth call (that module's own
    docstring explains why it needs this rather than the trimmed
    `AuthResponse` below: it needs the real `Session.expires_in` to size
    its cookie to the token's actual lifetime, not a guessed default).

    Never distinguishes "no such email" from "wrong password" — that
    distinction is an account-enumeration leak — so every failure raises
    the same 401 with the same message, regardless of caller. The one
    exception (FIX 2 above) is a structured, provider-level error that
    ISN'T a login failure at all, e.g. a rate limit -- propagating THAT
    doesn't weaken anti-enumeration, since it says nothing about whether
    this particular email exists.

    **Guardian-consent gate lives here** (docs/SECURITY.md "enforced
    server-side, not by a button"): once the password itself is verified
    correct, `app.api.guardian_consent.enforce_guardian_consent_gate`
    decides whether this caller may actually receive the `Session` —
    revealing "your account is pending guardian confirmation" at this
    point is not an enumeration leak the way it would be before password
    verification, since the caller has already proven they own the
    account. A pending account raises `HTTPException(403, ...)` here and
    a `Session` is never returned — every caller of `authenticate()`
    (this route and the reviewer console) gets that protection for free,
    with nothing downstream needing its own copy of the check.
    """
    try:
        result = client.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as exc:
        if exc.code in _RATE_LIMIT_ERROR_CODES:
            raise HTTPException(status_code=exc.status, detail=exc.message) from exc
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    if result.session is None or result.user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    enforce_guardian_consent_gate(
        client, result.session, result.user, sender=get_email_sender()
    )
    return result.session


@router.post("/sign-in", response_model=AuthResponse)
def sign_in(request: SignInRequest) -> AuthResponse:
    try:
        client = get_anon_client()
    except Exception as exc:
        # Same FIX 3 reasoning as sign_up() above.
        raise HTTPException(
            status_code=503,
            detail="Sign-in isn't available right now. Please try again shortly.",
        ) from exc
    try:
        session = authenticate(client, request.email, request.password)
        # authenticate() raises rather than returning for a pending
        # account (see its own docstring) — reaching this line means
        # account_status is genuinely "active" (an explicit row, or none
        # at all: a legacy/adult account, see app.api.guardian_consent).
        return AuthResponse(
            access_token=session.access_token, user_id=session.user.id, account_status="active"
        )
    finally:
        client.postgrest.aclose()
