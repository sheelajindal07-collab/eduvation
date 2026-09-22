"""Timeline-stage assembly — RULES-9. A pathway's published stage claims,
turned into `app/rules/timeline.py` `Stage` objects the Career Life Span
Calculator can pre-fill and `compute_timeline()` can run straight over.

Pure function only, no I/O — same shape as `app/planning/comparison.py`:
given already-fetched Claims/Sources for a pathway, assemble the exact
`Stage` list this pathway publishes. Callers in `app/web/` and (a future
task's) `app/api/` fetch via `app/db/client.py` and pass the results in,
which keeps this module fully unit-testable without a live database.

## The stage-claim convention this task introduces

Neither `db/migrations/*.sql` nor `docs/DATA.md` names a claim-field
convention for a pathway's timeline stages yet (checked before writing
this). Mirroring RULES-8's own precedent — documenting a new convention
in the module that first needs it, rather than silently guessing or
adding a migration/docs section no card asked for — Lite's pathway
timeline stages are ONE claim per fact, the same "atomic field, not a
JSON blob" shape every other engine in this codebase already uses
(`minimum_age`, `verified_charges`, RULES-10's `fee_component:<name>`):

    stage:<order>:name                         str — required for a
                                                stage to appear at all
    stage:<order>:duration_weeks                int, whole weeks
                                                (docs/CONTRACTS.md
                                                "Duration, dates, cycle,
                                                DOB")
    stage:<order>:kind                          "required" | "optional"
                                                — never "user_assumption"
                                                (see below)
    stage:<order>:overlap_weeks_with_previous   int, defaults to 0 when
                                                absent or unpublished

`<order>` is a positive integer (`1`, `2`, `3`, ...) that both names the
claim field AND fixes the resulting `Stage` list's own order — unlike
RULES-10's `fee_component:*` fields (sorted alphabetically, since fee
components have no inherent sequence), a stage's position determines
what `overlap_weeks_with_previous` even means, so it has to be an
explicit numeric order rather than a name-derived one.

This is deliberately FOUR separate claims per stage rather than one
structured JSON claim (RULES-3 would allow the latter — `Claim.value`
accepts a dict). A stage's NAME (a content author typically knows this
immediately — "a Bachelor's degree comes after Class 12") and its
DURATION (which needs an official source to verify) are two different
facts with two different certainties, and splitting them means a
pathway can publish "there is a stage here" before it can publish "and
it takes this long" — exactly this codebase's "explain the gap, don't
invent it" pattern (`app/rules/cost.py`'s `sum_verified_charges`,
`app/rules/timeline.py`'s own module docstring), now applied per-stage
rather than only to the whole timeline. A `stage:<order>:name` claim
that is not itself published means there is no verified stage at that
position at all, so the whole slot is skipped — there would be nothing
non-invented left to show.

`kind` never accepts `"user_assumption"` from a content claim: that
value means the STUDENT added the stage themselves
(`app/rules/timeline.py`'s `Stage.kind` docstring), and a pathway's own
published content can never claim to be the student's own assumption.
A `kind` claim holding that value (or anything else unrecognised)
degrades to `None`, which `Stage.display_kind` already falls back to
`required`/`optional` for via the `required` boolean.

Every fact is independently gated through `field_value_for()` — the
exact same "gate a claim's value on publication status" helper
`app/planning/comparison.py` and RULES-8's eligibility route already
use, not a second copy of that logic.
"""

from __future__ import annotations

import re
from datetime import date
from typing import cast

from app.data.models import Claim, Source, TrustLabel
from app.planning.comparison import field_value_for
from app.rules.timeline import Stage, StageKind

_STAGE_FIELD_RE = re.compile(
    r"^stage:(?P<order>\d+):(?P<part>name|duration_weeks|kind|overlap_weeks_with_previous)$"
)

_VALID_CONTENT_KINDS = frozenset({"required", "optional"})
"""Never `"user_assumption"` — see the module docstring: that kind means
the STUDENT added the stage, and a content claim asserting it would
misuse the label."""


def _stage_field(order: int, part: str) -> str:
    return f"stage:{order}:{part}"


