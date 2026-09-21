"""Tests for app/rules/eligibility.py.

The single most important property of this module: an unknown input is
NEVER a rejection. Every test class below exists to pin down one part of
that guarantee, including the combination/priority logic across several
criteria at once — which is exactly where a subtle bug would hide.
"""

from datetime import date

from app.data.jurisdictions import resolve_jurisdiction
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

    def test_meets_is_case_insensitive(self) -> None:
        """domicile_state is a bare text input (app/web/templates/
        requirements.html), so a plausible capitalisation mismatch
        ('delhi' vs the published 'Delhi') must not silently produce a
        hard does_not_meet."""
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="gujarat"))
        assert result.outcome == EligibilityOutcome.meets

    def test_meets_ignores_surrounding_whitespace(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="  Gujarat  "))
        assert result.outcome == EligibilityOutcome.meets

    def test_allowed_state_list_itself_is_matched_case_insensitively(self) -> None:
        """The normalisation applies to both sides -- a published state
        list authored in an unexpected case must still match the
        student's differently-cased answer."""
        criterion = domicile_in(frozenset({"GUJARAT"}))
        result = criterion.check(EligibilityInput(domicile_state="Gujarat"))
        assert result.outcome == EligibilityOutcome.meets

    def test_explanation_shows_original_casing_not_normalised_form(self) -> None:
        """The normalisation is comparison-only -- display text still
        shows what was actually published/entered."""
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="Maharashtra"))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "Gujarat" in result.explanation
        assert "Maharashtra" in result.explanation


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


