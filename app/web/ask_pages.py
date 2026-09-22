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
cards" terms as the JSON route's own `AskResponse` fields — but
`app/web/templates/ask.html` is a forbidden file for this card (AI-7's
own "Forbidden files" list) and, as of this card, has no markup that
reads either key: passing them through here keeps the two routes'
wiring identical and ready for a future template change, but today
neither key is visually rendered on `/ask/view`. The page's own
never-blank/never-error/never-a-second-message guarantee holds regardless
-- `show_fallback` and `fact_cards` below are completely unaffected by
this and render exactly as UI-11 left them.

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

from app.ai.schemas import AIAnswerStatus
from app.api.ask import ASK_TEMPLATES, _pipeline_answer, assemble_ask_answer, entity_kind_and_id
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
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    """`?template=<id>&pathway_id=<uuid>` (or `&career_id=<uuid>` instead
    of `pathway_id`) -- the human-clicked version of `GET /ask`. Three
    friendly, never-crashing degrade states plus the real answer, each
    rendered by the SAME `ask.html` (docs/UI.md "difficult states":
    explain, don't just error):

    - `state == "unknown_template"` -- a bad/old link's `template` value
      is never recognised, never reflected back into the page (avoid any
      reflected-value surface), and 404s (this card's own requirement:
      "friendly 404-style page, not a 500").
    - `state == "invalid_request"` -- neither/both of pathway_id/
      career_id, or a malformed id (ux-qa-reviewer-style finding this
      route pre-empts, matching `compare_page`'s own malformed-id
      degrade): 200, not 404 -- a human followed a plausible but broken
      link, not a request for a resource that doesn't exist.
    - `error` set (a plain, already-resolved string, matching
      `_DB_UNAVAILABLE_MESSAGE`'s use on every other screen in this
      codebase) -- the database is unreachable/unconfigured.
    - the real answer -- `state == "answered"`, always 200, always
      rendering the AI-unavailable fallback copy plus whatever fact
      cards ARE available when `AI_ENABLED`/`ai_configured` is off or
      this template found nothing published (see `app/api/ask.py`'s
      `AskResponse.show_fallback`) -- never an error page.
    """
    ask_template = ASK_TEMPLATES.get(template)
    if ask_template is None:
        return templates.TemplateResponse(
            request,
            "ask.html",
            {"error": None, "state": "unknown_template"},
            status_code=404,
        )

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
    ai_answer = _pipeline_answer(
        db, ask_template, entity_kind=entity_kind, entity_id=entity_id, as_of=as_of
    )
    if ai_answer is not None and ai_answer.status == AIAnswerStatus.answered:
        ai_sentences = list(ai_answer.sentences)
        ai_citations = list(ai_answer.citations)
    else:
        # Every other status, including "the pipeline was never called at
        # all" (ai_answer is None) -- render nothing extra. See this
        # module's own docstring for why neither key is visually rendered
        # by ask.html today regardless.
        ai_sentences = []
        ai_citations = []

    entity_table = "pathways" if entity_kind == "pathway" else "careers"
    name_result = db.table(entity_table).select("id, name").eq("id", entity_id).execute()
    entity_rows = cast("list[dict[str, Any]]", name_result.data)
    entity_name = entity_rows[0]["name"] if entity_rows else None

    settings = get_settings()
    show_fallback = not (settings.ai_enabled and settings.ai_configured) or not answer.fact_cards

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
        },
    )