def _stage_orders(claims_by_field: dict[str, Claim]) -> list[int]:
    """Every distinct `<order>` named by ANY `stage:<order>:*` field on
    this pathway, regardless of that particular claim's own publication
    status — a field simply existing is what defines a stage SLOT;
    whether any one fact in it is visible is decided per-field below,
    not here. Sorted NUMERICALLY (never alphabetically — `"stage:10"`
    must sort after `"stage:9"`, not between `"stage:1"` and
    `"stage:2"`), since this order is also the returned `Stage` list's
    own order and therefore what `overlap_weeks_with_previous` means for
    each one.
    """
    orders: set[int] = set()
    for field in claims_by_field:
        match = _STAGE_FIELD_RE.match(field)
        if match:
            orders.add(int(match.group("order")))
    return sorted(orders)


def _stage_duration(
    order: int,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> tuple[int | None, str | None]:
    """`(duration_weeks, source_claim_id)` for one stage.

    `duration_weeks` is `None` whenever the `duration_weeks` claim is
    not published, stale-and-sourceless, or synthetic-sourced (the exact
    same set of reasons `field_value_for` withholds any other field), or
    when a published value is not a whole number of weeks — never
    guessed, never dropped: the caller still gets a `Stage`, just with
    an unknown duration (`app/rules/timeline.py`'s own core rule).

    `source_claim_id` is returned whenever the field is AVAILABLE at
    all, even if its value could not be parsed as an int — provenance is
    about which claim published something, not about whether this
    function could read it.
    """
    field = _stage_field(order, "duration_weeks")
    fv = field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
    if fv.label == TrustLabel.not_available:
        return None, None
    claim = claims_by_field.get(field)
    source_claim_id = claim.id if claim else None
    if isinstance(fv.value, int) and not isinstance(fv.value, bool):
        return fv.value, source_claim_id
    return None, source_claim_id


def _stage_kind(
    order: int,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> StageKind | None:
    fv = field_value_for(
        _stage_field(order, "kind"), claims_by_field, sources_by_id, as_of=as_of
    )
    if isinstance(fv.value, str) and fv.value in _VALID_CONTENT_KINDS:
        return cast(StageKind, fv.value)
    return None


def _stage_overlap(
    order: int,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> int:
    fv = field_value_for(
        _stage_field(order, "overlap_weeks_with_previous"),
        claims_by_field,
        sources_by_id,
        as_of=as_of,
    )
    if isinstance(fv.value, int) and not isinstance(fv.value, bool):
        return fv.value
    return 0


def stages_from_claims(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> list[Stage]:
    """A pathway's published timeline stages, in order — this module's
    one public entry point.

    Every stage slot named by claims_by_field (see the module docstring
    for the `stage:<order>:*` convention) that has a published, readable
    `name` becomes one `Stage`. A slot whose `name` claim is not
    published is skipped entirely — there is no verified fact left to
    show. A published `name` with an unpublished/unreadable
    `duration_weeks` still becomes a `Stage`, with `duration_weeks=None`
    — the student sees the stage exists, with its duration honestly
    marked as not yet published, matching `app/rules/timeline.py`'s
    "never silently drop an incomplete stage" rule one level up (a
    `Stage` list `compute_timeline()` then reports as `complete=False`,
    never a partial total).
    """
    stages: list[Stage] = []
    for order in _stage_orders(claims_by_field):
        name_fv = field_value_for(
            _stage_field(order, "name"), claims_by_field, sources_by_id, as_of=as_of
        )
        if not isinstance(name_fv.value, str) or not name_fv.value.strip():
            continue
        name = name_fv.value.strip()

        duration_weeks, source_claim_id = _stage_duration(
            order, claims_by_field, sources_by_id, as_of=as_of
        )
        kind = _stage_kind(order, claims_by_field, sources_by_id, as_of=as_of)
        overlap = _stage_overlap(order, claims_by_field, sources_by_id, as_of=as_of)

        stages.append(
            Stage(
                name=name,
                duration_weeks=duration_weeks,
                required=(kind != "optional"),
                overlap_weeks_with_previous=overlap,
                source_claim_id=source_claim_id,
                kind=kind,
            )
        )
    return stages
