"""Tests for app/rules/ruleset.py (RULES-4).

Every test class pins down one of this module's stated safety
guarantees: an empty rule set never reports a bare `meets`, a result
always carries its identity, a stale cycle downgrades a confident
`meets`, duplicate registrations are rejected outright, and an
unreviewed module is invisible in a production-mode registry.
"""

from datetime import date

import pytest

from app.data.models import EligibilityOutcome
from app.rules.criteria_extra import NotChecked
from app.rules.eligibility import EligibilityInput, minimum_age
from app.rules.ruleset import (
    DuplicateRuleSetError,
    RuleSet,
    discover_exam_modules,
    discover_rule_sets,
    evaluate_for_exam,
    evaluate_ruleset,
    get_rule_set,
    register_rule_sets,
)

FAKE_EXAMS_PACKAGE = "tests.fixtures.fake_exams"


def _rule_set(
    *,
    exam_key: str = "fake_exam",
    cycle: str = "2027",
    cycle_end: date = date(2027, 12, 31),
    jurisdiction: str = "IN",
    rule_version: str = "v1",
    criteria: tuple = (),
    reviewed_by: str | None = None,
    reviewed_on: date | None = None,
    not_checked: tuple = (),
) -> RuleSet:
    return RuleSet(
        exam_key=exam_key,
        cycle=cycle,
        cycle_end=cycle_end,
        jurisdiction=jurisdiction,
        rule_version=rule_version,
        criteria=criteria,
        reviewed_by=reviewed_by,
        reviewed_on=reviewed_on,
        not_checked=not_checked,
    )


class TestRuleSetIsReviewed:
    def test_both_unset_is_not_reviewed(self) -> None:
        assert _rule_set().is_reviewed is False

    def test_only_reviewed_by_set_is_not_reviewed(self) -> None:
        assert _rule_set(reviewed_by="a@example.org").is_reviewed is False

    def test_only_reviewed_on_set_is_not_reviewed(self) -> None:
        assert _rule_set(reviewed_on=date(2026, 1, 1)).is_reviewed is False

    def test_both_set_is_reviewed(self) -> None:
        rule_set = _rule_set(reviewed_by="a@example.org", reviewed_on=date(2026, 1, 1))
        assert rule_set.is_reviewed is True


class TestEvaluateRulesetEmptyCriteria:
    """The single most important property of this module: an exam with
    no registered criteria must never look like a verified 'meets'."""

    def test_empty_criteria_sets_no_verified_rules_and_insufficient_information(self) -> None:
        rule_set = _rule_set(criteria=())
        result = evaluate_ruleset(rule_set, EligibilityInput(), as_of=date(2026, 9, 19))
        assert result.no_verified_rules is True
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_empty_criteria_still_carries_full_identity(self) -> None:
        rule_set = _rule_set(
            exam_key="some_exam", cycle="2027", jurisdiction="GJ", rule_version="v3"
        )
        result = evaluate_ruleset(rule_set, EligibilityInput(), as_of=date(2026, 9, 19))
        assert result.exam_key == "some_exam"
        assert result.cycle == "2027"
        assert result.jurisdiction == "GJ"
        assert result.rule_version == "v3"


class TestEvaluateRulesetResultAlwaysCarriesIdentity:
    def test_non_empty_criteria_result_carries_version_cycle_jurisdiction(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2026, 9, 19))
        assert result.exam_key == rule_set.exam_key
        assert result.cycle == rule_set.cycle
        assert result.jurisdiction == rule_set.jurisdiction
        assert result.rule_version == rule_set.rule_version
        assert result.outcome == EligibilityOutcome.meets

    def test_not_checked_declarations_pass_through(self) -> None:
        declarations = (NotChecked(name="Medical fitness"),)
        rule_set = _rule_set(criteria=(minimum_age(18),), not_checked=declarations)
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2026, 9, 19))
        assert result.not_checked == declarations


class TestCycleStale:
    def test_as_of_before_cycle_end_is_not_stale(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),), cycle_end=date(2027, 12, 31))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2026, 9, 19))
        assert result.cycle_stale is False

    def test_as_of_on_cycle_end_is_not_stale(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),), cycle_end=date(2027, 12, 31))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2027, 12, 31))
        assert result.cycle_stale is False

    def test_as_of_past_cycle_end_sets_cycle_stale(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),), cycle_end=date(2027, 12, 31))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2028, 1, 1))
        assert result.cycle_stale is True

    def test_stale_cycle_downgrades_meets_to_insufficient_information(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),), cycle_end=date(2027, 12, 31))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=20), as_of=date(2028, 1, 1))
        assert result.outcome == EligibilityOutcome.insufficient_information

    def test_stale_cycle_does_not_hide_a_real_does_not_meet(self) -> None:
        """A definite failure found under a stale cycle's rules is still
        true information -- it must not be masked by the staleness
        downgrade meant only to protect a confident-looking `meets`."""
        rule_set = _rule_set(criteria=(minimum_age(18),), cycle_end=date(2027, 12, 31))
        result = evaluate_ruleset(rule_set, EligibilityInput(age=10), as_of=date(2028, 1, 1))
        assert result.outcome == EligibilityOutcome.does_not_meet
        assert result.cycle_stale is True

    def test_evidence_stale_flag_also_downgrades_meets(self) -> None:
        rule_set = _rule_set(criteria=(minimum_age(18),))
        result = evaluate_ruleset(
            rule_set, EligibilityInput(age=20), as_of=date(2026, 9, 19), evidence_stale=True
        )
        assert result.outcome == EligibilityOutcome.insufficient_information
        assert result.evidence_stale is True


