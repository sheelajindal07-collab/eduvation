"""Tests for app/rules/cost.py.

The single most important property here: potential (unawarded)
assistance must NEVER reduce net_to_arrange. Every test class exists to
pin down one part of the four-amounts-never-merge guarantee. RULES-10
added a second safety property of the same weight: amounts in different
currencies must never be silently summed or coerced together
(docs/CONTRACTS.md "Money and currency").
"""

from datetime import date

from app.data.models import TrustLabel
from app.planning.comparison import FieldValue
from app.rules.cost import (
    AssistanceItem,
    FeeComponent,
    Money,
    compute_cost_summary,
    sum_money,
    sum_verified_charges,
    to_whole_rupees,
)

TODAY = date(2026, 9, 19)


def _verified(value: float, currency: str | None = "INR") -> FieldValue:
    return FieldValue(
        value=value,
        label=TrustLabel.checked_against_official_source,
        source_url="https://example.invalid/source",
        verification_date=TODAY,
        currency=currency,
    )


def _stale(value: float, currency: str | None = "INR") -> FieldValue:
    return FieldValue(
        value=value,
        label=TrustLabel.needs_rechecking,
        verification_date=TODAY,
        currency=currency,
    )


def _missing() -> FieldValue:
    return FieldValue(value=None, label=TrustLabel.not_available)


def _no_currency(value: float) -> FieldValue:
    """A published, otherwise-usable claim whose currency was never
    stated — docs/CONTRACTS.md: "a money claim with a null currency
    renders not_available", never silently assumed to be INR."""
    return FieldValue(
        value=value,
        label=TrustLabel.checked_against_official_source,
        source_url="https://example.invalid/source",
        verification_date=TODAY,
        currency=None,
    )


class TestMoney:
    """RULES-10 / docs/CONTRACTS.md "Money and currency": `Money` is one
    value type, an integer amount plus an ISO 4217 currency defaulting
    to INR."""

    def test_default_currency_is_inr(self) -> None:
        assert Money(amount=1000).currency == "INR"

    def test_amount_is_rounded_to_a_whole_unit_on_construction(self) -> None:
        """`Money` itself is the backstop: even if a caller passes a
        fractional amount directly (bypassing `to_whole_rupees`), the
        dataclass rounds it on construction -- there is exactly one
        place a paise-level fraction can ever survive into a `Money`."""
        assert Money(amount=1999.995).amount == 2000  # type: ignore[arg-type]
        assert isinstance(Money(amount=1999.995).amount, int)  # type: ignore[arg-type]

    def test_equality_compares_both_amount_and_currency(self) -> None:
        assert Money(amount=1000) == Money(amount=1000, currency="INR")
        assert Money(amount=1000, currency="INR") != Money(amount=1000, currency="USD")
        assert Money(amount=1000) != Money(amount=2000)


class TestSumMoney:
    """The shared "same currency only" guard every money total in this
    module is built on."""

    def test_empty_iterable_sums_to_zero_inr(self) -> None:
        assert sum_money([]) == Money(amount=0)

    def test_same_currency_amounts_sum(self) -> None:
        assert sum_money([Money(amount=100), Money(amount=250)]) == Money(amount=350)

    def test_mixed_currency_amounts_give_none(self) -> None:
        """The core safety property: no FX rate exists anywhere in
        Lite, so amounts in different currencies must never be silently
        summed or coerced -- the caller gets an explicit `None` instead."""
        result = sum_money([Money(amount=100, currency="INR"), Money(amount=5, currency="USD")])
        assert result is None

    def test_single_amount_returns_that_amount(self) -> None:
        assert sum_money([Money(amount=42, currency="USD")]) == Money(amount=42, currency="USD")


class TestSumVerifiedCharges:
    def test_sums_all_present_components(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Hostel", _verified(30000)),
            FeeComponent("Exam fee", _verified(2000)),
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=82000)
        assert result.complete is True
        assert result.stale is False
        assert result.mixed_currencies is False

    def test_missing_component_gives_none_total_not_a_partial_sum(self) -> None:
        """The core safety property: a missing fee component must never
        silently vanish from the total — the total becomes unknown, not
        smaller than reality."""
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Hostel", _missing()),
        ]
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.complete is False

    def test_no_components_gives_none_total(self) -> None:
        result = sum_verified_charges([])
        assert result.total is None
        assert result.complete is False

    def test_stale_component_still_sums_but_flags_stale(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Hostel", _stale(30000)),
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=80000)
        assert result.complete is True
        assert result.stale is True


