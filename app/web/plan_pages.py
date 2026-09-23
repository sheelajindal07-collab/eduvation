"""GET /my-plan, POST /my-plan/save, POST /my-plan/remove -- docs/UI.md
"My Plan": a current decision, up to three next actions, saved
alternatives, a remove control (AUTH-6).

## Read this before assuming an older card's own text still holds

Dependencies named on this task (AUTH-3, AUTH-4, AUTH-5, UI-1, SEC-2) are
all merged. There is no `PlanStore` abstraction anywhere in this
codebase -- an older card's description of one is stale. What actually
backs a saved plan today is two separate, already-built mechanisms this
module reads directly, exactly the way every other `app/web/*_pages.py`
module already calls into `app/api/*` rather than re-implementing it
(`app/web/account_pages.py`'s own docstring: "this module calls ...
directly -- the exact functions those routes' own decorators wrap --
rather than reimplementing ... or making a second HTTP round-trip"):

* A real, signed-in student's plans are `app/api/plans.py`'s
  `saved_plans` rows, reached here by calling `save_plan`/`list_plans`/
  `delete_plan` (aliased `_api_*` below) directly with an `AuthedSession`
  this module gets from `app.web.session.get_student_session` (AUTH-2,
  the cookie -- disclosed in AUTH-3's own merge as still having no real
  page calling it with a genuine student session; this is that page).
* A guest's plans are `guest_plans` rows, reached here through
  `app/web/guest_session.py`'s own `save_plan`/`list_plans`/`delete_plan`/
  `create_session`/`token_from_request` -- the mechanism AUTH-4 built and
  that module's own docstring says explicitly has "no call site anywhere
  in `app/` yet" (confirmed still true by grep before writing this file):
  this module is the first caller, and therefore the one that decides
  when a guest session actually begins (`app/api/ask.py`'s own
  `_ai_budget_for_request` docstring names this exact deferral).

`app/planning/actions.py`'s `derive_next_actions` (deterministic, no AI --
see that module's own docstring) is the "next three actions" engine; this
module's only job is fetching the current decision's own published claims
and handing them to it, the same claims-then-sources shape
`app/web/timeline_pages.py`'s `_pathway_prefill` already establishes for
a different screen (row-conversion helpers are a small file-local copy
here too, matching that module's own "each module carries its own small
copy" convention rather than a shared import).

## Which plan is "current"

Only a real account's `saved_plans.is_current` flag means anything --
`guest_plans` has no such column at all (AUTH-4's own schema:
`id, pathway_id, estimated_additional_expenses, created_at`, nothing
else). `tests/db/test_plan_actions.py::TestOneCurrentPlanPerStudent`'s
own comment states the philosophy this module follows for both session
kinds without exception: "nobody's decision is invented for them." A
guest therefore never gets a "current decision" — every one of their
saved routes renders as a saved alternative, honestly, rather than this
module guessing which one they meant. An account with no plan marked
current renders the identical honest empty state.

## "Never say Saved unless it saved" (`_states.html`'s `save_failed()`)

`POST /my-plan/save` never redirects on failure -- a redirect to a fresh
`GET /my-plan` would have to invent a query-string signal for "that just
failed," and there is already a macro built for exactly this state
(`_states.html`'s `save_failed()`: "Keep the draft visible; never say
'Saved'... keeping the draft visible is the caller's own job"). This
module's own job, per that macro's docstring, is to re-render the SAME
plan list the student already has (their real, unaffected "draft") in
the same response, with that macro shown instead of any success text --
never a bare 500, never a silent redirect that could read as success.
Proven live two ways in `tests/db/test_plan_pages.py`: a well-formed but
nonexistent `pathway_id` (a genuine foreign-key rejection from the real
`save_guest_plan`/`saved_plans` write -- no mock), and a monkeypatched
raise standing in for a total provider outage.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from supabase import Client

from app.api.deps import AuthedSession
from app.api.plans import PlanOut, SavePlanRequest
from app.api.plans import delete_plan as _api_delete_plan
from app.api.plans import list_plans as _api_list_plans
from app.api.plans import save_plan as _api_save_plan
from app.core.csrf import require_same_origin
from app.data.models import Claim, ClaimStatus, Source, SourceType
from app.planning.actions import NextActions, derive_next_actions
from app.web import guest_session
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _form_str,
    _looks_like_a_uuid,
)
from app.web.guest_session import COOKIE_NAME as _GUEST_COOKIE_NAME
from app.web.session import COOKIE_NAME as _STUDENT_COOKIE_NAME
from app.web.session import get_student_session, no_store
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

# SEC-2's own documented extension point (app/core/csrf.py's module
# docstring names this exact pair of cookies as the worked example) --
# covers BOTH session kinds this screen writes under. app/main.py's own
# OriginCheckMiddleware only ever guards `bcion_student_session`
# (deliberately, that module's own docstring says why), so a guest's
# `POST /my-plan/save` would otherwise have no Origin check at all beyond
# the guest cookie's own SameSite=Lax -- this closes that gap for both
# write routes below.
require_my_plan_origin = require_same_origin(_STUDENT_COOKIE_NAME, _GUEST_COOKIE_NAME)

_ACTION_LABELS: dict[str, str] = {
    "check_entry_requirements": "Check the entry requirements",
    "note_application_window": "Note the application window",
    "gather_documents": "Gather the required documents",
    "review_main_stages": "Review the main stages",
    "plan_for_duration": "Plan for the expected duration",
}
"""Plain-language text for `app/planning/actions.py`'s fixed action-key
vocabulary. No i18n catalogue entry exists for these yet (this screen is
new) -- left as plain English, matching every other screen in this app
today (compare.html/requirements.html/timeline_calculator.html are not
fully i18n-covered either; docs/CONTRACTS.md's catalogue is the eventual
target, tracked as backlog elsewhere, not a gate on this card)."""

_NOTICE_MESSAGES: dict[str, str] = {
    "remove_failed": "That route couldn't be removed just now. Please try again shortly.",
}
"""SEC-2's own `QUEUE_ERROR_MESSAGES` convention (`app/web/reviewer/
queue.py`): a stable CODE travels in the query string, never free text --
an unrecognised code (a typo, a stale bookmark) renders nothing rather
than reflecting whatever a caller put in the URL."""


class _PlanRow:
    """One saved route, normalised across the two real storage
    mechanisms (`app/api/plans.py`'s `PlanOut`, `app/web/guest_session.py`'s
    `GuestPlan`) so `my_plan.html` never has to know which one it is
    looking at. `is_current` is always `False` for a guest row -- see
    this module's own docstring, "Which plan is 'current'"."""

    __slots__ = ("id", "pathway_id", "is_current")

    def __init__(self, *, id: str, pathway_id: str, is_current: bool) -> None:
        self.id = id
        self.pathway_id = pathway_id
        self.is_current = is_current


def _row_to_source(row: dict[str, Any]) -> Source:
    """File-local copy, same convention `app/web/timeline_pages.py`'s
    identically-named helper documents (not shared -- each screen module
    owns its own small copy rather than coupling over a few lines)."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """File-local copy -- see `_row_to_source` above."""
    return Claim(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        field=row["field"],
        value=row["value"],
        source_id=row["source_id"],
        verification_date=row["verification_date"],
        verifier=row["verifier"],
        status=ClaimStatus(row["status"]),
        review_due_date=row["review_due_date"],
        superseded_by=row.get("superseded_by"),
        approved_draft_version=row.get("approved_draft_version"),
        extracted_by=row.get("extracted_by", "human"),
    )


def _next_actions_for_pathway(db: Client, pathway_id: str) -> NextActions:
    """The current decision's own up-to-three next actions -- only ever
    derived from that ONE pathway's published, non-synthetic claims
    (`app.planning.actions.derive_next_actions`'s own gate), never from
    an alternative."""
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .eq("entity_id", pathway_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)
    claims_by_field = {row["field"]: _row_to_claim(row) for row in claim_rows}

    source_ids = {row["source_id"] for row in claim_rows}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    return derive_next_actions(claims_by_field, sources_by_id)


def _pathway_names(db: Client, pathway_ids: list[str]) -> dict[str, str]:
    if not pathway_ids:
        return {}
    result = db.table("pathways").select("id, name").in_("id", pathway_ids).execute()
    rows = cast("list[dict[str, Any]]", result.data)
    return {row["id"]: row["name"] for row in rows}


def _render_my_plan(
    request: Request,
    db: Client | None,
    student_session: AuthedSession | None,
    *,
    guest_token: str | None,
    notice: str | None = None,
    save_error: bool = False,
    status_code: int = 200,
) -> Any:
    """Shared by `GET /my-plan` and `POST /my-plan/save`'s own failure
    path (see this module's docstring, "Never say Saved unless it
    saved") -- the exact same plan list either way, so a failed save
    genuinely keeps the student's existing plans visible rather than a
    second, drifting copy of how to build that list.

    `session_state` is set here, unconditionally, for every branch below
    (including the DB-unavailable one) -- this is the first page in this
    app to ever pass "account" into a template context at all (AUTH-3's
    own disclosed gap: base.html's "Sign out" nav branch has been dead
    code until now because nothing set this).
    """
    session_state = "account" if student_session is not None else "guest"

    if db is None:
        return no_store(
            templates.TemplateResponse(
                request,
                "my_plan.html",
                {
                    "error": _DB_UNAVAILABLE_MESSAGE,
                    "session_state": session_state,
                    "current": None,
                    "alternatives": [],
                    "pathway_names": {},
                    "next_actions": None,
                    "action_labels": _ACTION_LABELS,
                    "save_error": save_error,
                    "notice_message": None,
                },
                status_code=status_code,
            )
        )

    if student_session is not None:
        try:
            plans: list[PlanOut] = _api_list_plans(session=student_session)
        except Exception:
            return no_store(
                templates.TemplateResponse(
                    request,
                    "my_plan.html",
                    {
                        "error": _DB_UNAVAILABLE_MESSAGE,
                        "session_state": session_state,
                        "current": None,
                        "alternatives": [],
                        "pathway_names": {},
                        "next_actions": None,
                        "action_labels": _ACTION_LABELS,
                        "save_error": save_error,
                        "notice_message": None,
                    },
                    status_code=status_code,
                )
            )
        plan_rows = [
            _PlanRow(id=p.id, pathway_id=p.pathway_id, is_current=p.is_current) for p in plans
        ]
    else:
        guest_plans = guest_session.list_plans(db, guest_token) if guest_token else []
        plan_rows = [
            _PlanRow(id=g.id, pathway_id=g.pathway_id, is_current=False) for g in guest_plans
        ]

    current = next((row for row in plan_rows if row.is_current), None)
    alternatives = [row for row in plan_rows if row is not current]

    pathway_names = _pathway_names(db, [row.pathway_id for row in plan_rows])

    next_actions = (
        _next_actions_for_pathway(db, current.pathway_id) if current is not None else None
    )

    return no_store(
        templates.TemplateResponse(
            request,
            "my_plan.html",
            {
                "error": None,
                "session_state": session_state,
                "current": current,
                "alternatives": alternatives,
                "pathway_names": pathway_names,
                "next_actions": next_actions,
                "action_labels": _ACTION_LABELS,
                "save_error": save_error,
                "notice_message": _NOTICE_MESSAGES.get(notice or ""),
            },
            status_code=status_code,
        )
    )


@router.get("/my-plan")
def my_plan_page(
    request: Request,
    notice: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
    student_session: AuthedSession | None = Depends(get_student_session),
) -> Any:
    guest_token = guest_session.token_from_request(request)
    return _render_my_plan(
        request, db, student_session, guest_token=guest_token, notice=notice
    )


@router.post("/my-plan/save", dependencies=[Depends(require_my_plan_origin)])
async def save_pathway_submit(
    request: Request,
    db: Client | None = Depends(_db_client_or_none),
    student_session: AuthedSession | None = Depends(get_student_session),
) -> Any:
    """"Save this route" -- the additive form on Compare/Timeline/
    Requirements posts here. Always POST-and-render on failure (never a
    redirect -- see this module's docstring), always a plain 303 redirect
    to `/my-plan` on success, so the acceptance line "a guest saves from
    Compare and sees it on /my-plan" is a single followed redirect, not a
    second mechanism to test.
    """
    form = await request.form()
    pathway_id = _form_str(form, "pathway_id").strip()

    if db is None:
        return _render_my_plan(
            request,
            db,
            student_session,
            guest_token=None,
            save_error=True,
            status_code=503,
        )

    if not _looks_like_a_uuid(pathway_id):
        return _render_my_plan(
            request,
            db,
            student_session,
            guest_token=guest_session.token_from_request(request),
            save_error=True,
            status_code=422,
        )

    if student_session is not None:
        try:
            _api_save_plan(SavePlanRequest(pathway_id=pathway_id), session=student_session)
        except HTTPException as exc:
            # 409 ("already in your saved plans") is the one exception:
            # the state the student wanted -- this pathway saved -- is
            # already true, so treat it the same as a fresh save rather
            # than an honest failure over nothing. Every other status
            # (404 no such pathway, 422, 400) is a real failure.
            if exc.status_code != 409:
                return _render_my_plan(
                    request,
                    db,
                    student_session,
                    guest_token=None,
                    save_error=True,
                    status_code=200,
                )
        except Exception:
            return _render_my_plan(
                request, db, student_session, guest_token=None, save_error=True, status_code=200
            )
        return no_store(RedirectResponse(url="/my-plan", status_code=303))

    # Guest path. A brand-new visitor has no token yet -- mint one before
    # attempting the save (this module is the first caller anywhere in
    # `app/` to do so; see this module's own docstring), but attach its
    # Set-Cookie to whichever response is ACTUALLY returned below, success
    # or failure, so a retry after a failed first save reuses the same
    # session rather than minting a fresh one on every attempt.
    existing_token = guest_session.token_from_request(request)
    newly_minted = existing_token is None
    token: str = (
        existing_token if existing_token is not None else guest_session.create_session(db)
    )

    try:
        saved = guest_session.save_plan(db, token, pathway_id)
    except Exception:
        saved = False

    if saved:
        response: Any = RedirectResponse(url="/my-plan", status_code=303)
    else:
        response = _render_my_plan(
            request, db, None, guest_token=token, save_error=True, status_code=200
        )

    if newly_minted:
        guest_session.set_session_cookie(response, token)
    return no_store(response)


@router.post("/my-plan/remove", dependencies=[Depends(require_my_plan_origin)])
async def remove_plan_submit(
    request: Request,
    db: Client | None = Depends(_db_client_or_none),
    student_session: AuthedSession | None = Depends(get_student_session),
) -> Any:
    """The remove control on `/my-plan` itself. Always a redirect back to
    `/my-plan` -- unlike save, "never say Saved" has no equivalent
    "never say Removed" requirement, so a stable error CODE in the query
    string (looked up, never reflected -- SEC-2's own convention) is
    enough for the one real failure mode (the database itself unreachable
    mid-request); "not found or not yours" degrades to a quiet, ordinary
    redirect, matching `guest_session.delete_plan`'s and `app/api/plans.py`'s
    own "already gone is not an error" shape.
    """
    form = await request.form()
    plan_id = _form_str(form, "plan_id").strip()

    if not _looks_like_a_uuid(plan_id):
        return no_store(RedirectResponse(url="/my-plan?notice=remove_failed", status_code=303))

    if student_session is not None:
        try:
            _api_delete_plan(plan_id, session=student_session)
        except HTTPException:
            pass  # 404 ("not found or not yours") -- already the desired end state
        except Exception:
            return no_store(
                RedirectResponse(url="/my-plan?notice=remove_failed", status_code=303)
            )
        return no_store(RedirectResponse(url="/my-plan", status_code=303))

    if db is None:
        return no_store(RedirectResponse(url="/my-plan?notice=remove_failed", status_code=303))

    token = guest_session.token_from_request(request)
    if token is None:
        return no_store(RedirectResponse(url="/my-plan", status_code=303))
    try:
        guest_session.delete_plan(db, token, plan_id)
    except Exception:
        return no_store(RedirectResponse(url="/my-plan?notice=remove_failed", status_code=303))
    return no_store(RedirectResponse(url="/my-plan", status_code=303))
