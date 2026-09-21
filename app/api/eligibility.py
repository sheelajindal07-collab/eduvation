"""GET/POST /eligibility — the JSON eligibility route, wired to
`app/rules/ruleset.py`'s named-`RuleSet` registry (RULES-8).

Two ways a pathway's criteria can be decided, in this order:

1. **A named rule set** (RULES-4/5/6). A pathway publishes ONE claim on
   the field `rule_key` whose value names an exam module's `exam_key`
   (`"neet_ug"`, `"jee_main"`, `"gujcet"`, ...). The cycle and
   jurisdiction of the lookup come from that same claim's own
   `academic_cycle` and `jurisdiction` columns (SCOPE-3,
   db/migrations/0008), never from a second parsed field: `academic_cycle`
   is already "a text LABEL ... compared as a string, never parsed"
   (docs/CONTRACTS.md "Duration, dates, cycle, DOB"), which is exactly
   what `RuleSet.cycle` is. The registry match is exact on all three
   (`app.rules.ruleset.get_rule_set`) — never "closest", never "the only
   one under this exam_key" — so a 2026 claim can never be answered with
   2027's rule, and a Gujarat claim can never be answered with an
   all-India one. Nothing matches -> `no_verified_rules`, never a guess.
   The rule set's own criteria, thresholds and cited claim ids come from
   its reviewed case-table JSON in git, not from a database row
   (docs/CONTRACTS.md "Rule approval lives in git JSON").

2. **The pathway's own eligibility-shaped claims** (the pre-RULES-8
   behaviour, kept as the fallback for every pathway that has no
   published `rule_key`). Recognised claim fields on a Pathway:

     minimum_age                  int
     maximum_age                  int
     minimum_marks_percentage     float
     required_subjects            comma-separated string or a JSON list,
                                  e.g. "Physics,Chemistry,Biology"
     domicile_states              comma-separated string or a JSON list of
                                  state/country names, ISO codes or
                                  aliases, e.g. "Gujarat,IN-MH" — resolved
                                  by app.rules.eligibility.domicile_in via
                                  app.data.jurisdictions (SCOPE-5)

   Any of these that isn't published simply contributes no criterion.

**Zero criteria is never `meets`.** Both paths run through
`app.rules.ruleset.evaluate_ruleset`, so a pathway with nothing published
returns `insufficient_information` + `no_verified_rules` — docs/CONTRACTS.md
"Three eligibility outcomes": "a pathway with no published rules returns
insufficient_information + no_verified_rules — never not_eligible". This
REPLACES this route's former "vacuously meets" answer (an empty criteria
list has nothing to fail, so `evaluate_eligibility` alone reported
`meets`): "we found no rule" and "you pass every rule" are different
facts, and only one of them is safe to show a student who is deciding
what to do with their life.

**Nothing malformed ever becomes a 500.** A bad *request* is a clean 422
(`EligibilityCheckRequest`'s range validators; a non-UUID `pathway_id`
reaches a `uuid` column, so it is shape-checked here the same way
`app/api/compare.py` shape-checks its own). A bad *claim value* already
sitting in the database degrades that ONE criterion to a `not_checked`
entry and leaves the rest of the response intact — the same "one bad row
must not kill the whole response" convention `app/web/reviewer/queue.py`
and `app/planning/comparison.py` already follow.

SEC-5: age, marks_percentage, subjects_studied, domicile_state,
date_of_birth, category and year_of_passing are personal inputs and must
never be a query param or reach a URL (docs/CONTRACTS.md "Every personal
input ... is POST-only") — GET below accepts `pathway_id` only, and POST
carries every personal field in its JSON body. `date_of_birth` in
particular is "never logged, never in analytics": no logger call in this
module takes any personal input, only opaque ids (claim id, pathway id)
and claim field names, matching `app/api/auth.py`'s `_migrate_pending_plan`
failure logging.
"""

from __future__ import annotations

import logging
import uuid as uuid_module
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from supabase import Client

from app.api.deps import get_db_client
from app.core.config import get_settings
from app.data.models import Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.planning.comparison import safe_source_url, trust_label_for_claim
from app.rules.criteria_extra import NotChecked
from app.rules.eligibility import (
    Criterion,
    EligibilityInput,
    domicile_in,
    maximum_age,
    minimum_age,
    minimum_marks_percentage,
    required_subjects,
)
from app.rules.ruleset import (
    RuleSet,
    RuleSetResult,
    discover_rule_sets,
    evaluate_for_exam,
    evaluate_ruleset,
    get_rule_set,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["eligibility"])

