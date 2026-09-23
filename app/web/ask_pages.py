"""GET /ask/view — the "Ask BCION" answer page, zero-JS (UI-11 / BCI-014,
AI-7 wiring).

Distinct path from the JSON API (`/ask/view` vs. `/ask`), same convention
`app/api/compare.py`/`app/web/compare_pages.py` already use — the already
-tested JSON contract stays untouched, and this module's only job is
"render what `app.api.ask` already computes", never a second copy of the
fetch-and-assemble logic (`app.api.ask.assemble_ask_answer` is the one
place the deterministic fact-card logic lives, and `app.api.ask.
_pipeline_answer` is the one place the additive AI-pipeline call lives;
this module calls both, never reimplementing either — see
`app/api/ask.py`'s own module docstring for the full "deterministic
baseline never goes away, AI is an additive layer" rule this whole
feature follows).

`ai_sentences`/`ai_citations` are threaded into this page's template
context below on the same "answered-only, never in place of the fact
cards" terms as the JSON route's own `AskResponse` fields, and
`app/web/templates/ask.html` (BCI-025) now renders them, alongside the
fact cards, exactly like the JSON route's `AskResponse` shape — never in
place of them. The page's own never-blank/never-error/never-a-second
-message guarantee holds regardless -- `show_fallback` and `fact_cards`
below are completely unaffected by this and render exactly as UI-11 left
them.

## BCI-025: `next_steps`'s `plan_id` and `what_changed`'s `claim_id`

This route now mirrors `app.api.ask.ask()`'s own resolution for both
templates exactly (reusing that module's own `_pathway_id_for_plan`/
`_what_changed_answer` helpers directly, never a second, re-derived
copy of either): `next_steps` accepts a `plan_id` query parameter in
place of `pathway_id`/`career_id` (resolved through the same
ownership-checked `saved_plans` lookup the JSON route uses — a guest's
or another identity's plan id 404s, via `_pathway_id_for_plan`'s own
`HTTPException(404, "Plan not found.")`, propagated here unmodified so
this page's failure mode matches the JSON route byte-for-byte rather
than degrading to a second, friendlier-looking but behaviourally
different page); `what_changed` accepts a `claim_id` query parameter and
bypasses `entity_kind_and_id` entirely, same as the JSON route. A
missing or malformed `claim_id` is this page's own existing
`state == "invalid_request"` friendly 200 degrade (this page never
returns a raw 422 the way the JSON route does — every non-404 failure
mode on this page already renders via `ask.html`, and "a plausible but
broken link" is exactly what `invalid_request` already means here for
the pathway_id/career_id case).

## Router registration
Registered as its OWN standalone top-level `RouterSlot` ("ask_pages"),
not nested inside `app/web/pages.py` — `app/main.py` and
`app/web/pages.py` are both frozen/forbidden to this card, so this
module cannot register itself the way `compare_pages`/`explore_pages`/
`requirements_pages`/`timeline_pages` normally would. This is not a new
shape: `app/web/consent_pages.py`'s `router` is already registered as its
own standalone "consent_pages" slot for exactly this reason. See
`app/api/ask.py`'s module docstring for the full router-registration note
and the exact lines the lead needs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from supabase import Client

from app.ai.actions import NextStepAction, next_step_actions_from_citations
from app.ai.schemas import AIAnswerStatus
from app.ai.what_changed import RenderedDiffLine
from app.api.ask import (
    ASK_TEMPLATES,
    _looks_like_a_uuid,
    _pathway_id_for_plan,
    _pipeline_answer,
    _what_changed_answer,
    assemble_ask_answer,
    entity_kind_and_id,
)
from app.core.config import get_settings
from app.web.common import _DB_UNAVAILABLE_MESSAGE, _db_client_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


@router.get("/ask/view")
def ask_page(
    request: Request,
    template: str = Query(...),
    pathway_id: str | None = Query(default=None),
    career_id: str | None = Query(default=None),
    plan_id: str | None = Query(default=None),
    claim_id: str | None = Query(default=None),
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """`?template=<id>&pathway_id=<uuid>` (or `&career_id=<uuid>` instead
    of `pathway_id`, or -- `next_steps` only -- `&plan_id=<uuid>` instead of
    `pathway_id`/`career_id`, or -- `what_changed` only -- `&claim_id=<uuid>`
    instead of any of the above; see this module's own docstring's "BCI-025"
    section) -- the human-clicked version of `GET /ask`. Three friendly,
    never-crashing degrade states plus the real answer, each rendered by
    the SAME `ask.html` (docs/UI.md "difficult states": explain, don't
    just error):

    - `state == "unknown_template"` -- a bad/old link's `template` value
      is never recognised, never reflected back into the page (avoid any
      reflected-value surface), and 404s (this card's own requirement:
      "friendly 404-style page, not a 500").
    - `state == "invalid_request"` -- neither/both of pathway_id/
      career_id, or a malformed id (ux-qa-reviewer-style finding this
      route pre-empts, matching `compare_page`'s own malformed-id
      degrade), or -- `what_changed` only -- a missing/malformed
      `claim_id` (this page's own equivalent of the JSON route's 422 for
      the same case, see "BCI-025" docstring section above): 200, not
      404 -- a human followed a plausible but broken link, not a request
      for a resource that doesn't exist.
    - `error` set (a plain, already-resolved string, matching
      `_DB_UNAVAILABLE_MESSAGE`'s use on every other screen in this
      codebase) -- the database is unreachable/unconfigured.
    - the real answer -- `state == "answered"`, always 200, always
      rendering the AI-unavailable fallback copy plus whatever fact
      cards/actions/diff-lines ARE available when `AI_ENABLED`/
      `ai_configured` is off or this template found nothing published
      (see `app/api/ask.py`'s `AskResponse.show_fallback`) -- never an
      error page.

    A `next_steps` request naming a `plan_id` that does not resolve (a
    guest, another identity's plan, a nonexistent or malformed plan id)
    is the one exception to "every degrade renders via `ask.html`":
    `_pathway_id_for_plan` raises `HTTPException(404, "Plan not found.")`
    directly, and this route does not catch it -- propagated unmodified,
    exactly like `app.api.ask.ask()`'s own behaviour, per this module's
    "BCI-025" docstring section.
    """
    ask_template = ASK_TEMPLATES.get(template)
    if ask_template is None:
        return templates.TemplateResponse(
            request,
            "ask.html",
            {"error": None, "state": "unknown_template"},
            status_code=404,
        )

    if ask_template.id == "what_changed":
        # AI-19 mirror: what_changed needs a claim_id, not a pathway/career
        # id -- entity_kind_and_id() below is skipped entirely for this
        # template, same as app.api.ask.ask(). Unlike that JSON route
        # (422), a missing/malformed claim_id here is this page's own
        # existing "invalid_request" friendly 200 degrade -- see this
        # module's own "BCI-025" docstring section for why.
        if claim_id is None or not _looks_like_a_uuid(claim_id):
            return templates.TemplateResponse(
                request,
                "ask.html",
                {"error": None, "state": "invalid_request"},
            )
        entity_kind, entity_id = "claim", claim_id
    else:
        if ask_template.id == "next_steps" and plan_id is not None and pathway_id is None:
            # AI-18 mirror: resolve BEFORE entity_kind_and_id runs, same
            # order/condition app.api.ask.ask() uses. This is the one
            # resolution path that itself needs a real db client, so the
            # "db unavailable" check that normally comes later has to be
            # checked here first too.
            if db is None:
                return templates.TemplateResponse(
                    request,
                    "ask.html",
                    {"error": _DB_UNAVAILABLE_MESSAGE, "state": "db_unavailable"},
                )
            pathway_id = _pathway_id_for_plan(db, plan_id)

        resolved = entity_kind_and_id(pathway_id, career_id)
        if resolved is None:
            return templates.TemplateResponse(
                request,
                "ask.html",
                {"error": None, "state": "invalid_request"},
            )
        entity_kind, entity_id = resolved

    if db is None:
        return templates.TemplateResponse(
            request,
            "ask.html",
            {"error": _DB_UNAVAILABLE_MESSAGE, "state": "db_unavailable"},
        )

    as_of = datetime.now(tz=UTC).date()
    answer = assemble_ask_answer(
        db, ask_template, entity_kind=entity_kind, entity_id=entity_id, as_of=as_of
    )

    # Mirrors app.api.ask.ask()'s own branching exactly: what_changed goes
    # through its own parallel AI layer (_what_changed_answer), every other
    # template through _pipeline_answer -- see app/api/ask.py's own module
    # docstring's "AI-19" section for why the two cannot share one call.
    next_step_action_objs: tuple[NextStepAction, ...] = ()
    what_changed_line_objs: tuple[RenderedDiffLine, ...] = ()
    ai_sentences: list[str]
    ai_citations: list[dict[str, Any]]
    if ask_template.id == "what_changed":
        what_changed_result = _what_changed_answer(db, entity_id, as_of=as_of)
        if (
            what_changed_result is not None
            and what_changed_result.status == AIAnswerStatus.answered
        ):
            what_changed_line_objs = what_changed_result.lines
            ai_sentences = []
            ai_citations = list(what_changed_result.citations)
        else:
            # Every other status (including "never even called") -- render
            # nothing extra, same rule every other template follows.
            ai_sentences = []
            ai_citations = []
    else:
        ai_answer = _pipeline_answer(
            db, ask_template, entity_kind=entity_kind, entity_id=entity_id, as_of=as_of
        )
        if ai_answer is not None and ai_answer.status == AIAnswerStatus.answered:
            ai_sentences = list(ai_answer.sentences)
            ai_citations = list(ai_answer.citations)
            if ask_template.id == "next_steps":
                # AI-18: turning a surviving citation into action text is
                # entirely app.ai.actions's job, never this route's --
                # same rule app.api.ask.ask() itself follows.
                next_step_action_objs = next_step_actions_from_citations(ai_answer.citations)
        else:
            # Every other status, including "the pipeline was never called
            # at all" (ai_answer is None) -- render nothing extra.
            ai_sentences = []
            ai_citations = []

    entity_name: str | None = None
    if entity_kind != "claim":
        # what_changed's entity_kind is "claim" -- there is no
        # pathways/careers row to name, and no meaningful subheading to
        # show for one; skipped outright rather than issuing a lookup that
        # can only ever come back empty.
        entity_table = "pathways" if entity_kind == "pathway" else "careers"
        name_result = db.table(entity_table).select("id, name").eq("id", entity_id).execute()
        entity_rows = cast("list[dict[str, Any]]", name_result.data)
        entity_name = entity_rows[0]["name"] if entity_rows else None

    settings = get_settings()
    # Mirrors app.api.ask.ask()'s own show_fallback rule exactly:
    # next_step_action_objs/what_changed_line_objs are each only ever
    # assigned for their own template above, so for cost_breakdown/
    # pathway_overview/eligibility_gap this is byte-for-byte the original
    # `not answer.fact_cards` expression -- AI-18/AI-19 each add one more
    # way for a template to have "something to show" without changing what
    # that meant for the other three.
    show_fallback = not (settings.ai_enabled and settings.ai_configured) or not (
        answer.fact_cards or next_step_action_objs or what_changed_line_objs
    )

    return templates.TemplateResponse(
        request,
        "ask.html",
        {
            "error": None,
            "state": "answered",
            "prompt_key": ask_template.prompt_key,
            "entity_name": entity_name,
            "show_fallback": show_fallback,
            "fact_cards": answer.fact_cards,
            "missing_information": answer.missing_field_labels,
            "ai_sentences": ai_sentences,
            "ai_citations": ai_citations,
            "next_step_actions": next_step_action_objs,
            "what_changed_lines": what_changed_line_objs,
        },
    )
