"""GET /compare — Compare screen (docs/UI.md "Comparison fields").

Assembles the comparison-field structure for 2-3 pathways, using the
pure trust-label logic in app/planning/comparison.py over real,
currently-visible claims (RLS decides what "currently visible" means for
a given caller — a guest sees published only, a reviewer sees drafts
too). This route does the I/O; comparison.py stays pure and unit-tested.
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_db_client
from app.data.models import DEFAULT_JURISDICTION, Claim, ClaimStatus, Source, SourceType
from app.planning.comparison import (
    FieldValue,
    ProgrammeCostBreakdown,
    assemble_cost_breakdown,
    assemble_cost_summary,
    field_value_for,
)
from app.rules.cost import CostSummary

router = APIRouter(tags=["compare"])

# The non-cost fields shown on the Compare screen for this first slice.
# docs/UI.md lists more (work realities, alternatives) — added as the
# content track produces claims for them; an empty field degrades to
# "not_available" rather than a missing key, so adding one later is
# additive, not breaking.
COMPARISON_FIELDS = ["entry_requirements", "main_stages", "time_range", "location"]

MIN_PATHWAYS = 2
MAX_PATHWAYS = 3


def _looks_like_a_uuid(value: str) -> bool:
    """Local to this route file by the same convention
    app/web/pages.py's identically-named helper documents -- small
    per-route shape checks stay file-local rather than shared.

    Security-review finding, 2026-09-20 (MEDIUM): the JSON /compare
    route had zero UUID-shape validation on pathway_id before calling
    assemble_comparisons(), which passes it straight into a Postgres
    query -- a malformed id raised an uncaught postgrest APIError
    (Postgres code 22P02) that propagated as an unhandled 500.
    app/web/pages.py's HTML route already had this exact fix (for an
    earlier ux-qa-reviewer finding) but it was never applied here even
    though both routes now share assemble_comparisons() since a recent
    refactor.
    """
    try:
        uuid_module.UUID(value)
    except ValueError:
        return False
    return True


class FieldValueOut(BaseModel):
    value: str | int | float | bool | list[Any] | dict[str, Any] | None
    label: str
    source_url: str | None = None
    verification_date: date | None = None
    source_authority: str | None = None
    """Additive field (ux-qa-reviewer finding, 2026-09-19) — existing
    JSON consumers unaffected, a new optional key."""
    is_sample: bool = False
    """DATA-12 / docs/CONTRACTS.md "Settled — `is_sample`": this value came
    from a clearly-labelled SAMPLE claim, not a verified one, and must
    carry a visible label wherever it appears.

    True only when the backing claim is still `in_review` AND its Source
    is `synthetic` — i.e. exactly the rows
    `claims_select_demo_synthetic` (db/migrations/0007_demo_mode.sql)
    makes visible while demo mode is on. It is computed from the claim
    and source rows the caller already fetched, NOT from the application's
    own `DEMO_MODE` setting: the database decides what is visible, so the
    label has to be derived from what actually came back, or a
    misconfigured app process could render sample data with no label at
    all. A published claim is never a sample (the 0001 trigger makes a
    published synthetic claim impossible in the first place), so this
    stays False for every real verified fact.

    Additive with a False default — existing JSON consumers unaffected."""

    @classmethod
    def from_field_value(cls, fv: FieldValue, *, is_sample: bool = False) -> FieldValueOut:
        return cls(
            value=fv.value,
            label=fv.label.value,
            source_url=fv.source_url,
            verification_date=fv.verification_date,
            source_authority=fv.source_authority,
            is_sample=is_sample,
        )


class CostBreakdownOut(BaseModel):
    verified_charges: FieldValueOut
    estimated_additional_expenses: FieldValueOut
    potential_assistance_not_yet_awarded: FieldValueOut
    net_to_arrange: float | None = None
    """What the student needs to actually arrange: verified charges +
    estimated extras - CONFIRMED assistance only (app/rules/cost.py).
    `None` when verified_charges itself is not yet available -- never a
    confident-looking figure that's actually missing its main input.
    There is no confirmed_assistance source in this slice yet (that is
    student-specific award data, out of scope before M3's sign-in and
    consent work), so today this is verified + estimate with nothing
    subtracted; potential_assistance_not_yet_awarded, shown above, is
    never part of this number (Lite Build Pack §6: "an unawarded
    scholarship is never subtracted")."""


class PathwayComparisonOut(BaseModel):
    pathway_id: str
    fields: dict[str, FieldValueOut]
    cost: CostBreakdownOut


class CompareResponse(BaseModel):
    pathways: list[PathwayComparisonOut]


def _row_to_claim(row: dict[str, Any]) -> Claim:
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
        # SCOPE-3. `or DEFAULT_JURISDICTION` rather than a plain
        # `.get(..., DEFAULT_JURISDICTION)`: the key IS present on every
        # row once 0008 is applied, so the fallback is really for the
        # deploy window where this code is live and that migration is
        # not — and in that window PostgREST omits the key entirely.
        # `currency`/`academic_cycle` keep a None fallback because None
        # is their real, meaningful value (CONTRACTS.md: a money claim
        # with a null currency renders not_available), never a stand-in.
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


def _claim_is_sample(claim: Claim, sources_by_id: dict[str, Source]) -> bool:
    """Is this claim one of demo mode's clearly-labelled sample rows?

    The mirror image, in ordinary code, of what
    `claims_select_demo_synthetic` (db/migrations/0007_demo_mode.sql)
    lets through: `in_review` AND a `synthetic` Source. Both halves are
    required — an `in_review` claim from a real authority is an ordinary
    draft (and RLS never shows one to a guest at all), and a synthetic
    Source can never back a `published` claim because
    `forbid_publishing_synthetic_claims()` (0001_init.sql) refuses it.

    Unknown source id -> False is the right default rather than a
    fail-closed True: `sources_by_id` is built from the very ids these
    claims carry, so a miss means the source row was not visible to this
    caller, and labelling a fact "sample" on the strength of a row we
    could not read would put a false label on real content. The claim
    itself is the authority on its own status, and only an `in_review`
    claim can reach this branch.
    """
    if claim.status is not ClaimStatus.in_review:
        return False
    source = sources_by_id.get(claim.source_id)
    return source is not None and source.source_type is SourceType.synthetic


@dataclass(frozen=True)
class PathwayComparisonData:
    """The fully-assembled comparison for one pathway, before any
    presentation-layer choice about JSON vs HTML. This dataclass — not
    the JSON route below — is where "fetch claims, assemble trust
    labels, compute cost" actually happens, so app/web/pages.py's HTML
    rendering and this route's JSON response are guaranteed to show the
    exact same numbers, computed exactly once, by exactly the same code
    path. Duplicating this fetch-and-assemble logic for a second
    presentation layer would mean two chances to get the safety-critical
    trust-labelling wrong instead of one."""

    pathway_id: str
    fields: dict[str, FieldValue]
    cost_breakdown: ProgrammeCostBreakdown
    cost_summary: CostSummary
    sample_fields: frozenset[str] = frozenset()
    """DATA-12: the claim-field names on this pathway whose backing claim
    is a demo-mode sample row (see `_claim_is_sample`). Carried on the
    shared dataclass rather than computed in the JSON route so the HTML
    layer (app/web/compare_pages.py) gets the identical answer from the
    identical code path — the same reason this dataclass exists at all.

    Defaulted, so every existing caller and construction site keeps
    working untouched; the field names are the CLAIM's field names
    (`verified_charges`, `entry_requirements`, ...), so
    `estimated_additional_expenses` — always an estimate, never backed by
    a single claim (app/planning/comparison.py) — is correctly never in
    this set."""


def assemble_comparisons(
    db: Client,
    pathway_ids: list[str],
    *,
    as_of: date,
    estimated_additional_expenses_override: float | None = None,
) -> list[PathwayComparisonData]:
    """Fetch every claim/source for `pathway_ids` in two queries total
    (not one per pathway) and assemble each pathway's comparison data.
    Callers: `compare_pathways` below (JSON) and
    `app/web/pages.py`'s compare page (HTML) — see `PathwayComparisonData`
    for why this is a single shared function rather than two."""
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .in_("entity_id", pathway_ids)
        .execute()
    )
    # postgrest-py types .data as a broad JSON union; every row returned
    # by our own schema is, at runtime, a flat object — cast once here
    # rather than fighting the broad type at every access below.
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)

    source_ids = {row["source_id"] for row in claim_rows}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    results: list[PathwayComparisonData] = []
    for pid in pathway_ids:
        claims_by_field = {
            row["field"]: _row_to_claim(row) for row in claim_rows if row["entity_id"] == pid
        }
        fields = {
            field: field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
            for field in COMPARISON_FIELDS
        }
        cost_breakdown = assemble_cost_breakdown(claims_by_field, sources_by_id, as_of=as_of)
        cost_summary = assemble_cost_summary(
            claims_by_field,
            sources_by_id,
            as_of=as_of,
            estimated_additional_expenses_override=estimated_additional_expenses_override,
        )
        results.append(
            PathwayComparisonData(
                pathway_id=pid,
                fields=fields,
                cost_breakdown=cost_breakdown,
                cost_summary=cost_summary,
                sample_fields=frozenset(
                    field
                    for field, claim in claims_by_field.items()
                    if _claim_is_sample(claim, sources_by_id)
                ),
            )
        )
    return results


