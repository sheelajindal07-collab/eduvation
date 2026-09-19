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


class TestFloatingPointPrecision:
    """Repeated fractional sums (e.g. paise-level fee components) can
    accumulate binary floating-point error. Pin down the actual precision
    the engine delivers rather than assuming exactness."""

    def test_many_fractional_components_sum_within_tolerance(self) -> None:
        # 0.1 repeated 10 times is the textbook float-imprecision case:
        # naive summation gives 0.9999999999999999, not exactly 1.0.
        components = [FeeComponent(f"Fee {i}", _verified(0.1)) for i in range(10)]
        result = sum_verified_charges(components)
        assert result.total is not None
        assert abs(result.total - 1.0) < 1e-9
        # Document the actual float behaviour precisely: naive
        # left-to-right accumulation of ten 0.1s lands one ULP short of
        # 1.0, not exactly 1.0.
        assert result.total == 0.9999999999999999
        assert result.total != 1.0

    def test_fractional_rupee_components_sum_and_net_within_tolerance(self) -> None:
        components = [
            FeeComponent("Tuition", _verified(50000.10)),
            FeeComponent("Hostel", _verified(29999.90)),
            FeeComponent("Exam fee", _verified(1999.995)),
        ]
        summary = compute_cost_summary(
            fee_components=components,
            estimated_additional_expenses=1000.005,
            confirmed_assistance=[AssistanceItem("Scholarship", 999.995)],
            potential_assistance=[],
        )
        assert summary.net_to_arrange is not None
        expected = 50000.10 + 29999.90 + 1999.995 + 1000.005 - 999.995
        assert abs(summary.net_to_arrange - expected) < 1e-6

    def test_int_and_float_components_mixed_sum_correctly(self) -> None:
        """FeeComponent values may arrive as plain ints (e.g. round-rupee
        claims) alongside floats — both must contribute correctly to the
        float total."""
        components = [
            FeeComponent("Tuition", _verified(50000)),  # int
            FeeComponent("Hostel", _verified(29999.5)),  # float
        ]
        result = sum_verified_charges(components)
        assert result.total == 79999.5
        assert isinstance(result.total, float)