class TestNullCurrencyRendersNotAvailable:
    """docs/CONTRACTS.md "Money and currency": "A money claim with a
    null currency renders not_available." A published, numeric,
    otherwise-trustworthy claim with no stated currency must be treated
    exactly like a missing component -- never silently assumed INR."""

    def test_a_single_null_currency_component_gives_none_total(self) -> None:
        components = [FeeComponent("Tuition", _no_currency(50000))]
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.complete is False
        assert result.mixed_currencies is False

    def test_one_null_currency_component_among_others_gives_none_total(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Hostel", _no_currency(30000)),
        ]
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.complete is False


class TestMixedCurrencyFeeComponents:
    """docs/CONTRACTS.md "Money and currency": "Components sum only
    within one currency; a total over mixed currencies is None with
    reason mixed_currencies, shown to the student, never silently
    dropped or coerced." Distinguishable from `complete = False`: every
    component IS known here, they just can't be added together."""

    def test_two_currencies_gives_none_total_flagged_mixed_currencies(self) -> None:
        components = [
            FeeComponent("Indian application fee", _verified(5000, currency="INR")),
            FeeComponent("Foreign tuition", _verified(20000, currency="USD")),
        ]
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.mixed_currencies is True
        # Distinct from the "we don't know a component" reason:
        assert result.complete is True

    def test_three_currencies_still_gives_none_total(self) -> None:
        components = [
            FeeComponent("A", _verified(100, currency="INR")),
            FeeComponent("B", _verified(100, currency="USD")),
            FeeComponent("C", _verified(100, currency="GBP")),
        ]
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.mixed_currencies is True

    def test_same_non_inr_currency_throughout_still_sums_normally(self) -> None:
        """Mixed-currency detection is about currencies differing from
        EACH OTHER, not about differing from INR -- an all-USD pathway
        (e.g. a fully foreign programme) sums normally in USD."""
        components = [
            FeeComponent("Tuition", _verified(20000, currency="USD")),
            FeeComponent("Housing", _verified(8000, currency="USD")),
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=28000, currency="USD")
        assert result.mixed_currencies is False
        assert result.complete is True