class TestDomicileMultipleStates:
    """`domicile_in` allows a whole set of states at once (e.g. a quota
    open to several states) — distinct from the single-state cases above,
    which only ever exercised a one-element `allowed_states`."""

    def test_meets_when_matching_any_of_several_allowed_states(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat", "Maharashtra", "Rajasthan"}))
        result = criterion.check(EligibilityInput(domicile_state="Rajasthan"))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_when_outside_several_allowed_states(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat", "Maharashtra", "Rajasthan"}))
        result = criterion.check(EligibilityInput(domicile_state="Kerala"))
        assert result.outcome == EligibilityOutcome.does_not_meet
        # every allowed state should be named so the student knows the
        # full set they could have matched, not just one of them
        assert "Gujarat" in result.explanation
        assert "Maharashtra" in result.explanation
        assert "Rajasthan" in result.explanation

    def test_insufficient_information_still_wins_with_many_allowed_states(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat", "Maharashtra", "Rajasthan", "Kerala"}))
        result = criterion.check(EligibilityInput(domicile_state=None))
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestDuplicateNamedCriteria:
    """Nothing in `evaluate_eligibility` deduplicates by `Criterion.name`
    — two criteria that happen to share a name (e.g. two differently
    configured `minimum_marks_percentage` checks composed by mistake, or
    on purpose for two separate thresholds) must both run and both be
    reported, not merged or dropped."""

    def test_both_duplicate_named_criteria_are_evaluated_independently(self) -> None:
        criteria = [
            minimum_marks_percentage(50.0, source_claim_id="claim-a"),
            minimum_marks_percentage(60.0, source_claim_id="claim-b"),
        ]
        result = evaluate_eligibility(criteria, EligibilityInput(marks_percentage=55.0))
        # both have the same .name, but the engine must still run both:
        assert len(result.criteria) == 2
        assert all(c.name == "minimum_marks_percentage" for c in result.criteria)
        assert result.criteria[0].source_claim_id == "claim-a"
        assert result.criteria[1].source_claim_id == "claim-b"
        # 55% clears the 50% duplicate but fails the 60% duplicate —
        # overall must reflect the real failure, not be masked because
        # a same-named criterion elsewhere passed
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert len(result.failing) == 1
        assert result.failing[0].source_claim_id == "claim-b"

    def test_duplicate_named_criteria_both_unknown_are_both_reported(self) -> None:
        criteria = [
            domicile_in(frozenset({"Gujarat"}), source_claim_id="claim-x"),
            domicile_in(frozenset({"Maharashtra"}), source_claim_id="claim-y"),
        ]
        result = evaluate_eligibility(criteria, EligibilityInput(domicile_state=None))
        assert len(result.criteria) == 2
        assert len(result.unknown) == 2
        assert result.outcome == EligibilityOutcome.insufficient_information


class TestLargeCriteriaList:
    """A criteria list well beyond any real exam's shape (10+) — pins down
    that the combination logic scales by content, not by some assumed
    small fixed size, and that ordering/priority still holds at scale."""

    def test_large_all_meeting_list_gives_meets(self) -> None:
        criteria = [minimum_marks_percentage(10.0 + i) for i in range(15)]
        result = evaluate_eligibility(criteria, EligibilityInput(marks_percentage=99.0))
        assert len(result.criteria) == 15
        assert result.outcome == EligibilityOutcome.meets

    def test_large_list_with_one_failure_among_many_meets_and_unknowns(self) -> None:
        # 12 criteria that meet, 1 that fails, 5 that are unknown (age
        # unset) — the single failure must still win overall.
        criteria = (
            [minimum_marks_percentage(10.0 + i) for i in range(12)]
            + [minimum_marks_percentage(999.0)]  # impossible to meet -> fails
            + [minimum_age(10 + i) for i in range(5)]  # age unset -> unknown
        )
        result = evaluate_eligibility(criteria, EligibilityInput(marks_percentage=80.0))
        assert len(result.criteria) == 18
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert len(result.failing) == 1
        assert len(result.unknown) == 5

    def test_large_list_all_unknown_gives_insufficient_information(self) -> None:
        criteria = [minimum_age(15 + i) for i in range(10)] + [
            minimum_marks_percentage(40.0 + i) for i in range(5)
        ]
        result = evaluate_eligibility(criteria, EligibilityInput())
        assert len(result.criteria) == 15
        assert result.outcome == EligibilityOutcome.insufficient_information
        assert len(result.unknown) == 15


class TestUnicodeSubjectNames:
    """Subject names are free-text strings pulled from real curricula —
    Indian-language and accented subject names must compare correctly,
    not be mangled by naive ASCII assumptions."""

    def test_meets_with_devanagari_subject_names(self) -> None:
        required = frozenset({"गणित", "विज्ञान"})  # Maths, Science
        criterion = required_subjects(required)
        studied = frozenset({"गणित", "विज्ञान", "अंग्रेज़ी"})  # + English
        result = criterion.check(EligibilityInput(subjects_studied=studied))
        assert result.outcome == EligibilityOutcome.meets

    def test_does_not_meet_reports_missing_unicode_subject_by_name(self) -> None:
        required = frozenset({"गणित", "विज्ञान"})
        criterion = required_subjects(required)
        result = criterion.check(EligibilityInput(subjects_studied=frozenset({"गणित"})))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "विज्ञान" in result.explanation

    def test_accented_subject_name_is_not_confused_with_unaccented(self) -> None:
        """'Français' and 'Francais' must be treated as different strings
        — no implicit normalisation collapses them, so a student who
        studied one is not silently credited for the other."""
        criterion = required_subjects(frozenset({"Français"}))
        result = criterion.check(EligibilityInput(subjects_studied=frozenset({"Francais"})))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert "Français" in result.explanation

    def test_domicile_state_with_unicode_name_meets(self) -> None:
        criterion = domicile_in(frozenset({"पश्चिम बंगाल"}))  # West Bengal
        result = criterion.check(EligibilityInput(domicile_state="पश्चिम बंगाल"))
        assert result.outcome == EligibilityOutcome.meets


class TestFullyPopulatedStudentInput:
    """Every `EligibilityInput` field populated simultaneously — the
    realistic 'complete profile' case, as opposed to the sparse/partial
    inputs every other test class exercises."""

    def _fully_populated_student(self) -> EligibilityInput:
        return EligibilityInput(
            age=18,
            marks_percentage=87.5,
            subjects_studied=frozenset({"Physics", "Chemistry", "Biology", "English", "Maths"}),
            domicile_state="Gujarat",
            category="General",
            as_of=date(2026, 9, 19),
        )

    def test_all_fields_populated_and_meeting_gives_meets(self) -> None:
        criteria = [
            minimum_age(17, source_claim_id="src-age"),
            maximum_age(25, source_claim_id="src-age"),
            minimum_marks_percentage(50.0, source_claim_id="src-marks"),
            required_subjects(
                frozenset({"Physics", "Chemistry", "Biology"}), source_claim_id="src-subjects"
            ),
            domicile_in(frozenset({"Gujarat"}), source_claim_id="src-domicile"),
        ]
        result = evaluate_eligibility(criteria, self._fully_populated_student())
        assert result.outcome == EligibilityOutcome.meets
        assert result.failing == ()
        assert result.unknown == ()
        assert len(result.criteria) == 5

    def test_all_fields_populated_but_one_criterion_fails(self) -> None:
        """Every field is known (nothing unknown anywhere) — a single
        failing criterion (wrong domicile) must still drive the overall
        outcome to does_not_meet, not be swallowed by everything else
        being fully populated and otherwise passing."""
        criteria = [
            minimum_age(17),
            maximum_age(25),
            minimum_marks_percentage(50.0),
            required_subjects(frozenset({"Physics", "Chemistry", "Biology"})),
            domicile_in(frozenset({"Maharashtra"})),  # student is Gujarat -> fails
        ]
        result = evaluate_eligibility(criteria, self._fully_populated_student())
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert len(result.failing) == 1
        assert result.failing[0].name == "domicile_in"
        assert result.unknown == ()


class TestResolveJurisdiction:
    """SCOPE-5: app.data.jurisdictions.resolve_jurisdiction — the
    canonical-code lookup domicile_in below is built on."""

    def test_delhi_resolves_to_in_dl(self) -> None:
        assert resolve_jurisdiction("Delhi") == "IN-DL"

    def test_nct_of_delhi_alias_resolves_to_in_dl(self) -> None:
        """The exact acceptance case named in SCOPE-5's task card."""
        assert resolve_jurisdiction("NCT of Delhi") == "IN-DL"

    def test_unknown_state_does_not_resolve(self) -> None:
        assert resolve_jurisdiction("Narnia") is None

    def test_code_lookup_is_case_insensitive(self) -> None:
        assert resolve_jurisdiction("in-gj") == "IN-GJ"

    def test_pilot_country_resolves(self) -> None:
        assert resolve_jurisdiction("Singapore") == "SG"

    def test_country_alias_resolves(self) -> None:
        assert resolve_jurisdiction("UAE") == "AE"
        assert resolve_jurisdiction("UK") == "GB"

    def test_none_input_does_not_resolve(self) -> None:
        assert resolve_jurisdiction(None) is None

    def test_blank_input_does_not_resolve(self) -> None:
        assert resolve_jurisdiction("   ") is None


class TestDomicileInJurisdictionResolution:
    """SCOPE-5: domicile_in accepts a claim's/student's state or country
    given as a code or a known alias, not just an identical literal
    string -- and an input that resolves to NO known jurisdiction at all
    is insufficient_information, never a guessed does_not_meet."""

    def test_unrecognised_domicile_gives_insufficient_information_not_rejection(
        self,
    ) -> None:
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="Narnia"))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_alias_nct_of_delhi_matches_a_published_delhi(self) -> None:
        criterion = domicile_in(frozenset({"Delhi"}))
        result = criterion.check(EligibilityInput(domicile_state="NCT of Delhi"))
        assert result.outcome == EligibilityOutcome.meets

    def test_code_input_matches_a_published_state_name(self) -> None:
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="IN-GJ"))
        assert result.outcome == EligibilityOutcome.meets

    def test_recognised_state_outside_allowed_set_still_does_not_meet(self) -> None:
        """A recognised-but-wrong domicile is a real, known mismatch --
        still does_not_meet, not swallowed into insufficient_information
        just because the resolution path is now involved."""
        criterion = domicile_in(frozenset({"Gujarat"}))
        result = criterion.check(EligibilityInput(domicile_state="IN-MH"))
        assert result.outcome == EligibilityOutcome.does_not_meet

    def test_pilot_country_code_matches_a_published_country_name(self) -> None:
        criterion = domicile_in(frozenset({"Singapore"}))
        result = criterion.check(EligibilityInput(domicile_state="SG"))
        assert result.outcome == EligibilityOutcome.meets
