"""The field-by-field diff between a superseded claim and its
`superseded_by` successor (AI-19, `tasks/BCI-022.md`).

Pure functions only, following the same "pure, DB-free" convention
`app/planning/comparison.py` and `app/rules/eligibility.py` already
establish: given two already-fetched, claim-shaped snapshots, compute
what changed between them. No I/O here — `app/ai/what_changed.py` fetches
the two `Claim`/`Source` rows (re-verifying readability itself, the same
defensive "never trust the caller's RLS scope alone" pattern
`app/ai/retrieval.py` already uses) and passes their fields in as plain
`DiffableClaim` values.

## Why `DiffableClaim`, not `app.data.models.Claim`

A diff needs the claim's *source authority* alongside its own fields —
`Claim` itself only ever carries `source_id`, a foreign key, never the
resolved `Source.authority_name` (the same reason
`app.planning.comparison.field_value_for` returns a `FieldValue` that
carries `source_authority` separately from the `Claim`/`Source` it was
built from). `DiffableClaim` is this module's own, narrower input shape —
exactly the fields a diff can compare — so this module never needs to
import `app.data.models.Claim`/`Source` at all, and stays fully
unit-testable without a live database or even a real `Claim` object.

## What "field-by-field" means here

Each `Claim` row already names exactly ONE fact field (e.g.
`minimum_age`) — a supersession is a correction of that one fact, not a
multi-field record. "Field-by-field" here means comparing the claim's own
attributes one at a time: its `value`, its source's `authority_name`, and
its `verification_date` — the three pieces of a fact this codebase's own
provenance model (docs/DATA.md) actually tracks per claim. An attribute
identical on both sides produces no entry in `changed_fields` at all —
nothing to render is nothing to select (`app/ai/what_changed.py`'s own
two-pass model call only ever offers the model lines for attributes that
actually changed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final

#: The only three claim attributes this module ever compares, in this
#: fixed order — matches the exact three pieces of output this card's own
#: text names: "old value, new value, old/new source authority, old/new
#: verification date".
DIFF_ATTRIBUTES: Final[tuple[str, ...]] = ("value", "source_authority", "verification_date")


@dataclass(frozen=True)
class DiffableClaim:
    """A claim-shaped snapshot this module can diff. See module docstring
    for why this is not `app.data.models.Claim` itself."""

    claim_id: str
    field: str
    value: str | int | float | bool | list[Any] | dict[str, Any] | None
    source_authority: str | None
    verification_date: date


@dataclass(frozen=True)
class ClaimDiff:
    """The full field-by-field diff of one supersession — both claims'
    own snapshots, side by side, plus which of the three `DIFF_ATTRIBUTES`
    actually differ. `field` is the superseded claim's own field name
    (the identity of "what fact this diff is about"); a successor whose
    own `field` differs is not itself diffed here (`app/api/claims.py`'s
    `SupersedeRequest` does not enforce the two claims share a field —
    this module makes no assumption about that beyond reporting the
    superseded claim's own name, since a value/source/date comparison
    across two genuinely different fields would not mean "what changed"
    at all)."""

    superseded_claim_id: str
    successor_claim_id: str
    field: str
    changed_fields: tuple[str, ...]
    """Subset of `DIFF_ATTRIBUTES`, in that fixed order — only the
    attributes whose old and new value actually differ."""
    old_value: str | int | float | bool | list[Any] | dict[str, Any] | None
    new_value: str | int | float | bool | list[Any] | dict[str, Any] | None
    old_source_authority: str | None
    new_source_authority: str | None
    old_verification_date: date
    new_verification_date: date

    @property
    def has_changes(self) -> bool:
        """`True` when at least one of `DIFF_ATTRIBUTES` actually
        differs — the same "nothing to render is nothing to select" case
        `app/ai/what_changed.py` treats identically to an unreadable row
        (`AIAnswerStatus.not_available`): a supersession with no
        detectable field-level change is not something this template can
        usefully explain."""
        return bool(self.changed_fields)


def compute_claim_diff(superseded: DiffableClaim, successor: DiffableClaim) -> ClaimDiff:
    """The one function this module exposes. Pure: no I/O, no randomness,
    same two inputs always produce the same `ClaimDiff`."""
    changed: list[str] = []
    if superseded.value != successor.value:
        changed.append("value")
    if superseded.source_authority != successor.source_authority:
        changed.append("source_authority")
    if superseded.verification_date != successor.verification_date:
        changed.append("verification_date")
    return ClaimDiff(
        superseded_claim_id=superseded.claim_id,
        successor_claim_id=successor.claim_id,
        field=superseded.field,
        changed_fields=tuple(changed),
        old_value=superseded.value,
        new_value=successor.value,
        old_source_authority=superseded.source_authority,
        new_source_authority=successor.source_authority,
        old_verification_date=superseded.verification_date,
        new_verification_date=successor.verification_date,
    )
