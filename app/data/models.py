"""Core entity types for BCION Lite.

Mirrors docs/DATA.md. These are the shapes the API and rules engines pass
around; the actual persistence layer (Supabase tables + RLS policies) is
built at M1 ("data foundation and RLS tests", see Lite Build Pack §9). Until then,
these types are also used to define the synthetic fixtures under
tests/fixtures/ — which must NEVER be treated as published claims.

Every fact-bearing field on a real entity is backed by a Claim row, not
embedded loose on the entity. See docs/DATA.md "Claims table".
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ClaimStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    published = "published"
    superseded = "superseded"


class SourceType(StrEnum):
    official = "official"
    institution_self_declared = "institution_self_declared"
    # Fixture/test data only. The publishing console must refuse to ever
    # set a claim with this source type to `published` (docs/DATA.md,
    # "Synthetic fixtures").
    synthetic = "synthetic"


class TrustLabel(StrEnum):
    """UI-facing label. Derived from a Claim's status/source, never stored
    directly — see docs/DATA.md "Trust label <-> claim status mapping"."""

    checked_against_official_source = "checked_against_official_source"
    institution_reported = "institution_reported"
    estimate = "estimate"
    needs_rechecking = "needs_rechecking"
    not_available = "not_available"


class EligibilityOutcome(StrEnum):
    """Exactly three outcomes. Never a percentage, never "likely"."""

    meets = "meets"
    does_not_meet = "does_not_meet"
    insufficient_information = "insufficient_information"


class Source(BaseModel):
    id: str
    authority_name: str
    official_url: str
    source_type: SourceType


class Claim(BaseModel):
    """One provenanced fact. See docs/DATA.md."""

    id: str
    entity_type: str
    entity_id: str
    field: str
    value: str | int | float | bool | list[Any] | dict[str, Any] | None
    """Widened for RULES-3: a structured fact (e.g. an any-of subject
    group like `[["Physics"], ["Chemistry"], ["Biology", "Biotechnology"]]`,
    or a per-category thresholds map like `{"General": 50, "SC": 40}`)
    round-trips as ordinary JSON list/dict, same as any scalar claim
    value. `app.planning.comparison.field_value_for` already degrades a
    non-scalar value safely: its only numeric consumers
    (`_estimated_additional_expenses_hint`,
    `assemble_cost_summary`'s potential-assistance branch) both gate on
    `isinstance(value, int | float) and not isinstance(value, bool)`
    before doing arithmetic, so a list/dict value is treated as "not a
    usable number" rather than raising or silently coercing
    (tests/unit/test_models.py exercises this round-trip directly)."""
    source_id: str
    verification_date: date
    verifier: str  # a person's identifier — never "AI" (CLAUDE.md non-negotiable)
    status: ClaimStatus
    review_due_date: date
    superseded_by: str | None = None
    approved_draft_version: str | None = None
    extracted_by: str = "human"  # "human" | "ai" — an "ai" draft can never be published directly


class Career(BaseModel):
    id: str
    name: str
    # NCO-2015 unit group anchor — national DPR S10/S13.
    nco_anchor: str | None = Field(default=None)


class Pathway(BaseModel):
    id: str
    career_id: str
    name: str
    description: str


class Exam(BaseModel):
    id: str
    name: str
    state_specific: bool = False


class Institution(BaseModel):
    id: str
    name: str
    state: str


class ProgrammeCost(BaseModel):
    """Three separate amounts — never merged (docs/DATA.md, docs/UI.md)."""

    verified_charges: float
    estimated_additional_expenses: float
    potential_assistance_not_yet_awarded: float


class Scholarship(BaseModel):
    id: str
    name: str
    state: str | None = None


class StudentProfile(BaseModel):
    """Minimised per docs/DATA.md: only what quick-start needs. Sensitive
    fields (marks/category/income) are optional, encrypted at rest at the
    persistence layer (M1), and out of scope for this in-memory shape."""

    id: str
    current_class: str
    interests: list[str] = Field(default_factory=list)
    language: str = "en"
    broad_location: str | None = None
