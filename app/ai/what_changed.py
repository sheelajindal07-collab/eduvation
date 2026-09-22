"""AI-19 (`tasks/BCI-022.md`): the `what_changed` Ask BCION template — a
grounded, two-pass explanation of what changed between a superseded claim
and its `superseded_by` successor.

## Why this is not just another call to `app.ai.pipeline.answer()`

`app.ai.pipeline.answer()` (AI-6) dispatches retrieval by which
`PromptTemplateRequirement` a template declares — `pathway_id`/
`career_id` fetch every published per-field record for an entity
(`app.ai.retrieval.fetch_pathway_records`/`fetch_career_records`);
`claim_id` fetches exactly one PUBLISHED claim
(`app.ai.retrieval.fetch_claim_record`, gated on
`claim.status == ClaimStatus.published` — see that module's own
`_grounded_claims`). None of those three shapes fit this template: the
record `what_changed` is asked about, by definition, is the SUPERSEDED
half of a supersession — its own `status` is `superseded`, never
`published` — so `fetch_claim_record` would return `None` for it on
every single call, and `app.ai.pipeline.answer()` would degrade to
`not_available` unconditionally. This module is therefore its own
retrieval-plus-two-pass-call implementation, mirroring
`app.ai.pipeline.answer()`'s SHAPE (settings gate, reserve two calls
before any provider call, build/send a selection prompt, validate,
build/send a verification prompt, validate, drop anything stale, render)
step for step, over `app.ai.guards`' own validators — never a third,
differently-shaped implementation of the two-pass protocol itself.

## Readability — this module's own re-check, not `app.ai.retrieval`'s

`app/ai/retrieval.py`'s `_grounded_claims` accepts only
`ClaimStatus.published` claims — correct for "ground an answer on the
CURRENT fact", wrong here, where the superseded claim is the whole
subject. `_readable_claim` below is this module's own, independently
written copy of the same "never trust the caller's RLS scope alone"
principle (`app/ai/retrieval.py`'s own module docstring: a reviewer's own
RLS-scoped client can legitimately `SELECT` draft/in_review/superseded
rows — `db/migrations/0001_init.sql`'s `claims_select_published` policy
— so what comes back is not already "safe to ground an answer on" just
because RLS let it through): a claim is readable here when its `status`
is `published` OR `superseded` (never `draft`/`in_review` — an unapproved
fact must never reach this template, CLAUDE.md: "Unapproved facts never
reach public results"), its source resolves, and that source is not
`SourceType.synthetic` (docs/DATA.md "Synthetic fixtures ... NEVER
published as verified facts").

For a GUEST or an ordinary signed-in student, `claims_select_published`
means the superseded claim's row never even comes back from Postgres at
all for a non-reviewer caller — `_readable_claim` returns `None`, and the
whole answer is `not_available`, precisely the "not readable under the
caller's own RLS-equivalent access" case this card's own text asks for.
Only a reviewer's own RLS-scoped client (`is_reviewer()`) can see the row
in the first place; `_readable_claim`'s own re-check then still applies
on top, defensively, exactly as `app/ai/retrieval.py`'s does.

## Rendering — every line built in code from `claim_diff.py`'s own output

The two-pass model call here selects and verifies which of the diff's
own `changed_fields` are relevant to render — never which WORDS to use.
`_render_line` builds every `RenderedDiffLine.text` from `ClaimDiff`'s
own fields (`old_value`/`new_value`/`old_source_authority`/... — plain
data `app.planning.claim_diff.compute_claim_diff` already computed,
before the provider was ever called), keyed by attribute name off the
model's own surviving selection — never from anything the provider wrote
into its response text. The provider's response contributes a SET of
record ids only (validated against the retrieved set at every step,
exactly like `app/ai/pipeline.py`), never a word or a value.
`tests/unit/test_ai_what_changed.py`'s
`test_rendered_line_text_is_unchanged_by_whatever_the_provider_s_raw_text_says`
proves this directly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Final, cast

from supabase import Client

from app.ai.adapter import AIProvider
from app.ai.budget import AIBudgetExceededError, AIRequestBudget
from app.ai.guards import (
    assert_payload_traceable,
    build_outbound_payload,
    citation_for_record,
    parse_selection_response,
    parse_verification_response,
)
from app.ai.prompts import TEMPLATE_REGISTRY, build_selection_prompt, build_verification_prompt
from app.ai.retrieval import RetrievedRecord
from app.ai.schemas import MAX_ID_CHARS, AIAnswerStatus, AIProviderError
from app.core.config import get_settings
from app.data.models import DEFAULT_JURISDICTION, Claim, ClaimStatus, Source, SourceType
from app.planning.claim_diff import ClaimDiff, DiffableClaim, compute_claim_diff
from app.planning.comparison import DEFAULT_FRESHNESS_SLA_DAYS, safe_source_url

#: Human-readable label per `app.planning.claim_diff.DIFF_ATTRIBUTES`
#: entry, used only inside `_render_line`'s fixed sentence template below
#: — never a value a provider could influence.
_ATTRIBUTE_LABELS: Final[dict[str, str]] = {
    "value": "value",
    "source_authority": "source",
    "verification_date": "verification date",
}


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """File-local copy of `app/ai/retrieval.py`'s identically-named
    helper — deliberately duplicated, not imported, matching that
    module's own "each module carries its own small copy" convention
    (see its module docstring's "Never trust the caller's RLS scope
    alone" section)."""
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


def _readable_claim(db: Client, claim_id: str) -> tuple[Claim, Source] | None:
    """Fetch `claim_id` and its source through the caller's OWN
    request-scoped client, then re-verify in Python — see module
    docstring's "Readability" section. Returns `None` for every case that
    must degrade to `not_available`: the row does not exist (including
    "RLS filtered it out for this caller"), it is `draft`/`in_review`, its
    source cannot be resolved, or its source is `SourceType.synthetic`."""
    claim_result = db.table("claims").select("*").eq("id", claim_id).execute()
    claim_rows = cast("list[dict[str, Any]]", claim_result.data)
    if not claim_rows:
        return None
    claim = _row_to_claim(claim_rows[0])
    if claim.status not in (ClaimStatus.published, ClaimStatus.superseded):
        return None

    source_result = db.table("sources").select("*").eq("id", claim.source_id).execute()
    source_rows = cast("list[dict[str, Any]]", source_result.data)
    if not source_rows:
        return None
    source = _row_to_source(source_rows[0])
    if source.source_type == SourceType.synthetic:
        return None
    return claim, source


def _is_stale(claim: Claim, *, as_of: date) -> bool:
    """Mirrors `app/ai/retrieval.py`'s own `_is_stale` exactly (same
    constant, same comparison) — this module's own independent copy, per
    the same convention that module's docstring documents. Applied to the
    SUCCESSOR claim only: the successor is the current, replacing fact,
    so its own freshness is what "does this explanation still hold up"
    actually means here — the superseded claim is, by definition, no
    longer current, and staleness is not a meaningful question to ask of
    it."""
    return (as_of - claim.verification_date) > timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS)


