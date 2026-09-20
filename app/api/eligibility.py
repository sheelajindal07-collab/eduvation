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

from datetime import date
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_db_client
from app.data.models import ClaimStatus, Source, SourceType
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


def _safe_source_url(source: Source | None) -> str | None:
    """Security-review finding, 2026-09-20: `Source.official_url` is
    reviewer-write-only today, but nothing validates its scheme before
    it reaches `href="{{ ... }}"` in a template (Jinja autoescape only
    HTML-entity-escapes, it does not block a `javascript:`/`data:` URI).
    A malicious or compromised reviewer credential — or, once M4's
    publishing pipeline lands, an unscrutinized AI-extracted URL — could
    otherwise render a fully clickable script-executing link on an
    evidence badge. Same fix as `app/planning/comparison.py`'s
    `field_value_for` (a separate implementation here, not routed through
    it, so that fix doesn't cover this route): degrade a non-http(s)
    scheme to `None`, the same "unavailable" pattern already used
    elsewhere, rather than rendering it."""
    if source is None:
        return None
    if source.official_url.startswith(("http://", "https://")):
        return source.official_url
    return None


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


class EligibilityResponse(BaseModel):
    outcome: str
    criteria: list[CriterionResultOut]


def _criteria_from_claims(claim_rows: list[dict[str, Any]]) -> list[Criterion]:
    """Build the criteria list from whatever eligibility-shaped claims
    exist on this pathway.

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
    """
    published_rows = [row for row in claim_rows if row["status"] == ClaimStatus.published]
    by_field = {row["field"]: row for row in published_rows}
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
    )

    result = evaluate_eligibility(criteria, student)
    criteria_out = []
    for c in result.criteria:
        claim_row = published_claims_by_id.get(c.source_claim_id) if c.source_claim_id else None
        source = sources_by_id.get(claim_row["source_id"]) if claim_row else None
        criteria_out.append(
            CriterionResultOut(
                name=c.name,
                outcome=c.outcome.value,
                explanation=c.explanation,
                source_claim_id=c.source_claim_id,
                source_authority=source.authority_name if source else None,
                source_url=_safe_source_url(source),
                verification_date=claim_row["verification_date"] if claim_row else None,
            )
        )
    return EligibilityResponse(outcome=result.outcome.value, criteria=criteria_out)
