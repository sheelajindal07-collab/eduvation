"""GET/POST /sign-in, GET/POST /sign-up, POST /sign-out — the student
-facing HTML account pages (AUTH-3), the first real caller of
`app/web/session.py`'s `set_student_session_cookie` (AUTH-2, merged but
until now never wired into a route).

Same "web calls api, never the reverse, one fetch reused" convention
every other `app/web/*_pages.py` module already follows (see
`app/web/compare_pages.py`/`app/web/ask_pages.py`, or
`app/web/reviewer/auth.py`, whose `reviewer_sign_in_submit` this
module's `sign_in_submit` mirrors almost line for line): this module
calls `app.api.auth.authenticate()`/`sign_up()` directly — the exact
functions those routes' own decorators wrap — rather than re-implementing
Supabase Auth calls or making a second HTTP round-trip to `/auth/*`.

## Read this before assuming the task card's own description still holds

The card that authorised this module described a "202 (pending guardian
consent for a self-declared minor)" degrade state. Reading the CURRENT
`app/api/auth.py` (guardian consent + the admission axis both landed
since that card's text was written) shows that assumption is stale:
`sign_up()` returns `AuthResponse(account_status="pending_guardian_consent",
message=...)` for a self-declared minor (no exception raised at all,
whatever the email-confirmation setting), and reserves `HTTPException(202,
...)` for the unrelated case of an 18+ sign-up that needs email
confirmation before its first sign-in. Both are handled below, correctly
attributed, rather than blindly matching the card's mislabelled shape.

## Why this module never auto-signs-in after a successful sign-up

`set_student_session_cookie` (`app/web/session.py`) takes a real
Supabase `Session` object because it sizes the cookie's `Max-Age` to that
session's own `expires_in` — it must never guess a lifetime. `sign_up()`'s
`AuthResponse`, deliberately kept separate from `app.api.plans`' internal
`Session` type (see that model's own docstring), only ever exposes a bare
`access_token: str | None`, with no `expires_in` alongside it. Rather than
invent a fallback expiry this module has no authority to choose, or reach
into `app.api.auth.sign_up`'s own internals for its short-lived `client`
(which that function already closes before returning), a successful
sign-up here always ends at the same honest "Account created — sign in to
continue" message, with a link to `/sign-in`, which repeats the real
`authenticate()` call and gets a real `Session` to build the cookie from.
This also sidesteps needing to invent behaviour for the guardian-consent
and email-confirmation cases, which could never have had a session to set
a cookie from in the first place.

## SIGNUP_ENABLED

`app/core/config.py`'s `signup_enabled` field already existed before this
task (the card assumed it might not) — default `False` everywhere,
parsed fail-closed by `_fail_closed_bool`. Both `sign_up_form` (GET) and
`sign_up_submit` (POST) check it FIRST, before doing anything else: when
it is off, `app.api.auth.sign_up` is never called (not even constructed
a request model), and the same `sign_up.html` template renders its
`disabled=True` branch — an honest "sign-ups are closed" notice that
reflects the REAL invite-based admission sequence `docs/CONSENT.md`
section 3 describes (an invite code is entered AFTER first sign-in, not
at sign-up), not a vague placeholder.

## Sign-out clears BOTH cookies

`POST /sign-out` deletes `bcion_student_session` (this module's own
concern) AND `bcion_guest_session` (`app/web/guest_session.py`) — the
shared-device hygiene this card's acceptance criteria names. Neither
cookie mechanism owns the other; a browser could plausibly be carrying
both (e.g. after a "guest looks around, later signs in without ever
explicitly abandoning the guest session" path), so a full sign-out clears
both rather than only the one this module minted.

## Origin/CSRF

Deliberately no `require_same_origin`-style dependency on
`sign_in_submit`/`sign_up_submit`, for the identical reason
`app/web/reviewer/auth.py`'s own `reviewer_sign_in_submit` gives: neither
request carries `bcion_student_session` yet (a browser cannot present a
cookie it has not been issued), so gating a login/sign-up form on
`Origin` would lock out a legitimate client that omits the header for a
worse trade than the login-CSRF risk it would prevent (accepted residual
risk, `docs/SECURITY.md`). `POST /sign-out`, by contrast, IS reached by a
browser that already holds `bcion_student_session` — `app/main.py`'s
`OriginCheckMiddleware` already scopes itself to exactly that cookie, so
this route needs no per-route dependency of its own: this is simply the
first route that makes that already-built, previously-vacuous middleware
check real traffic for the first time.

## Difficult states rendered honestly, not as raw error text

Every `HTTPException` `authenticate()`/`sign_up()` can raise (401 wrong
credentials, 403 pending guardian consent, 429 rate-limited, 400 bad
input, 503 service unavailable) and the 202 "check your email" case are
all caught here and re-rendered through `_states.html`'s shared `alert()`
primitive with plain-language copy — the caller never sees a raw
`{"detail": ...}` JSON body. A locally-raised `pydantic.ValidationError`
(constructing `SignUpRequest` from form fields this module does not
pre-validate at the FastAPI-parameter layer, so a malformed value
degrades to a friendly message rather than a raw 422 — the exact
"explain, don't just error" convention `app/web/compare_pages.py`'s
`_safe_estimated_additional_expenses` already uses) is handled the same
way.

## AUTH-9 — GET /account, GET /account/export

Adds two routes to this SAME router (the task's own instruction: this is
not a new module) — a minimal signed-in-only account page, and a JSON
download of everything this app has saved for the caller's own account.

**Dependency choice**: `get_student_session` (yields `AuthedSession |
None`), not `app.api.deps.require_auth` (401 JSON) — a guest or a
signed-out browser hitting either of these must get an ordinary 303
redirect to `/sign-in`, the same shape `tests/db/test_account_pages.py`'s
own probe already proves for a protected page built on this dependency
(no other protected page existed until now — AUTH-6/AUTH-14 are still
open per `tasks/INDEX.md`).

**Only the caller's own RLS-scoped client, never service-role**: both
routes read exclusively through `session.client` (the connection
`get_student_session` builds from the caller's own cookie token) — the
same "RLS is the actual enforcement, not application code" convention
`app/api/plans.py`/`app/api/account.py` already state in their own
docstrings. This function adds no ownership filter of its own; two
students' exports are isolated because their own-row policies are
(`student_profiles_select_own`, `saved_plans_select_own`,
`plan_actions_own_row`, `consents_select_own`), not because this code
remembered to add a `WHERE`.

**What's actually in the payload, checked against the CURRENT migration
ledger (`db/migrations/0001`-`0017`), not assumed**: `student_profiles`
(0001), `saved_plans` (0002) with each plan's own `plan_actions` (0010),
and `consents` (0013) all exist and are included. `plan_versions` —
named in this task's own acceptance criteria — does **not** exist
anywhere in this schema; rather than invent an empty `"plan_versions": []`
key for a table that was never built, it is omitted from the payload
entirely. Each of the three real tables still degrades to the string
`"not available"` (CLAUDE.md: a missing section says "Not available",
never dropped silently) rather than crashing, for an environment that
somehow hasn't applied the relevant migration yet (`_select_own_rows`'s
own `42P01` check).

**Reviewers**: this route does not special-case `is_reviewer()` at all,
and by design. The ordinary case — a reviewer who only ever holds
`bcion_reviewer_session` (`app/web/reviewer/auth.py`'s own, separate
cookie) — is refused implicitly: `get_student_session` never reads that
cookie name, so that request is indistinguishable from a guest's and
gets the same redirect, no data. The unusual case — the same identity
ALSO signs in normally and holds a real `bcion_student_session` — reaches
the exact same RLS-scoped query as any other student; their own row's
`auth.uid()` is what every table's own-row policy scopes to, the same
guarantee any two ordinary students already get from each other. Chosen
over an explicit `is_reviewer()` refusal because the existing session
mechanism already makes the common path structurally safe, and the
uncommon path is no less safe than the student-vs-student case this
codebase already tests everywhere else — live-proven in
`tests/db/test_account_export.py`, not just asserted here.

**Never logged**: `app/core/logging.py`'s `RequestIdLoggingMiddleware` —
the only per-request log line this app emits — is read directly before
writing this route, not assumed: it logs only method, route template,
status code and latency, and its own docstring states it "never" reads a
request or response body. Neither route here adds any logging of its
own, so the export payload is never written to a log line by
construction, not by a filter that could miss something.

**`no-store` on both** (docs/PRODUCT.md shared-device hygiene) —
`account_page` wraps its `TemplateResponse` the same way every other GET
page in this module does; `export_account_data` wraps its `JSONResponse`
the same way.

**Access-matrix disclosure, not silently worked around**:
`tests/db/access_matrix.py`'s own `UNBUILT_OPERATIONS`/`Operation.EXPORT`
placeholder, and `tests/db/test_access_matrix.py`'s
`test_unbuilt_capability_placeholder` (`xfail(strict=True)`,
parametrized over `UNBUILT_CELLS`), exist specifically to go red the
moment an export route is built, via `_export_surfaces` scanning
`app.main.app.routes` for any route path containing `"export"`. Checked
LIVE, not assumed, after adding `GET /account/export`: with the FastAPI
version this repo currently pins (`fastapi==0.141.1`), `app.routes`
holds one `fastapi.routing._IncludedRouter` wrapper per
`app.include_router(...)` call, and that wrapper object carries no
`.path` attribute at all (the real routes live one level down, on its
own `.original_router.routes`) — so `_export_surfaces`'s bare
`getattr(route, "path", "")` scan cannot see ANY nested route, this new
one included, and the four `EXPORT` cells stayed `XFAIL` (verified by
actually running `test_unbuilt_capability_placeholder` against this
branch, not inferred). This is a pre-existing gap in that test helper's
own route-walking, unrelated to this task and not something a route
addition could trigger differently — it would just as invisibly miss
any OTHER export-like route added anywhere in this app today. Neither
`tests/db/access_matrix.py` nor `tests/db/test_access_matrix.py` is in
this task's own `Touches` list, so neither is edited here — flagged in
this session's own report instead, for whoever owns that file: the
`EXPORT` placeholder now needs BOTH a real per-role cell replacement
(the same way `db/migrations/0017_publishing_evidence.sql` replaced the
matching `STORAGE` placeholder) AND a fix to `_export_surfaces` itself
(e.g. walking `route.original_router.routes` when present) before the
placeholder's own "goes red the day export exists" promise is true again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import Client

from app.api.auth import SignUpRequest, authenticate, sign_up
from app.api.deps import AuthedSession
from app.core.config import get_settings
from app.db import get_anon_client
from app.web.guest_session import clear_session_cookie as _clear_guest_session_cookie
from app.web.session import COOKIE_NAME as _STUDENT_COOKIE_NAME
from app.web.session import COOKIE_PATH as _STUDENT_COOKIE_PATH
from app.web.session import (
    get_student_session,
    no_store,
    session_ended_redirect,
    set_student_session_cookie,
)
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


def _error_variant(status_code: int) -> str:
    """`_states.html`'s `alert()` variant for an HTTP status this page is
    re-rendering as prose: a genuine server/provider fault (>=500) reads
    as `"error"`; anything the student can act on (a wrong password, a
    rate limit, a bad form value) reads as the milder `"caution"`."""
    return "error" if status_code >= 500 else "caution"


@router.get("/sign-in")
def sign_in_form(request: Request, notice: str | None = Query(default=None)) -> Any:
    return no_store(
        templates.TemplateResponse(
            request,
            "sign_in.html",
            {"error": None, "notice": notice, "email": None},
        )
    )


@router.post("/sign-in")
def sign_in_submit(request: Request, email: str = Form(...), password: str = Form(...)) -> Any:
    """Reuses `app.api.auth.authenticate()` — the one place this app
    calls Supabase's own `sign_in_with_password`, shared with
    `app/web/reviewer/auth.py`'s own sign-in — rather than reimplementing
    it. On success, sets the real student session cookie and redirects
    (303, so the browser re-requests with GET, never resubmitting the
    form) to `/explore`, the start of the real journey (no My-Plan page
    exists yet for this to land on instead — see this module's own
    module docstring)."""
    try:
        client = get_anon_client()
    except Exception:
        return no_store(
            templates.TemplateResponse(
                request,
                "sign_in.html",
                {
                    "error": "Sign-in isn't available right now. Please try again shortly.",
                    "error_variant": "error",
                    "notice": None,
                    "email": email,
                },
                status_code=503,
            )
        )
    try:
        try:
            session = authenticate(client, email, password)
        except HTTPException as exc:
            return no_store(
                templates.TemplateResponse(
                    request,
                    "sign_in.html",
                    {
                        "error": exc.detail,
                        "error_variant": _error_variant(exc.status_code),
                        "notice": None,
                        "email": email,
                    },
                    status_code=exc.status_code,
                )
            )
        response = RedirectResponse(url="/explore", status_code=303)
        set_student_session_cookie(response, session)
        return no_store(response)
    finally:
        client.postgrest.aclose()


def _signup_form_context(
    *, error: str | None = None, error_variant: str | None = None
) -> dict[str, Any]:
    return {
        "disabled": False,
        "error": error,
        "error_variant": error_variant,
        "pending_message": None,
        "today_iso": date_type.today().isoformat(),
        "email": None,
        "date_of_birth": None,
        "guardian_email": None,
    }


def _signup_disabled_response(request: Request) -> Any:
    return no_store(
        templates.TemplateResponse(
            request,
            "sign_up.html",
            {
                "disabled": True,
                "error": None,
                "error_variant": None,
                "pending_message": None,
                "today_iso": None,
                "email": None,
                "date_of_birth": None,
                "guardian_email": None,
            },
        )
    )


@router.get("/sign-up")
def sign_up_form(request: Request) -> Any:
    if not get_settings().signup_enabled:
        return _signup_disabled_response(request)
    return no_store(
        templates.TemplateResponse(request, "sign_up.html", _signup_form_context())
    )


@router.post("/sign-up")
def sign_up_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    date_of_birth: str = Form(...),
    guardian_email: str = Form(default=""),
) -> Any:
    """`SIGNUP_ENABLED` is checked FIRST — when it is off,
    `app.api.auth.sign_up` is never constructed, let alone called (this
    module's own docstring, "SIGNUP_ENABLED"). Otherwise builds a real
    `SignUpRequest` from the submitted form fields (a plain `str` for
    `date_of_birth`/`email`, not `EmailStr`/`date` typed FastAPI
    parameters, so a malformed value degrades to this page's own friendly
    `ValidationError` branch below rather than a raw FastAPI 422) and
    calls `sign_up()` directly, re-rendering every `HTTPException` it can
    raise as styled prose (this module's own docstring, "Difficult
    states")."""
    settings = get_settings()
    if not settings.signup_enabled:
        return _signup_disabled_response(request)

    guardian_email_value = guardian_email.strip() or None

    def _redisplay(*, error: str, error_variant: str) -> dict[str, Any]:
        context = _signup_form_context(error=error, error_variant=error_variant)
        context["email"] = email
        context["date_of_birth"] = date_of_birth
        context["guardian_email"] = guardian_email_value
        return context

    try:
        signup_request = SignUpRequest(
            email=email,
            password=password,
            date_of_birth=date_of_birth,  # type: ignore[arg-type]  # pydantic parses the ISO string
            guardian_email=guardian_email_value,
        )
    except ValidationError:
        return no_store(
            templates.TemplateResponse(
                request,
                "sign_up.html",
                _redisplay(
                    error=(
                        "Please check the values you entered — a valid email, a "
                        "password, and a date of birth that isn't in the future "
                        "are all required."
                    ),
                    error_variant="caution",
                ),
                status_code=400,
            )
        )

    try:
        result = sign_up(signup_request)
    except HTTPException as exc:
        if exc.status_code == 202:
            # The 18+ "check your email to confirm" case (app/api/auth.py)
            # -- not an error, a real account now exists. See this
            # module's own docstring for why this is NOT the
            # pending-guardian-consent case the task card's own text
            # mislabelled this status code as.
            return no_store(
                templates.TemplateResponse(
                    request,
                    "sign_up.html",
                    {
                        "disabled": False,
                        "error": None,
                        "error_variant": None,
                        "pending_message": exc.detail,
                        "today_iso": None,
                        "email": None,
                        "date_of_birth": None,
                        "guardian_email": None,
                    },
                    status_code=202,
                )
            )
        return no_store(
            templates.TemplateResponse(
                request,
                "sign_up.html",
                _redisplay(error=exc.detail, error_variant=_error_variant(exc.status_code)),
                status_code=exc.status_code,
            )
        )

    # Two remaining success shapes, both rendered the same honest way --
    # see this module's own docstring, "Why this module never
    # auto-signs-in after a successful sign-up":
    #   - account_status == "pending_guardian_consent": result.message is
    #     always set (app/api/auth.py's sign_up()), explains the guardian
    #     email step.
    #   - account_status == "active": result.message is None; the default
    #     text below covers it.
    success_message = result.message or "Account created. Sign in to continue."
    return no_store(
        templates.TemplateResponse(
            request,
            "sign_up.html",
            {
                "disabled": False,
                "error": None,
                "error_variant": None,
                "pending_message": success_message,
                "today_iso": None,
                "email": None,
                "date_of_birth": None,
                "guardian_email": None,
            },
        )
    )


@router.post("/sign-out")
def sign_out_submit() -> Any:
    """Clears both `bcion_student_session` (this module) and
    `bcion_guest_session` (`app/web/guest_session.py`) -- see this
    module's own docstring, "Sign-out clears BOTH cookies". No per-route
    CSRF dependency needed: `app/main.py`'s `OriginCheckMiddleware`
    already scopes its Origin check to exactly `bcion_student_session`,
    and this is the first route in the whole app a browser ever reaches
    while actually holding that cookie -- see this module's own
    docstring, "Origin/CSRF"."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=_STUDENT_COOKIE_NAME, path=_STUDENT_COOKIE_PATH)
    _clear_guest_session_cookie(response)
    return no_store(response)


# --------------------------------------------------------------------
# AUTH-9 -- GET /account, GET /account/export
# --------------------------------------------------------------------

# Postgres: "undefined_table" -- raised when a table named below doesn't
# exist in the current schema at all. See this module's own docstring,
# "AUTH-9", for why this degrades to "not available" instead of a 500.
_UNDEFINED_TABLE = "42P01"


def _select_own_rows(
    client: Client, table: str, *, columns: str = "*"
) -> list[dict[str, Any]] | None:
    """The caller's OWN rows from `table` -- RLS on `client` (the caller's
    own token, from `get_student_session`) is what scopes this, not a
    filter added here (this module's own docstring, "AUTH-9"). `None`
    means `table` itself does not exist in the current schema; an empty
    list means the table exists and the caller simply has no rows in it
    -- two different facts this module's own caller keeps distinct
    rather than collapsing into one "nothing here" shape.
    """
    try:
        result = client.table(table).select(columns).execute()
    except APIError as exc:
        if exc.code == _UNDEFINED_TABLE:
            return None
        raise
    return cast("list[dict[str, Any]]", result.data)


def _select_own_plan_actions(client: Client, plan_id: str) -> list[dict[str, Any]] | None:
    """Same contract as `_select_own_rows`, for the one table that needs
    a `WHERE plan_id = ...` on top of RLS -- `plan_actions` has no
    `student_id` of its own (ownership is via the parent plan;
    `db/migrations/0010_plan_actions.sql`'s own comment), so every plan's
    actions must be fetched by that plan's id, mirroring
    `app.api.plans.list_plan_actions`'s own query exactly."""
    try:
        result = (
            client.table("plan_actions")
            .select("action_key, done, done_at")
            .eq("plan_id", plan_id)
            .execute()
        )
    except APIError as exc:
        if exc.code == _UNDEFINED_TABLE:
            return None
        raise
    return cast("list[dict[str, Any]]", result.data)


def _export_payload(client: Client) -> dict[str, Any]:
    """Assemble the signed-in caller's own export. See this module's own
    docstring, "AUTH-9", for the full reasoning behind what is and isn't
    included here."""
    profile_rows = _select_own_rows(client, "student_profiles")
    plans = _select_own_rows(client, "saved_plans")
    if plans is not None:
        for plan in plans:
            actions = _select_own_plan_actions(client, cast(str, plan["id"]))
            plan["actions"] = actions if actions is not None else "not available"
    consents = _select_own_rows(client, "consents")

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": (
            (profile_rows[0] if profile_rows else None)
            if profile_rows is not None
            else "not available"
        ),
        "plans": plans if plans is not None else "not available",
        "consents": consents if consents is not None else "not available",
    }


@router.get("/account")
def account_page(
    request: Request, session: AuthedSession | None = Depends(get_student_session)
) -> Any:
    """A minimal signed-in-only page with one action: download your data.
    See this module's own docstring, "AUTH-9", for the dependency choice
    and why this is also the first route to pass `session_state="account"`
    into `base.html`."""
    if session is None:
        return session_ended_redirect("/sign-in")
    return no_store(
        templates.TemplateResponse(
            request,
            "account.html",
            {"session_state": "account"},
        )
    )


@router.get("/account/export")
def export_account_data(
    session: AuthedSession | None = Depends(get_student_session),
) -> Any:
    """A JSON download of the signed-in student's own data. See this
    module's own docstring, "AUTH-9", for the full design reasoning --
    the dependency choice, why only `session.client` is ever used, what
    is and isn't in the payload, the reviewer design decision, and why
    the payload is never logged."""
    if session is None:
        return session_ended_redirect("/sign-in")
    payload = _export_payload(session.client)
    response = JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="bcion-my-data.json"'},
    )
    return no_store(response)
