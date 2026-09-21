"""Tests for app/rules/criteria_extra.py (RULES-3).

Same non-negotiable as every other rules-engine test module: an unknown
input is never a rejection. Also pins down the two named engine gaps in
docs/content-drafts/neet-ug-eligibility.md (fact 3, any-of subjects) and
docs/content-drafts/jee-main-eligibility.md (section 3, year-of-passing
window) that `required_subjects`/plain integer criteria cannot express.
"""

from app.data.models import EligibilityOutcome
from app.rules.criteria_extra import (
    NotChecked,
    minimum_marks_by_category,
    minimum_qualification_level,
    passed_or_appearing_in_years,
    subject_groups,
)
from app.rules.eligibility import EligibilityInput


class TestSubjectGroups:
    """The Biology-or-Biotechnology case named in RULES-3's acceptance
    criteria."""

    def _neet_style_groups(self) -> list[frozenset[str]]:
        return [
            frozenset({"Physics"}),
            frozenset({"Chemistry"}),
            frozenset({"Biology", "Biotechnology"}),
        ]

    def test_meets_with_biology(self) -> None:
        criterion = subject_groups(self._neet_style_groups())
        result = criterion.check(
            EligibilityInput(subjects_studied=frozenset({"Physics", "Chemistry", "Biology"}))
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_meets_with_biotechnology_instead_of_biology(self) -> None:
        """The exact bug `required_subjects` (all-of only) cannot avoid:
        a Biotechnology student must not be told they're missing
        Biology."""
        criterion = subject_groups(self._neet_style_groups())
        result = criterion.check(
            EligibilityInput(
                subjects_studied=frozenset({"Physics", "Chemistry", "Biotechnology"})
            )
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_fails_with_neither_biology_nor_biotechnology(self) -> None:
        criterion = subject_groups(self._neet_style_groups())
        result = criterion.check(
            EligibilityInput(subjects_studied=frozenset({"Physics", "Chemistry", "Maths"}))
        )
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "Biology" in result.explanation and "Biotechnology" in result.explanation

    def test_fails_missing_a_single_subject_group(self) -> None:
        criterion = subject_groups(self._neet_style_groups())
        result = criterion.check(
            EligibilityInput(subjects_studied=frozenset({"Chemistry", "Biology"}))
        )
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "Physics" in result.explanation

    def test_unknown_with_empty_subjects(self) -> None:
        criterion = subject_groups(self._neet_style_groups())
        result = criterion.check(EligibilityInput(subjects_studied=frozenset()))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_single_subject_group_behaves_like_a_plain_requirement(self) -> None:
        criterion = subject_groups([frozenset({"English"})])
        meets = criterion.check(EligibilityInput(subjects_studied=frozenset({"English"})))
        fails = criterion.check(EligibilityInput(subjects_studied=frozenset({"Hindi"})))
        assert meets.outcome == EligibilityOutcome.meets
        assert fails.outcome == EligibilityOutcome.does_not_meet


class TestMinimumMarksByCategory:
    THRESHOLDS = {"General": 50.0, "SC": 40.0, "ST": 40.0}

    def test_meets_general_threshold(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=55.0, category="General"))
        assert result.outcome == EligibilityOutcome.meets

    def test_fails_general_threshold(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=45.0, category="General"))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_meets_lower_reserved_category_threshold(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=42.0, category="SC"))
        assert result.outcome == EligibilityOutcome.meets

    def test_unknown_marks_gives_insufficient_information(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=None, category="General"))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_unknown_category_never_rejects_when_marks_below_ceiling(self) -> None:
        """The named RULES-3 acceptance case: unknown category never
        rejects."""
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=45.0, category=None))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_unknown_category_still_meets_when_marks_clear_every_threshold(self) -> None:
        """55% clears even the strictest (General, 50%) threshold, so no
        category could have made this student fail -- a confident `meets`
        without ever knowing the category."""
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=55.0, category=None))
        assert result.outcome == EligibilityOutcome.meets

    def test_known_category_not_in_thresholds_falls_back_to_default(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS, default=45.0)
        result = criterion.check(EligibilityInput(marks_percentage=46.0, category="OBC"))
        assert result.outcome == EligibilityOutcome.meets

    def test_known_category_not_in_thresholds_and_no_default_is_unknown(self) -> None:
        criterion = minimum_marks_by_category(self.THRESHOLDS)
        result = criterion.check(EligibilityInput(marks_percentage=42.0, category="OBC"))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestPassedOrAppearingInYears:
    ELIGIBLE_YEARS = frozenset({2024, 2025})

    def test_meets_when_passed_in_eligible_year(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(year_of_passing=2024, appearing=False))
        assert result.outcome == EligibilityOutcome.meets

    def test_boundary_earliest_eligible_year_meets(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(year_of_passing=2024))
        assert result.outcome == EligibilityOutcome.meets

    def test_boundary_latest_eligible_year_meets(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(year_of_passing=2025))
        assert result.outcome == EligibilityOutcome.meets

    def test_one_year_before_window_fails(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(year_of_passing=2023, appearing=False))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_one_year_after_window_fails(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(year_of_passing=2026, appearing=False))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_currently_appearing_meets_when_allowed(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS, allow_appearing=True)
        result = criterion.check(EligibilityInput(appearing=True))
        assert result.outcome == EligibilityOutcome.meets

    def test_currently_appearing_fails_when_not_allowed(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS, allow_appearing=False)
        result = criterion.check(EligibilityInput(appearing=True))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_neither_field_known_gives_insufficient_information(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput())
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_not_appearing_and_no_year_gives_insufficient_information(self) -> None:
        criterion = passed_or_appearing_in_years(self.ELIGIBLE_YEARS)
        result = criterion.check(EligibilityInput(appearing=False, year_of_passing=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestMinimumQualificationLevel:
    LEVELS = ("Class 10", "Class 12", "Diploma", "Bachelor's")

    def test_meets_exact_level(self) -> None:
        criterion = minimum_qualification_level("Class 12", level_order=self.LEVELS)
        result = criterion.check(EligibilityInput(qualification_level="Class 12"))
        assert result.outcome == EligibilityOutcome.meets

    def test_meets_higher_level(self) -> None:
        criterion = minimum_qualification_level("Class 12", level_order=self.LEVELS)
        result = criterion.check(EligibilityInput(qualification_level="Bachelor's"))
        assert result.outcome == EligibilityOutcome.meets

    def test_fails_lower_level(self) -> None:
        criterion = minimum_qualification_level("Class 12", level_order=self.LEVELS)
        result = criterion.check(EligibilityInput(qualification_level="Class 10"))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_unset_level_gives_insufficient_information(self) -> None:
        criterion = minimum_qualification_level("Class 12", level_order=self.LEVELS)
        result = criterion.check(EligibilityInput(qualification_level=None))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_unrecognised_level_gives_insufficient_information_not_a_guess(self) -> None:
        criterion = minimum_qualification_level("Class 12", level_order=self.LEVELS)
        result = criterion.check(EligibilityInput(qualification_level="Some Foreign Cert"))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_min_level_not_in_level_order_raises_at_construction(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="not in level_order"):
            minimum_qualification_level("PhD", level_order=self.LEVELS)


class TestNotChecked:
    def test_default_note_is_set(self) -> None:
        declaration = NotChecked(name="Medical fitness")
        assert declaration.name == "Medical fitness"
        assert "not checked" in declaration.note.lower()

    def test_custom_note_overrides_default(self) -> None:
        declaration = NotChecked(name="Marital status", note="Never collected by Lite.")
        assert declaration.note == "Never collected by Lite."

    def test_is_not_a_criterion(self) -> None:
        """NotChecked is plain metadata -- it has no `.check` and never
        runs against student input."""
        declaration = NotChecked(name="Gender")
        assert not hasattr(declaration, "check")
