"""Retrieval — the fetch-and-defensively-re-filter half of Ask BCION
(AI-5). Given a pathway id, a career id or a claim id, this module reads
`claims`/`sources` rows and turns them into compact, trust-checked
records a future prompt-template runner (a later card, out of scope
here) can hand to `app.ai.grounding`/`app.ai.schemas` as grounding
material. It also calls the existing rules engines (`app/rules/cost.py`,
`app/rules/timeline.py`, `app/rules/eligibility.py`) to expose the
derived, multi-claim figures those engines compute (a total cost, a
total duration) rather than re-deriving them here.

## Never trust the caller's RLS scope alone

CLAUDE.md: "AI never invents facts ... No record -> answer is 'not
verified'." A reviewer's own RLS-scoped Supabase client can legitimately
`SELECT` draft/in_review/superseded claims (db/migrations/0001_init.sql),
so whatever this module is handed back from a query is NOT already
guaranteed to be "safe to ground an AI answer on" just because *some*
caller's RLS let it through. This module re-checks, in Python, on every
fetch, regardless of who is calling: `claim.status == ClaimStatus.published`
AND the claim's `Source.source_type != SourceType.synthetic` — the exact
same "never trust a caller blindly" principle already applied by
`app/planning/comparison.py`'s `field_value_for()` and
`app/api/eligibility.py`'s `_criteria_from_claims()` (see those two
functions' own docstrings). `_grounded_claims()` below is this module's
own, independently-written copy of that same check — deliberately not
imported from `app/ai/grounding.py`'s identically-purposed private
`_grounded_claims`, so the two modules stay two independent
implementations of the same rule rather than one shared function a
single bug could silently break for both (matching how comparison.py,
eligibility.py and grounding.py already each carry their own copy rather
than a shared helper).

`field_value_for()` itself (imported, not re-implemented — see below)
performs this exact same check a SECOND time, per field, when building
each record's value/label. So every record emitted here has passed the
check twice, independently, before it can carry a value.

## Freshness / staleness

`Flag any claim past its freshness SLA using the same constant and
comparison `app/ai/grounding.py` already uses` — `_is_stale()` below
imports `DEFAULT_FRESHNESS_SLA_DAYS` from `app.planning.comparison` (the
one place that constant is defined) and reproduces the exact same
`(as_of - claim.verification_date) > timedelta(days=...)` comparison
`app/ai/grounding.py` and `app/planning/comparison.py`'s
`trust_label_for_claim` already use. A stale claim is still offered as a
record (staleness is not the same axis as "not_available" — an
unpublished or synthetic-backed claim never reaches a record at all, a
stale one does, flagged `is_stale=True`) — the same choice
`app/ai/grounding.py`'s module docstring documents and the same reason:
a caller further up the stack decides what to do with a stale-but-real
fact, this module's job is only to tell the truth about which is which.

## Compact records vs. derived numbers — two different shapes, on purpose

A "compact record" (`RetrievedRecord`) is always backed by exactly ONE
real, grounded `Claim` — `id`, `field`, `value`, `source_authority`,
`source_url` (via `field_value_for`'s own `safe_source_url` call — never
a second URL-safety check written here) and `is_stale`. A cost total or
a timeline total is NOT backed by one claim; it is computed from several
(every fee-component claim, every `stage:<order>:*` claim), by
`app/rules/cost.py`/`app/rules/timeline.py` themselves. Forcing a
multi-claim total into the single-claim `RetrievedRecord` shape would
either invent a fake "backing claim id" for it or silently drop the
provenance of every claim that went into it — so `pathway_cost_summary()`
and `pathway_timeline()` return the rules engines' own result types
(`CostSummary`, `TimelineResult`) unchanged, and a caller that wants to
cite the *individual* fee-component/stage claims behind those totals
gets them from `fetch_pathway_records()`'s ordinary per-field records
(the same claims, both ways — nothing here is computed twice from two
different claim sets).

## Eligibility — criteria, never an evaluated outcome

Unlike cost and timeline, an eligibility *outcome* (`meets` /
`does_not_meet` / `insufficient_information`) is only meaningful once it
is evaluated against a real student's answers
(`app.rules.eligibility.EligibilityInput`) — and this module, by this
card's own contract, must never import anything student-identity-bearing
and never sees a student's answers. Running `evaluate_eligibility()`
against an empty/default `EligibilityInput()` here would be either
useless (every generic criterion reports `insufficient_information` when
nothing is supplied) or actively dangerous (an entity with ZERO
published eligibility-shaped claims evaluates to a vacuous `meets` —
`app/api/eligibility.py`'s own module docstring calls this out as the
reason it never calls `evaluate_eligibility()` directly either, instead
routing through `evaluate_ruleset()`, which this module does not import).
A fabricated "meets" reaching an AI-facing record — even indirectly — is
exactly what CLAUDE.md's "no guarantees" rule forbids. `pathway_eligibility_criteria()`
therefore calls the existing per-criterion BUILDER functions
(`minimum_age`, `maximum_age`, `minimum_marks_percentage`,
`required_subjects`, `domicile_in` — real `app.rules.eligibility`
functions, not re-implemented arithmetic) to turn this pathway's own
published, re-verified eligibility-shaped claims into `Criterion`
objects, and returns them UNEVALUATED. `len(...)` on the result is the
one safe "derived number" available without a student: how many
eligibility requirements this pathway has actually published, each with
its own `source_claim_id` a caller can resolve back to a `RetrievedRecord`
via `fetch_pathway_records()`.

## What this module does NOT do (the import guard)

This module must never import anything from a student-identity-bearing
table or module (`student_profiles`, `saved_plans`, `guest_session`, ...
— SEC-5/docs/DATA.md "Minimisation") — it only ever reads career,
pathway, claim and source data. `tests/unit/test_ai_retrieval.py`'s
`TestImportGuard` inspects this module's own AST (import statements) and
raw source text so that a future edit accidentally adding such an import
fails a test rather than depending on a human catching it in review.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final, cast

from supabase import Client

from app.ai.schemas import MAX_ID_CHARS
from app.data.models import DEFAULT_JURISDICTION, Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.planning.comparison import (
    DEFAULT_FRESHNESS_SLA_DAYS,
    assemble_cost_summary,
    field_value_for,
)
from app.planning.timeline_assembly import stages_from_claims
from app.rules.cost import CostSummary
from app.rules.eligibility import (
    Criterion,
    domicile_in,
    maximum_age,
    minimum_age,
    minimum_marks_percentage,
    required_subjects,
)
from app.rules.timeline import TimelineResult, compute_timeline

ENTITY_TYPE_PATHWAY: Final[str] = "Pathway"
ENTITY_TYPE_CAREER: Final[str] = "Career"

#: The `entity_type` values this module will fetch claims for. Matches
#: `app/web/reviewer/queue.py`'s `_ENTITY_TABLES` vocabulary — the only
#: two entity types any route in this codebase currently resolves.
_KNOWN_ENTITY_TYPES: Final[tuple[str, ...]] = (ENTITY_TYPE_PATHWAY, ENTITY_TYPE_CAREER)

#: The generic, single-claim eligibility fields a pathway (or career) may
#: publish — the same five fields `app/api/eligibility.py`'s
#: `GENERIC_CRITERION_FIELDS` recognises, kept here as this module's own
#: constant rather than imported from that (forbidden-to-edit,
#: route-shaped) module. Fixed order for a deterministic criteria list.
GENERIC_ELIGIBILITY_FIELDS: Final[tuple[str, ...]] = (
    "minimum_age",
    "maximum_age",
    "minimum_marks_percentage",
    "required_subjects",
    "domicile_states",
)


@dataclass(frozen=True)
class RetrievedRecord:
    """One compact, already trust-checked fact — see the module
    docstring's "Compact records vs. derived numbers" section for why
    this is always backed by exactly one `Claim`."""

    id: str
    """A server-assigned short id. The real claim id when it already fits
    `app.ai.schemas.MAX_ID_CHARS` (true for every claim id this codebase
    actually issues — UUID strings, `app/data/models.py`); otherwise a
    deterministic shortened form (`_short_id` below) so a future, longer
    id scheme can never violate the outbound-payload id bound."""
    field: str
    value: str | int | float | bool | list[Any] | dict[str, Any] | None
    source_authority: str | None
    source_url: str | None
    is_stale: bool


def _short_id(claim_id: str) -> str:
    """See `RetrievedRecord.id`'s docstring. The hash is truncated to
    `MAX_ID_CHARS`, deterministic (same claim id -> same short id every
    call), and never needed in practice today since every real claim id
    is well under the bound — this exists only so the bound can never be
    silently violated if that ever changes."""
    if len(claim_id) <= MAX_ID_CHARS:
        return claim_id
    return hashlib.sha256(claim_id.encode("utf-8")).hexdigest()[:MAX_ID_CHARS]


def _is_stale(claim: Claim, *, as_of: date) -> bool:
    """Mirrors `app/ai/grounding.py`'s own `_is_stale` exactly — same
    constant, same comparison (see the module docstring's "Freshness /
    staleness" section). Not imported from `grounding.py`, for the same
    independent-implementation reason `_grounded_claims` below is not."""
    return (as_of - claim.verification_date) > timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS)


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """Identical in shape to `app/api/compare.py`'s file-local helper of
    the same name (kept file-local here too, matching this codebase's
    convention of not coupling otherwise-unrelated modules over a few
    lines of row-mapping)."""
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
        jurisdiction=row.get("jurisdiction") or DEFAULT_JURISDICTION,
        academic_cycle=row.get("academic_cycle"),
        currency=row.get("currency"),
    )


def _row_to_source(row: dict[str, Any]) -> Source:
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
        jurisdiction=row.get("jurisdiction") or DEFAULT_JURISDICTION,
    )


def _grounded_claims(claims: list[Claim], sources_by_id: dict[str, Source]) -> list[Claim]:
    """The defensive re-filter — see the module docstring's "Never trust
    the caller's RLS scope alone". Drops anything that is not
    `ClaimStatus.published`, anything backed by a `SourceType.synthetic`
    source, and anything whose source cannot be resolved at all (nothing
    to cite means nothing to verify against). Freshness is intentionally
    NOT checked here — a stale claim is still real, published,
    non-synthetic grounding material; see `_is_stale`."""
    grounded = []
    for claim in claims:
        if claim.status != ClaimStatus.published:
            continue
        source = sources_by_id.get(claim.source_id)
        if source is None:
            continue
        if source.source_type == SourceType.synthetic:
            continue
        grounded.append(claim)
    return grounded


def _claims_by_field(grounded_claims: list[Claim]) -> dict[str, Claim]:
    """One claim per field, built ONLY from already-`_grounded_claims`-
    filtered claims — so a draft/in_review/superseded duplicate for the
    same field can never shadow a real published one in this dict (the
    risk a naive `{row["field"]: claim for row in <every row>}` build,
    the shape `app/api/compare.py` uses on its own already-published-only
    query, would carry if applied here to a broader, re-checked-in-Python
    fetch). If more than one published, non-synthetic claim exists for
    the same field, the last one in `grounded_claims` wins — the same
    tie-break-by-iteration-order `app/api/compare.py` already accepts;
    resolving that properly is `docs/CONTRACTS.md`'s "Entity vocabulary"
    tie-break rule, which is not this module's job to build."""
    return {claim.field: claim for claim in grounded_claims}


def _fetch_claims_and_sources(
    db: Client, entity_type: str, entity_id: str
) -> tuple[list[Claim], dict[str, Source]]:
    """The one I/O step. Two queries total (claims, then their sources),
    matching `app/api/compare.py`'s `assemble_comparisons` shape. Returns
    EVERY claim row the caller's client could see, regardless of status —
    the defensive re-filter happens entirely in `_grounded_claims`, never
    here, so this function's own behaviour never has to be trusted."""
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", entity_type)
        .eq("entity_id", entity_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)
    claims = [_row_to_claim(row) for row in claim_rows]

    source_ids = {claim.source_id for claim in claims}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}
    return claims, sources_by_id


