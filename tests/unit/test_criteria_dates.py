"""Tests for app/rules/criteria_dates.py (RULES-2).

The property under test throughout: a reference-date age check must give
the same answer a human counting years on a calendar would give,
including on the genuinely tricky calendar dates (29 February, the exact
cutoff day, the day either side of it) — and must never turn a missing
date of birth or a missing category into a rejection.
"""

from datetime import date

from app.data.models import EligibilityOutcome
from app.rules.criteria_dates import (
    age_on,
    born_between,
    maximum_age_on_date,
    minimum_age_on_date,
)
from app.rules.eligibility import EligibilityInput


class TestAgeOn:
    """Table tests for the pure `age_on` helper."""

    def test_birthday_already_passed_this_year(self) -> None:
        assert age_on(date(2008, 6, 15), date(2026, 9, 19)) == 18

    def test_birthday_later_this_year_not_yet_reached(self) -> None:
        assert age_on(date(2008, 12, 31), date(2026, 9, 19)) == 17

    def test_exact_birthday_counts_as_reached(self) -> None:
        assert age_on(date(2008, 9, 19), date(2026, 9, 19)) == 18

    def test_one_day_before_birthday(self) -> None:
        assert age_on(date(2008, 9, 19), date(2026, 9, 18)) == 17

    def test_one_day_after_birthday(self) -> None:
        assert age_on(date(2008, 9, 19), date(2026, 9, 20)) == 18

    def test_leap_day_dob_on_28_feb_non_leap_reference_year_not_yet_reached(self) -> None:
        """29 Feb 2008 (leap) -- on 28 Feb 2026 (not leap) the birthday
        has not yet occurred."""
        assert age_on(date(2008, 2, 29), date(2026, 2, 28)) == 17

    def test_leap_day_dob_on_1_march_non_leap_reference_year_reached(self) -> None:
        """The day after the 28th in a non-leap year is treated as the
        29-Feb birthday having been reached."""
        assert age_on(date(2008, 2, 29), date(2026, 3, 1)) == 18

    def test_leap_day_dob_on_leap_reference_year_exact_birthday(self) -> None:
        """When the reference year is itself a leap year, 29 Feb exists
        and is the exact boundary, same as any other birthday."""
        assert age_on(date(2008, 2, 29), date(2028, 2, 29)) == 20
        assert age_on(date(2008, 2, 29), date(2028, 2, 28)) == 19

    def test_born_same_day_as_reference_gives_zero(self) -> None:
        assert age_on(date(2026, 9, 19), date(2026, 9, 19)) == 0


class TestMinimumAgeOnDate:
    """The reference NEET-UG-shaped case: 17 as on 31 December of the
    exam year, not today's naive integer age."""

    CUTOFF = date(2027, 12, 31)

    def test_turns_17_well_before_cutoff_meets(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2010, 1, 1)))
        assert result.outcome == EligibilityOutcome.meets

    def test_16_year_old_today_who_turns_17_by_31_dec_meets(self) -> None:
        """The exact bug class this module exists to close: a student who
        is 16 by today's naive subtraction but will complete 17 years
        before the cutoff date must meet the criterion."""
        criterion = minimum_age_on_date(17, self.CUTOFF)
        # Born 15 Dec 2010: turns 17 on 15 Dec 2027, i.e. before the
        # 31 Dec 2027 cutoff -- but as of "today" (2026-09-19) this
        # student is only 15/16 by naive subtraction.
        result = criterion.check(EligibilityInput(date_of_birth=date(2010, 12, 15)))
        assert result.outcome == EligibilityOutcome.meets

    def test_exact_boundary_on_cutoff_day_meets(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2010, 12, 31)))
        assert result.outcome == EligibilityOutcome.meets

    def test_one_day_after_cutoff_birthday_does_not_meet(self) -> None:
        """Born 1 Jan 2011 -- turns 17 on 1 Jan 2028, one day after the
        31 Dec 2027 cutoff."""
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2011, 1, 1)))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_one_day_before_cutoff_still_meets(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2010, 12, 30)))
        assert result.outcome == EligibilityOutcome.meets

    def test_unknown_dob_gives_insufficient_information(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=None))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_leap_day_dob_on_leap_year_cutoff(self) -> None:
        """29 Feb 2008 dob against a leap-year cutoff of 29 Feb 2028 --
        exact boundary, must meet."""
        criterion = minimum_age_on_date(20, date(2028, 2, 29))
        result = criterion.check(EligibilityInput(date_of_birth=date(2008, 2, 29)))
        assert result.outcome == EligibilityOutcome.meets

    def test_leap_day_dob_against_non_leap_year_cutoff(self) -> None:
        """29 Feb 2008 dob against a non-leap cutoff of 28 Feb 2026: the
        birthday has not yet occurred that year, so the student is still
        17, not 18."""
        criterion = minimum_age_on_date(18, date(2026, 2, 28))
        result = criterion.check(EligibilityInput(date_of_birth=date(2008, 2, 29)))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_relaxation_lets_younger_student_in_reserved_category_meet(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF, relaxation_years={"SC": 2})
        # Turns 15 by the cutoff -- fails the general 17, but 15 >= 17-2.
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2012, 12, 1), category="SC")
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_relaxation_does_not_help_a_category_without_one(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF, relaxation_years={"SC": 2})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2012, 12, 1), category="General")
        )
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_unknown_category_with_relaxation_and_failing_rule_is_unknown(self) -> None:
        """The named RULES-2 acceptance case: an unknown category, when
        relaxations exist and the general rule fails, must not be a
        rejection."""
        criterion = minimum_age_on_date(17, self.CUTOFF, relaxation_years={"SC": 2})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2012, 12, 1), category=None)
        )
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_unknown_category_is_irrelevant_when_general_rule_already_meets(self) -> None:
        """A category lookup is only needed when the general check fails
        -- a student who already clears the unrelaxed minimum must not be
        asked for a category they don't need."""
        criterion = minimum_age_on_date(17, self.CUTOFF, relaxation_years={"SC": 2})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2005, 1, 1), category=None)
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_no_relaxation_table_never_asks_for_category(self) -> None:
        criterion = minimum_age_on_date(17, self.CUTOFF)
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2020, 1, 1), category=None)
        )
        assert result.outcome == EligibilityOutcome.does_not_meet


