"""GET /pathways/{id}/view — pathway/career detail page (UI-5).

The "see the full record" screen `_components.html`'s `pathway_detail_link`
macro has been linking to since UI-1 pre-wired it (Explore, Compare) --
until this task, that macro rendered nothing at all because no route
existed for it to point at.

PUBLICATION INTEGRITY: every fact on this page is built through
`app.planning.comparison.field_value_for` (and the small additive
`academic_cycle_for` helper next to it) -- the exact same published-only
assembly `app/api/compare.py`'s `assemble_comparisons` already uses for
the Compare screen, and the exact same "no record -> not_available"
contract `app/web/requirements_pages.py` follows via `check_eligibility`.
This module does its OWN two-query claims/sources fetch (a plain
`entity_type="Pathway", entity_id=<this pathway>` claims query, then one
sources lookup) rather than reaching into `app.api.compare`'s private
per-pathway assembly, because `PathwayComparisonData` does not expose the
raw claims a caller would need to also read `Claim.academic_cycle` from
(`assemble_cost_breakdown`/`assemble_cost_summary`/`field_value_for`
themselves ARE imported and reused directly, unchanged, for the actual
trust-label/cost logic). The `_row_to_claim`/`_row_to_source` row-shaping
helpers below are therefore file-local copies, matching the established
convention already used identically in `app/api/compare.py`,
`app/api/eligibility.py` and `app/web/timeline_pages.py` (each one's own
docstring says so) rather than a new shared import -- this task does not
touch any of those three files.

Degrades the same friendly way every other screen in this codebase
already does: a DB that's down/unconfigured, a malformed id, or an id
with no matching row all render this same template with a plain
in-page message and a link back to Explore -- never a 500, and never a
distinct "not found" wording keyed to whether the id happens to be a
real UUID that just has no row (matching `compare_pages.py`'s and
`requirements_pages.py`'s own choice not to treat "well-formed but
unknown" as a special, separately-worded case).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.api.compare import COMPARISON_FIELDS
from app.data.models import DEFAULT_JURISDICTION, Claim, ClaimStatus, Source, SourceType
from app.planning.comparison import (
    academic_cycle_for,
    assemble_cost_breakdown,
    assemble_cost_summary,
    field_value_for,
)
from app.web.common import (
    _DB_UNAVAILABLE_MESSAGE,
    _db_client_or_none,
    _looks_like_a_uuid,
)
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface

# The cost-breakdown fields that ARE backed by a single named claim, and
# therefore have an academic_cycle worth looking up. Unlike
# COMPARISON_FIELDS above (imported from app.api.compare, not redefined
# here), "estimated_additional_expenses" is deliberately excluded: it is
# always a derived TrustLabel.estimate (an override, a published hint, or
# a bare zero -- app.planning.comparison.assemble_cost_breakdown), never
# itself a single Claim, so there is no one claim's cycle to attribute it
# to.
_COST_CYCLE_FIELDS = ("verified_charges", "potential_assistance_not_yet_awarded")


def _row_to_source(row: dict[str, Any]) -> Source:
    """Identical to app/api/compare.py's/app/api/eligibility.py's/
    app/web/timeline_pages.py's helper of the same name -- kept
    file-local rather than shared, matching this codebase's established
    convention of not coupling otherwise-unrelated route files over a
    few lines."""
    return Source(
        id=row["id"],
        authority_name=row["authority_name"],
        official_url=row["official_url"],
        source_type=SourceType(row["source_type"]),
        jurisdiction=row.get("jurisdiction") or DEFAULT_JURISDICTION,
    )


def _row_to_claim(row: dict[str, Any]) -> Claim:
    """Identical to app/api/compare.py's helper of the same name
    (including the jurisdiction/academic_cycle/currency columns SCOPE-3
    added) -- same file-local convention as `_row_to_source` above. This
    page needs `academic_cycle` on the real `Claim`, unlike
    app/web/timeline_pages.py's own copy, which does not."""
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


