"""RuleSet, auto-discovering registry, cycle/jurisdiction guard — Lite
Build Pack §6, task RULES-4.

`app/rules/eligibility.py::evaluate_eligibility` alone can only answer
"do these criteria say meets/does_not_meet/insufficient_information" --
it has no idea whether it is even running the RIGHT criteria. A `RuleSet`
names exactly which exam, cycle and jurisdiction a set of criteria
belongs to, and `evaluate_ruleset` adds the honesty checks that decide
whether those criteria should even be trusted right now:

- An empty `RuleSet` (no registered criteria at all) never reports a bare
  `meets` -- that would be "nothing failed" mistaken for "verified
  eligible". `no_verified_rules=True` forces `insufficient_information`
  instead (docs/CONTRACTS.md "Three eligibility outcomes": "a pathway
  with no published rules returns insufficient_information +
  no_verified_rules -- never not_eligible").
- A `RuleSet` whose `cycle_end` is before `as_of` is `cycle_stale` -- the
  cycle it was written for has ended, so a `meets` from it is downgraded
  to `insufficient_information` (a real `does_not_meet` still stands: a
  definite failure found under last cycle's rules is still information
  worth surfacing, just not a confident pass).
- The registry (`discover_rule_sets`) never lets two `RuleSet`s silently
  collide under the same `(exam_key, cycle)`, and looking one up
  (`get_rule_set`) is an exact `(exam_key, cycle, jurisdiction)` match
  only -- never "closest" or "the only one registered under this
  exam_key", which could otherwise silently serve the wrong year's or
  the wrong state's rule.
- `discover_rule_sets`'s `app_env` parameter (an explicit, required
  keyword -- this module deliberately never imports
  `app.core.config.get_settings` itself, so it stays a pure function
  callable from a test with no environment/config coupling at all)
  excludes any `RuleSet` that isn't yet human-reviewed
  (`RuleSet.is_reviewed`) when set to `"production"`. An unreviewed
  module is simply absent from what a production caller can see, never
  partially exposed.

Each module under `app.rules.exams` is expected to expose a module-level
`RULE_SETS: tuple[RuleSet, ...]` — see `app/rules/exams/__init__.py` for
the convention every exam module (RULES-5/6/...) follows.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from types import ModuleType

from app.data.models import EligibilityOutcome
from app.rules.criteria_extra import NotChecked
from app.rules.eligibility import (
    Criterion,
    EligibilityInput,
    EligibilityResult,
    evaluate_eligibility,
)

_DEFAULT_EXAMS_PACKAGE = "app.rules.exams"


class DuplicateRuleSetError(ValueError):
    """Raised when two `RuleSet`s are registered under the same
    `(exam_key, cycle)` — a silent overwrite here could mean serving the
    wrong year's rule under a right-looking key, so this is rejected
    outright rather than letting the later one quietly win."""


@dataclass(frozen=True)
class RuleSet:
    """One exam's criteria for one cycle and jurisdiction.

    `reviewed_by`/`reviewed_on` both unset is how a rule set marks
    itself as not yet human-reviewed (RULES-7's card: "modules ship with
    reviewed_by empty so the registry hides them publicly until claims
    are primary-source verified"); RULES-11/RULES-12 record these two
    fields in the rule set's own case-table JSON header, approved by a
    reviewed pull request — never typed into a database row (see
    docs/CONTRACTS.md "Rule approval lives in git JSON").
    """

    exam_key: str
    cycle: str
    cycle_end: date
    jurisdiction: str
    rule_version: str
    criteria: tuple[Criterion, ...] = ()
    reviewed_by: str | None = None
    reviewed_on: date | None = None
    not_checked: tuple[NotChecked, ...] = field(default_factory=tuple)

    @property
    def is_reviewed(self) -> bool:
        return self.reviewed_by is not None and self.reviewed_on is not None


@dataclass(frozen=True)
class RuleSetResult:
    """`evaluate_eligibility`'s outcome plus the honesty metadata a bare
    `EligibilityResult` has no way to carry: which exam, which cycle,
    whether the rule set backing this answer should even be trusted
    right now."""

    outcome: EligibilityOutcome
    eligibility: EligibilityResult
    exam_key: str
    cycle: str
    jurisdiction: str
    rule_version: str
    not_checked: tuple[NotChecked, ...]
    no_verified_rules: bool
    cycle_stale: bool
    evidence_stale: bool


def evaluate_ruleset(
    rule_set: RuleSet,
    eligibility_input: EligibilityInput,
    *,
    as_of: date,
    evidence_stale: bool = False,
) -> RuleSetResult:
    """Run `rule_set.criteria` (unless there are none — see module
    docstring) and wrap the result with cycle/version/jurisdiction
    honesty metadata.

    `evidence_stale` is a caller-supplied flag: whether the published
    claims a criterion was built from are themselves past their
    review-due date is a fact about the claims/content layer, decided by
    whoever builds `eligibility_input`'s companion evidence — this module
    has no `Claim` access of its own, so it only folds the flag it's
    given into the same "never a confident-looking meets" guard as
    `cycle_stale` and `no_verified_rules`.
    """
    no_verified_rules = len(rule_set.criteria) == 0
    cycle_stale = as_of > rule_set.cycle_end

    if no_verified_rules:
        eligibility = EligibilityResult(
            outcome=EligibilityOutcome.insufficient_information, criteria=()
        )
        outcome = EligibilityOutcome.insufficient_information
    else:
        eligibility = evaluate_eligibility(list(rule_set.criteria), eligibility_input)
        outcome = eligibility.outcome
        if (cycle_stale or evidence_stale) and outcome == EligibilityOutcome.meets:
            # A real does_not_meet found under stale rules/evidence is
            # still a true fact worth surfacing -- only a confident
            # `meets` is unsafe to keep reporting once the cycle has
            # ended or the evidence behind it is overdue for a recheck.
            outcome = EligibilityOutcome.insufficient_information

    return RuleSetResult(
        outcome=outcome,
        eligibility=eligibility,
        exam_key=rule_set.exam_key,
        cycle=rule_set.cycle,
        jurisdiction=rule_set.jurisdiction,
        rule_version=rule_set.rule_version,
        not_checked=rule_set.not_checked,
        no_verified_rules=no_verified_rules,
        cycle_stale=cycle_stale,
        evidence_stale=evidence_stale,
    )


def register_rule_sets(rule_sets: Iterable[RuleSet]) -> dict[tuple[str, str], RuleSet]:
    """Build a `(exam_key, cycle) -> RuleSet` mapping, rejecting a
    duplicate `(exam_key, cycle)` pair outright (see
    `DuplicateRuleSetError`)."""
    registered: dict[tuple[str, str], RuleSet] = {}
    for rule_set in rule_sets:
        key = (rule_set.exam_key, rule_set.cycle)
        if key in registered:
            raise DuplicateRuleSetError(
                f"Duplicate RuleSet for exam_key={rule_set.exam_key!r} "
                f"cycle={rule_set.cycle!r} — a rule set is already registered "
                "for this exam and cycle."
            )
        registered[key] = rule_set
    return registered


def discover_exam_modules(package_name: str = _DEFAULT_EXAMS_PACKAGE) -> tuple[ModuleType, ...]:
    """Import every submodule of `package_name` via `pkgutil`. A module
    that fails to import is a content-authoring bug to catch in tests,
    not something to degrade gracefully on."""
    package = importlib.import_module(package_name)
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return ()
    modules = []
    for _finder, name, _is_pkg in pkgutil.iter_modules(package_path, prefix=f"{package_name}."):
        modules.append(importlib.import_module(name))
    return tuple(modules)


def discover_rule_sets(
    package_name: str = _DEFAULT_EXAMS_PACKAGE,
    *,
    app_env: str,
) -> dict[tuple[str, str], RuleSet]:
    """Discover every exam module's `RULE_SETS` under `package_name`
    (each module exposes a module-level `RULE_SETS: tuple[RuleSet, ...]`
    — see `app/rules/exams/__init__.py`), reject a duplicate
    `(exam_key, cycle)` across the whole registry, and — when `app_env`
    is `"production"` — silently exclude any `RuleSet` that isn't yet
    human-reviewed (`RuleSet.is_reviewed`), so an unreviewed module is
    simply absent from a production listing, never partially exposed.
    """
    is_production = app_env == "production"

    all_rule_sets: list[RuleSet] = []
    for module in discover_exam_modules(package_name):
        rule_sets: tuple[RuleSet, ...] = getattr(module, "RULE_SETS", ())
        for rule_set in rule_sets:
            if is_production and not rule_set.is_reviewed:
                continue
            all_rule_sets.append(rule_set)
    return register_rule_sets(all_rule_sets)


def get_rule_set(
    registry: Mapping[tuple[str, str], RuleSet],
    *,
    exam_key: str,
    cycle: str,
    jurisdiction: str,
) -> RuleSet | None:
    """Exact match only on `(exam_key, cycle)` AND `jurisdiction` — the
    guard this function exists for: never silently return a rule set for
    the wrong cycle or the wrong jurisdiction just because it happens to
    be the only one registered under that `exam_key`."""
    rule_set = registry.get((exam_key, cycle))
    if rule_set is None or rule_set.jurisdiction != jurisdiction:
        return None
    return rule_set


def evaluate_for_exam(
    registry: Mapping[tuple[str, str], RuleSet],
    *,
    exam_key: str,
    cycle: str,
    jurisdiction: str,
    eligibility_input: EligibilityInput,
    as_of: date,
) -> RuleSetResult:
    """`get_rule_set` plus `evaluate_ruleset`, with an honest
    `no_verified_rules` result (never a crash, never a guess) when
    nothing is registered for the requested `(exam_key, cycle,
    jurisdiction)` at all."""
    rule_set = get_rule_set(registry, exam_key=exam_key, cycle=cycle, jurisdiction=jurisdiction)
    if rule_set is None:
        return RuleSetResult(
            outcome=EligibilityOutcome.insufficient_information,
            eligibility=EligibilityResult(
                outcome=EligibilityOutcome.insufficient_information, criteria=()
            ),
            exam_key=exam_key,
            cycle=cycle,
            jurisdiction=jurisdiction,
            rule_version="unregistered",
            not_checked=(),
            no_verified_rules=True,
            cycle_stale=False,
            evidence_stale=False,
        )
    return evaluate_ruleset(rule_set, eligibility_input, as_of=as_of)