# docs/CONTRACTS.md "Duration, dates, cycle, DOB": "'Today' is the current
# date in Asia/Kolkata, computed server-side; every `as_of` defaults to it
# and the client's clock is never trusted."
#
# A fixed +05:30 offset rather than `zoneinfo.ZoneInfo("Asia/Kolkata")`:
# India Standard Time has been exactly UTC+05:30 with no daylight saving
# since 1945, so the two give the identical answer for every date this
# product can be asked about — but `ZoneInfo` needs a system tz database
# (or the `tzdata` package, which is NOT in `requirements.lock`), and a
# slim container image without one raises `ZoneInfoNotFoundError` at
# import. A date arithmetic rule that can fail to load is worse than one
# that cannot. Adding `tzdata` to the lockfile is a lockfile edit, which
# parallel work rules forbid outside a dedicated task.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def today_ist() -> date:
    """Server-computed "today" in Asia/Kolkata (see `IST` above). Every
    `as_of` in this module comes from here; no client-supplied date is
    ever accepted as "now", not even for validation bounds."""
    return datetime.now(tz=IST).date()


RULE_KEY_FIELD = "rule_key"
"""The claim field a pathway uses to name which registered `RuleSet`
applies to it. The claim's VALUE is the exam module's `exam_key`; its own
`academic_cycle` and `jurisdiction` columns complete the exact
`(exam_key, cycle, jurisdiction)` lookup (see the module docstring)."""

MIN_AGE_YEARS = 0
MAX_AGE_YEARS = 120
"""Plausible-range bounds for the already-computed integer `age` input.
Not an eligibility rule — no exam's rules live in this file — purely the
"this cannot be a real person's age" guard that turns a negative or
absurd number into a clean 422 instead of a criterion evaluated against
nonsense. 120 rather than a tighter school-age bound on purpose: this
tool must not decide who is too old to ask a career question."""

MIN_MARKS_PERCENTAGE = 0.0
MAX_MARKS_PERCENTAGE = 100.0
"""A percentage. Above 100 is not a high scorer, it is a malformed
input — and `minimum_marks_percentage` would silently report `meets`
against every published threshold if it were let through."""

EARLIEST_YEAR_OF_PASSING = 1900
YEAR_OF_PASSING_FUTURE_LIMIT_YEARS = 10
"""`year_of_passing` must land in [1900, this year + 10]. The future
window exists because a student genuinely can name a year they have not
reached yet (the year they expect to pass); ten years is enough for any
school pathway and still rejects a typo'd 20265."""

MAX_CATEGORY_LENGTH = 64
"""`category` is looked up in a rule set's own per-category threshold or
relaxation table (`app/rules/criteria_extra.py`,
`app/rules/criteria_dates.py`); an unrecognised one is already
`insufficient_information`, never a rejection. The cap only stops an
unbounded string being carried through the request."""

MALFORMED_CLAIM_NOTE = (
    "This published requirement could not be read, so it was not checked here — "
    "confirm it against the official notification."
)
"""Shown verbatim for a claim whose stored value this route cannot turn
into a criterion (a `minimum_age` of "seventeen", a marks threshold of
"fifty percent"). Deliberately a `NotChecked` entry rather than a
criterion with an `insufficient_information` outcome: those two say
different things. `insufficient_information` means "we have the rule and
would check it if you told us X"; this means "we could not read the rule
at all" — the student's own answers cannot fix it, and a reviewer needs
to."""

UNREADABLE_RULE_KEY_NOTE = (
    "This pathway names a rule set that could not be identified, so no named "
    "rules were applied — confirm the requirements against the official "
    "notification."
)


@lru_cache(maxsize=1)
def _rule_set_registry(app_env: str) -> Mapping[tuple[str, str], RuleSet]:
    """The `(exam_key, cycle) -> RuleSet` registry, discovered once per
    process (importing every `app.rules.exams` module and parsing its
    case-table JSON on every request would be real per-request work for
    a set of files that cannot change without a redeploy).

    `app_env` is passed in rather than read inside, both because
    `discover_rule_sets` insists on it being explicit and because it is
    then the cache key — a test that switches environments gets a
    correctly separate registry instead of a stale one. In
    `"production"` an unreviewed rule set (no `reviewed_by`/`reviewed_on`
    in its case-table JSON) is simply absent, so a pathway pointing at
    one gets `no_verified_rules` rather than an unreviewed answer.

    A discovery failure (a duplicate `(exam_key, cycle)`, an exam module
    that will not import) degrades to an EMPTY registry, logged at
    error level. That is a content-authoring bug and
    `tests/unit/rules/test_exam_cases.py` is where it should be caught —
    but if one ever reaches production, every eligibility answer becoming
    an honest `insufficient_information` + `no_verified_rules` is a far
    better failure than every eligibility request 500ing.
    """
    try:
        return discover_rule_sets(app_env=app_env)
    except Exception:
        logger.exception(
            "Rule-set discovery failed for app_env=%s; serving an empty registry "
            "(every pathway with a rule_key claim will report no_verified_rules)",
            app_env,
        )
        return {}


