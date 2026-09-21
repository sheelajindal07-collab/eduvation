"""Cost engine — Lite Build Pack §6, docs/DATA.md "Cost engine",
docs/CONTRACTS.md "Money and currency".

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

## Money (RULES-10, docs/CONTRACTS.md "Money and currency")

Every amount this module produces or accepts is a `Money`: an
**integer** `amount` in the currency's major unit (whole rupees, never
paise, never a `float`) plus an ISO 4217 `currency`, defaulting to
`INR` since Lite is an India-first pilot with no FX conversion anywhere
— amounts are never converted between currencies. `Money.__post_init__`
runs every amount through `to_whole_rupees` (round-half-to-even, the
same rule `app/i18n/formatting.py`'s on-screen `format(value, ".0f")`
already applies) so this is the ONE place a paise-level fraction can
ever be rounded away, not something every call site has to remember to
do itself.

Components sum only within one currency (`sum_money` below): a claim
whose Source publishes a fee in USD and one in INR must never be added
together into one meaningless figure. `sum_verified_charges` surfaces
this as `VerifiedChargesResult.mixed_currencies = True` with `total =
None` — a DIFFERENT, distinguishable reason for "no total" than
`complete = False` (an unpublished/unavailable component): the first
means "we know every charge, they just don't share a currency", the
second means "we don't know one of the charges at all".

A money claim with a **null** currency renders as unavailable, exactly
like a missing value — `app/data/models.py`'s `Claim.currency`
docstring: "must never be silently assumed to be INR, that would invent
a fact about a real fee". `sum_verified_charges` treats a null-currency
component as `not_available` for this reason.

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
can see and edit, never a stale or invisible one. `net_to_arrange`
itself goes through the same `sum_money` currency guard as
`sum_verified_charges`: a caller-supplied estimate/override/assistance
figure in a currency that does not match the verified charges' currency
must not be silently added or coerced either, so the total is `None` in
that case too, rather than a confidently-wrong number.
"""

from __future__ import annotations

from collections.abc import Iterable
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

DEFAULT_CURRENCY = "INR"
"""docs/CONTRACTS.md "Money and currency": `Money`'s default currency —
Lite is an India-first pilot and has no currency-selection UI anywhere,
so any amount with no claim-provenanced currency of its own (a stated
assumption, a per-request override, an as-yet-unsourced assistance
figure) is INR, not left ambiguous."""


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
class Money:
    """One amount, in one currency's major unit (docs/CONTRACTS.md
    "Money and currency"). `amount` is always a whole-unit `int` —
    `__post_init__` runs it through `to_whole_rupees` even if a caller
    passes a `float` by mistake, so this dataclass is the single point
    where a paise-level fraction can ever be rounded away, not
    something every construction site has to remember to do itself.

    `currency` is an ISO 4217 code, defaulting to `INR`
    (`DEFAULT_CURRENCY`). Amounts are never converted between
    currencies — no FX rate exists anywhere in Lite; see `sum_money`
    for the one place more than one `Money` is combined."""

    amount: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_whole_rupees(self.amount))


def sum_money(amounts: Iterable[Money]) -> Money | None:
    """Sum `Money` amounts that share one currency.

    `None` when the amounts span more than one currency — there is no
    FX rate anywhere in Lite, so a cross-currency sum must never
    silently drop one side or coerce it into the other's currency
    (docs/CONTRACTS.md: "never silently dropped or coerced"). The
    caller decides what "can't be summed" means for its own output;
    `sum_verified_charges` below turns this into
    `VerifiedChargesResult.mixed_currencies = True`.

    An empty iterable sums to `Money(0)` (whole rupees, `INR` default)
    — "nothing to add" is a well-defined zero, not an unknown total.
    """
    resolved = list(amounts)
    if not resolved:
        return Money(amount=0)
    currencies = {m.currency for m in resolved}
    if len(currencies) > 1:
        return None
    return Money(amount=sum(m.amount for m in resolved), currency=resolved[0].currency)


@dataclass(frozen=True)
class FeeComponent:
    """One line item of the official charges (e.g. "Tuition", "Hostel",
    "Exam fee"). `field_value` is already trust-labelled — build it with
    `app.planning.comparison.field_value_for` from a real claim. Its
    `.currency` (also from the claim) is what `sum_verified_charges`
    reads to build this component's `Money`."""

    name: str
    field_value: FieldValue


