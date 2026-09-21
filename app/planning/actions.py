"""Next actions for a saved plan (AUTH-5).

docs/UI.md's My Plan screen shows a current decision and **up to three
next actions**. This module decides what those three are.

**Ordinary code, not AI.** CLAUDE.md: "Ordinary code for facts, rules
and arithmetic. AI only for grounded explanation with server-owned
citations." Which actions a student sees is a fact about what has been
verified for their pathway, so it is a lookup over claims, not a
generated suggestion. Nothing in this module calls a model, and it is
pure — no I/O, no clock, no database handle — so every branch is
unit-testable (tests/unit/test_plan_actions.py).

**Only published claims, ever.**
`docs/CONTRACTS.md`: "only `published` reaches a student-facing result."
An action is an instruction to a child about their education; deriving
one from a draft would be telling them to go and do something nobody has
checked. `_is_usable` below is the single gate, and it requires the
claim to be `published` AND its source not to be `synthetic`.

The synthetic check is belt-and-braces on purpose, not redundancy for
its own sake: a synthetic claim cannot in fact be published
(`forbid_publishing_synthetic_claims()`, db/migrations/0001_init.sql),
so the status check alone would do today. But demo mode
(db/migrations/0007_demo_mode.sql) deliberately puts `in_review`
synthetic claims into the read path, so this module now genuinely
receives them, and "the status check happens to be enough" is a property
of another migration that this module would not notice losing.

**Machine keys, never display text.** Same rule docs/CONTRACTS.md sets
for eligibility reasons: `action_key` and `reason` are stable codes,
resolved to English or Hindi at the presentation layer. A stored or
returned English sentence cannot be re-translated and cannot be changed
without a migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date

from app.data.models import Claim, ClaimStatus, Source, SourceType

MAX_ACTIONS = 3
"""docs/UI.md: "next three actions". Three is the whole point — a list of
eleven things is not a plan, it is a reason to close the tab."""

NOT_VERIFIED_YET = "not_verified_yet"
"""The reason code when no published claim supports any action.

docs/CONTRACTS.md, "Settled — coverage": "absence of a published claim
reads 'not verified yet' — never 'no', never zero, never blank." An
empty action list is a statement about what we have checked, not about
what the student needs to do."""


@dataclass(frozen=True)
class ActionRule:
    """One claim field that, when published, yields one next action.

    Order in `ACTION_RULES` below is priority order: the first three
    whose claims are published are the three shown.
    """

    claim_field: str
    action_key: str


# Deliberately a small, fixed, ordered list rather than anything derived
# at runtime. These are the fields the content track actually produces
# (app/api/compare.py's COMPARISON_FIELDS, plus the two application-
# process fields), and the ordering is the order a student meets them:
# what do I need, when do I apply, what do I bring, what happens then.
ACTION_RULES: tuple[ActionRule, ...] = (
    ActionRule(claim_field="entry_requirements", action_key="check_entry_requirements"),
    ActionRule(claim_field="application_window", action_key="note_application_window"),
    ActionRule(claim_field="documents_required", action_key="gather_documents"),
    ActionRule(claim_field="main_stages", action_key="review_main_stages"),
    ActionRule(claim_field="time_range", action_key="plan_for_duration"),
)


@dataclass(frozen=True)
class NextAction:
    """One action, with the evidence it came from.

    The citation fields are not decoration: docs/UI.md requires the
    source authority, the verification date and the official link
    alongside anything presented as a fact, and an action derived from a
    claim inherits that obligation. They are server-owned — read off the
    claim and its source here, never assembled by a caller and never
    produced by a model.
    """

    action_key: str
    claim_field: str
    source_authority: str | None = None
    source_url: str | None = None
    verification_date: date | None = None


@dataclass(frozen=True)
class NextActions:
    """Up to three actions, or none with a reason."""

    actions: list[NextAction] = dataclass_field(default_factory=list)
    reason: str | None = None
    """`NOT_VERIFIED_YET` when `actions` is empty, otherwise None. A
    caller renders the reason's copy key rather than an empty list, so
    "we have not checked this yet" is never shown as a blank panel."""

    def __bool__(self) -> bool:
        return bool(self.actions)


def _is_usable(claim: Claim, sources_by_id: dict[str, Source]) -> bool:
    """May this claim drive an action shown to a student?

    Both conditions are required; see the module docstring for why the
    second one is not redundant.
    """
    if claim.status is not ClaimStatus.published:
        return False
    source = sources_by_id.get(claim.source_id)
    if source is None:
        # No source row means no citation, and docs/UI.md requires one
        # alongside anything presented as verified. Refusing is the
        # fail-closed direction: an action with no attribution is exactly
        # the "AI invents facts" shape CLAUDE.md forbids, even when
        # ordinary code produced it.
        return False
    return source.source_type is not SourceType.synthetic


def derive_next_actions(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
) -> NextActions:
    """Up to three next actions for one pathway.

    `claims_by_field` is whatever the caller could actually read — which,
    under RLS, already excludes most things a student should not see.
    This function does not rely on that: it re-checks every claim itself,
    because "the caller already filtered" is precisely the assumption
    that stops being true the first time a reviewer's session, a demo
    mode, or a service-role script calls it.
    """
    actions: list[NextAction] = []

    for rule in ACTION_RULES:
        if len(actions) >= MAX_ACTIONS:
            break
        claim = claims_by_field.get(rule.claim_field)
        if claim is None or not _is_usable(claim, sources_by_id):
            continue
        source = sources_by_id[claim.source_id]
        actions.append(
            NextAction(
                action_key=rule.action_key,
                claim_field=rule.claim_field,
                source_authority=source.authority_name,
                source_url=source.official_url,
                verification_date=claim.verification_date,
            )
        )

    if not actions:
        return NextActions(actions=[], reason=NOT_VERIFIED_YET)
    return NextActions(actions=actions)


def action_keys(next_actions: NextActions) -> list[str]:
    """Just the keys, for matching against `plan_actions.action_key`."""
    return [action.action_key for action in next_actions.actions]


def is_known_action_key(key: str) -> bool:
    """Whether `key` is one this module can ever produce.

    The API layer uses this to reject an arbitrary string before it
    becomes a `plan_actions` row: `action_key` is `text` in the database
    (db/migrations/0010_plan_actions.sql) with no enum behind it, so
    without this check a caller could tick off — and store — anything at
    all, including free text on a table that is deliberately supposed to
    hold none.
    """
    return any(rule.action_key == key for rule in ACTION_RULES)
