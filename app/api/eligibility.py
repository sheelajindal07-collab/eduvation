"""GET /eligibility — the first real wiring of app/rules/eligibility.py
into a request-handling route.

Criteria are built dynamically from a pathway's own published claims —
never hardcoded per exam in application code (that belongs to the
content track, docs/DATA.md), and never invented if the claim doesn't
exist. Recognised claim fields on a Pathway:

  minimum_age                  int
  maximum_age                  int
  minimum_marks_percentage     float
  required_subjects            comma-separated string, e.g. "Physics,Chemistry,Biology"
  domicile_states               comma-separated string, e.g. "Gujarat,Maharashtra"

Any of these that isn't published simply contributes no criterion at
all — it is not the same as "insufficient_information" (that's reserved
for a criterion that exists but the STUDENT's input is missing). A
pathway with none of these claims published returns `meets` (vacuously;
see app/rules/eligibility.py's empty-criteria-list test) rather than a
misleading "insufficient_information" about rules that were never
stated in the first place.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_db_client
from app.rules.eligibility import (
    Criterion,
    EligibilityInput,
    domicile_in,
    evaluate_eligibility,
    maximum_age,
    minimum_age,
    minimum_marks_percentage,
    required_subjects,
)

router = APIRouter(tags=["eligibility"])


class CriterionResultOut(BaseModel):
    name: str
    outcome: str
    explanation: str
    source_claim_id: str | None = None


class EligibilityResponse(BaseModel):
    outcome: str
    criteria: list[CriterionResultOut]


def _criteria_from_claims(claim_rows: list[dict[str, Any]]) -> list[Criterion]:
    """Build the criteria list from whatever eligibility-shaped claims
    exist on this pathway. Only published claims ever reach this
    function — the caller fetches through the normal RLS-scoped client,
    same as everywhere else in this codebase."""
    by_field = {row["field"]: row for row in claim_rows}
    criteria: list[Criterion] = []

    if row := by_field.get("minimum_age"):
        criteria.append(minimum_age(int(row["value"]), source_claim_id=row["id"]))
    if row := by_field.get("maximum_age"):
        criteria.append(maximum_age(int(row["value"]), source_claim_id=row["id"]))
    if row := by_field.get("minimum_marks_percentage"):
        criteria.append(
            minimum_marks_percentage(float(row["value"]), source_claim_id=row["id"])
        )
    if row := by_field.get("required_subjects"):
        subjects = frozenset(s.strip() for s in str(row["value"]).split(",") if s.strip())
        if subjects:
            criteria.append(required_subjects(subjects, source_claim_id=row["id"]))
    if row := by_field.get("domicile_states"):
        states = frozenset(s.strip() for s in str(row["value"]).split(",") if s.strip())
        if states:
            criteria.append(domicile_in(states, source_claim_id=row["id"]))

    return criteria


@router.get("/eligibility", response_model=EligibilityResponse)
def check_eligibility(
    pathway_id: str = Query(...),
    age: int | None = Query(default=None),
    marks_percentage: float | None = Query(default=None),
    subjects_studied: str | None = Query(
        default=None, description="Comma-separated, e.g. Physics,Chemistry,Biology"
    ),
    domicile_state: str | None = Query(default=None),
    db: Client = Depends(get_db_client),
) -> EligibilityResponse:
    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .eq("entity_id", pathway_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)
    criteria = _criteria_from_claims(claim_rows)

    student = EligibilityInput(
        age=age,
        marks_percentage=marks_percentage,
        subjects_studied=(
            frozenset(s.strip() for s in subjects_studied.split(",") if s.strip())
            if subjects_studied
            else frozenset()
        ),
        domicile_state=domicile_state,
    )

    result = evaluate_eligibility(criteria, student)
    return EligibilityResponse(
        outcome=result.outcome.value,
        criteria=[
            CriterionResultOut(
                name=c.name,
                outcome=c.outcome.value,
                explanation=c.explanation,
                source_claim_id=c.source_claim_id,
            )
            for c in result.criteria
        ],
    )
