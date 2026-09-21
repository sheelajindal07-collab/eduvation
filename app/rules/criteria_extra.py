"""Extra eligibility criteria — Lite Build Pack §6, task RULES-3.

Four more composable, source-cited criteria beyond
`app/rules/eligibility.py`'s originals:

- `subject_groups`: an all-of list of any-of subject sets (e.g. NEET-UG's
  "Physics AND Chemistry AND (Biology OR Biotechnology)" — see
  docs/content-drafts/neet-ug-eligibility.md fact 3's "engine gap" note;
  `required_subjects` in eligibility.py is a plain all-of set and cannot
  express the "or" without wrongly failing a Biotechnology student).
- `minimum_marks_by_category`: a per-category marks threshold (e.g.
  General 50%, SC/ST 40%), honest when the category is unknown.
- `passed_or_appearing_in_years`: JEE-Main-shaped "passed in year X/Y or
  currently appearing" rule.
- `minimum_qualification_level`: an ordered qualification-level floor
  (e.g. "at least Class 12").

Plus `NotChecked`, a plain declaration (not a `Criterion` — it never runs
against student input) for a real eligibility condition a rule set
deliberately does not evaluate (medical fitness, nationality, gender,
marital status, ...) — named so a `RuleSet` (RULES-4) can be honest about
what it genuinely never checks, which is a different fact from
`insufficient_information`'s "we'd check this if we had the data".

Same priority rule as the rest of this engine: an unknown input is
`insufficient_information`, NEVER a rejection. This is a new file and
does not edit `app/rules/eligibility.py`'s existing criteria.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.data.models import EligibilityOutcome
from app.rules.eligibility import Criterion, CriterionResult, EligibilityInput


def subject_groups(
    groups: Sequence[frozenset[str]], *, source_claim_id: str | None = None
) -> Criterion:
    """Every group in `groups` must have at least one of its subjects in
    `EligibilityInput.subjects_studied` (all-of list of any-of sets).

    A single-subject group (`frozenset({"Physics"})`) behaves like a
    plain required subject; a multi-subject group
    (`frozenset({"Biology", "Biotechnology"})`) is satisfied by either.
    An empty `subjects_studied` means "we don't know what was studied",
    not "studied nothing" — same convention as `required_subjects`.
    """

    def check(inp: EligibilityInput) -> CriterionResult:
        wanted = ", ".join(" or ".join(sorted(g)) for g in groups)
        if not inp.subjects_studied:
            return CriterionResult(
                name="subject_groups",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=f"Subjects studied are needed to check for {wanted}.",
                source_claim_id=source_claim_id,
            )
        unmet = [g for g in groups if not (g & inp.subjects_studied)]
        if unmet:
            missing = ", ".join(" or ".join(sorted(g)) for g in unmet)
            return CriterionResult(
                name="subject_groups",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=f"Missing required subject group(s): {missing}.",
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="subject_groups",
            outcome=EligibilityOutcome.meets,
            explanation=f"Has at least one subject from every required group ({wanted}).",
            source_claim_id=source_claim_id,
        )

    return Criterion(name="subject_groups", check=check, source_claim_id=source_claim_id)


def minimum_marks_by_category(
    thresholds: Mapping[str, float],
    *,
    default: float | None = None,
    source_claim_id: str | None = None,
) -> Criterion:
    """A per-category minimum marks percentage (e.g. General 50%,
    SC/ST 40%).

    An unknown category never rejects: if the student's marks already
    clear the highest threshold across every listed category (plus
    `default`, if given), the result is `meets` regardless of which
    category actually applies -- no category could have made that
    student fail. Only when the marks fall short of that ceiling, AND the
    category is unknown, does this return `insufficient_information`
    (never a guessed `does_not_meet`). A category that is known but not
    in `thresholds` falls back to `default`; with no `default` either,
    that is also `insufficient_information`, never a guess.
    """
    all_thresholds = list(thresholds.values()) + ([default] if default is not None else [])

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.marks_percentage is None:
            return CriterionResult(
                name="minimum_marks_by_category",
                outcome=EligibilityOutcome.insufficient_information,
                explanation="Marks percentage is needed to check the category threshold.",
                source_claim_id=source_claim_id,
            )
        if all_thresholds and inp.marks_percentage >= max(all_thresholds):
            return CriterionResult(
                name="minimum_marks_by_category",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"{inp.marks_percentage}% clears the highest category threshold "
                    f"({max(all_thresholds)}%), so this is met regardless of category."
                ),
                source_claim_id=source_claim_id,
            )
        if inp.category is None:
            return CriterionResult(
                name="minimum_marks_by_category",
                outcome=EligibilityOutcome.insufficient_information,
                explanation="Category is needed to look up the applicable marks threshold.",
                source_claim_id=source_claim_id,
            )
        threshold = thresholds.get(inp.category, default)
        if threshold is None:
            return CriterionResult(
                name="minimum_marks_by_category",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=f"No published marks threshold for category {inp.category}.",
                source_claim_id=source_claim_id,
            )
        if inp.marks_percentage >= threshold:
            return CriterionResult(
                name="minimum_marks_by_category",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"Meets the {threshold}% threshold for category {inp.category}."
                ),
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="minimum_marks_by_category",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Category {inp.category} requires {threshold}%; "
                f"given marks are {inp.marks_percentage}%."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(name="minimum_marks_by_category", check=check, source_claim_id=source_claim_id)


def passed_or_appearing_in_years(
    eligible_passing_years: frozenset[int],
    *,
    allow_appearing: bool = True,
    source_claim_id: str | None = None,
) -> Criterion:
    """JEE-Main-shaped rule: passed the qualifying exam in one of
    `eligible_passing_years`, OR is currently appearing this cycle (when
    `allow_appearing` is True).

    Neither `year_of_passing` nor `appearing` known -> insufficient
    information. `appearing=True` short-circuits to `meets` (or, when
    `allow_appearing` is False, to `does_not_meet` -- the rule requires
    having already passed) without needing `year_of_passing` at all,
    since a currently-appearing student has by definition not passed yet.
    """

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.appearing is None and inp.year_of_passing is None:
            return CriterionResult(
                name="passed_or_appearing_in_years",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    "Year of passing (or whether currently appearing) is needed "
                    "to check this requirement."
                ),
                source_claim_id=source_claim_id,
            )
        if inp.appearing:
            if allow_appearing:
                return CriterionResult(
                    name="passed_or_appearing_in_years",
                    outcome=EligibilityOutcome.meets,
                    explanation="Currently appearing in the qualifying examination.",
                    source_claim_id=source_claim_id,
                )
            return CriterionResult(
                name="passed_or_appearing_in_years",
                outcome=EligibilityOutcome.does_not_meet,
                explanation=(
                    "This rule requires having already passed the qualifying "
                    "examination; currently appearing does not qualify."
                ),
                source_claim_id=source_claim_id,
            )
        if inp.year_of_passing is None:
            return CriterionResult(
                name="passed_or_appearing_in_years",
                outcome=EligibilityOutcome.insufficient_information,
                explanation="Year of passing is needed to check this requirement.",
                source_claim_id=source_claim_id,
            )
        years = ", ".join(str(y) for y in sorted(eligible_passing_years))
        if inp.year_of_passing in eligible_passing_years:
            return CriterionResult(
                name="passed_or_appearing_in_years",
                outcome=EligibilityOutcome.meets,
                explanation=(
                    f"Passed in {inp.year_of_passing}, one of the eligible years ({years})."
                ),
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="passed_or_appearing_in_years",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Eligible passing years are {years}; given year of passing is "
                f"{inp.year_of_passing}."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(
        name="passed_or_appearing_in_years", check=check, source_claim_id=source_claim_id
    )


def minimum_qualification_level(
    min_level: str,
    *,
    level_order: Sequence[str],
    source_claim_id: str | None = None,
) -> Criterion:
    """`level_order` names every recognised qualification level, lowest
    first (e.g. `("Class 10", "Class 12", "Diploma", "Bachelor's")`).
    `min_level` must be one of them. A student's `qualification_level`
    that isn't in `level_order` can't be ranked -- that is
    `insufficient_information`, never a guessed rejection, the same as an
    unset level.
    """
    ranks = {name: i for i, name in enumerate(level_order)}
    if min_level not in ranks:
        raise ValueError(f"min_level {min_level!r} is not in level_order {tuple(level_order)!r}.")

    def check(inp: EligibilityInput) -> CriterionResult:
        if inp.qualification_level is None:
            return CriterionResult(
                name="minimum_qualification_level",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=f"Qualification level is needed to check for at least {min_level}.",
                source_claim_id=source_claim_id,
            )
        if inp.qualification_level not in ranks:
            return CriterionResult(
                name="minimum_qualification_level",
                outcome=EligibilityOutcome.insufficient_information,
                explanation=(
                    f"Qualification level {inp.qualification_level!r} is not "
                    "recognised, so it can't be checked against "
                    f"the required minimum of {min_level}."
                ),
                source_claim_id=source_claim_id,
            )
        if ranks[inp.qualification_level] >= ranks[min_level]:
            return CriterionResult(
                name="minimum_qualification_level",
                outcome=EligibilityOutcome.meets,
                explanation=f"{inp.qualification_level} meets the minimum of {min_level}.",
                source_claim_id=source_claim_id,
            )
        return CriterionResult(
            name="minimum_qualification_level",
            outcome=EligibilityOutcome.does_not_meet,
            explanation=(
                f"Minimum qualification level is {min_level}; given level is "
                f"{inp.qualification_level}."
            ),
            source_claim_id=source_claim_id,
        )

    return Criterion(
        name="minimum_qualification_level", check=check, source_claim_id=source_claim_id
    )


@dataclass(frozen=True)
class NotChecked:
    """A real eligibility condition this rule set deliberately does NOT
    evaluate (medical fitness, nationality, gender, marital status, ...).

    Not a `Criterion` -- it never runs against `EligibilityInput` and
    never contributes to `evaluate_eligibility`'s combined outcome. It is
    metadata a `RuleSet` (RULES-4) carries and surfaces to the student
    verbatim (e.g. "Medical fitness: not checked here -- confirm with the
    official notification."), so the engine is honest about a real
    condition it is choosing not to compute, which is a different fact
    from `insufficient_information`'s "we'd check this if we had the
    data" -- collecting some of these (medical history, marital status)
    is out of scope for what Lite asks a student for at all.
    """

    name: str
    note: str = "Not checked by this tool — confirm with the official notification."