class TestRegisterRuleSets:
    def test_two_distinct_exam_key_cycle_pairs_both_register(self) -> None:
        rs1 = _rule_set(exam_key="exam_a", cycle="2027")
        rs2 = _rule_set(exam_key="exam_b", cycle="2027")
        registry = register_rule_sets([rs1, rs2])
        assert registry[("exam_a", "2027")] is rs1
        assert registry[("exam_b", "2027")] is rs2

    def test_same_exam_key_different_cycle_both_register(self) -> None:
        rs1 = _rule_set(exam_key="exam_a", cycle="2026")
        rs2 = _rule_set(exam_key="exam_a", cycle="2027")
        registry = register_rule_sets([rs1, rs2])
        assert len(registry) == 2

    def test_duplicate_exam_key_and_cycle_is_rejected(self) -> None:
        rs1 = _rule_set(exam_key="exam_a", cycle="2027", jurisdiction="IN")
        rs2 = _rule_set(exam_key="exam_a", cycle="2027", jurisdiction="GJ")
        with pytest.raises(DuplicateRuleSetError):
            register_rule_sets([rs1, rs2])


class TestGetRuleSetCycleJurisdictionGuard:
    def test_exact_match_returns_the_rule_set(self) -> None:
        rs = _rule_set(exam_key="exam_a", cycle="2027", jurisdiction="IN")
        registry = register_rule_sets([rs])
        found = get_rule_set(registry, exam_key="exam_a", cycle="2027", jurisdiction="IN")
        assert found is rs

    def test_wrong_cycle_returns_none_not_the_only_registered_one(self) -> None:
        rs = _rule_set(exam_key="exam_a", cycle="2027", jurisdiction="IN")
        registry = register_rule_sets([rs])
        found = get_rule_set(registry, exam_key="exam_a", cycle="2026", jurisdiction="IN")
        assert found is None

    def test_wrong_jurisdiction_returns_none_even_with_matching_cycle(self) -> None:
        """The exact guard this function exists for: a rule set
        registered for one state must never be silently handed back for
        a student in a different state just because the (exam_key,
        cycle) matched."""
        rs = _rule_set(exam_key="exam_a", cycle="2027", jurisdiction="GJ")
        registry = register_rule_sets([rs])
        found = get_rule_set(registry, exam_key="exam_a", cycle="2027", jurisdiction="MH")
        assert found is None

    def test_unknown_exam_key_returns_none(self) -> None:
        registry = register_rule_sets([_rule_set(exam_key="exam_a")])
        found = get_rule_set(registry, exam_key="exam_z", cycle="2027", jurisdiction="IN")
        assert found is None


class TestEvaluateForExam:
    def test_registered_exam_evaluates_normally(self) -> None:
        rs = _rule_set(
            exam_key="exam_a", cycle="2027", jurisdiction="IN", criteria=(minimum_age(18),)
        )
        registry = register_rule_sets([rs])
        result = evaluate_for_exam(
            registry,
            exam_key="exam_a",
            cycle="2027",
            jurisdiction="IN",
            eligibility_input=EligibilityInput(age=20),
            as_of=date(2026, 9, 19),
        )
        assert result.outcome == EligibilityOutcome.meets

    def test_unregistered_exam_gives_honest_no_verified_rules(self) -> None:
        registry = register_rule_sets([_rule_set(exam_key="exam_a")])
        result = evaluate_for_exam(
            registry,
            exam_key="does_not_exist",
            cycle="2027",
            jurisdiction="IN",
            eligibility_input=EligibilityInput(),
            as_of=date(2026, 9, 19),
        )
        assert result.outcome == EligibilityOutcome.insufficient_information
        assert result.no_verified_rules is True
        assert result.exam_key == "does_not_exist"

    def test_wrong_jurisdiction_gives_honest_no_verified_rules_not_the_other_states_rule(
        self,
    ) -> None:
        registry = register_rule_sets(
            [_rule_set(exam_key="exam_a", cycle="2027", jurisdiction="GJ")]
        )
        result = evaluate_for_exam(
            registry,
            exam_key="exam_a",
            cycle="2027",
            jurisdiction="MH",
            eligibility_input=EligibilityInput(),
            as_of=date(2026, 9, 19),
        )
        assert result.no_verified_rules is True
        assert result.jurisdiction == "MH"


class TestDiscoverExamModules:
    def test_discovers_every_module_in_the_fake_package(self) -> None:
        modules = discover_exam_modules(FAKE_EXAMS_PACKAGE)
        names = {m.__name__ for m in modules}
        assert f"{FAKE_EXAMS_PACKAGE}.reviewed_exam" in names
        assert f"{FAKE_EXAMS_PACKAGE}.unreviewed_exam" in names


class TestDiscoverRuleSets:
    def test_development_env_includes_unreviewed_modules(self) -> None:
        registry = discover_rule_sets(FAKE_EXAMS_PACKAGE, app_env="development")
        assert ("fake_reviewed_exam", "2027") in registry
        assert ("fake_unreviewed_exam", "2027") in registry

    def test_production_env_excludes_unreviewed_modules(self) -> None:
        """The named RULES-4 acceptance case: an unreviewed module is
        hidden in production mode."""
        registry = discover_rule_sets(FAKE_EXAMS_PACKAGE, app_env="production")
        assert ("fake_reviewed_exam", "2027") in registry
        assert ("fake_unreviewed_exam", "2027") not in registry

    def test_production_env_still_includes_reviewed_modules(self) -> None:
        registry = discover_rule_sets(FAKE_EXAMS_PACKAGE, app_env="production")
        reviewed = registry[("fake_reviewed_exam", "2027")]
        assert reviewed.is_reviewed is True
