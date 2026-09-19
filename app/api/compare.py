"""GET /compare — Compare screen (docs/UI.md "Comparison fields").

Assembles the comparison-field structure for 2-3 pathways, using the
pure trust-label logic in app/planning/comparison.py over real,
currently-visible claims (RLS decides what "currently visible" means for
a given caller — a guest sees published only, a reviewer sees drafts
too). This route does the I/O; comparison.py stays pure and unit-tested.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_db_client
from app.data.models import Claim, ClaimStatus, Source, SourceType
from app.planning.comparison import FieldValue, assemble_cost_breakdown, field_value_for

router = APIRouter(tags=["compare"])

# The non-cost fields shown on the Compare screen for this first slice.
# docs/UI.md lists more (work realities, alternatives) — added as the
# content track produces claims for them; an empty field degrades to
# "not_available" rather than a missing key, so adding one later is
# additive, not breaking.
COMPARISON_FIELDS = ["entry_requirements", "main_stages", "time_range", "location"]

MIN_PATHWAYS = 2
MAX_PATHWAYS = 3


class FieldValueOut(BaseModel):
    value: str | int | float | bool | None
    label: str
    source_url: str | None = None
    verification_date: date | None = None

    @classmethod
    def from_field_value(cls, fv: FieldValue) -> FieldValueOut:
        return cls(
            value=fv.value,
            label=fv.label.value,
            source_url=fv.source_url,
            verification_date=fv.verification_date,
        )


class CostBreakdownOut(BaseModel):
    verified_charges: FieldValueOut
    estimated_additional_expenses: FieldValueOut
    potential_assistance_not_yet_awarded: FieldValueOut


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
    )


def _row_to_source(row: dict[str, Any]) -> Source:
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
    )


@router.get("/compare", response_model=CompareResponse)
def compare_pathways(
    pathway_id: list[str] = Query(..., alias="pathway_id"),
    db: Client = Depends(get_db_client),
) -> CompareResponse:
    """`?pathway_id=<id>&pathway_id=<id>` (2 or 3 of them) — docs/UI.md:
    "Examine two or three shortlisted pathways"."""
    if not (MIN_PATHWAYS <= len(pathway_id) <= MAX_PATHWAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Compare needs {MIN_PATHWAYS} or {MAX_PATHWAYS} pathway_id values.",
        )

    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .in_("entity_id", pathway_id)
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

    as_of = datetime.now(tz=UTC).date()
    pathways_out: list[PathwayComparisonOut] = []
    for pid in pathway_id:
        claims_by_field = {
            row["field"]: _row_to_claim(row) for row in claim_rows if row["entity_id"] == pid
        }
        fields_out = {
            field: FieldValueOut.from_field_value(
                field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
            )
            for field in COMPARISON_FIELDS
        }
        cost = assemble_cost_breakdown(claims_by_field, sources_by_id, as_of=as_of)
        pathways_out.append(
            PathwayComparisonOut(
                pathway_id=pid,
                fields=fields_out,
                cost=CostBreakdownOut(
                    verified_charges=FieldValueOut.from_field_value(cost.verified_charges),
                    estimated_additional_expenses=FieldValueOut.from_field_value(
                        cost.estimated_additional_expenses
                    ),
                    potential_assistance_not_yet_awarded=FieldValueOut.from_field_value(
                        cost.potential_assistance_not_yet_awarded
                    ),
                ),
            )
        )
    return CompareResponse(pathways=pathways_out)
