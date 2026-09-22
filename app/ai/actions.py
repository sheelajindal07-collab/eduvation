"""AI-18 (`tasks/BCI-021.md`): the server-owned next-action catalogue for
Ask BCION's `next_steps` template.

## What this module is, and is not

This is NOT a second two-pass runner. `app/api/ask.py`'s existing
`_pipeline_answer()` (AI-7, unchanged, called exactly as it already is
for `pathway_overview`/`cost_breakdown`/`eligibility_gap`) already does
every step this card's own text describes for the model's role — reserve
the budget, build and send a selection prompt over the pathway's
published, non-stale, trust-checked per-field records
(`app.ai.retrieval.fetch_pathway_records`, via `app.ai.pipeline.answer`'s
`PromptTemplateRequirement.pathway_id` dispatch), validate it
(`app.ai.guards.parse_selection_response`), send an adversarial
verification pass, validate that too
(`app.ai.guards.parse_verification_response`), drop anything stale, and
return the surviving records as both `Answer.sentences` (generic "field
is value" prose this module never uses) and `Answer.citations` (plain
data: `record_id`/`field`/`value`/`source_authority`/`source_url`/
`is_stale` — `app.ai.guards.citation_for_record`'s own shape). This
card's own text says exactly this: "reuse `app.ai.pipeline.answer()`'s
two-call pattern and `app.ai.guards`' validation helpers rather than
writing a third parallel implementation" — so this module writes NONE of
that. `app/ai/prompts.py`'s `TEMPLATE_REGISTRY["next_steps"]` entry
(this card's own addition, folded into that file rather than a separate
`prompt_next_steps.py` — see the choice explained in that file's module
docstring, under "The template registry": this template needs no new
prompt-building logic at all) is what points `pipeline.answer()` at the
pathway's generic per-field records for this template.

## What THIS module actually does

Translates the *verified, code-derived* `Answer.citations` list —
already grounded, already trust-checked, already in the exact order the
model selected and then an adversarial second pass confirmed
(`app/ai/pipeline.py` step 11's own ordering, preserved end to end) —
into actual next-action TEXT, entirely in code, from a small, fixed,
ordered catalogue (`ACTION_TEMPLATE_RULES`) mapping a specific claim
FIELD NAME to a specific action-text template. A citation whose field has
no entry here produces no action at all — never rendered as a fact
either (this template's `fields` tuple in `app/api/ask.py`'s
`ASK_TEMPLATES` is deliberately empty, so nothing here duplicates
`pathway_overview`'s job) and never invented into an action text nobody
asked for.

This is the "already-computed candidate" property this card's own text
requires: `ACTION_TEMPLATE_RULES` is fixed, in code, evaluated
identically regardless of which fields the model happened to select —
the model only ever narrows a membership rule THIS module already fully
owns; it can never add a field/text combination this module does not
already recognise, and it never writes a character of the resulting
text.

`ACTION_TEMPLATE_RULES` covers the same two claim fields
`app/planning/actions.py`'s own, independently-built `ACTION_RULES`
already recognises as action-worthy for the unrelated, deterministic,
machine-key-only "My Plan next three actions" feature —
`application_window` (a deadline-shaped field) and `documents_required`
(a required-document field) — matching this card's own two worked
examples exactly ("a claim with a deadline-shaped field produces
'register before <date>' ... a claim naming a required document
produces 'collect <document>'"). The two modules are NOT coupled (this
one does not import, and is not imported by, `app/planning/actions.py`
— the same "each module carries its own small copy" convention
`app/ai/retrieval.py`'s own module docstring documents for
`_grounded_claims`/`_is_stale`); the field-name overlap is simply this
codebase's already-established vocabulary for "a claim that describes
something to do", not a shared dependency.

## Every action text is code-only, provably

Every `NextStepAction.text` below is built by plain Python string
substitution from `citation["value"]` — a value `app.ai.guards.
citation_for_record` already copied verbatim from an already
trust-checked `app.ai.retrieval.RetrievedRecord`, itself always backed by
exactly one real, published, non-synthetic `Claim`
(`app/ai/retrieval.py`'s own module docstring). This module never
imports an AI provider, an adapter, or `app/ai/pipeline.py`/
`app/ai/guards.py`/`app/ai/retrieval.py` themselves — it only ever reads
already-built citation dicts, a plain `Mapping`, never a typed object
from any of those forbidden-to-edit modules
(`tests/unit/test_ai_next_steps.py`'s `TestActionTextIsCodeOnly` proves
this by AST inspection, mirroring `tests/unit/test_ai_retrieval.py`'s own
import-guard test). There is no parameter through which a model's own
words could reach `.text`, even by accident.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final


def _clean_scalar(value: Any) -> str | None:
    """`value` rendered as a single, trimmed string, or `None` when there
    is genuinely nothing to act on: a blank/whitespace-only string, or a
    shape (`list`, `dict`, `None`) this module cannot sensibly render as
    one date/label without inventing formatting the claim itself never
    stated."""
    if value is None or isinstance(value, list | dict):
        return None
    text = str(value).strip()
    return text or None


def _deadline_action_texts(value: Any) -> tuple[str, ...]:
    """A deadline-shaped claim value -> one "register before" action, the
    date/window text taken straight from the claim, verbatim — this
    card's own first worked example."""
    cleaned = _clean_scalar(value)
    if cleaned is None:
        return ()
    return (f"Register before {cleaned}.",)