class TestMaximumAgeOnDate:
    CUTOFF = date(2027, 12, 31)

    def test_within_limit_meets(self) -> None:
        criterion = maximum_age_on_date(25, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2005, 1, 1)))
        assert result.outcome == EligibilityOutcome.meets

    def test_exact_boundary_meets(self) -> None:
        criterion = maximum_age_on_date(25, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2002, 12, 31)))
        assert result.outcome == EligibilityOutcome.meets

    def test_just_over_boundary_does_not_meet(self) -> None:
        """One year older than the exact-boundary case above -- already
        26 (not 25) as on the cutoff date."""
        criterion = maximum_age_on_date(25, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=date(2001, 12, 31)))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_unknown_dob_gives_insufficient_information(self) -> None:
        criterion = maximum_age_on_date(25, self.CUTOFF)
        result = criterion.check(EligibilityInput(date_of_birth=None))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_relaxation_raises_the_ceiling_for_named_category(self) -> None:
        criterion = maximum_age_on_date(25, self.CUTOFF, relaxation_years={"OBC": 3})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2000, 6, 1), category="OBC")
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_unknown_category_with_relaxation_and_failing_rule_is_unknown(self) -> None:
        criterion = maximum_age_on_date(25, self.CUTOFF, relaxation_years={"OBC": 3})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2000, 6, 1), category=None)
        )
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestBornBetween:
    EARLIEST = date(2005, 1, 1)
    LATEST = date(2011, 12, 31)

    def test_within_window_meets(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=date(2008, 6, 1)))
        assert result.outcome == EligibilityOutcome.meets

    def test_exact_earliest_boundary_meets(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=self.EARLIEST))
        assert result.outcome == EligibilityOutcome.meets

    def test_exact_latest_boundary_meets(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=self.LATEST))
        assert result.outcome == EligibilityOutcome.meets

    def test_one_day_before_earliest_does_not_meet(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=date(2004, 12, 31)))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_one_day_after_latest_does_not_meet(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=date(2012, 1, 1)))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_unknown_dob_gives_insufficient_information(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST)
        result = criterion.check(EligibilityInput(date_of_birth=None))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_relaxation_widens_earliest_bound_for_named_category(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST, relaxation_years={"ST": 3})
        # 1 day before the general earliest bound, but within 3 years of it.
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2004, 12, 31), category="ST")
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_relaxation_never_applies_on_the_latest_side(self) -> None:
        """A dob after `latest` is never rescued by a relaxation -- only
        the earliest bound relaxes."""
        criterion = born_between(self.EARLIEST, self.LATEST, relaxation_years={"ST": 3})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2012, 1, 1), category="ST")
        )
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_unknown_category_with_relaxation_and_failing_window_is_unknown(self) -> None:
        criterion = born_between(self.EARLIEST, self.LATEST, relaxation_years={"ST": 3})
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2004, 12, 31), category=None)
        )
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_leap_day_earliest_bound_relaxed_into_non_leap_year_falls_back_to_28_feb(self) -> None:
        """`_shift_years` must not raise when a 29-Feb `earliest` bound is
        shifted into a non-leap target year."""
        criterion = born_between(
            date(2008, 2, 29), date(2011, 12, 31), relaxation_years={"ST": 1}
        )
        # Shifting 2008-02-29 back 1 year lands on 2007, not a leap year
        # -> falls back to 2007-02-28.
        result = criterion.check(
            EligibilityInput(date_of_birth=date(2007, 2, 28), category="ST")
        )
        assert result.outcome == EligibilityOutcome.meets