def _record_for_field(
    field: str,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> RetrievedRecord | None:
    """`None` when `field_value_for` says `not_available` for this field
    (no claim, draft, stale-and-sourceless, synthetic-sourced) — the same
    second, independent check the module docstring describes. Otherwise
    the claim behind this field is, by construction, already in
    `claims_by_field` (built from `_grounded_claims`'s output), so it is
    safe to resolve directly for `.id`/`.verification_date`."""
    fv = field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
    if fv.label == TrustLabel.not_available:
        return None
    claim = claims_by_field[field]
    return RetrievedRecord(
        id=_short_id(claim.id),
        field=field,
        value=fv.value,
        source_authority=fv.source_authority,
        source_url=fv.source_url,
        is_stale=_is_stale(claim, as_of=as_of),
    )


def fetch_entity_records(
    db: Client, entity_type: str, entity_id: str, *, as_of: date | None = None
) -> tuple[RetrievedRecord, ...]:
    """Every published, non-synthetic, source-resolvable claim on
    `(entity_type, entity_id)`, one `RetrievedRecord` per field, sorted by
    field name for a deterministic order. `entity_type` must be
    `"Pathway"` or `"Career"` (`ValueError` otherwise) — the two entity
    types claims are ever attached to in this codebase
    (`app/web/reviewer/queue.py`'s `_ENTITY_TABLES`). Callers are assumed
    to have already shape-checked `entity_id` (a UUID), the same
    assumption `app/api/eligibility.py`'s `check_eligibility` documents
    for its own `pathway_id` parameter — this function does retrieval,
    not request validation.
    """
    if entity_type not in _KNOWN_ENTITY_TYPES:
        raise ValueError(
            f"entity_type must be one of {_KNOWN_ENTITY_TYPES}, got {entity_type!r}"
        )
    resolved_as_of = as_of if as_of is not None else date.today()
    claims, sources_by_id = _fetch_claims_and_sources(db, entity_type, entity_id)
    claims_by_field = _claims_by_field(_grounded_claims(claims, sources_by_id))

    records = []
    for field in sorted(claims_by_field):
        record = _record_for_field(field, claims_by_field, sources_by_id, as_of=resolved_as_of)
        if record is not None:
            records.append(record)
    return tuple(records)


def fetch_pathway_records(
    db: Client, pathway_id: str, *, as_of: date | None = None
) -> tuple[RetrievedRecord, ...]:
    return fetch_entity_records(db, ENTITY_TYPE_PATHWAY, pathway_id, as_of=as_of)


def fetch_career_records(
    db: Client, career_id: str, *, as_of: date | None = None
) -> tuple[RetrievedRecord, ...]:
    return fetch_entity_records(db, ENTITY_TYPE_CAREER, career_id, as_of=as_of)


def fetch_claim_record(
    db: Client, claim_id: str, *, as_of: date | None = None
) -> RetrievedRecord | None:
    """A single claim by id, re-verified exactly like every other record
    here (published, non-synthetic-sourced) — `None` when the claim does
    not exist, or exists but does not pass `_grounded_claims`. Callers are
    assumed to have already shape-checked `claim_id`, same convention as
    `fetch_entity_records`."""
    resolved_as_of = as_of if as_of is not None else date.today()
    claim_result = db.table("claims").select("*").eq("id", claim_id).execute()
    claim_rows = cast("list[dict[str, Any]]", claim_result.data)
    if not claim_rows:
        return None
    claim = _row_to_claim(claim_rows[0])

    source_result = db.table("sources").select("*").eq("id", claim.source_id).execute()
    source_rows = cast("list[dict[str, Any]]", source_result.data)
    sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    grounded = _grounded_claims([claim], sources_by_id)
    if not grounded:
        return None
    claims_by_field = _claims_by_field(grounded)
    return _record_for_field(
        grounded[0].field, claims_by_field, sources_by_id, as_of=resolved_as_of
    )


def pathway_cost_summary(
    db: Client, pathway_id: str, *, as_of: date | None = None
) -> CostSummary:
    """The pathway's cost total, computed by `app/rules/cost.py` (via
    `app.planning.comparison.assemble_cost_summary`, which builds the
    `FeeComponent`/`Money` inputs from `field_value_for` — never
    re-derived here). See the module docstring's "Compact records vs.
    derived numbers"."""
    resolved_as_of = as_of if as_of is not None else date.today()
    claims, sources_by_id = _fetch_claims_and_sources(db, ENTITY_TYPE_PATHWAY, pathway_id)
    claims_by_field = _claims_by_field(_grounded_claims(claims, sources_by_id))
    return assemble_cost_summary(claims_by_field, sources_by_id, as_of=resolved_as_of)


def pathway_timeline(
    db: Client, pathway_id: str, *, as_of: date | None = None
) -> TimelineResult:
    """The pathway's timeline total, computed by `app/rules/timeline.py`
    (`compute_timeline`) over the `Stage` list
    `app.planning.timeline_assembly.stages_from_claims` builds from this
    pathway's published `stage:<order>:*` claims — never re-derived
    here."""
    resolved_as_of = as_of if as_of is not None else date.today()
    claims, sources_by_id = _fetch_claims_and_sources(db, ENTITY_TYPE_PATHWAY, pathway_id)
    claims_by_field = _claims_by_field(_grounded_claims(claims, sources_by_id))
    stages = stages_from_claims(claims_by_field, sources_by_id, as_of=resolved_as_of)
    return compute_timeline(stages)


def _as_int(value: Any) -> int:
    """Type coercion only — not the "arithmetic" the module docstring
    means to never duplicate. Mirrors the shape (not the code — that
    function is private to a forbidden-to-edit route module)
    `app/api/eligibility.py`'s own `_as_int` uses."""
    if value is None or isinstance(value, bool | list | dict):
        raise ValueError(f"not a number: {type(value).__name__}")
    return int(value)


def _as_float(value: Any) -> float:
    if value is None or isinstance(value, bool | list | dict):
        raise ValueError(f"not a number: {type(value).__name__}")
    return float(value)


def _as_name_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        parts: list[Any] = value.split(",")
    elif isinstance(value, list):
        parts = list(value)
    else:
        raise ValueError(f"not a list of names: {type(value).__name__}")
    names = {str(p).strip() for p in parts}
    return frozenset(n for n in names if n)


def _build_criterion(field: str, claim: Claim) -> Criterion | None:
    """One re-verified, published claim -> one `Criterion`, built by
    calling the real `app.rules.eligibility` functions (never
    re-implementing what "minimum age" or "required subjects" mean).
    `None` when the claim genuinely states nothing to check (an empty
    subject/domicile list); raises `ValueError`/`TypeError` for a value
    that cannot be read at all, which `pathway_eligibility_criteria`
    below treats as "skip this one field", never as an error for the
    whole pathway."""
    value = claim.value
    if field == "minimum_age":
        return minimum_age(_as_int(value), source_claim_id=claim.id)
    if field == "maximum_age":
        return maximum_age(_as_int(value), source_claim_id=claim.id)
    if field == "minimum_marks_percentage":
        return minimum_marks_percentage(_as_float(value), source_claim_id=claim.id)
    if field == "required_subjects":
        subjects = _as_name_set(value)
        return required_subjects(subjects, source_claim_id=claim.id) if subjects else None
    if field == "domicile_states":
        states = _as_name_set(value)
        return domicile_in(states, source_claim_id=claim.id) if states else None
    raise ValueError(f"no generic builder for claim field {field!r}")


def pathway_eligibility_criteria(db: Client, pathway_id: str) -> tuple[Criterion, ...]:
    """This pathway's published, re-verified eligibility-shaped claims, as
    UNEVALUATED `Criterion` objects — see the module docstring's
    "Eligibility — criteria, never an evaluated outcome" section for why
    this deliberately never calls `evaluate_eligibility()`. `len(...)` on
    the result is a safe derived number: how many eligibility
    requirements this pathway has actually published."""
    claims, sources_by_id = _fetch_claims_and_sources(db, ENTITY_TYPE_PATHWAY, pathway_id)
    claims_by_field = _claims_by_field(_grounded_claims(claims, sources_by_id))

    criteria: list[Criterion] = []
    for field in GENERIC_ELIGIBILITY_FIELDS:
        claim = claims_by_field.get(field)
        if claim is None:
            continue
        try:
            criterion = _build_criterion(field, claim)
        except (ValueError, TypeError):
            continue
        if criterion is not None:
            criteria.append(criterion)
    return tuple(criteria)
