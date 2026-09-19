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
