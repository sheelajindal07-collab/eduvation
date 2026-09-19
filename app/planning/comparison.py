"""Comparison assembly — docs/UI.md "Comparison screen", docs/DATA.md
"Trust label <-> claim status mapping".

Pure functions only: given already-fetched Claims/Sources for a pathway
(published rows, or reviewer-visible drafts when the caller is a
reviewer — the RLS policies in db/migrations/0001_init.sql decide what a
given caller can even fetch), assemble the exact field set the Compare
screen shows. No I/O here — callers in app/api/ fetch via
app/db/client.py and pass the results in, which keeps this module fully
unit-testable without a live database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.data.models import Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.rules.cost import AssistanceItem, CostSummary, FeeComponent, compute_cost_summary

# Tier-1-ish default freshness SLA for Lite, in days (docs/DATA.md S11
# scales this per tier; Lite uses one conservative default until the
# per-tier engine lands).
DEFAULT_FRESHNESS_SLA_DAYS = 180


def trust_label_for_claim(
    claim: Claim | None,
    source: Source | None,
    *,
    as_of: date,
    freshness_sla_days: int = DEFAULT_FRESHNESS_SLA_DAYS,
) -> TrustLabel:
    """docs/DATA.md's trust-label mapping table, as code.

    | UI label                         | Claim condition                                   |
    |-----------------------------------|----------------------------------------------------|
    | checked_against_official_source   | published, source.type=official, within SLA        |
    | institution_reported              | published, source.type=institution_self_declared    |
    | needs_rechecking                  | published but stale (or no source, defensively)     |
    | not_available                     | no published claim, or (defensively) a synthetic    |
    |                                    | source that should never have reached "published"   |

    "estimate" is intentionally never returned here — an estimate is a
    *derived* field computed from other claims plus a stated assumption,
    never itself backed by a single Claim row (docs/DATA.md). Callers that
    compute a derived value label it `TrustLabel.estimate` themselves.
    """
    if claim is None or claim.status != ClaimStatus.published:
        return TrustLabel.not_available
    if source is None:
        # A published claim always has a source per the schema's foreign
        # key (db/migrations/0001_init.sql) — this branch exists only so
        # the function can't silently mislabel if a caller passes
        # inconsistent data, e.g. a stale in-memory cache.
        return TrustLabel.needs_rechecking
    if source.source_type == SourceType.synthetic:
        # The DB trigger in 0001_init.sql forbids this state from ever
        # existing for real, but a unit test may still construct it —
        # never surface a synthetic-backed value as if it were a fact.
        return TrustLabel.not_available
    stale = (as_of - claim.verification_date) > timedelta(days=freshness_sla_days)
    if stale:
        return TrustLabel.needs_rechecking
    if source.source_type == SourceType.official:
        return TrustLabel.checked_against_official_source
    return TrustLabel.institution_reported


@dataclass(frozen=True)
class FieldValue:
    """One field on the comparison screen: a value plus its trust label
    and, when available, the evidence to show alongside it (docs/UI.md:
    "source authority, applicable cycle, verification date, official
    link, Report an issue" — the link/date live here; the rest is
    assembled by the caller from the Source/claim it already has)."""

    value: str | int | float | bool | None
    label: TrustLabel
    source_url: str | None = None
    verification_date: date | None = None


def field_value_for(
    field: str,
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> FieldValue:
    """Look up one field's claim (if any published claim exists for it)
    and assemble its display value with a trust label."""
    claim = claims_by_field.get(field)
    source = sources_by_id.get(claim.source_id) if claim else None
    label = trust_label_for_claim(claim, source, as_of=as_of)
    return FieldValue(
        value=claim.value if (claim and label != TrustLabel.not_available) else None,
        label=label,
        source_url=source.official_url if (source and label != TrustLabel.not_available) else None,
        verification_date=claim.verification_date if claim else None,
    )


@dataclass(frozen=True)
class ProgrammeCostBreakdown:
    """Three separate amounts — NEVER merged into one figure (docs/UI.md
    "Timeline and cost"; docs/DATA.md "Cost engine")."""

    verified_charges: FieldValue
    estimated_additional_expenses: FieldValue
    potential_assistance_not_yet_awarded: FieldValue


def assemble_cost_breakdown(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
) -> ProgrammeCostBreakdown:
    """Assemble the three-amount cost display for one programme/pathway.

    Expects (when present) claims on the fields "verified_charges" and
    "potential_assistance_not_yet_awarded" — each independently
    provenanced. "estimated_additional_expenses" is always an estimate:
    it is computed elsewhere from stated assumptions, never backed by a
    single Claim, so it is assembled directly as a TrustLabel.estimate
    FieldValue rather than looked up.
    """
    estimate_hint = claims_by_field.get("estimated_additional_expenses_hint")
    estimate_value = estimate_hint.value if estimate_hint else None

    return ProgrammeCostBreakdown(
        verified_charges=field_value_for(
            "verified_charges", claims_by_field, sources_by_id, as_of=as_of
        ),
        estimated_additional_expenses=FieldValue(value=estimate_value, label=TrustLabel.estimate),
        potential_assistance_not_yet_awarded=field_value_for(
            "potential_assistance_not_yet_awarded", claims_by_field, sources_by_id, as_of=as_of
        ),
    )


def assemble_cost_summary(
    claims_by_field: dict[str, Claim],
    sources_by_id: dict[str, Source],
    *,
    as_of: date,
    estimated_additional_expenses_override: float | None = None,
) -> CostSummary:
    """Run `app/rules/cost.py`'s real arithmetic (including `net_to_arrange`)
    over the same claims `assemble_cost_breakdown` already displays.

    This is intentionally the conservative first wiring, not a schema
    change: `verified_charges` stays the single already-verified claim a
    content reviewer publishes (docs/DATA.md "Cost engine") rather than
    switching content authoring over to itemised fee components — that's
    a content-workflow decision for a future task, not this one. Here it
    is simply passed through `sum_verified_charges` as a one-component
    list so the SAME "missing -> None, never a partial sum" guarantee
    `cost.py` already proves applies to the live figure too.

    `estimated_additional_expenses_override` is the "assumption editing"
    Build Pack §6/docs/UI.md call for: a caller-supplied value (never
    persisted, never a Claim) that replaces the `estimated_additional_expenses_hint`
    claim for this one request. Falls back to that hint, then to 0.0 —
    an omitted assumption is "assume nothing extra", not "unknown"; the
    student can always edit it in the UI.

    `potential_assistance_not_yet_awarded` becomes at most one
    `AssistanceItem` — omitted entirely (not zero) when the claim is
    `not_available`, since "no known potential assistance" and "assumed
    zero potential assistance" are different facts. There is no
    `confirmed_assistance` source yet (that is student-specific award
    data, which does not exist before the M3 sign-in/consent work), so
    it is always empty here — `net_to_arrange` correctly reduces to
    verified + estimate with nothing confirmed subtracted.
    """
    verified = field_value_for("verified_charges", claims_by_field, sources_by_id, as_of=as_of)
    fee_components = [FeeComponent(name="Verified charges", field_value=verified)]

    if estimated_additional_expenses_override is not None:
        estimated_additional_expenses = estimated_additional_expenses_override
    else:
        hint = claims_by_field.get("estimated_additional_expenses_hint")
        hint_value = hint.value if hint else None
        estimated_additional_expenses = (
            float(hint_value)
            if isinstance(hint_value, int | float) and not isinstance(hint_value, bool)
            else 0.0
        )

    potential = field_value_for(
        "potential_assistance_not_yet_awarded", claims_by_field, sources_by_id, as_of=as_of
    )
    potential_assistance = (
        [AssistanceItem(name="Potential assistance", amount=float(potential.value))]
        if isinstance(potential.value, int | float) and not isinstance(potential.value, bool)
        else []
    )

    return compute_cost_summary(
        fee_components=fee_components,
        estimated_additional_expenses=estimated_additional_expenses,
        confirmed_assistance=[],
        potential_assistance=potential_assistance,
    )
