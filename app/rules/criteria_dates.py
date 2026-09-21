"""Date-based age criteria — Lite Build Pack §6, task RULES-2.

A real date-of-birth cutoff check, not today's naive integer-age
subtraction. `app/rules/eligibility.py`'s existing `minimum_age`/
`maximum_age` compare a pre-computed integer `age` against a threshold,
which is wrong for exams like NEET-UG whose rule is "must have completed
17 years as on or before 31 December of the exam year" — a fixed
reference date, not "today". A 16-year-old who turns 17 before that
cutoff is eligible, and the integer-age criterion would wrongly say they
are not (see `docs/content-drafts/neet-ug-eligibility.md`, fact 1's
"engine gap" note — the exact bug class this module exists to close).

These are new, additive criteria: they read the new
`EligibilityInput.date_of_birth` field (and, when a per-category
relaxation table is supplied, `EligibilityInput.category`) but do not
replace `minimum_age`/`maximum_age`, which stay for callers that only
have an already-computed integer age.

Same priority rule as the rest of this engine: an unknown input is
`insufficient_information`, NEVER a rejection.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.data.models import EligibilityOutcome
from app.rules.eligibility import Criterion, CriterionResult, EligibilityInput


def _shift_years(d: date, years: int) -> date:
    """`d` moved back by `years` whole years, tolerating a 29 February
    `d` landing on a non-leap target year by falling back to 28 February
    that year (`date.replace` would otherwise raise `ValueError` for a
    day that doesn't exist in the target year)."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def age_on(dob: date, ref_date: date) -> int:
    """Whole completed years of age as of `ref_date` (inclusive — a
    birthday on `ref_date` itself counts as reached).

    Deliberately compares `(month, day)` tuples rather than constructing
    "this year's birthday" as a `date` object, which would raise for a
    29 February date of birth in a non-leap reference year
    (`date(2027, 2, 29)` does not exist). The tuple comparison instead
    falls out correctly on its own: on 28 Feb of a non-leap year a
    29-Feb-born student's birthday has not yet occurred (`(2, 28) <
    (2, 29)`), and on 1 March it has (`(3, 1) < (2, 29)` is False) — the
    birthday is treated as reached on 1 March in a year that has no
    29 February, which is the standard "age on a date" convention.
    """
    born = (dob.month, dob.day)
    ref = (ref_date.month, ref_date.day)
    return ref_date.year - dob.year - (ref < born)


def minimum_age_on_date(
    min_age: int,
    cutoff_date: date,
    *,
    relaxation_years: Mapping[str, int] | None = None,
    source_claim_id: str | None = None,
) -> Criterion:
    """`min_age` as completed on or before `cutoff_date` (e.g. NEET-UG:
    17 years as on 31 December of the exam year).

    `relaxation_years`, if given, maps a category name to how many years
    the minimum is LOWERED for that category — a student in that category
    may be up to that many years younger than the general minimum and
    still meet this criterion. A category absent from the mapping gets no
    relaxation (falls back to the general `min_age`). The category is
    only looked up — and only then can an unknown category produce
    `insufficient_information` — when the general (unrelaxed) check has
    already failed; a student who already clears the general minimum
    never needs their category to decide this criterion.
    """
    relaxations = dict(relaxation_years or {})

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.date_of_birth is None:
            return CriterionResult(
                name="minimum_age_on_date",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Date of birth is needed to check the minimum age of "
                    f"{min_age} as on {cutoff_date.isoformat()}."
                ),
                source_claim_id=source_claim_id,
            )
        age = age_on(inp.date_of_birth, cutoff_date)
        if age >= min_age:
            return CriterionResult(
                name="minimum_age_on_date",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"Meets the minimum age of {min_age} as on "
                    f"{cutoff_date.isoformat()} (age on that date: {age})."
                ),
                source_claim_id=source_claim_id,
            )
        if relaxations:
            if inp.category is None:
                return CriterionResult(
                    name="minimum_age_on_date",
                    outcome=EligibilityOutcome.insufficient_information,
                    explanation=(
                        "Category is needed: some categories get a minimum-age "
                        "relaxation that could change this result, and the "
                        "general minimum age was not met."
                    ),
                    source_claim_id=source_claim_id,
                )
            relaxation = relaxations.get(inp.category, 0)
            relaxed_min = min_age - relaxation
            if age >= relaxed_min:
                return CriterionResult(
                    name="minimum_age_on_date",
                    outcome=EligibilityOutcome.meets,
                    explanation=(
                        f"Meets the relaxed minimum age of {relaxed_min} for "
                        f"category {inp.category} as on "
                        f"{cutoff_date.isoformat()} (age on that date: {age})."
                    ),
                    source_claim_id=source_claim_id,
                )
        return CriterionResult(
            name="minimum_age_on_date",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Minimum age is {min_age} as on {cutoff_date.isoformat()}; "
                f"age on that date is {age}."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(name="minimum_age_on_date", check=check, source_claim_id=source_claim_id)


def maximum_age_on_date(
    max_age: int,
    cutoff_date: date,
    *,
    relaxation_years: Mapping[str, int] | None = None,
    source_claim_id: str | None = None,
) -> Criterion:
    """`max_age` as completed on or before `cutoff_date`.

    `relaxation_years`, if given, maps a category name to how many years
    the maximum is RAISED for that category (a reserved-category student
    permitted to be that many years older than the general upper limit
    and still meet this criterion). Same "only ask for category once the
    general check fails" behaviour as `minimum_age_on_date`.
    """
    relaxations = dict(relaxation_years or {})

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.date_of_birth is None:
            return CriterionResult(
                name="maximum_age_on_date",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Date of birth is needed to check the upper age limit of "
                    f"{max_age} as on {cutoff_date.isoformat()}."
                ),
                source_claim_id=source_claim_id,
            )
        age = age_on(inp.date_of_birth, cutoff_date)
        if age <= max_age:
            return CriterionResult(
                name="maximum_age_on_date",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"Within the upper age limit of {max_age} as on "
                    f"{cutoff_date.isoformat()} (age on that date: {age})."
                ),
                source_claim_id=source_claim_id,
            )
        if relaxations:
            if inp.category is None:
                return CriterionResult(
                    name="maximum_age_on_date",
                    outcome=EligibilityOutcome.insufficient_information,
                    explanation=(
                        "Category is needed: some categories get an upper-age "
                        "relaxation that could change this result, and the "
                        "general upper age limit was exceeded."
                    ),
                    source_claim_id=source_claim_id,
                )
            relaxation = relaxations.get(inp.category, 0)
            relaxed_max = max_age + relaxation
            if age <= relaxed_max:
                return CriterionResult(
                    name="maximum_age_on_date",
                    outcome=EligibilityOutcome.meets,
                    explanation=(
                        f"Within the relaxed upper age limit of {relaxed_max} "
                        f"for category {inp.category} as on "
                        f"{cutoff_date.isoformat()} (age on that date: {age})."
                    ),
                    source_claim_id=source_claim_id,
                )
        return CriterionResult(
            name="maximum_age_on_date",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Upper age limit is {max_age} as on {cutoff_date.isoformat()} "
                f"(before applicable relaxations); age on that date is {age}."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(name="maximum_age_on_date", check=check, source_claim_id=source_claim_id)


def born_between(
    earliest: date,
    latest: date,
    *,
    relaxation_years: Mapping[str, int] | None = None,
    source_claim_id: str | None = None,
) -> Criterion:
    """Date of birth must fall within `[earliest, latest]`, inclusive
    (e.g. NDA's born-between window).

    `relaxation_years`, if given, maps a category name to how many years
    the window widens at the `earliest` end for that category (a
    reserved-category student is allowed to be born that many years
    earlier — i.e. older — and still meet this criterion). `latest` is
    never relaxed: an upper age-window bound relaxation would mean
    allowing a YOUNGER student through a rule meant to set a floor on
    age, which is not a real-world relaxation pattern for this shape of
    criterion.
    """
    relaxations = dict(relaxation_years or {})

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.date_of_birth is None:
            return CriterionResult(
                name="born_between",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Date of birth is needed to check the "
                    f"{earliest.isoformat()} to {latest.isoformat()} window."
                ),
                source_claim_id=source_claim_id,
            )
        dob = inp.date_of_birth
        if earliest <= dob <= latest:
            return CriterionResult(
                name="born_between",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"Date of birth {dob.isoformat()} is within the required "
                    f"window {earliest.isoformat()} to {latest.isoformat()}."
                ),
                source_claim_id=source_claim_id,
            )
        # A dob after `latest` can never be rescued by a relaxation --
        # only the `earliest` bound ever relaxes (see docstring) -- so a
        # category lookup is only useful when the miss is on the
        # `earliest` side.
        if relaxations and dob < earliest:
            if inp.category is None:
                return CriterionResult(
                    name="born_between",
                    outcome=EligibilityOutcome.insufficient_information,
                    explanation=(
                        "Category is needed: some categories get a relaxed "
                        "earliest-birth-date bound that could change this "
                        "result, and the general window was not met."
                    ),
                    source_claim_id=source_claim_id,
                )
            relaxation = relaxations.get(inp.category, 0)
            if relaxation:
                relaxed_earliest = _shift_years(earliest, relaxation)
                if relaxed_earliest <= dob <= latest:
                    return CriterionResult(
                        name="born_between",
                        outcome=EligibilityOutcome.meets,
                        explanation=(
                            f"Date of birth {dob.isoformat()} is within the "
                            f"relaxed window for category {inp.category} "
                            f"({relaxed_earliest.isoformat()} to "
                            f"{latest.isoformat()})."
                        ),
                        source_claim_id=source_claim_id,
                    )
        return CriterionResult(
            name="born_between",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Date of birth must be between {earliest.isoformat()} and "
                f"{latest.isoformat()} (before applicable relaxations); "
                f"given date of birth is {dob.isoformat()}."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(name="born_between", check=check, source_claim_id=source_claim_id)
