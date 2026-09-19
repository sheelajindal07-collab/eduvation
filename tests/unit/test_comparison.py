"""Tests for app/planning/comparison.py — docs/UI.md trust-label rules
applied as code. These are safety-relevant (a mislabelled field reads as
a verified fact to a student), so every branch of the mapping table gets
its own test rather than one combined happy-path test."""

from datetime import date, timedelta

from app.data.models import Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.planning.comparison import (
    DEFAULT_FRESHNESS_SLA_DAYS,
    assemble_cost_breakdown,
    field_value_for,
    trust_label_for_claim,
)

TODAY = date(2026, 9, 19)

OFFICIAL_SOURCE = Source(
    id="src-1",
    authority_name="GSEB",
    official_url="https://gseb.example.invalid",
    source_type=SourceType.official,
)
INSTITUTION_SOURCE = Source(
    id="src-2",
    authority_name="Some College",
    official_url="https://college.example.invalid",
    source_type=SourceType.institution_self_declared,
)
SYNTHETIC_SOURCE = Source(
    id="src-3",
    authority_name="TEST FIXTURE",
    official_url="https://example.invalid",
    source_type=SourceType.synthetic,
)


def _claim(status: ClaimStatus, source_id: str, verification_date: date) -> Claim:
    return Claim(
        id="claim-1",
        entity_type="Programme",
        entity_id="prog-1",
        field="verified_charges",
        value=50000,
        source_id=source_id,
        verification_date=verification_date,
        verifier="test-reviewer",
        status=status,
        review_due_date=date(2099, 1, 1),
    )


def test_no_claim_is_not_available() -> None:
    assert trust_label_for_claim(None, None, as_of=TODAY) == TrustLabel.not_available


def test_draft_claim_is_not_available() -> None:
    claim = _claim(ClaimStatus.draft, OFFICIAL_SOURCE.id, TODAY)
    assert trust_label_for_claim(claim, OFFICIAL_SOURCE, as_of=TODAY) == TrustLabel.not_available


def test_in_review_claim_is_not_available() -> None:
    claim = _claim(ClaimStatus.in_review, OFFICIAL_SOURCE.id, TODAY)
    assert trust_label_for_claim(claim, OFFICIAL_SOURCE, as_of=TODAY) == TrustLabel.not_available


def test_published_official_and_fresh_is_checked_against_official_source() -> None:
    claim = _claim(ClaimStatus.published, OFFICIAL_SOURCE.id, TODAY)
    assert (
        trust_label_for_claim(claim, OFFICIAL_SOURCE, as_of=TODAY)
        == TrustLabel.checked_against_official_source
    )


def test_published_institution_and_fresh_is_institution_reported() -> None:
    claim = _claim(ClaimStatus.published, INSTITUTION_SOURCE.id, TODAY)
    assert (
        trust_label_for_claim(claim, INSTITUTION_SOURCE, as_of=TODAY)
        == TrustLabel.institution_reported
    )


def test_published_but_stale_is_needs_rechecking() -> None:
    old_date = TODAY - timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS + 1)
    claim = _claim(ClaimStatus.published, OFFICIAL_SOURCE.id, old_date)
    assert trust_label_for_claim(claim, OFFICIAL_SOURCE, as_of=TODAY) == TrustLabel.needs_rechecking


def test_published_at_exact_sla_boundary_is_still_fresh() -> None:
    """Boundary case: exactly at the SLA, not yet stale (docs/SECURITY.md
    quality gates: "boundaries" is an explicit required test category)."""
    boundary_date = TODAY - timedelta(days=DEFAULT_FRESHNESS_SLA_DAYS)
    claim = _claim(ClaimStatus.published, OFFICIAL_SOURCE.id, boundary_date)
    assert (
        trust_label_for_claim(claim, OFFICIAL_SOURCE, as_of=TODAY)
        == TrustLabel.checked_against_official_source
    )


def test_published_claim_with_missing_source_is_needs_rechecking_not_a_crash() -> None:
    claim = _claim(ClaimStatus.published, "nonexistent-source", TODAY)
    assert trust_label_for_claim(claim, None, as_of=TODAY) == TrustLabel.needs_rechecking


def test_synthetic_source_never_surfaces_as_a_fact_even_if_marked_published() -> None:
    """Defence in depth: the DB trigger (0001_init.sql) is the real
    guarantee, but this function must independently refuse to ever label
    a synthetic-backed value as trustworthy, in case a caller (e.g. a
    test, or a future code path) constructs this state in memory."""
    claim = _claim(ClaimStatus.published, SYNTHETIC_SOURCE.id, TODAY)
    assert trust_label_for_claim(claim, SYNTHETIC_SOURCE, as_of=TODAY) == TrustLabel.not_available


def test_field_value_for_hides_value_when_not_available() -> None:
    """A "not available" field must not leak a stale/unpublished value
    into the UI just because a Claim row happens to exist."""
    claim = _claim(ClaimStatus.draft, OFFICIAL_SOURCE.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert result.label == TrustLabel.not_available
    assert result.value is None
    assert result.source_url is None


def test_field_value_for_missing_field_is_not_available() -> None:
    result = field_value_for("cost", {}, {}, as_of=TODAY)
    assert result.label == TrustLabel.not_available
    assert result.value is None


def test_cost_breakdown_keeps_three_amounts_separate() -> None:
    """The core UI/data rule: verified, estimated and potential must
    never be merged into one number (docs/UI.md, docs/DATA.md)."""
    verified_claim = Claim(
        id="c1",
        entity_type="Programme",
        entity_id="prog-1",
        field="verified_charges",
        value=120000,
        source_id=OFFICIAL_SOURCE.id,
        verification_date=TODAY,
        verifier="test-reviewer",
        status=ClaimStatus.published,
        review_due_date=date(2099, 1, 1),
    )
    potential_claim = Claim(
        id="c2",
        entity_type="Programme",
        entity_id="prog-1",
        field="potential_assistance_not_yet_awarded",
        value=20000,
        source_id=OFFICIAL_SOURCE.id,
        verification_date=TODAY,
        verifier="test-reviewer",
        status=ClaimStatus.published,
        review_due_date=date(2099, 1, 1),
    )
    claims_by_field = {
        "verified_charges": verified_claim,
        "potential_assistance_not_yet_awarded": potential_claim,
    }
    breakdown = assemble_cost_breakdown(
        claims_by_field,
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert breakdown.verified_charges.value == 120000
    assert breakdown.verified_charges.label == TrustLabel.checked_against_official_source
    assert breakdown.potential_assistance_not_yet_awarded.value == 20000
    assert breakdown.estimated_additional_expenses.label == TrustLabel.estimate
    # Three distinct fields, never summed into one:
    assert breakdown.verified_charges.value != breakdown.potential_assistance_not_yet_awarded.value