def _document_names(value: Any) -> tuple[str, ...]:
    """A required-document claim value -> the individual document names
    it lists, in the claim's own order, de-duplicated but never
    reordered or relabelled — this module never improves on what the
    claim actually says. Accepts either a `list` (each entry one
    document) or a comma-separated `str` — the two shapes a
    required-documents claim value is realistically stored as in this
    codebase today. Any other shape (`dict`, `None`, blank) yields no
    documents."""
    raw_items: Sequence[Any]
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = value.split(",")
    else:
        return ()
    names: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        cleaned = _clean_scalar(item)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        names.append(cleaned)
    return tuple(names)


def _document_action_texts(value: Any) -> tuple[str, ...]:
    """A required-document claim value -> one "collect" action per
    document it names — this card's own second worked example. A claim
    naming three documents yields three actions, all citing the SAME
    claim id (`next_step_actions_from_citations` below) — one claim can
    still be the traceable source of more than one action."""
    return tuple(f"Collect {name}." for name in _document_names(value))


@dataclass(frozen=True)
class ActionTemplateRule:
    """One claim field this catalogue recognises as describing something
    to do, and the code-only function that turns that field's own value
    into action text (never the model — see module docstring)."""

    claim_field: str
    action_texts_for_value: Callable[[Any], tuple[str, ...]]


#: Fixed, ordered, append-only — the entire, server-owned vocabulary of
#: "what a next action can be" for this template. See module docstring
#: for why membership here, not the model's own judgement, is what
#: ultimately decides whether a verified fact becomes an action at all.
ACTION_TEMPLATE_RULES: Final[tuple[ActionTemplateRule, ...]] = (
    ActionTemplateRule(
        claim_field="application_window",
        action_texts_for_value=_deadline_action_texts,
    ),
    ActionTemplateRule(
        claim_field="documents_required",
        action_texts_for_value=_document_action_texts,
    ),
)

_RULES_BY_FIELD: Final[dict[str, ActionTemplateRule]] = {
    rule.claim_field: rule for rule in ACTION_TEMPLATE_RULES
}


@dataclass(frozen=True)
class NextStepAction:
    """One next-action, with the evidence it came from — same
    "citation fields are not decoration" convention
    `app/planning/actions.py`'s own `NextAction` documents. `claim_id` is
    always the citation's own `record_id` (`app.ai.guards.
    citation_for_record`'s field, itself the real or short-hashed claim
    id — `app.ai.retrieval.RetrievedRecord.id`'s own docstring) — this
    card's own "every candidate action must cite the specific claim id it
    was derived from" requirement, satisfied structurally rather than by
    convention: there is no other id this dataclass could have been
    given."""

    text: str
    claim_id: str
    source_authority: str | None
    source_url: str | None
    is_stale: bool


def next_step_actions_from_citations(
    citations: Sequence[Mapping[str, Any]],
) -> tuple[NextStepAction, ...]:
    """The one function this module exposes to `app/api/ask.py`.

    `citations` is `Answer.citations` from an ALREADY-SUCCESSFUL
    (`AIAnswerStatus.answered`) `app.ai.pipeline.answer()` call, in that
    call's own surviving order (`app/ai/pipeline.py` step 11 — selection
    order, filtered to what verification confirmed, filtered again to
    what survived the freshness check). This function never reorders,
    never re-selects and never re-verifies; it only ever narrows
    further, by field name, against `ACTION_TEMPLATE_RULES` (module
    docstring). A citation for a field this catalogue does not recognise
    contributes no action at all — silently, not an error, since "the
    model picked a real, verified fact that just is not action-shaped"
    is an entirely ordinary outcome, not a bug.

    Each citation is expected to already have `app.ai.guards.
    citation_for_record`'s exact shape (`record_id`, `field`, `value`,
    `source_authority`, `source_url`, `is_stale`) — a plain `Mapping`
    rather than that module's own type, so this function never needs to
    import `app.ai.guards`/`app.ai.retrieval` at all (see module
    docstring's "code-only, provably" section). A citation missing
    `record_id` (should never happen for a real `Answer.citations` entry)
    is skipped rather than trusted with a placeholder id — an action with
    no traceable claim id is exactly the "AI invents facts" shape
    CLAUDE.md forbids, even when ordinary code produced the text.
    """
    actions: list[NextStepAction] = []
    for citation in citations:
        rule = _RULES_BY_FIELD.get(str(citation.get("field")))
        if rule is None:
            continue
        claim_id = citation.get("record_id")
        if not claim_id:
            continue
        for text in rule.action_texts_for_value(citation.get("value")):
            actions.append(
                NextStepAction(
                    text=text,
                    claim_id=str(claim_id),
                    source_authority=citation.get("source_authority"),
                    source_url=citation.get("source_url"),
                    is_stale=bool(citation.get("is_stale", False)),
                )
            )
    return tuple(actions)