def _record_id_for(claim_id: str, attribute: str) -> str:
    """A short, valid record id per diff line — `<claim_id>:<attribute>`
    when that already fits `MAX_ID_CHARS` (true for every real claim id
    this codebase issues, UUID strings), otherwise a deterministic
    shortened form, mirroring `app/ai/retrieval.py`'s own `_short_id`
    (same reasoning, same never-needed-in-practice fallback)."""
    raw = f"{claim_id}:{attribute}"
    if len(raw) <= MAX_ID_CHARS:
        return raw
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:MAX_ID_CHARS]


def _display(value: Any) -> str:
    """Plain-text rendering of one side of a diff line, for both the
    model-facing selection value and the final rendered sentence — always
    from a `ClaimDiff`'s own field, never from provider output."""
    if value is None:
        return "no value recorded"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _old_and_new(diff: ClaimDiff, attribute: str) -> tuple[Any, Any]:
    if attribute == "value":
        return diff.old_value, diff.new_value
    if attribute == "source_authority":
        return diff.old_source_authority, diff.new_source_authority
    if attribute == "verification_date":
        return diff.old_verification_date, diff.new_verification_date
    raise ValueError(f"unknown diff attribute: {attribute!r}")  # pragma: no cover - closed set


@dataclass(frozen=True)
class RenderedDiffLine:
    """One diff line the model selected and an adversarial second pass
    confirmed, rendered ENTIRELY in code from `ClaimDiff`'s own fields —
    see module docstring's "Rendering" section."""

    attribute: str
    old_value: Any
    new_value: Any
    text: str


