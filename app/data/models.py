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


# SCOPE-3 / docs/CONTRACTS.md "Entity vocabulary": one text code — ISO
# 3166-1 alpha-2 for a country ("IN"), ISO 3166-2 for a subdivision
# ("IN-MH"). Matches the CHECK constraints in
# db/migrations/0008_jurisdiction_currency.sql exactly, so a value that
# would be refused by the database is refused here too rather than
# failing later with a raw Postgres error. No covered-set list is
# hardcoded anywhere: CONTRACTS.md forbids that until SCOPE-1 is
# answered, so this is shape-only.
JURISDICTION_PATTERN = r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$"

# ISO 4217, uppercase (docs/CONTRACTS.md "Money and currency"). Amounts
# are NEVER converted — no FX rate exists anywhere in Lite.
CURRENCY_PATTERN = r"^[A-Z]{3}$"

# docs/CONTRACTS.md "Duration, dates, cycle, DOB": a text LABEL, `YYYY`
# or `YYYY-YY`, "stored exactly as the source states it, compared as a
# string, never parsed". Deliberately a `str`, never a date or an int.
ACADEMIC_CYCLE_PATTERN = r"^[0-9]{4}(-[0-9]{2})?$"

DEFAULT_JURISDICTION = "IN"


class Source(BaseModel):
    id: str
    authority_name: str
    official_url: str
    source_type: SourceType
    jurisdiction: str = Field(default=DEFAULT_JURISDICTION, pattern=JURISDICTION_PATTERN)
    """SCOPE-3: the authority's remit — whose rules this body actually
    speaks for. Not derived from the claims that cite it."""


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
    jurisdiction: str = Field(default=DEFAULT_JURISDICTION, pattern=JURISDICTION_PATTERN)
    """SCOPE-3. Which jurisdiction this fact is true for. Defaults to the
    India-first pilot's 'IN', matching the column default in
    db/migrations/0008_jurisdiction_currency.sql, so a claim read back
    from a row written before that migration is still well-formed here.

    docs/CONTRACTS.md: "Fields on a non-`IN` pathway are display-only:
    shown with source and currency, never fed to the eligibility engine
    or into a total." """
    academic_cycle: str | None = Field(default=None, pattern=ACADEMIC_CYCLE_PATTERN)
    """SCOPE-3. A LABEL (`2026`, `2026-27`), never a date, never parsed —
    compared as a string. None when the fact is not cycle-scoped."""
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)
    """SCOPE-3. ISO 4217, for a money-valued claim. None is a real state,
    not a missing default: docs/CONTRACTS.md says "a money claim with a
    null currency renders not_available", so it must never be silently
    assumed to be INR — that would invent a fact about a real fee."""


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
    jurisdiction: str = Field(default=DEFAULT_JURISDICTION, pattern=JURISDICTION_PATTERN)
    """SCOPE-3. docs/CONTRACTS.md: a non-`IN` pathway's fields are
    display-only — shown with source and currency, never fed to the
    eligibility engine or into a total."""


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