def _render(request: Request, **context: Any) -> Any:
    """Every branch below renders the same template with the same key
    set (missing keys default to None/empty inside the template) -- one
    place that stays true, instead of a slightly different dict on each
    early-return path drifting out of sync with what detail.html
    actually reads."""
    base: dict[str, Any] = {
        "error": None,
        "pathway_id": None,
        "pathway": None,
        "career": None,
        "fields": {},
        "academic_cycles": {},
        "cost_breakdown": None,
        "cost_summary": None,
        "cost_academic_cycles": {},
    }
    base.update(context)
    return templates.TemplateResponse(request, "detail.html", base)


@router.get("/pathways/{pathway_id}/view")
def pathway_detail_page(
    pathway_id: str,
    request: Request,
    db: Client | None = Depends(_db_client_or_none),
) -> Any:
    if db is None:
        return _render(request, error=_DB_UNAVAILABLE_MESSAGE, pathway_id=pathway_id)

    if not _looks_like_a_uuid(pathway_id):
        return _render(
            request,
            error="That link doesn't point to a valid pathway.",
            pathway_id=pathway_id,
        )

    pathway_result = (
        db.table("pathways")
        .select("id, career_id, name, description")
        .eq("id", pathway_id)
        .execute()
    )
    pathway_rows = cast("list[dict[str, Any]]", pathway_result.data)
    if not pathway_rows:
        # Same posture as compare_pages.py/requirements_pages.py: a
        # well-formed id with no row is not specially distinguished from
        # any other "nothing published" state -- both would otherwise
        # need the caller to know in advance which one they hit, and
        # this catalogue is world-readable already (docs/UI.md), so
        # there is no cross-user information to protect either way.
        return _render(
            request,
            error="We couldn't find that pathway.",
            pathway_id=pathway_id,
        )
    pathway = pathway_rows[0]

    career_result = (
        db.table("careers")
        .select("id, name, nco_anchor")
        .eq("id", pathway["career_id"])
        .execute()
    )
    career_rows = cast("list[dict[str, Any]]", career_result.data)
    career = career_rows[0] if career_rows else None

    as_of = datetime.now(tz=UTC).date()

    claims_result = (
        db.table("claims")
        .select("*")
        .eq("entity_type", "Pathway")
        .eq("entity_id", pathway_id)
        .execute()
    )
    claim_rows = cast("list[dict[str, Any]]", claims_result.data)
    claims_by_field = {row["field"]: _row_to_claim(row) for row in claim_rows}

    source_ids = {row["source_id"] for row in claim_rows}
    sources_by_id: dict[str, Source] = {}
    if source_ids:
        sources_result = db.table("sources").select("*").in_("id", list(source_ids)).execute()
        source_rows = cast("list[dict[str, Any]]", sources_result.data)
        sources_by_id = {row["id"]: _row_to_source(row) for row in source_rows}

    fields = {
        field: field_value_for(field, claims_by_field, sources_by_id, as_of=as_of)
        for field in COMPARISON_FIELDS
    }
    academic_cycles = {
        field: academic_cycle_for(field, claims_by_field, sources_by_id, as_of=as_of)
        for field in COMPARISON_FIELDS
    }

    cost_breakdown = assemble_cost_breakdown(claims_by_field, sources_by_id, as_of=as_of)
    cost_summary = assemble_cost_summary(claims_by_field, sources_by_id, as_of=as_of)
    cost_academic_cycles = {
        field: academic_cycle_for(field, claims_by_field, sources_by_id, as_of=as_of)
        for field in _COST_CYCLE_FIELDS
    }

    return _render(
        request,
        pathway_id=pathway_id,
        pathway=pathway,
        career=career,
        fields=fields,
        academic_cycles=academic_cycles,
        cost_breakdown=cost_breakdown,
        cost_summary=cost_summary,
        cost_academic_cycles=cost_academic_cycles,
    )