@dataclass(frozen=True)
class WhatChangedAnswer:
    """What `answer_what_changed` returns. Not `app.ai.schemas.Answer` —
    that shape is `sentences`-based (generic "field is value" prose, via
    `app.ai.guards.fact_sentence_for_record`), which this template never
    produces; `lines` is this template's own, structured equivalent, each
    entry already carrying its own code-rendered `text`."""

    status: AIAnswerStatus
    diff: ClaimDiff | None = None
    lines: tuple[RenderedDiffLine, ...] = ()
    citations: list[dict[str, Any]] = field(default_factory=list)
    selection_ids: list[str] = field(default_factory=list)
    verification_ids: list[str] = field(default_factory=list)


def _render_line(diff: ClaimDiff, attribute: str) -> RenderedDiffLine:
    old, new = _old_and_new(diff, attribute)
    label = _ATTRIBUTE_LABELS[attribute]
    text = f"The {label} changed from {_display(old)} to {_display(new)}."
    return RenderedDiffLine(attribute=attribute, old_value=old, new_value=new, text=text)


def answer_what_changed(
    db: Client,
    claim_id: str,
    provider: AIProvider,
    budget: AIRequestBudget,
    *,
    as_of: date | None = None,
) -> WhatChangedAnswer:
    """Answer `what_changed` for the (superseded) claim named by
    `claim_id`. See module docstring for the full shape this mirrors from
    `app.ai.pipeline.answer()`.

    `provider` and `budget` are always injected, never constructed here —
    same contract `app.ai.pipeline.answer()` upholds, so no test path in
    this module ever touches the network.
    """
    resolved_as_of = as_of if as_of is not None else date.today()

    # Settings gate, before any retrieval or budget reservation — mirrors
    # app.ai.pipeline.answer()'s own step 2.
    settings = get_settings()
    if not settings.ai_enabled or not settings.ai_configured:
        return WhatChangedAnswer(status=AIAnswerStatus.ai_unavailable)

    superseded = _readable_claim(db, claim_id)
    if superseded is None:
        return WhatChangedAnswer(status=AIAnswerStatus.not_available)
    superseded_claim, superseded_source = superseded

    successor_id = superseded_claim.superseded_by
    if not successor_id:
        return WhatChangedAnswer(status=AIAnswerStatus.not_available)

    successor = _readable_claim(db, successor_id)
    if successor is None:
        return WhatChangedAnswer(status=AIAnswerStatus.not_available)
    successor_claim, successor_source = successor

    diff = compute_claim_diff(
        DiffableClaim(
            claim_id=superseded_claim.id,
            field=superseded_claim.field,
            value=superseded_claim.value,
            source_authority=superseded_source.authority_name,
            verification_date=superseded_claim.verification_date,
        ),
        DiffableClaim(
            claim_id=successor_claim.id,
            field=successor_claim.field,
            value=successor_claim.value,
            source_authority=successor_source.authority_name,
            verification_date=successor_claim.verification_date,
        ),
    )
    if not diff.has_changes:
        # Nothing to render is nothing to select -- the provider is never
        # called, same "no records -> not_available" rule
        # app.ai.pipeline.answer() step 3 applies to an empty retrieval.
        return WhatChangedAnswer(status=AIAnswerStatus.not_available, diff=diff)

    stale = _is_stale(successor_claim, as_of=resolved_as_of)
    source_url = safe_source_url(successor_source.official_url)

    records: list[RetrievedRecord] = []
    attribute_by_record_id: dict[str, str] = {}
    for attribute in diff.changed_fields:
        old, new = _old_and_new(diff, attribute)
        record_id = _record_id_for(diff.superseded_claim_id, attribute)
        records.append(
            RetrievedRecord(
                id=record_id,
                field=attribute,
                value=f"{_display(old)} -> {_display(new)}",
                source_authority=successor_source.authority_name,
                source_url=source_url,
                is_stale=stale,
            )
        )
        attribute_by_record_id[record_id] = attribute

    template = TEMPLATE_REGISTRY["what_changed"]

    # Reserve exactly two calls, both before any provider call -- mirrors
    # app.ai.pipeline.answer() step 4.
    try:
        budget.reserve(today=resolved_as_of)
        budget.reserve(today=resolved_as_of)
    except AIBudgetExceededError:
        return WhatChangedAnswer(status=AIAnswerStatus.budget_exhausted, diff=diff)

    # Traceability self-check, then the selection prompt -- mirrors step 5.
    payload, records_map = build_outbound_payload(template.id, records, lang="en")
    assert_payload_traceable(payload, records_map)
    selection_prompt = build_selection_prompt(template, records)

    # Send the selection prompt -- mirrors step 6.
    try:
        raw_selection = provider.generate(selection_prompt)
    except AIProviderError:
        return WhatChangedAnswer(status=AIAnswerStatus.ai_unavailable, diff=diff)

    # Validate the selection response -- mirrors step 7.
    valid_ids = {record.id for record in records}
    selection_ids = parse_selection_response(raw_selection, valid_ids)
    if not selection_ids:
        return WhatChangedAnswer(status=AIAnswerStatus.insufficient_information, diff=diff)

    records_by_id = {record.id: record for record in records}

    # Build and send the verification prompt -- mirrors step 8.
    verification_prompt = build_verification_prompt(
        template, [records_by_id[record_id] for record_id in selection_ids]
    )
    try:
        raw_verification = provider.generate(verification_prompt)
    except AIProviderError:
        return WhatChangedAnswer(
            status=AIAnswerStatus.ai_unavailable, diff=diff, selection_ids=list(selection_ids)
        )

    # Validate the verification response -- mirrors step 9.
    verification_ids = parse_verification_response(raw_verification, set(selection_ids))
    if verification_ids is None:
        return WhatChangedAnswer(
            status=AIAnswerStatus.insufficient_information,
            diff=diff,
            selection_ids=list(selection_ids),
        )

    verification_id_set = set(verification_ids)
    surviving_ids = [
        record_id for record_id in selection_ids if record_id in verification_id_set
    ]
    if not surviving_ids:
        return WhatChangedAnswer(
            status=AIAnswerStatus.insufficient_information,
            diff=diff,
            selection_ids=list(selection_ids),
            verification_ids=list(verification_ids),
        )

    # Freshness, all-or-nothing -- mirrors step 10. Every surviving record
    # shares the same successor-level `stale` value (see `_is_stale`'s
    # docstring), so one check covers all of them.
    if stale:
        return WhatChangedAnswer(
            status=AIAnswerStatus.insufficient_information,
            diff=diff,
            selection_ids=list(selection_ids),
            verification_ids=list(verification_ids),
        )

    # Rendering -- mirrors step 11, but every line is built from
    # `ClaimDiff`'s own fields (module docstring's "Rendering" section),
    # never from `fact_sentence_for_record`/provider output.
    rendered_lines = tuple(
        _render_line(diff, attribute_by_record_id[record_id]) for record_id in surviving_ids
    )
    citations = [citation_for_record(records_by_id[record_id]) for record_id in surviving_ids]

    return WhatChangedAnswer(
        status=AIAnswerStatus.answered,
        diff=diff,
        lines=rendered_lines,
        citations=citations,
        selection_ids=list(selection_ids),
        verification_ids=list(verification_ids),
    )