@dataclass(frozen=True)
class VerifiedChargesResult:
    """The summed official-fees figure, honest about incompleteness AND
    about currency (docs/CONTRACTS.md "Money and currency")."""

    total: Money | None
    """`None` exactly when `complete` is `False` OR `mixed_currencies`
    is `True` — two different reasons a caller must be able to tell
    apart (see each field's own docstring)."""
    components: tuple[FeeComponent, ...]
    complete: bool
    """False if any component is `not_available`, OR is published with
    a value but a null currency (docs/CONTRACTS.md: a money claim with
    a null currency renders not_available) — `total` is then `None`
    rather than a silently-partial sum."""
    stale: bool
    """True if every component has a value but at least one needs
    rechecking — `total` is still usable, just flagged."""
    mixed_currencies: bool = False
    """True when every component DOES have a known value and currency,
    but they don't all share the same one -- `total` is still `None`
    here too, but for a different reason than `complete = False`: every
    charge is known, they simply cannot be added into one figure
    without an FX rate this pilot deliberately does not have."""


def sum_verified_charges(components: list[FeeComponent]) -> VerifiedChargesResult:
    if not components:
        return VerifiedChargesResult(total=None, components=(), complete=False, stale=False)

    resolved: list[Money] = []
    any_unusable = False
    for c in components:
        fv = c.field_value
        if fv.label == TrustLabel.not_available:
            any_unusable = True
            continue
        if fv.currency is None:
            # docs/CONTRACTS.md: "a money claim with a null currency
            # renders not_available" -- never silently assumed INR.
            any_unusable = True
            continue
        if isinstance(fv.value, int | float) and not isinstance(fv.value, bool):
            resolved.append(Money(amount=to_whole_rupees(fv.value), currency=fv.currency))
        # else: a non-numeric value on an otherwise-available claim
        # contributes nothing, the same pre-existing defensive skip
        # this function has always applied.

    if any_unusable:
        return VerifiedChargesResult(
            total=None, components=tuple(components), complete=False, stale=False
        )

    stale = any(c.field_value.label == TrustLabel.needs_rechecking for c in components)
    total = sum_money(resolved)
    if total is None:
        return VerifiedChargesResult(
            total=None,
            components=tuple(components),
            complete=True,
            stale=stale,
            mixed_currencies=True,
        )
    return VerifiedChargesResult(
        total=total, components=tuple(components), complete=True, stale=stale
    )


@dataclass(frozen=True)
class AssistanceItem:
    """One scholarship/loan amount, confirmed or potential."""

    name: str
    amount: Money
    source_claim_id: str | None = None


@dataclass(frozen=True)
class CostSummary:
    verified_charges: VerifiedChargesResult
    estimated_additional_expenses: Money
    """The estimate this engine's caller computed (e.g. from a published
    `estimated_additional_expenses_hint` claim, or `Money(0)` when there
    is none) — always present. Kept distinct from
    `additional_expenses_override` so a caller/template can show BOTH
    "our estimate" and "your assumption" as two separate lines instead
    of one clobbering the other (see module docstring)."""
    additional_expenses_override: Money | None
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
    def effective_additional_expenses(self) -> Money:
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
    def confirmed_assistance_total(self) -> Money | None:
        """`None` when confirmed assistance items span more than one
        currency (see `sum_money`) — informational sums are held to the
        same no-silent-coercion rule as the verified charges total."""
        return sum_money(item.amount for item in self.confirmed_assistance)

    @property
    def potential_assistance_total(self) -> Money | None:
        """Informational only. Never used in `net_to_arrange` — see
        module docstring. `None` on a currency mismatch, same as
        `confirmed_assistance_total`."""
        return sum_money(item.amount for item in self.potential_assistance)

    @property
    def net_to_arrange(self) -> Money | None:
        """What the student needs to actually arrange: verified charges
        + effective additional expenses (the override when the student
        has supplied one for this request, else the computed estimate)
        − CONFIRMED assistance only. `None` when verified_charges itself
        is incomplete or mixed-currency, when confirmed assistance items
        don't share one currency, or when the effective additional
        expenses/confirmed total don't share the verified charges'
        currency — an unknown or unsummable total cost must never be
        papered over with a confident-looking net figure.
        """
        if self.verified_charges.total is None:
            return None
        confirmed_total = self.confirmed_assistance_total
        if confirmed_total is None:
            return None
        negated_confirmed = Money(amount=-confirmed_total.amount, currency=confirmed_total.currency)
        return sum_money(
            [self.verified_charges.total, self.effective_additional_expenses, negated_confirmed]
        )


def compute_cost_summary(
    fee_components: list[FeeComponent],
    estimated_additional_expenses: Money,
    confirmed_assistance: list[AssistanceItem],
    potential_assistance: list[AssistanceItem],
    *,
    additional_expenses_override: Money | None = None,
) -> CostSummary:
    return CostSummary(
        verified_charges=sum_verified_charges(fee_components),
        estimated_additional_expenses=estimated_additional_expenses,
        additional_expenses_override=additional_expenses_override,
        confirmed_assistance=tuple(confirmed_assistance),
        potential_assistance=tuple(potential_assistance),
    )
