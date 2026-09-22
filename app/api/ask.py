"""GET /ask — the "Ask BCION" answer (UI-11 / BCI-014, AI-7 wiring).

**The deterministic baseline (UI-11 / BCI-014).** Every fact card this
route shows comes from `app.planning.comparison.field_value_for` (and,
for the cost template, `assemble_cost_breakdown`, which is built on top
of the same function) against already-published claims for the given
pathway or career — exactly the pattern `app/api/compare.py`'s
`assemble_comparisons` already uses. `assemble_ask_answer()` below is
the whole reason UI-11 was built deterministic-first, and this module
still calls it unconditionally, on every request, regardless of the AI
pipeline's outcome — see `_pipeline_answer()`'s own docstring.

**The additive AI layer (AI-7, this card).** `app/ai/pipeline.py` (AI-6)
is now merged. When `Settings.ai_enabled` and `Settings.ai_configured`
are both true, `_pipeline_answer()` below also calls
`app.ai.pipeline.answer()` and, only when its `Answer.status` is
`AIAnswerStatus.answered`, this route's `AskResponse.ai_sentences`/
`ai_citations` are populated ALONGSIDE the fact cards above — never in
place of them. Every other status renders nothing extra: the response is
byte-for-byte the same fact-card/fallback shape the AI-disabled path
already produced. `app/ai/grounding.py`'s `answer_question` is still
never used here — that module needs a free-text `question`, which this
route never has and never will: `docs/UI.md`'s component set is explicit
that a contextual "Ask BCION" entry point is "canned prompts over
retrieved records ... never a blank chat box".

## The fixed prompt registry

`ASK_TEMPLATES` is the small, hardcoded, server-side list `docs/UI.md`
requires ("fixed template ... never a blank chat box" — also the
Tier-0/Tier-1 spend control from the national DPR §9): the three ids the
three existing `_ask.html` call sites already use — `cost_breakdown`
(compare.html's cost card), `pathway_overview` (compare.html's pathway
column) and `eligibility_gap` (requirements.html's eligibility line) —
plus `next_steps` (AI-18, `tasks/BCI-021.md`) and `what_changed` (AI-19,
`tasks/BCI-022.md`), neither of which has an `_ask.html` call site yet
(`app/web/ask_pages.py`/`app/web/templates/**` are outside this card's
owned files). `template_id` is always one of these five ids, never free
text a student typed — the query string carries an id, never a question
(`docs/CONTRACTS.md`: "Every personal input ... is POST-only"; a canned
template id is not personal input, but it still never becomes a
sentence).

## AI-18: `next_steps` and `plan_id`

`next_steps` is answered exactly like `pathway_overview` — same
`_pipeline_answer()` call below, unchanged, over the same
`fetch_pathway_records` per-field records — but its `AskTemplate.fields`
is deliberately empty (`assemble_ask_answer()`'s deterministic fact-card
baseline has nothing to show for it: "next actions" is not a field on
any entity, it is derived, see `app/ai/actions.py`). When
`ai_answer.status` is `AIAnswerStatus.answered`, `AskResponse.
next_step_actions` is populated from `ai_answer.citations` via
`app.ai.actions.next_step_actions_from_citations` — never from
`ai_answer.sentences`, which this template leaves unused (its generic
"field is value" phrasing is not action text — see that module's own
docstring).

`next_steps` accepts `pathway_id` exactly like the other three templates,
OR a new `plan_id` query parameter naming a `saved_plans` row
(`app/api/plans.py`, AUTH-5) to resolve to ITS `pathway_id` before the
usual `entity_kind_and_id` resolution runs. Resolution reuses the exact
ownership-check PATTERN `app/api/plans.py`'s own routes already use
(e.g. `list_plan_actions`): query `saved_plans` through the SAME
already-request-scoped `db` this route receives from `get_db_client`
(guest anon-key client by default, a signed-in caller's own JWT-scoped
client when a bearer token is present — identical shape to
`app.api.deps.AuthedSession.client`) and let `saved_plans_own_row` RLS
(`db/migrations/0002_saved_plans.sql`, tightened by 0004) decide what is
visible — never a second, service-role read path. A guest's anon client
sees no `saved_plans` row at all (creating one requires sign-in,
`app/api/plans.py`'s own docstring); another student's JWT-scoped client
sees only THEIR OWN rows. Either case, or a plan id that does not exist
at all, or one that is not even UUID-shaped, resolves identically —
`_pathway_id_for_plan` below 404s with the same deliberately ambiguous
"Plan not found." `app/api/plans.py` already uses, never distinguishing
"no such plan" from "not yours" (that module's own precedent, security
review 2026-09-19/2026-09-21: an oracle that told them apart would leak
which plan ids exist).

## AI-19: `what_changed` and `claim_id`

`what_changed` needs a `claim_id` — the SUPERSEDED claim's own id, never
a pathway/career id — so it is resolved entirely differently from the
other four templates: `entity_kind_and_id(pathway_id, career_id)` below
is skipped outright for this template (a `claim_id` is not a pathway or
a career), and `claim_id` itself is shape-checked with the same
`_looks_like_a_uuid` helper before anything else runs, 422-ing with a
fixed, generic message for a missing or malformed id — never a 404, since
"the claim id does not resolve to anything explainable" is this
template's own `not_available` outcome, not a routing failure. Once
resolved, `entity_kind="claim"`/`entity_id=claim_id` still flow through
`assemble_ask_answer()` unconditionally, exactly like every other
template (this module's own "assemble once, always" rule) — harmless,
since `ASK_TEMPLATES["what_changed"].fields == ()` degrades to zero fact
cards regardless of what `entity_type` that call ends up querying.

The AI layer is where `what_changed` actually diverges: `_pipeline_answer()`
is never called for this template — it builds an `AskRequest` carrying
only `pathway_id`/`career_id`, never a `claim_id`, so
`app.ai.pipeline.answer()` would see `record_id_for(template) is None`
and degrade to `unsupported_template` every time. `_what_changed_answer()`
below is `what_changed`'s own parallel helper (same settings gate, same
`GeminiProvider()` construction and `GeminiNotConfiguredError` handling as
`_pipeline_answer()`) that calls `app.ai.what_changed.answer_what_changed()`
instead — see that module's own docstring for why its retrieval cannot
reuse `app.ai.pipeline.answer()` at all. Its `WhatChangedAnswer.lines`
(already rendered, code-only text — see that module's docstring) becomes
`AskResponse.what_changed_lines` only when `status` is
`AIAnswerStatus.answered`, the same "render nothing extra for any other
status" rule every other template follows; `ai_sentences` stays empty for
this template (there is no generic "field is value" phrasing equivalent —
`what_changed`'s own `RenderedDiffLine.text` already IS the sentence), and
`ai_citations` carries `WhatChangedAnswer.citations` instead, the same
plain-data citation shape every other template's `ai_citations` already
uses.

## Router registration (see this card's own completion report)

`app/main.py` is a frozen, lead-only registry — this module cannot add
itself to it. `router` (aliased `ask_router` to match the name this
card's own text suggests) is the JSON route only, one of TWO new
`RouterSlot`s the lead needs to add — the other is
`app.web.ask_pages.router` ("ask_pages"), the HTML page. Two slots, not
one, deliberately: `app/web/pages.py` is the usual place a new HTML page
router gets nested (as `compare_pages`/`explore_pages`/
`requirements_pages`/`timeline_pages` already are), but that file is
forbidden to this card too. `app/web/consent_pages.py`'s `router` is
already registered as its OWN standalone top-level slot ("consent_pages")
in exactly this situation — this module follows that same, already-
precedented shape rather than inventing an api->web import back into this
file just to keep the slot count at one (this codebase's established
direction is web imports api, never the reverse; see
`app/web/ask_pages.py`'s own docstring).
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app.ai import pipeline as ai_pipeline
from app.ai.actions import NextStepAction, next_step_actions_from_citations
from app.ai.budget import AIRequestBudget, default_budget
from app.ai.gemini_provider import GeminiNotConfiguredError, GeminiProvider
from app.ai.schemas import AIAnswerStatus, AskRequest
from app.ai.schemas import Answer as AIAnswer
from app.ai.what_changed import RenderedDiffLine, WhatChangedAnswer, answer_what_changed
from app.api.compare import COMPARISON_FIELDS, FieldValueOut
from app.api.deps import get_db_client
from app.api.eligibility import GENERIC_CRITERION_FIELDS
from app.core.config import get_settings
from app.data.models import DEFAULT_JURISDICTION, Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.i18n import translate
from app.planning.comparison import FieldValue, assemble_cost_breakdown, field_value_for

router = APIRouter(tags=["ask"])
ask_router = router
"""Alias — see this module's docstring's "Router registration" section."""


@dataclass(frozen=True)
class AskTemplate:
    """One entry in the fixed prompt registry — see module docstring."""

    id: str
    prompt_key: str
    """`app/i18n/en.json`/`hi.json` key for this template's canned
    question text (new `ask.*` keys this card adds)."""
    fields: tuple[str, ...]
    """Claim field names this template looks up, in display order."""


ASK_TEMPLATES: dict[str, AskTemplate] = {
    "cost_breakdown": AskTemplate(
        id="cost_breakdown",
        prompt_key="askbcion.prompt.cost_breakdown",
        fields=(
            "verified_charges",
            "estimated_additional_expenses",
            "potential_assistance_not_yet_awarded",
        ),
    ),
    "pathway_overview": AskTemplate(
        id="pathway_overview",
        prompt_key="askbcion.prompt.pathway_overview",
        # Reuses compare.py's own field list -- the same fields shown on
        # the Compare screen, so this template answers "what does this
        # pathway involve" with exactly what Compare already shows, never
        # a second, drifting list.
        fields=tuple(COMPARISON_FIELDS),
    ),
    "eligibility_gap": AskTemplate(
        id="eligibility_gap",
        prompt_key="askbcion.prompt.eligibility_gap",
        # Reuses eligibility.py's own generic-criterion field list -- the
        # same claim fields requirements.html's eligibility check reads,
        # so this template's "what's missing" list means the same thing
        # requirements.html's own badges mean.
        fields=GENERIC_CRITERION_FIELDS,
    ),
    "next_steps": AskTemplate(
        id="next_steps",
        # No i18n key added for this card (app/i18n/*.json is outside
        # this card's owned files) -- app.i18n.translate()/lookup()
        # already fall back to returning the bare key itself when a
        # catalogue entry is missing (app/i18n/__init__.py), so this is
        # a safe, non-crashing placeholder, not a new failure mode.
        prompt_key="askbcion.prompt.next_steps",
        # Deliberately empty -- see module docstring's "AI-18" section.
        # `assemble_ask_answer()` below iterates `template.fields`, so an
        # empty tuple degrades to zero fact cards / zero missing labels,
        # never an error.
        fields=(),
    ),
    "what_changed": AskTemplate(
        id="what_changed",
        # No i18n key added for this card either -- same safe,
        # non-crashing placeholder-key precedent `next_steps` above
        # already establishes.
        prompt_key="askbcion.prompt.what_changed",
        # Deliberately empty -- see module docstring's "AI-19" section.
        # This template's deterministic baseline has nothing to show:
        # "what changed" is derived from a diff of two claims, not a
        # field on either one.
        fields=(),
    ),
}

_MONEY_TEMPLATE_IDS = frozenset({"cost_breakdown"})
"""Which templates' fields are money fields (need `field_value(money=true)`
on the rendering side, and `assemble_cost_breakdown`'s currency-safe
assembly here rather than a bare `field_value_for` call — SCOPE-4)."""

_FIELD_LABELS: dict[str, str] = {
    # Matches compare.html's own headings verbatim (ux-qa-reviewer
    # consistency: the same field shown on two screens should say the
    # same thing on both).
    "entry_requirements": "Entry requirements",
    "main_stages": "Main stages",
    "time_range": "Time",
    "location": "Location",
    "verified_charges": "Verified charges",
    "estimated_additional_expenses": "Estimated additional expenses",
    "potential_assistance_not_yet_awarded": "Potential assistance (not yet awarded)",
    "minimum_age": "Minimum age",
    "maximum_age": "Maximum age",
    "minimum_marks_percentage": "Minimum marks percentage",
    "required_subjects": "Required subjects",
    "domicile_states": "Domicile",
}


def _field_label(field: str) -> str:
    return _FIELD_LABELS.get(field, field.replace("_", " ").replace(":", " ").strip().capitalize())


def _looks_like_a_uuid(value: str) -> bool:
    """File-local convention (see `app/api/compare.py`'s identically-named
    helper's own docstring) — a malformed id must 422/friendly-degrade,
    never reach Postgres raw and crash to an unhandled 500."""
    try:
        uuid_module.UUID(value)
    except ValueError:
        return False
    return True


def entity_kind_and_id(pathway_id: str | None, career_id: str | None) -> tuple[str, str] | None:
    """`(entity_kind, entity_id)` for exactly one well-formed id, or
    `None` for every other case this route must degrade, never crash,
    for: neither given, both given, or a malformed id. Shared by the
    JSON route below and `app/web/ask_pages.py` (imported forward, the
    established web-imports-api direction — see this module's docstring)."""
    if bool(pathway_id) == bool(career_id):
        return None
    entity_id = pathway_id if pathway_id else career_id
    assert entity_id is not None  # one of the two, by the check above
    if not _looks_like_a_uuid(entity_id):
        return None
    entity_kind = "pathway" if pathway_id else "career"
    return entity_kind, entity_id


def _pathway_id_for_plan(db: Client, plan_id: str) -> str:
    """AI-18: `next_steps`'s `plan_id` -> its `pathway_id` — see this
    module's own docstring's "AI-18: `next_steps` and `plan_id`" section
    for the full ownership-check reasoning. Raises `HTTPException(404)`
    for every case that must look identical to the caller: a malformed
    id, a nonexistent plan, a guest (who owns no `saved_plans` row at
    all), or another identity's plan — never a 422 that would let a
    caller distinguish "wrong id shape" from "not yours"."""
    if not _looks_like_a_uuid(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        result = db.table("saved_plans").select("pathway_id").eq("id", plan_id).execute()
    except APIError as exc:
        # CONSENT-4 (0014): saved_plans_select_own's USING clause calls
        # account_active(auth.uid()), which anon no longer has EXECUTE
        # on (the account_active() cross-user oracle fix) -- Postgres
        # checks that grant at query-analysis time for EVERY caller who
        # touches the policy, including a guest whose own row-match
        # would have been "no", not just one who'd have matched. Before
        # that fix, a guest's query here degraded to an empty result
        # (the intended "a guest owns no saved_plans row at all" case,
        # named in this function's own docstring); now it raises 42501
        # instead. Same "not found" outcome either way -- a guest was
        # never going to see a real plan_id's pathway through this path.
        if exc.code == "42501":
            raise HTTPException(status_code=404, detail="Plan not found.") from exc
        raise
    rows = cast("list[dict[str, Any]]", result.data)
    if not rows:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return cast("str", rows[0]["pathway_id"])


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """File-local convention (see `app/api/compare.py`'s identically-named
    helper's own docstring: "small per-route shape checks stay
    file-local")."""
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
        jurisdiction=row.get("jurisdiction") or DEFAULT_JURISDICTION,
        academic_cycle=row.get("academic_cycle"),
        currency=row.get("currency"),
    )


def _row_to_source(row: dict[str, Any]) -> Source:
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
        jurisdiction=row.get("jurisdiction") or DEFAULT_JURISDICTION,
    )


@dataclass(frozen=True)
class AskFactCard:
    field: str
    field_label: str
    value: FieldValue
    money: bool = False


@dataclass(frozen=True)
class AskAnswerData:
    """The fully-assembled deterministic answer for one template + entity,
    before any presentation-layer choice about JSON vs HTML — the same
    "assemble once, render twice" shape `app/api/compare.py`'s
    `PathwayComparisonData` uses, and for the same reason: the JSON route
    below and `app/web/ask_pages.py`'s HTML page must show the exact same
    facts, computed exactly once."""

    template: AskTemplate
    entity_kind: str
    entity_id: str
    fact_cards: tuple[AskFactCard, ...]
    """Only fields with a published, available value — never a
    `not_available` field_value(), which belongs in
    `missing_field_labels` instead."""
    missing_field_labels: tuple[str, ...]


def assemble_ask_answer(
    db: Client,
    template: AskTemplate,
    *,
    entity_kind: str,
    entity_id: str,
    as_of: date,
) -> AskAnswerData:
    """Fetch every claim/source for one entity and assemble one
    template's fact cards — the deterministic lookup this card's own text
    requires ("call `app.planning.comparison.field_value_for` directly
    against published claims ... exactly the way ... `compare.html`'s
    backing route already do[es]")."""
    entity_type = "Pathway" if entity_kind == "pathway" else "Career"
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", entity_type)
        .eq("entity_id", entity_id)
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

    if template.id in _MONEY_TEMPLATE_IDS:
        # SCOPE-4: money fields go through assemble_cost_breakdown, which
        # applies the currency-safety rule field_value_for alone does not
        # (a money claim with no stated currency renders not_available,
        # never a bare rupee-assumed number) -- the exact same function
        # compare.py's cost card already uses.
        breakdown = assemble_cost_breakdown(claims_by_field, sources_by_id, as_of=as_of)
        field_values: dict[str, FieldValue] = {
            "verified_charges": breakdown.verified_charges,
            "estimated_additional_expenses": breakdown.estimated_additional_expenses,
            "potential_assistance_not_yet_awarded": breakdown.potential_assistance_not_yet_awarded,
        }
    else:
        field_values = {
            field: field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
            for field in template.fields
        }

    money = template.id in _MONEY_TEMPLATE_IDS
    fact_cards = tuple(
        AskFactCard(
            field=field,
            field_label=_field_label(field),
            value=field_values[field],
            money=money,
        )
        for field in template.fields
        if field_values[field].label != TrustLabel.not_available
    )
    missing_field_labels = tuple(
        _field_label(field)
        for field in template.fields
        if field_values[field].label == TrustLabel.not_available
    )
    return AskAnswerData(
        template=template,
        entity_kind=entity_kind,
        entity_id=entity_id,
        fact_cards=fact_cards,
        missing_field_labels=missing_field_labels,
    )


@lru_cache
def _ai_budget() -> AIRequestBudget:
    """One process-local `AIRequestBudget`, shared by every `/ask`
    request in this process — the same `lru_cache` singleton lifecycle
    `app.core.config.get_settings()` uses (this module's docstring:
    "Provider and budget, both real but injected, not constructed
    per-request"). `default_budget()` (`app/ai/budget.py`) is
    deliberately NOT cached itself — its own docstring: "a caller that
    wants a single shared counter across requests ... should construct
    one `AIRequestBudget` itself at app startup and reuse that instance"
    — this function is that one caller, constructing exactly once per
    process. A fresh `AIRequestBudget` built per-request would reset the
    daily counter to zero on every single call, defeating the entire
    point of a daily spend cap.
    """
    return default_budget()


def _pipeline_answer(
    db: Client,
    template: AskTemplate,
    *,
    entity_kind: str,
    entity_id: str,
    as_of: date,
) -> AIAnswer | None:
    """The additive AI layer over `assemble_ask_answer()`'s unconditional
    deterministic fact cards — see this module's own docstring's
    "additive AI layer" section. Returns `None` — meaning "the pipeline
    was never even called" — whenever `Settings.ai_enabled`/
    `ai_configured` is false: `app.ai.pipeline.answer()` would only
    degrade to `AIAnswerStatus.ai_unavailable` in that case anyway (its
    own step 2), but this route skips the call outright rather than
    making a call whose outcome is already known, per this card's own
    instruction ("do not call `pipeline.answer()` at all" when disabled).

    `app.ai.gemini_provider.GeminiProvider()` is constructed fresh here,
    inside this AI-enabled branch only — never at import time, so an
    unconfigured environment never fails merely by importing this
    module. `GeminiNotConfiguredError` (raised when `GEMINI_API_KEY` is
    missing) is caught here and treated exactly like
    `AIAnswerStatus.ai_unavailable` — never allowed to escape as an
    unhandled 500 — by returning that status directly rather than
    calling `app.ai.pipeline.answer()` at all (there is no provider to
    give it).

    `template.id` is always a key in `ASK_TEMPLATES` above (the caller
    already resolved it via `ASK_TEMPLATES.get(...)`) and, not
    coincidentally, also a key in `app.ai.prompts.TEMPLATE_REGISTRY` —
    the three ids are shared verbatim across both registries. A template
    whose registered `PromptTemplateRequirement` does not match what this
    route actually has on hand for `entity_kind` (e.g. `eligibility_gap`
    requires a `claim_id`, which this route — given only a pathway/career
    id — never has) degrades to `AIAnswerStatus.unsupported_template`
    inside `app.ai.pipeline.answer()` itself, exactly like every other
    non-`answered` status: nothing extra rendered, no error.
    """
    settings = get_settings()
    if not (settings.ai_enabled and settings.ai_configured):
        return None
    try:
        provider = GeminiProvider()
    except GeminiNotConfiguredError:
        return AIAnswer(status=AIAnswerStatus.ai_unavailable)
    request = AskRequest(
        template_id=template.id,
        pathway_id=entity_id if entity_kind == "pathway" else None,
        career_id=entity_id if entity_kind == "career" else None,
    )
    return ai_pipeline.answer(db, request, provider, _ai_budget(), as_of=as_of)


def _what_changed_answer(
    db: Client,
    claim_id: str,
    *,
    as_of: date,
) -> WhatChangedAnswer | None:
    """`what_changed`'s own additive AI layer — mirrors `_pipeline_answer()`
    above (same settings gate, same `GeminiProvider()` construction and
    `GeminiNotConfiguredError` handling), but calls
    `app.ai.what_changed.answer_what_changed()` instead of
    `app.ai.pipeline.answer()`. See this module's own docstring's "AI-19"
    section for why `what_changed` cannot go through `_pipeline_answer()`
    at all: that function only ever builds an `AskRequest` carrying
    `pathway_id`/`career_id`, never a `claim_id`, and `what_changed`
    requires `claim_id` (`app.ai.prompts.TEMPLATE_REGISTRY`).

    Returns `None` under the exact same condition `_pipeline_answer()`
    does — AI disabled/not configured — meaning "never even called",
    never a status.
    """
    settings = get_settings()
    if not (settings.ai_enabled and settings.ai_configured):
        return None
    try:
        provider = GeminiProvider()
    except GeminiNotConfiguredError:
        return WhatChangedAnswer(status=AIAnswerStatus.ai_unavailable)
    return answer_what_changed(db, claim_id, provider, _ai_budget(), as_of=as_of)


class AskFactCardOut(BaseModel):
    field: str
    field_label: str
    value: FieldValueOut


class NextStepActionOut(BaseModel):
    """One `app.ai.actions.NextStepAction`, JSON-shaped — AI-18. Always
    present as a key on `AskResponse` (possibly empty), same
    always-present-possibly-empty convention `ai_sentences`/`ai_citations`
    already use, never omitted for a non-`next_steps` template."""

    text: str
    claim_id: str
    source_authority: str | None
    source_url: str | None


class WhatChangedLineOut(BaseModel):
    """One `app.ai.what_changed.RenderedDiffLine`, JSON-shaped — AI-19.
    Always present as a key on `AskResponse` (possibly empty), same
    always-present-possibly-empty convention `next_step_actions` already
    uses, never omitted for a non-`what_changed` template. `old_value`/
    `new_value` are already JSON-safe here (`_json_safe` below converts a
    `date` to its ISO string at the route boundary — `RenderedDiffLine`
    itself stays a plain, generically-typed dataclass; see `ask()`)."""

    attribute: str
    old_value: str | int | float | bool | list[Any] | dict[str, Any] | None
    new_value: str | int | float | bool | list[Any] | dict[str, Any] | None
    text: str


def _json_safe(value: Any) -> Any:
    """`RenderedDiffLine.old_value`/`.new_value` may hold a raw
    `datetime.date` (the `verification_date` diff line) alongside every
    other attribute's already-JSON-safe `Claim.value`/`str | None` shapes
    — this is the one, single place that date is turned into its ISO
    string, at the route boundary, so `WhatChangedLineOut` never has to
    carry a type pydantic/FastAPI would otherwise have to guess how to
    serialise."""
    if isinstance(value, date):
        return value.isoformat()
    return value


class AskResponse(BaseModel):
    template_id: str
    prompt: str
    entity_kind: str
    entity_id: str
    ai_enabled: bool
    show_fallback: bool
    """True when the AI-unavailable fallback copy must be shown alongside
    whatever fact cards ARE available -- AI_ENABLED/ai_configured is off
    (the pilot's default), or this template found nothing published at
    all for this entity. Never an error either way (module docstring)."""
    fallback_message: str | None
    """The exact `docs/UI.md` copy ("You can still compare routes and use
    the calculators.") when `show_fallback` is true, else `None`."""
    fact_cards: list[AskFactCardOut]
    missing_information: list[str]
    ai_sentences: list[str]
    """Populated ONLY when the additive AI layer (`_pipeline_answer()`,
    called when `ai_enabled`/`ai_configured` are both true) returned
    `AIAnswerStatus.answered` -- never for any other status, per this
    module's own "render nothing extra" rule. Always alongside
    `fact_cards` above, never in place of them: `fact_cards` is computed
    by `assemble_ask_answer()` unconditionally, on every request,
    regardless of whether this list is empty."""
    ai_citations: list[dict[str, Any]]
    """Structured citations for `ai_sentences`, same order, same
    "answered-only" rule -- plain data (`app.ai.guards.citation_for_record`'s
    own shape), never prose."""
    next_step_actions: list[NextStepActionOut]
    """AI-18. Populated ONLY for `template_id == "next_steps"` and only
    when the additive AI layer returned `AIAnswerStatus.answered` -- same
    "answered-only" rule as `ai_sentences`/`ai_citations` above, plus the
    template check (this module's own docstring's "AI-18" section). Empty
    for every other template, always, never omitted."""
    what_changed_lines: list[WhatChangedLineOut]
    """AI-19. Populated ONLY for `template_id == "what_changed"` and only
    when `_what_changed_answer()` returned `AIAnswerStatus.answered` --
    same "answered-only" rule as every other additive field above, plus
    the template check (this module's own docstring's "AI-19" section).
    Empty for every other template, always, never omitted."""


@router.get("/ask", response_model=AskResponse)
def ask(
    template: str = Query(...),
    pathway_id: str | None = Query(default=None),
    career_id: str | None = Query(default=None),
    plan_id: str | None = Query(default=None),
    claim_id: str | None = Query(default=None),
    db: Client = Depends(get_db_client),
) -> AskResponse:
    """`?template=<id>&pathway_id=<uuid>` (or `&career_id=<uuid>` instead
    of `pathway_id`, or -- `next_steps` only -- `&plan_id=<uuid>` instead
    of `pathway_id`; see module docstring's "AI-18" section, or --
    `what_changed` only -- `&claim_id=<uuid>` instead of any of the above;
    see module docstring's "AI-19" section) — see module docstring. An
    unknown `template_id` 404s with a fixed, generic message that never
    reflects the raw value back (avoid any reflected-value surface) — the
    id is deliberately left out of `detail` entirely, not merely
    escaped."""
    ask_template = ASK_TEMPLATES.get(template)
    if ask_template is None:
        raise HTTPException(status_code=404, detail="We don't recognise that question.")

    if ask_template.id == "what_changed":
        # AI-19: what_changed needs a claim_id, not a pathway/career id --
        # entity_kind_and_id() below is skipped entirely for this
        # template. See module docstring's "AI-19" section.
        if claim_id is None or not _looks_like_a_uuid(claim_id):
            raise HTTPException(status_code=422, detail="Provide a valid claim_id.")
        entity_kind, entity_id = "claim", claim_id
    else:
        if ask_template.id == "next_steps" and plan_id is not None and pathway_id is None:
            # AI-18: resolve BEFORE entity_kind_and_id runs, so a plan that
            # does not resolve 404s here rather than falling through to the
            # generic 422 the other three templates already use for "neither
            # id given". Only ever consulted for next_steps -- see module
            # docstring; the other three templates never see a plan_id.
            pathway_id = _pathway_id_for_plan(db, plan_id)

        resolved = entity_kind_and_id(pathway_id, career_id)
        if resolved is None:
            raise HTTPException(
                status_code=422,
                detail="Provide exactly one of pathway_id or career_id, each a valid id.",
            )
        entity_kind, entity_id = resolved

    as_of = datetime.now(tz=UTC).date()
    answer = assemble_ask_answer(
        db, ask_template, entity_kind=entity_kind, entity_id=entity_id, as_of=as_of
    )

    next_step_action_objs: tuple[NextStepAction, ...] = ()
    what_changed_line_objs: tuple[RenderedDiffLine, ...] = ()
    ai_sentences: list[str]
    ai_citations: list[dict[str, Any]]
    if ask_template.id == "what_changed":
        # AI-19: what_changed's own AI layer -- see module docstring's
        # "AI-19" section for why this cannot go through
        # `_pipeline_answer()`/`ai_pipeline.answer()` at all.
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
                # AI-18: the model's role was only to select and order which
                # of the pathway's verified facts survive two-pass grounding
                # (ai_answer.citations, unchanged pipeline output) -- turning
                # a surviving citation into actual action text is entirely
                # app.ai.actions's job, never this route's and never the
                # model's (see that module's own docstring).
                next_step_action_objs = next_step_actions_from_citations(ai_answer.citations)
        else:
            # Every other status (including "the pipeline was never called at
            # all", ai_answer is None) -- render nothing extra, per this
            # module's docstring: the response is exactly what the AI-off
            # path already produces, plus these always-present, possibly
            # -empty lists.
            ai_sentences = []
            ai_citations = []

    settings = get_settings()
    # `next_step_action_objs`/`what_changed_line_objs` are each only ever
    # assigned for their own template above, so this is exactly the
    # original expression for pathway_overview/cost_breakdown/
    # eligibility_gap -- AI-18 and AI-19 each add one more way for a
    # template to have "something to show" without changing what that
    # meant for the others.
    show_fallback = not (settings.ai_enabled and settings.ai_configured) or not (
        answer.fact_cards or next_step_action_objs or what_changed_line_objs
    )

    return AskResponse(
        template_id=ask_template.id,
        prompt=translate(ask_template.prompt_key, "en"),
        entity_kind=entity_kind,
        entity_id=entity_id,
        ai_enabled=settings.ai_enabled,
        show_fallback=show_fallback,
        fallback_message=(
            translate("global.difficult_state.ai_unavailable", "en") if show_fallback else None
        ),
        fact_cards=[
            AskFactCardOut(
                field=card.field,
                field_label=card.field_label,
                value=FieldValueOut.from_field_value(card.value),
            )
            for card in answer.fact_cards
        ],
        missing_information=list(answer.missing_field_labels),
        ai_sentences=ai_sentences,
        ai_citations=ai_citations,
        next_step_actions=[
            NextStepActionOut(
                text=action.text,
                claim_id=action.claim_id,
                source_authority=action.source_authority,
                source_url=action.source_url,
            )
            for action in next_step_action_objs
        ],
        what_changed_lines=[
            WhatChangedLineOut(
                attribute=line.attribute,
                old_value=_json_safe(line.old_value),
                new_value=_json_safe(line.new_value),
                text=line.text,
            )
            for line in what_changed_line_objs
        ],
    )