def _looks_like_a_uuid(value: str) -> bool:
    """File-local by the same convention `app/api/compare.py` and
    `app/web/pages.py` document for their identically-named helpers.

    Same bug class compare.py fixed on 2026-09-20 and
    `app/web/requirements_pages.py` fixed for the HTML screen, still open
    on this route until RULES-8 and reproduced live: `entity_id` is a
    `uuid` column (db/migrations/0001_init.sql), so a malformed
    `pathway_id` reached PostgREST raw, came back as a 400 (Postgres
    22P02) and propagated as an unhandled 500 on both GET and POST
    /eligibility.
    """
    try:
        uuid_module.UUID(value)
    except ValueError:
        return False
    return True


def _row_to_source(row: dict[str, Any]) -> Source:
    """Identical to app/api/compare.py's helper of the same name — kept
    file-local rather than shared, matching this codebase's convention
    of not coupling otherwise-unrelated route files over a few lines."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """Identical to app/api/compare.py's helper of the same name — same
    file-local convention as `_row_to_source` above. Needed to call
    app/planning/comparison.py's `trust_label_for_claim()`, which takes a
    real `Claim`, not the raw row dict this route already has on hand."""
    return Claim(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        field=row["field"],
        value=row["value"],
        source_id=row["source_id"],
        verification_date=row["verification_date"],
        verifier=row["verifier"],
        status=ClaimStatus(row["status"]),
        review_due_date=row["review_due_date"],
        superseded_by=row.get("superseded_by"),
        approved_draft_version=row.get("approved_draft_version"),
        extracted_by=row.get("extracted_by", "human"),
    )


class NotCheckedOut(BaseModel):
    """One real eligibility condition this response deliberately did NOT
    evaluate (`app/rules/criteria_extra.py`'s `NotChecked`).

    Distinct from a criterion with an `insufficient_information`
    outcome: that one says "tell us X and we will check it", this one
    says "this tool does not check this at all — medical fitness,
    nationality, marital status — confirm it yourself". Surfacing them
    separately is what keeps a short criteria list from reading as "these
    are all the requirements there are"."""

    name: str
    note: str


class CriterionResultOut(BaseModel):
    name: str
    outcome: str
    explanation: str
    source_claim_id: str | None = None
    source_authority: str | None = None
    source_url: str | None = None
    verification_date: date | None = None
    """Resolved from `source_claim_id` (ux-qa-reviewer finding,
    2026-09-19): a bare claim UUID is useless to a UI trying to show
    docs/UI.md's required "source authority ... official link,
    verification date" per fact — this route already fetches every claim
    on the pathway, so resolving the source it points at costs one more
    query, not a design change, the same `_row_to_source`/`sources_by_id`
    shape `app/api/compare.py` already uses."""
    trust_label: str | None = None
    """docs/UI.md's five-value trust-label vocabulary (checked_against_
    official_source / institution_reported / needs_rechecking /
    not_available / estimate — see app/web/templates/_trust_badge.html's
    `trust_badge()` macro) for the underlying claim this criterion is
    based on. Deliberately separate from `outcome` above: `outcome` says
    whether the STUDENT's input meets the requirement; `trust_label` says
    how much the requirement ITSELF (the fact `check_eligibility` is
    checking against) should be trusted — e.g. a criterion can `meet`
    while its source is `needs_rechecking`, and the student should see
    both. Computed by the same `trust_label_for_claim()` the Compare
    screen uses (app/planning/comparison.py), not a second copy of that
    logic. `None` when the criterion has no `source_claim_id`, and also
    when it cites one that is not a published claim on THIS pathway —
    a named rule set's criteria cite claim ids from its own case-table
    JSON, which may name a claim this request never fetched."""


class EligibilityResponse(BaseModel):
    outcome: str
    criteria: list[CriterionResultOut]
    as_of: date | None = None
    """The server-computed Asia/Kolkata date this answer was evaluated
    against (docs/CONTRACTS.md "Duration, dates, cycle, DOB"). Present so
    a client can show "checked on ..." without inventing its own date
    from a device clock we deliberately never trust. Additive with a None
    default, like every field below it — existing JSON consumers and the
    `requirements.html` template are unaffected."""
    rule_version: str | None = None
    """The declared version string of the named `RuleSet` that produced
    this answer (docs/CONTRACTS.md "Rule approval lives in git JSON": it
    is the reviewed case-table file's own version, not a database row).
    `None` when no named rule set applied and the criteria came straight
    from this pathway's published claims. `"unregistered"` when the
    pathway named a rule set the registry has nothing for — which is
    also `no_verified_rules`."""
    cycle: str | None = None
    """The admission cycle label (`"2027"`, `"2026-27"`) the applied rule
    set is for. A LABEL compared as a string, never parsed
    (docs/CONTRACTS.md). `None` on the published-claims path."""
    jurisdiction: str | None = None
    """The jurisdiction the applied rule set is for. `None` on the
    published-claims path — those criteria are not scoped to one rule
    set's jurisdiction, and inventing one here would be exactly the
    "answered with the wrong state's rule" failure the registry's exact
    match exists to prevent."""
    no_verified_rules: bool = False
    """No criteria were evaluated at all: nothing published, or a named
    rule set that is not registered / not yet human-reviewed. Forces
    `outcome` to `insufficient_information` — never `does_not_meet`
    (docs/CONTRACTS.md "Three eligibility outcomes")."""
    stale: bool = True
    """This answer should be re-checked before it is relied on, because
    either the rule set's own cycle has ended (`cycle_end` before
    `as_of`) or at least one published claim behind a criterion is past
    its freshness window — the SAME staleness notion the Compare screen
    already shows, `app/planning/comparison.py`'s `trust_label_for_claim`
    returning `needs_rechecking`, not a second definition invented here.

    When it is true, a would-be `meets` has already been downgraded to
    `insufficient_information` by `app.rules.ruleset.evaluate_ruleset`; a
    real `does_not_meet` still stands, because a definite failure found
    under stale rules is still worth surfacing.

    Defaults to True, not False: a response constructed without this
    field having been thought about should read "recheck this", never
    "this is fresh"."""
    not_checked: list[NotCheckedOut] = Field(default_factory=list)
    """Conditions deliberately or unavoidably NOT evaluated — see
    `NotCheckedOut`. Includes both what the applied rule set declares it
    never checks, and any published claim on this pathway whose stored
    value could not be read."""


def _as_int(value: Any) -> int:
    """`int()` with the two non-numeric shapes `Claim.value` can now hold
    (RULES-3 widened it to allow a list/dict) turned into the same
    `ValueError` a malformed string already raises, so every caller has
    one exception type to degrade on."""
    if value is None or isinstance(value, bool | list | dict):
        raise ValueError(f"not a number: {type(value).__name__}")
    return int(value)


def _as_float(value: Any) -> float:
    if value is None or isinstance(value, bool | list | dict):
        raise ValueError(f"not a number: {type(value).__name__}")
    return float(value)


def _as_name_set(value: Any) -> frozenset[str]:
    """A claim holding a list of names ("Physics", "Gujarat", ...), in
    either shape a published claim can legitimately carry: a
    comma-separated string, or a real JSON list (`Claim.value` has
    allowed lists since RULES-3).

    A list is NOT stringified-then-split, which is what the pre-RULES-8
    `str(value).split(",")` did: `["Physics", "Chemistry"]` became the
    subject names `"['Physics'"` and `"'Chemistry']"`, and a student
    would be told, in so many words, that they were missing a subject
    called `['Physics'`. Anything that is neither string nor list raises,
    and the caller degrades that one criterion to `not_checked`."""
    if isinstance(value, str):
        parts: list[Any] = value.split(",")
    elif isinstance(value, list):
        parts = list(value)
    else:
        raise ValueError(f"not a list of names: {type(value).__name__}")
    names = {str(p).strip() for p in parts}
    return frozenset(n for n in names if n)


def _build_generic_criterion(field: str, row: dict[str, Any]) -> Criterion | None:
    """One published claim -> one `Criterion`, or `None` when the claim
    genuinely states nothing to check (an empty subject/domicile list).

    Raises `ValueError`/`TypeError` for a value it cannot read at all;
    `_criteria_from_claims` turns that into a `not_checked` entry.
    """
    claim_id = row["id"]
    value = row["value"]
    if field == "minimum_age":
        return minimum_age(_as_int(value), source_claim_id=claim_id)
    if field == "maximum_age":
        return maximum_age(_as_int(value), source_claim_id=claim_id)
    if field == "minimum_marks_percentage":
        return minimum_marks_percentage(_as_float(value), source_claim_id=claim_id)
    if field == "required_subjects":
        subjects = _as_name_set(value)
        return required_subjects(subjects, source_claim_id=claim_id) if subjects else None
    if field == "domicile_states":
        states = _as_name_set(value)
        return domicile_in(states, source_claim_id=claim_id) if states else None
    raise ValueError(f"no generic builder for claim field {field!r}")


GENERIC_CRITERION_FIELDS = (
    "minimum_age",
    "maximum_age",
    "minimum_marks_percentage",
    "required_subjects",
    "domicile_states",
)
"""Fixed order, so the criteria list is stable across requests rather
than following whatever order PostgREST happened to return rows in."""


def _criteria_from_claims(
    claim_rows: list[dict[str, Any]],
) -> tuple[tuple[Criterion, ...], tuple[NotChecked, ...]]:
    """Build the criteria list from whatever eligibility-shaped claims
    exist on this pathway — the fallback path, used when no published
    `rule_key` claim names a registered rule set.

    `claim_rows` is whatever the caller's RLS-scoped client was allowed
    to SELECT — for a guest or student that's published claims only
    (db/migrations/0001_init.sql's `claims_select_published` policy),
    but for a reviewer it is `status = 'published' or is_reviewer()`,
    i.e. every draft/in_review/superseded row too, so reviewers can
    review them. RLS controls fetchability, not "is this a fact" — this
    function still has to filter to published claims itself before
    using a row's value, the same defense-in-depth check
    app/planning/comparison.py's field_value_for() applies. Skipping it
    would mean a reviewer calling this route could get an eligibility
    outcome computed from an unapproved draft criterion — exactly what
    CLAUDE.md's maker-checker rule ("unapproved facts never reach public
    results") forbids, regardless of who's asking.

    Returns the criteria AND the `NotChecked` entries for any published
    claim whose value could not be read. A malformed row degrades to one
    declared-unchecked line; it never raises, so one bad row in the
    database cannot take down the whole response (same convention as
    `app/web/reviewer/queue.py`'s per-row resolution and
    `app/planning/comparison.py`'s per-field degradation).
    """
    published_rows = [row for row in claim_rows if row["status"] == ClaimStatus.published]
    by_field = {row["field"]: row for row in published_rows}
    criteria: list[Criterion] = []
    not_checked: list[NotChecked] = []

    for field in GENERIC_CRITERION_FIELDS:
        row = by_field.get(field)
        if row is None:
            continue
        try:
            criterion = _build_generic_criterion(field, row)
        except (ValueError, TypeError):
            # Opaque ids and the claim FIELD name only -- never the
            # stored value, and never anything the student sent
            # (docs/SECURITY.md "no personal data in logs"; this route's
            # module docstring on date_of_birth).
            logger.warning(
                "Unreadable published eligibility claim: field=%s claim_id=%s "
                "pathway_id=%s (criterion reported as not_checked; the rest of "
                "the response is unaffected)",
                field,
                row["id"],
                row["entity_id"],
            )
            not_checked.append(NotChecked(name=field, note=MALFORMED_CLAIM_NOTE))
            continue
        if criterion is not None:
            criteria.append(criterion)

    return tuple(criteria), tuple(not_checked)


PATHWAY_CLAIMS_EXAM_KEY = "pathway_claims"
"""The pseudo-`exam_key` of the ad-hoc `RuleSet` built from a pathway's
own published claims. Never registered in the registry, never matched by
a lookup, and never reported on the wire (`EligibilityResponse.
rule_version`/`cycle`/`jurisdiction` are `None` on this path) — it exists
only so the claims path and the named path go through the SAME
`evaluate_ruleset`, and therefore get the same no-verified-rules and
staleness guards. Two code paths with two different answers to "is an
empty criteria list a pass?" is exactly the bug this consolidation
removes."""


def _evidence_stale(
    criteria: tuple[Criterion, ...],
    published_claims_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> bool:
    """Is any published claim behind these criteria overdue for a
    recheck?

    Deliberately `trust_label_for_claim(...) == needs_rechecking` rather
    than a fresh comparison against `claims.review_due_date`: the Compare
    screen already decides "this fact needs rechecking" that way
    (`app/planning/comparison.py`, docs/DATA.md's trust-label mapping),
    and the requirements screen renders the very same label beside each
    criterion. A second, differently-derived staleness rule here would
    let one screen badge a fact `checked_against_official_source` while
    another called the same fact stale, on the same day, for the same
    student.
    """
    return any(
        trust_label_for_claim(
            _row_to_claim(claim_row),
            sources_by_id.get(claim_row["source_id"]),
            as_of=as_of,
        )
        == TrustLabel.needs_rechecking
        for c in criteria
        if c.source_claim_id and (claim_row := published_claims_by_id.get(c.source_claim_id))
    )


def _winning_rule_key_row(published_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Which published `rule_key` claim applies, when a pathway somehow
    has more than one.

    docs/CONTRACTS.md "Entity vocabulary" settles the general case ("two
    published claims on one field: later `checked_at` wins, tie broken by
    later source publication date, then lower claim id"), and the
    flagging half of that rule — "the loser is flagged for review, never
    silently discarded" — is not built anywhere in this codebase yet.
    What is in scope here is the deterministic half: taking whichever row
    PostgREST happened to return first would mean the SAME pathway could
    be evaluated against two different cycles' rules on two consecutive
    requests, which is precisely what `app.rules.ruleset`'s exact-match
    guard exists to make impossible.

    So: latest `verification_date` wins, ties broken by lowest claim id
    (`verification_date` is a `date` column, returned as `YYYY-MM-DD`,
    where lexicographic order IS chronological order). Sorting by id
    first and then taking `max` by date works because `max` returns the
    first maximal element it sees. The source-publication-date tier of
    the contract's rule is skipped: this function is given claim rows
    only, and fetching every candidate's source just to break a tie that
    the claim id already breaks deterministically would be a query for
    no gain.
    """
    candidates = sorted(
        (row for row in published_rows if row["field"] == RULE_KEY_FIELD),
        key=lambda row: str(row["id"]),
    )
    if not candidates:
        return None
    return max(candidates, key=lambda row: str(row["verification_date"]))


def _resolve_and_evaluate(
    claim_rows: list[dict[str, Any]],
    student: EligibilityInput,
    published_claims_by_id: dict[str, dict[str, Any]],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> tuple[RuleSetResult, bool, tuple[NotChecked, ...]]:
    """Pick the rule source for this pathway and run it.

    Returns `(result, named, extra_not_checked)` — `named` is True when a
    published `rule_key` claim drove the lookup, which is what decides
    whether `rule_version`/`cycle`/`jurisdiction` are meaningful enough
    to put on the wire.

    **An UNPUBLISHED `rule_key` claim is ignored entirely** (the pathway
    falls back to its published claims, exactly as if the draft did not
    exist) rather than being honoured as "a rule set is named, so report
    not_checked". A reviewer's RLS-scoped client can SELECT draft rows,
    so honouring a draft `rule_key` would let an unapproved row change
    what that reviewer sees — here by BLANKING a pathway's real published
    criteria instead of adding fake ones, but it is the same
    maker-checker bypass `TestDraftClaimsNeverAffectEligibilityOutcome`
    was written to catch, pointed the other way. A draft is not a fact,
    in either direction.
    """
    published_rows = [row for row in claim_rows if row["status"] == ClaimStatus.published]
    rule_key_row = _winning_rule_key_row(published_rows)

    if rule_key_row is not None:
        raw_value = rule_key_row["value"]
        exam_key = raw_value.strip() if isinstance(raw_value, str) else ""
        raw_cycle = rule_key_row.get("academic_cycle")
        cycle = raw_cycle.strip() if isinstance(raw_cycle, str) else ""
        jurisdiction = rule_key_row.get("jurisdiction") or ""
        extra: tuple[NotChecked, ...] = ()
        if not exam_key or not cycle or not jurisdiction:
            # A named rule set that cannot be identified is NOT quietly
            # downgraded to the generic claims path: a pathway whose
            # content says "use the NEET-UG rules" must never be answered
            # with a different, incidentally-published set of criteria.
            # The lookup below will find nothing and report
            # no_verified_rules; this note says why.
            logger.warning(
                "Unreadable published %s claim: claim_id=%s pathway_id=%s "
                "(no named rule set applied; reporting no_verified_rules)",
                RULE_KEY_FIELD,
                rule_key_row["id"],
                rule_key_row["entity_id"],
            )
            extra = (NotChecked(name=RULE_KEY_FIELD, note=UNREADABLE_RULE_KEY_NOTE),)
        registry = _rule_set_registry(get_settings().app_env)
        rule_set = get_rule_set(
            registry, exam_key=exam_key, cycle=cycle, jurisdiction=jurisdiction
        )
        if rule_set is None:
            # `evaluate_for_exam` re-does the lookup above, deliberately:
            # its own honest "nothing registered for this key" result
            # (`rule_version="unregistered"`, `no_verified_rules=True`) is
            # not worth hand-copying here just to save one dict lookup.
            return (
                evaluate_for_exam(
                    registry,
                    exam_key=exam_key,
                    cycle=cycle,
                    jurisdiction=jurisdiction,
                    eligibility_input=student,
                    as_of=as_of,
                ),
                True,
                extra,
            )
        result = evaluate_ruleset(
            rule_set,
            student,
            as_of=as_of,
            evidence_stale=_evidence_stale(
                rule_set.criteria, published_claims_by_id, sources_by_id, as_of=as_of
            ),
        )
        return result, True, extra

    criteria, malformed = _criteria_from_claims(claim_rows)
    ad_hoc = RuleSet(
        exam_key=PATHWAY_CLAIMS_EXAM_KEY,
        cycle="",
        # Never cycle-stale: criteria assembled from this pathway's own
        # claims are not scoped to an admission cycle at all, and each
        # one's freshness is already carried by `evidence_stale` below.
        cycle_end=date.max,
        jurisdiction="",
        rule_version="",
        criteria=criteria,
        not_checked=malformed,
    )
    result = evaluate_ruleset(
        ad_hoc,
        student,
        as_of=as_of,
        evidence_stale=_evidence_stale(
            criteria, published_claims_by_id, sources_by_id, as_of=as_of
        ),
    )
    return result, False, ()


def check_eligibility(
    pathway_id: str,
    age: int | None,
    marks_percentage: float | None,
    subjects_studied: str | None,
    domicile_state: str | None,
    db: Client,
    *,
    date_of_birth: date | None = None,
    category: str | None = None,
    year_of_passing: int | None = None,
) -> EligibilityResponse:
    """The actual eligibility-checking logic — deliberately a plain,
    directly-callable function rather than a route itself.

    SEC-5: personal inputs must never be a query param or reach a URL
    (docs/CONTRACTS.md "Every personal input ... is POST-only"), so this
    is called from TWO routes below — `GET /eligibility` (pathway_id
    only) and `POST /eligibility` (every field, in the body) — instead
    of being the GET route directly. It is also still called straight
    from Python by app/web/requirements_pages.py's own requirements
    screen (one fetch/rule-evaluation, reused, never a second copy of
    this logic or an HTTP round-trip to our own JSON route).

    RULES-8's three new personal inputs (`date_of_birth`, `category`,
    `year_of_passing` — feeding `app/rules/criteria_dates.py`'s real
    DOB-cutoff criteria and `app/rules/criteria_extra.py`'s per-category
    and year-of-passing ones) are keyword-only WITH defaults, so every
    existing positional caller keeps working untouched. `pathway_id` is
    assumed already shape-checked by the caller (both routes below, and
    `app/web/requirements_pages.py`, do it) — this function does the
    evaluation, not the request validation.
    """
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .eq("entity_id", pathway_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)

    # Resolved for display only -- same defense-in-depth as
    # _criteria_from_claims: only a PUBLISHED claim's source is ever
    # exposed. A draft criterion never contributes a Criterion in the
    # first place, so it can't reach this map either, but the explicit
    # published_rows filter here means that stays true even if this
    # function is ever refactored independently of that one.
    published_rows = [row for row in claim_rows if row["status"] == ClaimStatus.published]
    published_claims_by_id = {row["id"]: row for row in published_rows}
    source_ids = {row["source_id"] for row in published_rows}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    student = EligibilityInput(
        age=age,
        marks_percentage=marks_percentage,
        subjects_studied=(
            frozenset(s.strip() for s in subjects_studied.split(",") if s.strip())
            if subjects_studied
            else frozenset()
        ),
        domicile_state=domicile_state,
        category=category,
        date_of_birth=date_of_birth,
        year_of_passing=year_of_passing,
    )

    as_of = today_ist()
    result, named, extra_not_checked = _resolve_and_evaluate(
        claim_rows,
        student,
        published_claims_by_id,
        sources_by_id,
        as_of=as_of,
    )

    criteria_out = []
    for c in result.eligibility.criteria:
        claim_row = published_claims_by_id.get(c.source_claim_id) if c.source_claim_id else None
        source = sources_by_id.get(claim_row["source_id"]) if claim_row else None
        trust_label = (
            trust_label_for_claim(_row_to_claim(claim_row), source, as_of=as_of).value
            if claim_row
            else None
        )
        criteria_out.append(
            CriterionResultOut(
                name=c.name,
                outcome=c.outcome.value,
                explanation=c.explanation,
                source_claim_id=c.source_claim_id,
                source_authority=source.authority_name if source else None,
                # RULES-8: the ONE url-scheme guard
                # (app/planning/comparison.py), imported rather than
                # re-implemented here -- this route used to carry its own
                # weaker `startswith` copy of the same 2026-09-20
                # security fix.
                source_url=safe_source_url(source.official_url) if source else None,
                verification_date=claim_row["verification_date"] if claim_row else None,
                trust_label=trust_label,
            )
        )

    not_checked_out = [
        NotCheckedOut(name=n.name, note=n.note)
        for n in (*result.not_checked, *extra_not_checked)
    ]
    return EligibilityResponse(
        outcome=result.outcome.value,
        criteria=criteria_out,
        as_of=as_of,
        rule_version=(result.rule_version or None) if named else None,
        cycle=(result.cycle or None) if named else None,
        jurisdiction=(result.jurisdiction or None) if named else None,
        no_verified_rules=result.no_verified_rules,
        stale=result.cycle_stale or result.evidence_stale,
        not_checked=not_checked_out,
    )


class EligibilityCheckRequest(BaseModel):
    """POST body for `POST /eligibility` (SEC-5). `pathway_id` travels
    here too, alongside the personal fields, rather than staying a query
    param on the POST — a request body is the one place none of this can
    end up echoed into a URL, a Location header or browser history.

    Every range bound below exists so a malformed value is a clean 422
    from FastAPI's own validation, never a 500 and never a criterion
    silently evaluated against nonsense (a `marks_percentage` of 900
    would `meet` every published threshold there is). None of these is an
    eligibility RULE — no exam's requirements live in this file; they are
    only "this cannot be a real answer" guards.
    """

    pathway_id: str
    age: int | None = Field(default=None, ge=MIN_AGE_YEARS, le=MAX_AGE_YEARS)
    marks_percentage: float | None = Field(
        default=None, ge=MIN_MARKS_PERCENTAGE, le=MAX_MARKS_PERCENTAGE
    )
    subjects_studied: str | None = None
    """Comma-separated, e.g. Physics,Chemistry,Biology."""
    domicile_state: str | None = None
    date_of_birth: date | None = None
    """RULES-8. Feeds `app/rules/criteria_dates.py`'s real DOB-cutoff
    criteria ("completed 17 years as on 31 December of the exam year"),
    which the integer `age` above cannot express. docs/CONTRACTS.md
    "Duration, dates, cycle, DOB": POST body only, never a query param,
    never in a URL, **never logged**, never in analytics — no logger call
    in this module accepts it, or any other personal input."""
    category: str | None = None
    """RULES-8. Looked up in a rule set's own per-category thresholds or
    age relaxations. An unrecognised category is
    `insufficient_information`, never a rejection
    (`app/rules/criteria_extra.py`)."""
    year_of_passing: int | None = None
    """RULES-8. Feeds `passed_or_appearing_in_years`."""

    @field_validator("date_of_birth")
    @classmethod
    def _plausible_date_of_birth(cls, value: date | None) -> date | None:
        """A future date of birth, or one implying an impossible age, is
        rejected outright rather than fed to `age_on()` — which would
        happily return a negative age and let a `minimum_age_on_date`
        criterion report a confident `does_not_meet` derived from a
        typo. Bounds are measured against the SERVER's Asia/Kolkata today
        (`today_ist`), never a client-supplied date.

        Same "not in the future" shape as `app/api/auth.py`'s
        `SignUpRequest` validator; the lower bound is new here because
        that route's DOB is a consent gate, while this one is arithmetic
        input.
        """
        if value is None:
            return None
        today = today_ist()
        if value > today:
            raise ValueError("date_of_birth cannot be in the future.")
        if value.year < today.year - MAX_AGE_YEARS:
            raise ValueError(
                f"date_of_birth implies an age over {MAX_AGE_YEARS}; check the year."
            )
        return value

    @field_validator("year_of_passing")
    @classmethod
    def _plausible_year_of_passing(cls, value: int | None) -> int | None:
        """A student may legitimately name a year they have not reached
        yet (the year they expect to pass), so the upper bound is this
        Asia/Kolkata year plus a window, not "this year"."""
        if value is None:
            return None
        latest = today_ist().year + YEAR_OF_PASSING_FUTURE_LIMIT_YEARS
        if not (EARLIEST_YEAR_OF_PASSING <= value <= latest):
            raise ValueError(
                f"year_of_passing must be between {EARLIEST_YEAR_OF_PASSING} and {latest}."
            )
        return value

    @field_validator("category")
    @classmethod
    def _tidy_category(cls, value: str | None) -> str | None:
        """A submitted-but-blank category means "not provided" — the same
        convention `app/web/requirements_pages.py`'s `_none_if_blank`
        uses — and must stay `None` so a per-category criterion reports
        `insufficient_information` rather than looking up the empty
        string and finding nothing."""
        if value is None:
            return None
        tidied = value.strip()
        if not tidied:
            return None
        if len(tidied) > MAX_CATEGORY_LENGTH:
            raise ValueError(f"category must be at most {MAX_CATEGORY_LENGTH} characters.")
        return tidied


@router.get("/eligibility", response_model=EligibilityResponse)
def get_eligibility(
    pathway_id: str = Query(...),
    db: Client = Depends(get_db_client),
) -> EligibilityResponse:
    """SEC-5: GET keeps `pathway_id` only — no personal input may ever
    be a query param (docs/CONTRACTS.md "Every personal input ... is
    POST-only"). Every criterion comes back `insufficient_information`
    (nothing about a student is known yet); that is this endpoint's
    normal pre-fill response, not an error. Personal fields live on
    `POST /eligibility` below."""
    if not _looks_like_a_uuid(pathway_id):
        raise HTTPException(status_code=422, detail="pathway_id must be a valid id.")
    return check_eligibility(pathway_id, None, None, None, None, db)


@router.post("/eligibility", response_model=EligibilityResponse)
def post_eligibility(
    body: EligibilityCheckRequest, db: Client = Depends(get_db_client)
) -> EligibilityResponse:
    """SEC-5: the only route that accepts a personal input — always in a
    POST body, never a query string."""
    if not _looks_like_a_uuid(body.pathway_id):
        raise HTTPException(status_code=422, detail="pathway_id must be a valid id.")
    return check_eligibility(
        body.pathway_id,
        body.age,
        body.marks_percentage,
        body.subjects_studied,
        body.domicile_state,
        db,
        date_of_birth=body.date_of_birth,
        category=body.category,
        year_of_passing=body.year_of_passing,
    )