@router.get("/compare", response_model=CompareResponse)
def compare_pathways(
    pathway_id: list[str] = Query(..., alias="pathway_id"),
    estimated_additional_expenses: float | None = Query(
        default=None,
        description=(
            "Assumption override for this request only (Lite Build Pack §6/"
            "docs/UI.md 'assumption editing') -- never persisted, never a "
            "Claim. Applied to every pathway in this comparison. Omit to "
            "use each pathway's estimated_additional_expenses_hint claim, "
            "or 0.0 if it has none."
        ),
    ),
    db: Client = Depends(get_db_client),
) -> CompareResponse:
    """`?pathway_id=<id>&pathway_id=<id>` (2 or 3 of them) — docs/UI.md:
    "Examine two or three shortlisted pathways"."""
    if not (MIN_PATHWAYS <= len(pathway_id) <= MAX_PATHWAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Compare needs {MIN_PATHWAYS} or {MAX_PATHWAYS} pathway_id values.",
        )
    if len(set(pathway_id)) != len(pathway_id):
        # Security-review finding, 2026-09-20 (LOW): requesting the same
        # pathway_id twice passed the count check above and silently
        # rendered the same pathway twice as if it were a real two-way
        # comparison.
        raise HTTPException(
            status_code=400,
            detail="pathway_id values must be distinct -- pick different pathways to compare.",
        )
    if not all(_looks_like_a_uuid(pid) for pid in pathway_id):
        raise HTTPException(status_code=422, detail="pathway_id must be a valid id.")

    as_of = datetime.now(tz=UTC).date()
    comparisons = assemble_comparisons(
        db,
        pathway_id,
        as_of=as_of,
        estimated_additional_expenses_override=estimated_additional_expenses,
    )
    return CompareResponse(
        pathways=[
            PathwayComparisonOut(
                pathway_id=c.pathway_id,
                fields={
                    field: FieldValueOut.from_field_value(
                        fv, is_sample=field in c.sample_fields
                    )
                    for field, fv in c.fields.items()
                },
                cost=CostBreakdownOut(
                    verified_charges=FieldValueOut.from_field_value(
                        c.cost_breakdown.verified_charges,
                        is_sample="verified_charges" in c.sample_fields,
                    ),
                    # Never a sample: always computed from stated
                    # assumptions, never backed by a single claim
                    # (app/planning/comparison.py's assemble_cost_breakdown).
                    estimated_additional_expenses=FieldValueOut.from_field_value(
                        c.cost_breakdown.estimated_additional_expenses
                    ),
                    potential_assistance_not_yet_awarded=FieldValueOut.from_field_value(
                        c.cost_breakdown.potential_assistance_not_yet_awarded,
                        is_sample="potential_assistance_not_yet_awarded" in c.sample_fields,
                    ),
                    # RULES-10 made CostSummary.net_to_arrange a Money
                    # value (currency-mismatch safety); this response
                    # shape is still a bare rupee figure until SCOPE-4
                    # does the real currency-aware display work, so only
                    # the amount is unwrapped here -- a currency-mismatch
                    # None (mixed_currencies) still comes through as None.
                    net_to_arrange=(
                        c.cost_summary.net_to_arrange.amount
                        if c.cost_summary.net_to_arrange is not None
                        else None
                    ),
                ),
            )
            for c in comparisons
        ]
    )
