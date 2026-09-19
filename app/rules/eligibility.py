"""Eligibility engine — Lite Build Pack §6, docs/DATA.md.

Deterministic, versioned, source-cited rule functions. No model tokens
anywhere in this module. Three outcomes only:
`meets` / `does_not_meet` / `insufficient_information`.

**The single most safety-critical rule in this module:** an unknown or
missing input is `insufficient_information`, NEVER `does_not_meet`. A
student is never told they're rejected because we simply don't know
something about them (Build Pack §6: "An unknown domicile rule or
missing subject requirement never becomes a rejection").

Priority when combining several criteria into one overall outcome:
`does_not_meet` (any definite failure) > `insufficient_information` (any
unknown, if nothing definitely failed) > `meets` (only if every
criterion definitely passed). A definite failure elsewhere is not masked
by an unrelated unknown — the student needs to see the fact that
actually blocks them, not an "unknown" that happens to sort first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.data.models import EligibilityOutcome


@dataclass(frozen=True)
class EligibilityInput:
    """The optional, separately-consented facts eligibility checks may
    need — deliberately NOT part of the minimal StudentProfile
    (docs/DATA.md "Minimisation"). Every field is optional; a missing
    field is what drives `insufficient_information`, not an error."""

    age: int | None = None
    marks_percentage: float | None = None
    subjects_studied: frozenset[str] = field(default_factory=frozenset)
    domicile_state: str | None = None
    category: str | None = None
    as_of: date | None = None


@dataclass(frozen=True)
class CriterionResult:
    """One criterion's verdict, always explainable — never a bare
    boolean (docs/UI.md: "Name the missing requirement; never guess")."""

    name: str
    outcome: EligibilityOutcome
    explanation: str
    source_claim_id: str | None = None


@dataclass(frozen=True)
class Criterion:
    """A single named, versioned, source-cited eligibility check.

    `check` takes the input and returns a CriterionResult. Criteria are
    plain functions wrapped this way so each one can be unit-tested,
    versioned and cited independently (Build Pack §6: "Rule functions
    are reviewed, versioned and cite their source").
    """

    name: str
    check: Callable[[EligibilityInput], CriterionResult]
    source_claim_id: str | None = None
    rule_version: str = "v1"


@dataclass(frozen=True)
class EligibilityResult:
    outcome: EligibilityOutcome
    criteria: tuple[CriterionResult, ...]

    @property
    def failing(self) -> tuple[CriterionResult, ...]:
        return tuple(c for c in self.criteria if c.outcome == EligibilityOutcome.does_not_meet)

    @property
    def unknown(self) -> tuple[CriterionResult, ...]:
        return tuple(
            c for c in self.criteria if c.outcome == EligibilityOutcome.insufficient_information
        )


def evaluate_eligibility(
    criteria: list[Criterion], eligibility_input: EligibilityInput
) -> EligibilityResult:
    """Run every criterion, then combine by the priority rule documented
    at module level: does_not_meet > insufficient_information > meets."""
    results = tuple(c.check(eligibility_input) for c in criteria)

    if any(r.outcome == EligibilityOutcome.does_not_meet for r in results):
        overall = EligibilityOutcome.does_not_meet
    elif any(r.outcome == EligibilityOutcome.insufficient_information for r in results):
        overall = EligibilityOutcome.insufficient_information
    else:
        overall = EligibilityOutcome.meets
    return EligibilityResult(outcome=overall, criteria=results)


# ---------------------------------------------------------------------
# Reusable criterion builders. Each returns a Criterion; callers compose
# a list of these per exam/programme (the composition itself, and the
# concrete thresholds/subjects/source claim IDs, belong to the content
# track's per-exam rule definitions, not to this generic engine).
# ---------------------------------------------------------------------


def minimum_age(min_age: int, *, source_claim_id: str | None = None) -> Criterion:
    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.age is None:
            return CriterionResult(
                name="minimum_age",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=f"Age is needed to check the {min_age}+ requirement.",
                source_claim_id=source_claim_id,
            )
        if inp.age < min_age:
            return CriterionResult(
                name="minimum_age",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=f"Minimum age is {min_age}; given age is {inp.age}.",
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="minimum_age",
            outcome=EligibilityOutcome.meets,
            explanation=f"Meets the minimum age of {min_age}.",
            source_claim_id=source_claim_id,
        )

    return Criterion(name="minimum_age", check=check, source_claim_id=source_claim_id)


def maximum_age(max_age: int, *, source_claim_id: str | None = None) -> Criterion:
    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.age is None:
            return CriterionResult(
                name="maximum_age",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=f"Age is needed to check the {max_age} upper-age-limit requirement.",
                source_claim_id=source_claim_id,
            )
        if inp.age > max_age:
            return CriterionResult(
                name="maximum_age",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=(
                    f"Upper age limit is {max_age} "
                    f"(before applicable relaxations); given age is {inp.age}."
                ),
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="maximum_age",
            outcome=EligibilityOutcome.meets,
            explanation=f"Within the upper age limit of {max_age}.",
            source_claim_id=source_claim_id,
        )

    return Criterion(name="maximum_age", check=check, source_claim_id=source_claim_id)


def minimum_marks_percentage(
    min_percentage: float, *, source_claim_id: str | None = None
) -> Criterion:
    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.marks_percentage is None:
            return CriterionResult(
                name="minimum_marks_percentage",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Marks percentage is needed to check the {min_percentage}% requirement."
                ),
                source_claim_id=source_claim_id,
            )
        if inp.marks_percentage < min_percentage:
            return CriterionResult(
                name="minimum_marks_percentage",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=(
                    f"Minimum required is {min_percentage}%; "
                    f"given marks are {inp.marks_percentage}%."
                ),
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="minimum_marks_percentage",
            outcome=EligibilityOutcome.meets,
            explanation=f"Meets the minimum of {min_percentage}%.",
            source_claim_id=source_claim_id,
        )

    return Criterion(
        name="minimum_marks_percentage", check=check, source_claim_id=source_claim_id
    )


def required_subjects(
    required: frozenset[str], *, source_claim_id: str | None = None
) -> Criterion:
    """Every subject in `required` must appear in the student's
    `subjects_studied`. Missing the *list itself* (empty set given as
    "unknown", not "took nothing") is the caller's responsibility to
    distinguish — this criterion treats an empty `subjects_studied` as
    "no subjects reported" -> insufficient_information, not a failure,
    since a genuinely empty transcript is not a real-world case we
    should silently reject on.
    """

    def check(inp: EligibilityInput) -> CriterionResult:
        if not inp.subjects_studied:
            return CriterionResult(
                name="required_subjects",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Subjects studied are needed to check for "
                    f"{', '.join(sorted(required))}."
                ),
                source_claim_id=source_claim_id,
            )
        missing = required - inp.subjects_studied
        if missing:
            return CriterionResult(
                name="required_subjects",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=f"Missing required subject(s): {', '.join(sorted(missing))}.",
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="required_subjects",
            outcome=EligibilityOutcome.meets,
            explanation="Has all required subjects.",
            source_claim_id=source_claim_id,
        )

    return Criterion(name="required_subjects", check=check, source_claim_id=source_claim_id)


def domicile_in(
    allowed_states: frozenset[str], *, source_claim_id: str | None = None
) -> Criterion:
    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.domicile_state is None:
            return CriterionResult(
                name="domicile_in",
                outcome=EligibilityOutcome.insufficient_information,
                explanation="Domicile state is needed to check this eligibility rule.",
                source_claim_id=source_claim_id,
            )
        if inp.domicile_state not in allowed_states:
            return CriterionResult(
                name="domicile_in",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=(
                    f"Requires domicile in {', '.join(sorted(allowed_states))}; "
                    f"given domicile is {inp.domicile_state}."
                ),
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="domicile_in",
            outcome=EligibilityOutcome.meets,
            explanation="Meets the domicile requirement.",
            source_claim_id=source_claim_id,
        )

    return Criterion(name="domicile_in", check=check, source_claim_id=source_claim_id)
