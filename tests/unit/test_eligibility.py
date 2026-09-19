"""Tests for app/rules/eligibility.py.

The single most important property of this module: an unknown input is
NEVER a rejection. Every test class below exists to pin down one part of
that guarantee, including the combination/priority logic across several
criteria at once — which is exactly where a subtle bug would hide.
"""

from datetime import date

from app.data.models import EligibilityOutcome
from app.rules.eligibility import (
    EligibilityInput,
    domicile_in,
    evaluate_eligibility,
    maximum_age,
    minimum_age,
    minimum_marks_percentage,
    required_subjects,
)


class TestMinimumAge:
    def test_meets_when_above_minimum(self) -> None:
        criterion = minimum_age(17)
        result = criterion.check(EligibilityInput(age=18))
        assert result.outcome == EligibilityOutcome.meets

    def test_meets_at_exact_boundary(self) -> None:
        """Boundary case: exactly the minimum age must pass, not fail."""
        criterion = minimum_age(17)
        result = criterion.check(EligibilityInput(age=17))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_below_minimum(self) -> None:
        criterion = minimum_age(17)
        result = criterion.check(EligibilityInput(age=16))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "16" in result.explanation and "17" in result.explanation

    def test_insufficient_information_when_age_unknown(self) -> None:
        criterion = minimum_age(17)
        result = criterion.check(EligibilityInput(age=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestMaximumAge:
    def test_meets_at_exact_boundary(self) -> None:
        criterion = maximum_age(25)
        result = criterion.check(EligibilityInput(age=25))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_above_maximum(self) -> None:
        criterion = maximum_age(25)
        result = criterion.check(EligibilityInput(age=26))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_insufficient_information_when_age_unknown(self) -> None:
        criterion = maximum_age(25)
        result = criterion.check(EligibilityInput(age=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestMinimumMarksPercentage:
    def test_meets_at_exact_boundary(self) -> None:
        criterion = minimum_marks_percentage(50.0)
        result = criterion.check(EligibilityInput(marks_percentage=50.0))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_below_boundary(self) -> None:
        criterion = minimum_marks_percentage(50.0)
        result = criterion.check(EligibilityInput(marks_percentage=49.9))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_insufficient_information_when_unknown(self) -> None:
        criterion = minimum_marks_percentage(50.0)
        result = criterion.check(EligibilityInput(marks_percentage=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestRequiredSubjects:
    def test_meets_when_all_present(self) -> None:
        criterion = required_subjects(frozenset({"Physics", "Chemistry", "Maths"}))
        studied = frozenset({"Physics", "Chemistry", "Maths", "English"})
        result = criterion.check(EligibilityInput(subjects_studied=studied))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_when_one_missing(self) -> None:
        criterion = required_subjects(frozenset({"Physics", "Chemistry", "Maths"}))
        result = criterion.check(
            EligibilityInput(subjects_studied=frozenset({"Physics", "Chemistry"}))
        )
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "Maths" in result.explanation

    def test_insufficient_information_when_no_subjects_reported(self) -> None:
        """An empty subjects_studied set means 'we don't know', not
        'this student has no subjects' — must never read as a failure."""
        criterion = required_subjects(frozenset({"Physics"}))
        result = criterion.check(EligibilityInput(subjects_studied=frozenset()))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestDomicileIn:
    def test_meets_when_in_allowed_state(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="Gujarat"))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_when_outside_allowed_states(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="Maharashtra"))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_insufficient_information_when_domicile_unknown(self) -> None:
        """The exact case named in Build Pack §6: 'an unknown domicile
        rule ... never becomes a rejection'."""
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestEvaluateEligibilityPriority:
    """The combination logic across multiple criteria — this is where a
    real bug would most likely hide, so every ordering gets its own
    explicit test rather than relying on the individual-criterion tests
    above to imply the combined behaviour is correct."""

    def test_all_meet_gives_overall_meets(self) -> None:
        criteria = [minimum_age(17), minimum_marks_percentage(50.0)]
        result = evaluate_eligibility(
            criteria, EligibilityInput(age=18, marks_percentage=60.0)
        )
        assert result.outcome == EligibilityOutcome.meets
        assert result.failing == ()
        assert result.unknown == ()

    def test_one_unknown_rest_meet_gives_insufficient_information(self) -> None:
        criteria = [minimum_age(17), minimum_marks_percentage(50.0)]
        result = evaluate_eligibility(criteria, EligibilityInput(age=18, marks_percentage=None))
        assert result.outcome == EligibilityOutcome.insufficient_information
        assert len(result.unknown) == 1
        assert result.unknown[0].name == "minimum_marks_percentage"

    def test_one_failure_rest_meet_gives_does_not_meet(self) -> None:
        criteria = [minimum_age(17), minimum_marks_percentage(50.0)]
        result = evaluate_eligibility(criteria, EligibilityInput(age=15, marks_percentage=60.0))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert len(result.failing) == 1

    def test_failure_plus_unknown_gives_does_not_meet_not_unknown(self) -> None:
        """The critical priority-ordering case: a definite failure must
        win over an unrelated unknown — a real, known problem should
        never be hidden behind 'insufficient information'."""
        criteria = [
            minimum_age(17),
            minimum_marks_percentage(50.0),
            domicile_in(frozenset({"Gujarat"})),
        ]
        result = evaluate_eligibility(
            criteria,
            EligibilityInput(age=15, marks_percentage=None, domicile_state=None),
        )
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert len(result.failing) == 1
        assert result.failing[0].name == "minimum_age"
        # the two unknowns are still visible for explanation, just not
        # what determines the overall outcome:
        assert len(result.unknown) == 2

    def test_all_unknown_gives_insufficient_information(self) -> None:
        criteria = [minimum_age(17), minimum_marks_percentage(50.0)]
        result = evaluate_eligibility(criteria, EligibilityInput())
        assert result.outcome == EligibilityOutcome.insufficient_information
        assert len(result.unknown) == 2

    def test_empty_criteria_list_gives_meets(self) -> None:
        """Boundary case: no criteria to check at all — vacuously meets,
        not an error and not unknown."""
        result = evaluate_eligibility([], EligibilityInput())
        assert result.outcome == EligibilityOutcome.meets
        assert result.criteria == ()

    def test_criterion_results_carry_source_claim_id(self) -> None:
        criteria = [minimum_age(17, source_claim_id="claim-source-123")]
        result = evaluate_eligibility(criteria, EligibilityInput(age=10))
        assert result.criteria[0].source_claim_id == "claim-source-123"


class TestRealisticExamComposition:
    """A composed, exam-shaped rule set, as a per-exam rule definition
    (content track) would actually build one — not just isolated
    criteria in the classes above."""

    def _neet_ug_style_criteria(self) -> list:
        return [
            minimum_age(17, source_claim_id="src-neet-age"),
            maximum_age(25, source_claim_id="src-neet-age"),
            required_subjects(
                frozenset({"Physics", "Chemistry", "Biology"}), source_claim_id="src-neet-subjects"
            ),
            minimum_marks_percentage(50.0, source_claim_id="src-neet-marks"),
        ]

    def test_eligible_student(self) -> None:
        criteria = self._neet_ug_style_criteria()
        student = EligibilityInput(
            age=18,
            marks_percentage=72.0,
            subjects_studied=frozenset({"Physics", "Chemistry", "Biology", "English"}),
            as_of=date(2026, 9, 19),
        )
        result = evaluate_eligibility(criteria, student)
        assert result.outcome == EligibilityOutcome.meets

    def test_missing_one_required_subject_blocks(self) -> None:
        criteria = self._neet_ug_style_criteria()
        student = EligibilityInput(
            age=18,
            marks_percentage=72.0,
            subjects_studied=frozenset({"Physics", "Chemistry", "Maths"}),  # no Biology
        )
        result = evaluate_eligibility(criteria, student)
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert any(c.name == "required_subjects" for c in result.failing)

    def test_student_with_only_class_and_interests_gets_insufficient_information(self) -> None:
        """Matches the quick-start minimisation flow (docs/DATA.md): a
        brand-new student has given only class/interests/language, none
        of which feed eligibility — must be insufficient_information,
        never a silent rejection."""
        criteria = self._neet_ug_style_criteria()
        student = EligibilityInput()  # nothing filled in yet
        result = evaluate_eligibility(criteria, student)
        assert result.outcome == EligibilityOutcome.insufficient_information
