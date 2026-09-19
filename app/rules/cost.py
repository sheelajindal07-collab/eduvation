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

    total: float | None
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
    total = 0.0
    for c in components:
        value = c.field_value.value
        if isinstance(value, int | float) and not isinstance(value, bool):
            total += float(value)
    return VerifiedChargesResult(
        total=total, components=tuple(components), complete=True, stale=stale
    )


@dataclass(frozen=True)
class AssistanceItem:
    """One scholarship/loan amount, confirmed or potential."""

    name: str
    amount: float
    source_claim_id: str | None = None


@dataclass(frozen=True)
class CostSummary:
    verified_charges: VerifiedChargesResult
    estimated_additional_expenses: float
    confirmed_assistance: tuple[AssistanceItem, ...]
    potential_assistance: tuple[AssistanceItem, ...]

    @property
    def confirmed_assistance_total(self) -> float:
        return sum(item.amount for item in self.confirmed_assistance)

    @property
    def potential_assistance_total(self) -> float:
        """Informational only. Never used in `net_to_arrange` — see
        module docstring."""
        return sum(item.amount for item in self.potential_assistance)

    @property
    def net_to_arrange(self) -> float | None:
        """What the student needs to actually arrange: verified charges
        + estimated extras − CONFIRMED assistance only. `None` when
        verified_charges itself is incomplete — an unknown total cost
        must never be papered over with a confident-looking net figure.
        """
        if self.verified_charges.total is None:
            return None
        return (
            self.verified_charges.total
            + self.estimated_additional_expenses
            - self.confirmed_assistance_total
        )


def compute_cost_summary(
    fee_components: list[FeeComponent],
    estimated_additional_expenses: float,
    confirmed_assistance: list[AssistanceItem],
    potential_assistance: list[AssistanceItem],
) -> CostSummary:
    return CostSummary(
        verified_charges=sum_verified_charges(fee_components),
        estimated_additional_expenses=estimated_additional_expenses,
        confirmed_assistance=tuple(confirmed_assistance),
        potential_assistance=tuple(potential_assistance),
    )