class TestCostSummaryFourAmountsNeverMerge:
    def test_confirmed_assistance_reduces_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=20000),
            confirmed_assistance=[AssistanceItem("State merit scholarship", Money(amount=15000))],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == Money(amount=100000 + 20000 - 15000)

    def test_potential_assistance_never_reduces_net_to_arrange(self) -> None:
        """The core rule (Lite Build Pack §6): 'an unawarded scholarship
        is never subtracted'. This is the single test that matters most
        in this file."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=20000),
            confirmed_assistance=[],
            potential_assistance=[
                AssistanceItem("Maybe-eligible scholarship", Money(amount=50000))
            ],
        )
        assert summary.net_to_arrange == Money(amount=100000 + 20000)
        assert summary.potential_assistance_total == Money(amount=50000)
        # explicitly: the potential amount is visible for awareness...
        assert summary.potential_assistance[0].amount == Money(amount=50000)
        # ...but categorically absent from the arithmetic above.

    def test_both_confirmed_and_potential_present_stay_separate(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=10000),
            confirmed_assistance=[AssistanceItem("Awarded scholarship", Money(amount=20000))],
            potential_assistance=[AssistanceItem("Applied, not yet decided", Money(amount=30000))],
        )
        assert summary.confirmed_assistance_total == Money(amount=20000)
        assert summary.potential_assistance_total == Money(amount=30000)
        assert summary.net_to_arrange == Money(amount=100000 + 10000 - 20000)
        # the two totals are never added or conflated:
        assert summary.confirmed_assistance_total != summary.potential_assistance_total

    def test_incomplete_verified_charges_gives_none_net_not_a_guess(self) -> None:
        """An unknown total cost must never be papered over with a
        confident-looking net figure that's actually missing a piece."""
        summary = compute_cost_summary(
            fee_components=[
                FeeComponent("Tuition", _verified(100000)),
                FeeComponent("Hostel", _missing()),
            ],
            estimated_additional_expenses=Money(amount=10000),
            confirmed_assistance=[AssistanceItem("Some scholarship", Money(amount=5000))],
            potential_assistance=[],
        )
        assert summary.verified_charges.total is None
        assert summary.net_to_arrange is None

    def test_multiple_confirmed_assistance_items_sum_correctly(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=0),
            confirmed_assistance=[
                AssistanceItem("Scholarship A", Money(amount=10000)),
                AssistanceItem("Scholarship B", Money(amount=5000)),
            ],
            potential_assistance=[],
        )
        assert summary.confirmed_assistance_total == Money(amount=15000)
        assert summary.net_to_arrange == Money(amount=100000 - 15000)

    def test_zero_cost_edge_case(self) -> None:
        """Boundary: a free programme with no assistance at all."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(0))],
            estimated_additional_expenses=Money(amount=0),
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == Money(amount=0)


class TestNetToArrangeCurrencyMismatch:
    """RULES-10: `net_to_arrange` runs the same "same currency only"
    guard `sum_verified_charges` does -- a caller-supplied estimate,
    override or confirmed-assistance figure in a different currency to
    the verified charges must not be silently added or coerced either."""

    def test_confirmed_assistance_in_a_different_currency_gives_none_net(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000, currency="INR"))],
            estimated_additional_expenses=Money(amount=0),
            confirmed_assistance=[
                AssistanceItem("Foreign grant", Money(amount=100, currency="USD"))
            ],
            potential_assistance=[],
        )
        # the charges ARE known, but can't be combined with a USD assistance figure:
        assert summary.verified_charges.total is not None
        assert summary.net_to_arrange is None

    def test_estimate_in_a_different_currency_gives_none_net(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(20000, currency="USD"))],
            estimated_additional_expenses=Money(amount=5000, currency="INR"),
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange is None

    def test_matching_non_inr_currency_throughout_nets_normally(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(20000, currency="USD"))],
            estimated_additional_expenses=Money(amount=1000, currency="USD"),
            confirmed_assistance=[AssistanceItem("Grant", Money(amount=500, currency="USD"))],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == Money(amount=20000 + 1000 - 500, currency="USD")


class TestEstimateVsUserAssumptionOverride:
    """RULES-10: `CostSummary` keeps the computed estimate and a
    per-request user override as two distinct lines rather than one
    clobbering the other. `net_to_arrange`'s arithmetic still uses
    whichever is authoritative -- the override when the caller supplies
    one, else the estimate -- so this splits the DISPLAY of the two
    figures without changing the total a student is shown."""

    def test_no_override_uses_the_estimate_for_both_display_and_arithmetic(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=15000),
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.estimated_additional_expenses == Money(amount=15000)
        assert summary.additional_expenses_override is None
        assert summary.effective_additional_expenses == Money(amount=15000)
        assert summary.net_to_arrange == Money(amount=115000)

    def test_override_is_visible_separately_and_still_wins_the_arithmetic(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=15000),
            confirmed_assistance=[],
            potential_assistance=[],
            additional_expenses_override=Money(amount=30000),
        )
        # Both lines stay visible, distinctly -- neither clobbers the other:
        assert summary.estimated_additional_expenses == Money(amount=15000)
        assert summary.additional_expenses_override == Money(amount=30000)
        # ...but the override is what net_to_arrange actually uses:
        assert summary.effective_additional_expenses == Money(amount=30000)
        assert summary.net_to_arrange == Money(amount=130000)

    def test_a_zero_override_is_distinct_from_no_override_at_all(self) -> None:
        """A student explicitly zeroing out the estimate ("I have no
        extra expenses") must not look identical to never having
        touched the field -- `None` and `Money(0)` are different facts."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=15000),
            confirmed_assistance=[],
            potential_assistance=[],
            additional_expenses_override=Money(amount=0),
        )
        assert summary.additional_expenses_override == Money(amount=0)
        assert summary.additional_expenses_override is not None
        assert summary.effective_additional_expenses == Money(amount=0)
        assert summary.net_to_arrange == Money(amount=100000)


