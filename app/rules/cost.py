"""Cost engine — Lite Build Pack §6, docs/DATA.md "Cost engine".

Deterministic. No model tokens. Four amounts, and the whole point of
this engine is that they never collapse into one number:

- **verified_charges**: summed from official fee-component claims
  (tuition, hostel, exam fee, ...). If any expected component is
  missing, the total is `None` — never a silently-partial sum shown as
  if it were the complete cost.
- **estimated_additional_expenses**: a stated assumption (travel, books,
  ...), never itself backed by a Claim (docs/DATA.md).
- **confirmed_assistance**: scholarships/loans actually awarded — the
  *only* amount that reduces what a student is shown they still need to
  arrange.
- **potential_assistance**: eligible-but-not-yet-awarded — shown for
  awareness, **never subtracted** from `net_to_arrange`. This is the
  single most safety-critical rule in this module: an unawarded
  scholarship must never look like money already in hand (Lite Build
  Pack §6: "an unawarded scholarship is never subtracted").

## Integer rupees (RULES-10)

Every amount this module produces or accepts is a whole rupee `int`,
never a `float`. Real fee-schedule claims occasionally quote a
paise-level fraction (e.g. "50000.10"); `to_whole_rupees` below is the
one place that fraction is rounded away, using the same round-half-to-
even rule `app/i18n/formatting.py`'s on-screen `format(value, ".0f")`
already applies, so a total computed here and the same figure rendered
on a page never disagree at a rounding boundary. `sum_verified_charges`
rounds each fee component as it sums them (raw claim data is the one
place a fraction can still arrive); everything else in this module
(`estimated_additional_expenses`, `AssistanceItem.amount`, the override)
is typed as an `int` and expected to already be in whole rupees by the
time it reaches this engine — `app/planning/comparison.py`'s assembly
layer is where a caller-supplied or claim-derived float is converted,
using this same `to_whole_rupees` function, before it ever reaches
`compute_cost_summary`.

## Estimate vs. user assumption (RULES-10)

`CostSummary` keeps two distinct lines instead of one that silently
clobbers the other: `estimated_additional_expenses` is the figure this
engine (or its caller) computed, `additional_expenses_override` is a
student's own edit for this one request only (Build Pack §6's
"assumption editing") — `None` when they have not edited anything.
Neither field is ever written to a database; `additional_expenses_override`
in particular only ever exists for the lifetime of one request, exactly
like `confirmed_assistance` below. `effective_additional_expenses` picks
whichever one actually feeds `net_to_arrange`: the override when the
student has supplied one, else the computed estimate — so the number a
student is shown they must arrange always matches the assumption they
can see and edit, never a stale or invisible one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.data.models import TrustLabel

if TYPE_CHECKING:
    # Deferred: app.planning.comparison now imports this module too
    # (assemble_cost_summary, added when the cost engine was wired into
    # GET /compare), so a top-level import here would be circular.
    # FieldValue is used only as a type annotation below, and
    # `from __future__ import annotations` means annotations are never
    # evaluated at runtime, so this guard is enough.
    from app.planning.comparison import FieldValue


def to_whole_rupees(value: int | float) -> int:
    """Coerce one rupee amount to a whole-rupee `int`.

    An `int` passes through unchanged (no float round-trip, no
    precision loss — this is the common case, since most fee amounts
    are already whole rupees). A `float` carrying a paise-level
    fraction (e.g. `50000.10`, `1999.995`) is rounded with Python's
    built-in `round()`, which — like `format(value, ".0f")` in
    `app/i18n/formatting.py` — resolves ties on the value's true binary
    representation using round-half-to-even. Using the identical
    rounding rule here and in that display formatter is deliberate: the
    same figure computed by this engine and rendered on a page must
    never disagree by a rupee at a rounding boundary.

    `bool` is excluded from the int fast-path (it is an `int` subclass
    in Python) so a stray `True`/`False` cannot silently pass through
    as `1`/`0` rupees without going through `round()` — a defensive
    branch matching the `isinstance(x, int | float) and not
    isinstance(x, bool)` guard callers already apply before this
    function is ever reached.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(round(value))


@dataclass(frozen=True)
class FeeComponent:
    """One line item of the official charges (e.g. "Tuition", "Hostel",
    "Exam fee"). `field_value` is already trust-labelled — build it with
    `app.planning.comparison.field_value_for` from a real claim."""

    name: str
    field_value: FieldValue


