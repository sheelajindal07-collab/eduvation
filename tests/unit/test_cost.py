"""Tests for app/rules/cost.py.

The single most important property here: potential (unawarded)
assistance must NEVER reduce net_to_arrange. Every test class exists to
pin down one part of the four-amounts-never-merge guarantee.
"""

from datetime import date

from app.data.models import TrustLabel
from app.planning.comparison import FieldValue
from app.rules.cost import (
    AssistanceItem,
    FeeComponent,
    compute_cost_summary,
    sum_verified_charges,
    to_whole_rupees,
)

TODAY = date(2026, 9, 19)


def _verified(value: float) -> FieldValue:
    return FieldValue(
        value=value,
        label=TrustLabel.checked_against_official_source,
        source_url="https://example.invalid/source",
        verification_date=TODAY,
    )


def _stale(value: float) -> FieldValue:
    return FieldValue(
        value=value, label=TrustLabel.needs_rechecking, verification_date=TODAY
    )


def _missing() -> FieldValue:
    return FieldValue(value=None, label=TrustLabel.not_available)


class TestSumVerifiedCharges:
    def test_sums_all_present_components(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000)),
            FeeComponent("Hostel", _verified(30000)),
            FeeComponent("Exam fee", _verified(2000)),
        ]
        result = sum_verified_charges(components)
        assert result.total == 82000
        assert result.complete is True
        assert result.stale is False

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
        assert result.total == 80000
        assert result.complete is True
        assert result.stale is True