class TestNegativeEstimatedAdditionalExpenses:
    """estimated_additional_expenses is a stated assumption, not a Claim —
    the engine does not itself validate its sign. Pin down what actually
    happens if a negative value reaches it (e.g. a data-entry correction
    representing an expected refund/rebate), rather than assuming it's
    rejected."""

    def test_negative_estimate_reduces_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=-5000),
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == Money(amount=95000)

    def test_negative_estimate_can_drive_net_to_arrange_negative(self) -> None:
        """No floor is applied — net_to_arrange can go below zero if the
        caller supplies a large negative estimate. This test pins the
        current (unclamped) behaviour rather than asserting it's desired."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(1000))],
            estimated_additional_expenses=Money(amount=-5000),
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == Money(amount=-4000)


class TestLargeMagnitudeValues:
    """Costs at lakhs/crores scale (real-world Indian fee ranges run into
    lakhs; some professional-programme totals across years approach
    crores)."""

    def test_lakhs_scale_components_sum_correctly(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(12_50_000)),  # 12.5 lakh
            FeeComponent("Hostel", _verified(3_00_000)),  # 3 lakh
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=15_50_000)
        assert result.complete is True

    def test_crores_scale_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(1_00_00_000))],  # 1 crore
            estimated_additional_expenses=Money(amount=5_00_000),
            confirmed_assistance=[AssistanceItem("Merit scholarship", Money(amount=20_00_000))],
            potential_assistance=[AssistanceItem("Loan under review", Money(amount=50_00_000))],
        )
        assert summary.net_to_arrange == Money(amount=1_00_00_000 + 5_00_000 - 20_00_000)
        # potential assistance, however large, still never touches the net
        assert summary.potential_assistance_total == Money(amount=50_00_000)


class TestManyFeeComponents:
    """10+ fee components summed together — realistic for a professional
    programme with tuition, hostel, mess, exam, lab, library, sports,
    development fee, insurance, caution deposit, etc."""

    def test_eleven_components_sum_correctly(self) -> None:
        names_and_values = [
            ("Tuition", 50000),
            ("Hostel", 30000),
            ("Mess", 18000),
            ("Exam fee", 2000),
            ("Lab fee", 5000),
            ("Library fee", 1000),
            ("Sports fee", 1500),
            ("Development fee", 7000),
            ("Insurance", 800),
            ("Caution deposit", 10000),
            ("Miscellaneous", 3000),
        ]
        components = [FeeComponent(n, _verified(v)) for n, v in names_and_values]
        result = sum_verified_charges(components)
        assert len(components) == 11
        assert result.total == Money(amount=sum(v for _, v in names_and_values))
        assert result.complete is True

    def test_one_missing_among_many_still_gives_none_total(self) -> None:
        """Even with ten present components, a single missing one out of
        eleven must still null out the total — completeness is all-or-
        nothing, not "mostly complete"."""
        components = [
            FeeComponent(f"Fee {i}", _verified(1000 * i)) for i in range(1, 11)
        ]
        components.append(FeeComponent("Fee 11", _missing()))
        result = sum_verified_charges(components)
        assert result.total is None
        assert result.complete is False

    def test_one_stale_among_many_flags_stale_but_still_sums(self) -> None:
        components = [
            FeeComponent(f"Fee {i}", _verified(1000 * i)) for i in range(1, 11)
        ]
        components.append(FeeComponent("Fee 11", _stale(500)))
        result = sum_verified_charges(components)
        assert result.total == Money(amount=sum(1000 * i for i in range(1, 11)) + 500)
        assert result.complete is True
        assert result.stale is True


class TestDuplicateNamedItems:
    """Fee components and assistance items are keyed by content, not name
    uniqueness — the engine has no dedup logic. Pin down that duplicate
    names are summed as distinct line items, not collapsed or double-
    counted incorrectly."""

    def test_duplicate_named_fee_components_both_counted(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Tuition", _verified(50000)),
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=100000)
        assert len(result.components) == 2

    def test_duplicate_named_confirmed_assistance_items_both_summed(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=0),
            confirmed_assistance=[
                AssistanceItem("State scholarship", Money(amount=10000)),
                AssistanceItem("State scholarship", Money(amount=10000)),
            ],
            potential_assistance=[],
        )
        # Both instances count — this is not a "same scholarship twice"
        # dedup problem for the engine to solve; it sums what it's given.
        assert summary.confirmed_assistance_total == Money(amount=20000)
        assert summary.net_to_arrange == Money(amount=100000 - 20000)

    def test_duplicate_named_potential_assistance_items_both_summed_but_excluded(
        self,
    ) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=Money(amount=0),
            confirmed_assistance=[],
            potential_assistance=[
                AssistanceItem("Maybe scholarship", Money(amount=5000)),
                AssistanceItem("Maybe scholarship", Money(amount=5000)),
            ],
        )
        assert summary.potential_assistance_total == Money(amount=10000)
        assert summary.net_to_arrange == Money(amount=100000)


class TestToWholeRupees:
    """RULES-10: every amount this engine produces is a whole rupee
    `int`, never a `float`. `to_whole_rupees` is the one conversion
    point; pin down its rounding rule directly before trusting the
    higher-level engine functions that depend on it."""

    def test_int_passes_through_unchanged(self) -> None:
        assert to_whole_rupees(50000) == 50000

    def test_float_below_half_rounds_down(self) -> None:
        assert to_whole_rupees(50000.10) == 50000

    def test_float_above_half_rounds_up(self) -> None:
        assert to_whole_rupees(29999.90) == 30000

    def test_exact_half_uses_round_half_to_even_like_the_display_layer(self) -> None:
        """Same rule as `format(value, ".0f")` in app/i18n/formatting.py
        -- an exact `.5` resolves to the nearest EVEN integer, not always
        up, so a total computed here and the same figure rendered on
        screen never disagree at a rounding boundary."""
        assert to_whole_rupees(2.5) == 2
        assert to_whole_rupees(3.5) == 4

    def test_result_is_always_an_int(self) -> None:
        assert isinstance(to_whole_rupees(29999.5), int)
        assert isinstance(to_whole_rupees(50000), int)


class TestIntegerRupeeRounding:
    """RULES-10: cost arithmetic moved from float to whole-rupee `int`
    (now carried inside `Money.amount`). A component whose claim value
    still carries a paise-level fraction is rounded to the nearest
    rupee as it is summed (`to_whole_rupees`), so the total this engine
    returns is always exact whole rupees -- never a float carrying
    binary-imprecision artefacts."""

    def test_paise_level_components_round_before_summing(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000.10)),  # rounds to 50000
            FeeComponent("Hostel", _verified(29999.90)),  # rounds to 30000
            FeeComponent("Exam fee", _verified(1999.995)),  # rounds to 2000
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=82000)
        assert result.total is not None
        assert isinstance(result.total.amount, int)

    def test_fractional_rupee_summary_nets_to_exact_whole_rupees(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000.10)),
            FeeComponent("Hostel", _verified(29999.90)),
            FeeComponent("Exam fee", _verified(1999.995)),
        ]
        summary = compute_cost_summary(
            fee_components=components,
            estimated_additional_expenses=Money(amount=1000.005),  # type: ignore[arg-type]
            confirmed_assistance=[AssistanceItem("Scholarship", Money(amount=999.995))],  # type: ignore[arg-type]
            potential_assistance=[],
        )
        # 50000 + 30000 + 2000 = 82000 verified; +1000 estimate -1000 confirmed
        assert summary.net_to_arrange == Money(amount=82000)

    def test_int_and_float_components_mixed_sum_to_a_whole_rupee_int(self) -> None:
        """FeeComponent values may arrive as plain ints (e.g. round-rupee
        claims) alongside floats -- both must contribute correctly to
        the whole-rupee total, and an already-whole int is never
        perturbed by a float round-trip."""
        components = [
            FeeComponent("Tuition", _verified(50000)),  # int
            FeeComponent("Hostel", _verified(29999.5)),  # float, rounds to 30000 (half-to-even)
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=80000)

    def test_large_sum_with_paise_fraction_rounds_correctly_at_scale(self) -> None:
        """Large-magnitude (crore-scale) components with a paise-level
        fraction must round exactly, the same as a small one -- no float
        precision loss creeping in at scale."""
        components = [
            FeeComponent("Tuition", _verified(99_99_999.60)),  # rounds to 1,00,00,000
            FeeComponent("Hostel", _verified(5_00_000.40)),  # rounds to 5,00,000
        ]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=1_05_00_000)

    def test_many_sub_rupee_components_each_round_to_zero(self) -> None:
        """Ten 0.1-rupee components each individually round to 0 rupees
        before summing (RULES-10 rounds per component, not the final
        float sum) -- the old float-accumulation-error case this test
        used to pin down no longer applies once the arithmetic is
        integer throughout."""
        components = [FeeComponent(f"Fee {i}", _verified(0.1)) for i in range(10)]
        result = sum_verified_charges(components)
        assert result.total == Money(amount=0)