@dataclass(frozen=True)
class VerifiedChargesResult:
    """The summed official-fees figure, honest about incompleteness."""

    total: int | None
    """Whole rupees — see `to_whole_rupees`. `None` exactly when
    `complete` is `False`."""
    components: tuple[FeeComponent, ...]
    complete: bool
    """False if any component is `not_available` — `total` is then
    `None` rather than a silently-partial sum."""
    stale: bool
    """True if every component has a value but at least one needs
    rechecking — `total` is still usable, just flagged."""


def sum_verified_charges(components: list[FeeComponent]) -> VerifiedChargesResult:
    if not components:
        return VerifiedChargesResult(
            total=None, components=(), complete=False, stale=False
        )

    missing = [c for c in components if c.field_value.label == TrustLabel.not_available]
    if missing:
        return VerifiedChargesResult(
            total=None,
            components=tuple(components),
            complete=False,
            stale=False,
        )

    stale = any(c.field_value.label == TrustLabel.needs_rechecking for c in components)
    total = 0
    for c in components:
        value = c.field_value.value
        if isinstance(value, int | float) and not isinstance(value, bool):
            total += to_whole_rupees(value)
    return VerifiedChargesResult(
        total=total, components=tuple(components), complete=True, stale=stale
    )


@dataclass(frozen=True)
class AssistanceItem:
    """One scholarship/loan amount, confirmed or potential. `amount` is
    whole rupees (see module docstring) — a caller converting a raw
    claim or request value should run it through `to_whole_rupees`
    first."""

    name: str
    amount: int
    source_claim_id: str | None = None


@dataclass(frozen=True)
class CostSummary:
    verified_charges: VerifiedChargesResult
    estimated_additional_expenses: int
    """The estimate this engine's caller computed (e.g. from a published
    `estimated_additional_expenses_hint` claim, or `0` when there is
    none) — always present, always whole rupees. Kept distinct from
    `additional_expenses_override` so a caller/template can show BOTH
    "our estimate" and "your assumption" as two separate lines instead
    of one clobbering the other (see module docstring)."""
    additional_expenses_override: int | None
    """A caller-supplied assumption for THIS request only (Build Pack
    §6's "assumption editing"). Never a Claim, never persisted or stored
    anywhere — like `confirmed_assistance` below, it lives only for the
    lifetime of one request. `None` when the student has not edited the
    estimate; see `effective_additional_expenses` for which of the two
    fields actually feeds `net_to_arrange`."""
    confirmed_assistance: tuple[AssistanceItem, ...]
    """Scholarships/loans actually awarded, supplied per request only —
    there is no database write path anywhere in this module, and none
    should ever be added here; award data belongs to student-specific
    consent-gated storage (docs/DATA.md), not this pure arithmetic
    engine."""
    potential_assistance: tuple[AssistanceItem, ...]

    @property
    def effective_additional_expenses(self) -> int:
        """Whichever of the two "additional expenses" lines is
        authoritative for arithmetic: the student's own override when
        they have supplied one for this request, else the computed
        estimate. Exposed so a caller can display exactly what
        `net_to_arrange` was built from without re-deriving this same
        choice itself."""
        return (
            self.additional_expenses_override
            if self.additional_expenses_override is not None
            else self.estimated_additional_expenses
        )

    @property
    def confirmed_assistance_total(self) -> int:
        return sum(item.amount for item in self.confirmed_assistance)

    @property
    def potential_assistance_total(self) -> int:
        """Informational only. Never used in `net_to_arrange` — see
        module docstring."""
        return sum(item.amount for item in self.potential_assistance)

    @property
    def net_to_arrange(self) -> int | None:
        """What the student needs to actually arrange: verified charges
        + effective additional expenses (the override when the student
        has supplied one for this request, else the computed estimate)
        − CONFIRMED assistance only. `None` when verified_charges itself
        is incomplete — an unknown total cost must never be papered over
        with a confident-looking net figure.
        """
        if self.verified_charges.total is None:
            return None
        return (
            self.verified_charges.total
            + self.effective_additional_expenses
            - self.confirmed_assistance_total
        )


def compute_cost_summary(
    fee_components: list[FeeComponent],
    estimated_additional_expenses: int,
    confirmed_assistance: list[AssistanceItem],
    potential_assistance: list[AssistanceItem],
    *,
    additional_expenses_override: int | None = None,
) -> CostSummary:
    return CostSummary(
        verified_charges=sum_verified_charges(fee_components),
        estimated_additional_expenses=estimated_additional_expenses,
        additional_expenses_override=additional_expenses_override,
        confirmed_assistance=tuple(confirmed_assistance),
        potential_assistance=tuple(potential_assistance),
    )