class TestCostSummaryFourAmountsNeverMerge:
    def test_confirmed_assistance_reduces_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=20000,
            confirmed_assistance=[AssistanceItem("State merit scholarship", 15000)],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == 100000 + 20000 - 15000

    def test_potential_assistance_never_reduces_net_to_arrange(self) -> None:
        """The core rule (Lite Build Pack §6): 'an unawarded scholarship
        is never subtracted'. This is the single test that matters most
        in this file."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=20000,
            confirmed_assistance=[],
            potential_assistance=[AssistanceItem("Maybe-eligible scholarship", 50000)],
        )
        assert summary.net_to_arrange == 100000 + 20000
        assert summary.potential_assistance_total == 50000
        # explicitly: the potential amount is visible for awareness...
        assert summary.potential_assistance[0].amount == 50000
        # ...but categorically absent from the arithmetic above.

    def test_both_confirmed_and_potential_present_stay_separate(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=10000,
            confirmed_assistance=[AssistanceItem("Awarded scholarship", 20000)],
            potential_assistance=[AssistanceItem("Applied, not yet decided", 30000)],
        )
        assert summary.confirmed_assistance_total == 20000
        assert summary.potential_assistance_total == 30000
        assert summary.net_to_arrange == 100000 + 10000 - 20000
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
            estimated_additional_expenses=10000,
            confirmed_assistance=[AssistanceItem("Some scholarship", 5000)],
            potential_assistance=[],
        )
        assert summary.verified_charges.total is None
        assert summary.net_to_arrange is None

    def test_multiple_confirmed_assistance_items_sum_correctly(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=0,
            confirmed_assistance=[
                AssistanceItem("Scholarship A", 10000),
                AssistanceItem("Scholarship B", 5000),
            ],
            potential_assistance=[],
        )
        assert summary.confirmed_assistance_total == 15000
        assert summary.net_to_arrange == 100000 - 15000

    def test_zero_cost_edge_case(self) -> None:
        """Boundary: a free programme with no assistance at all."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(0))],
            estimated_additional_expenses=0,
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == 0


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
            estimated_additional_expenses=15000,
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.estimated_additional_expenses == 15000
        assert summary.additional_expenses_override is None
        assert summary.effective_additional_expenses == 15000
        assert summary.net_to_arrange == 115000

    def test_override_is_visible_separately_and_still_wins_the_arithmetic(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=15000,
            confirmed_assistance=[],
            potential_assistance=[],
            additional_expenses_override=30000,
        )
        # Both lines stay visible, distinctly -- neither clobbers the other:
        assert summary.estimated_additional_expenses == 15000
        assert summary.additional_expenses_override == 30000
        # ...but the override is what net_to_arrange actually uses:
        assert summary.effective_additional_expenses == 30000
        assert summary.net_to_arrange == 130000

    def test_a_zero_override_is_distinct_from_no_override_at_all(self) -> None:
        """A student explicitly zeroing out the estimate ("I have no
        extra expenses") must not look identical to never having
        touched the field -- `None` and `0` are different facts."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=15000,
            confirmed_assistance=[],
            potential_assistance=[],
            additional_expenses_override=0,
        )
        assert summary.additional_expenses_override == 0
        assert summary.additional_expenses_override is not None
        assert summary.effective_additional_expenses == 0
        assert summary.net_to_arrange == 100000


class TestNegativeEstimatedAdditionalExpenses:
    """estimated_additional_expenses is a stated assumption, not a Claim —
    the engine does not itself validate its sign. Pin down what actually
    happens if a negative value reaches it (e.g. a data-entry correction
    representing an expected refund/rebate), rather than assuming it's
    rejected."""

    def test_negative_estimate_reduces_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=-5000,
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == 95000

    def test_negative_estimate_can_drive_net_to_arrange_negative(self) -> None:
        """No floor is applied — net_to_arrange can go below zero if the
        caller supplies a large negative estimate. This test pins the
        current (unclamped) behaviour rather than asserting it's desired."""
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(1000))],
            estimated_additional_expenses=-5000,
            confirmed_assistance=[],
            potential_assistance=[],
        )
        assert summary.net_to_arrange == -4000


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
        assert result.total == 15_50_000
        assert result.complete is True

    def test_crores_scale_net_to_arrange(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(1_00_00_000))],  # 1 crore
            estimated_additional_expenses=5_00_000,
            confirmed_assistance=[AssistanceItem("Merit scholarship", 20_00_000)],
            potential_assistance=[AssistanceItem("Loan under review", 50_00_000)],
        )
        assert summary.net_to_arrange == 1_00_00_000 + 5_00_000 - 20_00_000
        # potential assistance, however large, still never touches the net
        assert summary.potential_assistance_total == 50_00_000


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
        assert result.total == sum(v for _, v in names_and_values)
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
        assert result.total == sum(1000 * i for i in range(1, 11)) + 500
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
        assert result.total == 100000
        assert len(result.components) == 2

    def test_duplicate_named_confirmed_assistance_items_both_summed(self) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=0,
            confirmed_assistance=[
                AssistanceItem("State scholarship", 10000),
                AssistanceItem("State scholarship", 10000),
            ],
            potential_assistance=[],
        )
        # Both instances count — this is not a "same scholarship twice"
        # dedup problem for the engine to solve; it sums what it's given.
        assert summary.confirmed_assistance_total == 20000
        assert summary.net_to_arrange == 100000 - 20000

    def test_duplicate_named_potential_assistance_items_both_summed_but_excluded(
        self,
    ) -> None:
        summary = compute_cost_summary(
            fee_components=[FeeComponent("Tuition", _verified(100000))],
            estimated_additional_expenses=0,
            confirmed_assistance=[],
            potential_assistance=[
                AssistanceItem("Maybe scholarship", 5000),
                AssistanceItem("Maybe scholarship", 5000),
            ],
        )
        assert summary.potential_assistance_total == 10000
        assert summary.net_to_arrange == 100000


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
    """RULES-10: cost arithmetic moved from float to whole-rupee `int`.
    A component whose claim value still carries a paise-level fraction
    is rounded to the nearest rupee as it is summed (`to_whole_rupees`),
    so the total this engine returns is always exact whole rupees --
    never a float carrying binary-imprecision artefacts."""

    def test_paise_level_components_round_before_summing(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000.10)),  # rounds to 50000
            FeeComponent("Hostel", _verified(29999.90)),  # rounds to 30000
            FeeComponent("Exam fee", _verified(1999.995)),  # rounds to 2000
        ]
        result = sum_verified_charges(components)
        assert result.total == 82000
        assert isinstance(result.total, int)

    def test_fractional_rupee_summary_nets_to_exact_whole_rupees(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000.10)),
            FeeComponent("Hostel", _verified(29999.90)),
            FeeComponent("Exam fee", _verified(1999.995)),
        ]
        summary = compute_cost_summary(
            fee_components=components,
            estimated_additional_expenses=to_whole_rupees(1000.005),
            confirmed_assistance=[AssistanceItem("Scholarship", to_whole_rupees(999.995))],
            potential_assistance=[],
        )
        # 50000 + 30000 + 2000 = 82000 verified; +1000 estimate -1000 confirmed
        assert summary.net_to_arrange == 82000

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
        assert result.total == 80000
        assert isinstance(result.total, int)

    def test_large_sum_with_paise_fraction_rounds_correctly_at_scale(self) -> None:
        """Large-magnitude (crore-scale) components with a paise-level
        fraction must round exactly, the same as a small one -- no float
        precision loss creeping in at scale."""
        components = [
            FeeComponent("Tuition", _verified(99_99_999.60)),  # rounds to 1,00,00,000
            FeeComponent("Hostel", _verified(5_00_000.40)),  # rounds to 5,00,000
        ]
        result = sum_verified_charges(components)
        assert result.total == 1_05_00_000
        assert isinstance(result.total, int)

    def test_many_sub_rupee_components_each_round_to_zero(self) -> None:
        """Ten 0.1-rupee components each individually round to 0 rupees
        before summing (RULES-10 rounds per component, not the final
        float sum) -- the old float-accumulation-error case this test
        used to pin down no longer applies once the arithmetic is
        integer throughout."""
        components = [FeeComponent(f"Fee {i}", _verified(0.1)) for i in range(10)]
        result = sum_verified_charges(components)
        assert result.total == 0
        assert isinstance(result.total, int)
