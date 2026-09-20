"""Tests for app/planning/comparison.py — docs/UI.md trust-label rules
applied as code. These are safety-relevant (a mislabelled field reads as
a verified fact to a student), so every branch of the mapping table gets
its own test rather than one combined happy-path test."""

from datetime import date, timedelta

from app.data.models import Claim, ClaimStatus, Source, SourceType, TrustLabel
from app.planning.comparison import (
    DEFAULT_FRESHNESS_SLA_DAYS,
    _safe_source_url,
    assemble_cost_breakdown,
    assemble_cost_summary,
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


def test_field_value_for_carries_source_authority_when_available() -> None:
    """Added for ux-qa-reviewer, 2026-09-19: the HTML comparison page had
    no way to name which source it was linking to, so every evidence
    link showed the same generic text regardless of trust label."""
    claim = _claim(ClaimStatus.published, OFFICIAL_SOURCE.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert result.source_authority == OFFICIAL_SOURCE.authority_name


def test_field_value_for_hides_source_authority_when_not_available() -> None:
    """Same "never leak evidence for an unpublished fact" rule that
    already applies to value/source_url must apply to the new field too
    -- an unpublished claim's source name is not something a student
    should see attached to a "not available" badge."""
    claim = _claim(ClaimStatus.draft, OFFICIAL_SOURCE.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert result.source_authority is None


def test_field_value_for_hides_verification_date_when_not_available() -> None:
    """Security-review finding, 2026-09-20: verification_date was set
    whenever a claim object existed at all, with no gating on label --
    unlike value/source_url/source_authority. A draft (or
    synthetic-sourced) claim's verification_date must be hidden exactly
    like its value and source already are."""
    claim = _claim(ClaimStatus.draft, OFFICIAL_SOURCE.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert result.verification_date is None


def test_field_value_for_shows_verification_date_when_available() -> None:
    claim = _claim(ClaimStatus.published, OFFICIAL_SOURCE.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE},
        as_of=TODAY,
    )
    assert result.verification_date == TODAY


class TestSafeSourceUrl:
    """Security-review finding, 2026-09-20 (HIGH, XSS):
    app/web/templates/_trust_badge.html renders `source_url` straight
    into `href="{{ fv.source_url }}"`. Jinja's autoescaping only
    HTML-entity-escapes angle brackets/quotes -- it does not block a
    dangerous scheme, so a `javascript:`/`data:` URI in a Source row
    would render as a fully clickable link framed as trustworthy
    evidence. Only http/https may ever reach the template; anything else
    must come back None (the same "hide it" pattern as not_available),
    never raise."""

    def test_javascript_scheme_is_hidden(self) -> None:
        assert _safe_source_url("javascript:alert(document.cookie)") is None

    def test_data_scheme_is_hidden(self) -> None:
        assert (
            _safe_source_url("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==")
            is None
        )

    def test_https_url_passes_through(self) -> None:
        url = "https://gseb.example.invalid/official-page"
        assert _safe_source_url(url) == url

    def test_http_url_passes_through(self) -> None:
        """Some real Indian government sites are still http-only."""
        url = "http://gseb.example.invalid/official-page"
        assert _safe_source_url(url) == url

    def test_case_variant_scheme_is_still_caught(self) -> None:
        """A naive prefix check like `.startswith("javascript:")` would
        miss this -- the scheme must be normalised before comparison."""
        assert _safe_source_url("JavaScript:alert(1)") is None

    def test_whitespace_padded_scheme_is_still_caught(self) -> None:
        assert _safe_source_url("   javascript:alert(1)   ") is None

    def test_none_is_hidden_not_a_crash(self) -> None:
        assert _safe_source_url(None) is None

    def test_empty_string_is_hidden_not_a_crash(self) -> None:
        assert _safe_source_url("") is None


def test_field_value_for_hides_javascript_scheme_source_url() -> None:
    """End-to-end (not just the helper in isolation): a published,
    genuinely official-source claim whose Source row carries an unsafe
    URL scheme must still have its source_url hidden -- URL-scheme
    safety is checked regardless of trust label."""
    unsafe_source = Source(
        id="src-xss",
        authority_name="Malicious Source",
        official_url="javascript:alert(document.cookie)",
        source_type=SourceType.official,
    )
    claim = _claim(ClaimStatus.published, unsafe_source.id, TODAY)
    result = field_value_for(
        "verified_charges",
        {"verified_charges": claim},
        {unsafe_source.id: unsafe_source},
        as_of=TODAY,
    )
    assert result.label == TrustLabel.checked_against_official_source
    assert result.value == claim.value  # value itself is unaffected
    assert result.source_url is None  # only the unsafe link is hidden


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


def _field_claim(
    field: str,
    value: str | int | float | bool | None,
    *,
    status: ClaimStatus = ClaimStatus.published,
    source_id: str = OFFICIAL_SOURCE.id,
    verification_date: date = TODAY,
) -> Claim:
    return Claim(
        id=f"claim-{field}",
        entity_type="Programme",
        entity_id="prog-1",
        field=field,
        value=value,
        source_id=source_id,
        verification_date=verification_date,
        verifier="test-reviewer",
        status=status,
        review_due_date=date(2099, 1, 1),
    )


SOURCES_BY_ID = {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE}


class TestAssembleCostSummary:
    """`assemble_cost_summary` wires app/rules/cost.py's real arithmetic
    (net_to_arrange, "unawarded never subtracted") into the live claims
    already used for `assemble_cost_breakdown` -- these tests pin down
    that the wiring itself is correct, not the underlying engine (already
    covered by tests/unit/test_cost.py)."""

    def test_verified_charges_with_no_hint_or_override_nets_to_verified_alone(self) -> None:
        claims_by_field = {"verified_charges": _field_claim("verified_charges", 100000)}
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.verified_charges.total == 100000
        assert summary.net_to_arrange == 100000

    def test_missing_verified_charges_gives_none_net_not_a_guess(self) -> None:
        """The core safety property, now proven at the wiring layer too:
        a draft (not yet published) claim must never surface as a
        confident net figure."""
        claims_by_field = {
            "verified_charges": _field_claim(
                "verified_charges", 100000, status=ClaimStatus.draft
            )
        }
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.verified_charges.total is None
        assert summary.net_to_arrange is None

    def test_estimate_hint_is_used_when_no_override_given(self) -> None:
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000
            ),
        }
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.estimated_additional_expenses == 15000
        assert summary.net_to_arrange == 115000

    def test_override_replaces_the_hint_for_this_request_only(self) -> None:
        """The "assumption editing" mechanic (Lite Build Pack §6,
        docs/UI.md): a caller-supplied value wins over the published
        hint, without touching any Claim."""
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000
            ),
        }
        summary = assemble_cost_summary(
            claims_by_field,
            SOURCES_BY_ID,
            as_of=TODAY,
            estimated_additional_expenses_override=30000,
        )
        assert summary.estimated_additional_expenses == 30000
        assert summary.net_to_arrange == 130000

    def test_no_hint_and_no_override_assumes_zero_extra_not_unknown(self) -> None:
        claims_by_field = {"verified_charges": _field_claim("verified_charges", 100000)}
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.estimated_additional_expenses == 0.0
        assert summary.net_to_arrange == 100000

    def test_potential_assistance_is_visible_but_never_reduces_net_to_arrange(self) -> None:
        """The single most important property here, carried over from
        test_cost.py: an unawarded scholarship must never look like money
        already in hand."""
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "potential_assistance_not_yet_awarded": _field_claim(
                "potential_assistance_not_yet_awarded", 50000
            ),
        }
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.potential_assistance_total == 50000
        assert summary.net_to_arrange == 100000  # unchanged by the potential amount

    def test_no_potential_assistance_claim_gives_an_empty_list_not_a_zero_item(self) -> None:
        claims_by_field = {"verified_charges": _field_claim("verified_charges", 100000)}
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.potential_assistance == ()

    def test_confirmed_assistance_is_always_empty_in_this_slice(self) -> None:
        """No source of student-specific award data exists before M3's
        sign-in/consent work -- documented here so the gap is visible
        and tested, not just implied by the absence of a parameter."""
        claims_by_field = {"verified_charges": _field_claim("verified_charges", 100000)}
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.confirmed_assistance == ()

    def test_an_unpublished_hint_is_ignored_not_leaked_into_net_to_arrange(self) -> None:
        """A draft/in_review estimated_additional_expenses_hint must be
        treated exactly like no hint at all -- CLAUDE.md's maker-checker
        rule ("unapproved facts never reach public results") applies to
        this field too, not just the ones that read as plain facts."""
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000, status=ClaimStatus.draft
            ),
        }
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert summary.estimated_additional_expenses == 0.0
        assert summary.net_to_arrange == 100000

    def test_a_synthetic_sourced_hint_is_ignored_not_leaked_into_net_to_arrange(self) -> None:
        synthetic_sources = {**SOURCES_BY_ID, SYNTHETIC_SOURCE.id: SYNTHETIC_SOURCE}
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000, source_id=SYNTHETIC_SOURCE.id
            ),
        }
        summary = assemble_cost_summary(claims_by_field, synthetic_sources, as_of=TODAY)
        assert summary.estimated_additional_expenses == 0.0
        assert summary.net_to_arrange == 100000


class TestAssembleCostBreakdownEstimateHintProvenance:
    """assemble_cost_breakdown's estimated_additional_expenses must go
    through the same published/synthetic checks as assemble_cost_summary
    -- previously it read the hint claim's raw value straight out of the
    dict, bypassing field_value_for() entirely."""

    def test_an_unpublished_hint_does_not_leak_into_the_displayed_value(self) -> None:
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000, status=ClaimStatus.draft
            ),
        }
        breakdown = assemble_cost_breakdown(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert breakdown.estimated_additional_expenses.value == 0.0

    def test_a_synthetic_sourced_hint_does_not_leak_into_the_displayed_value(self) -> None:
        synthetic_sources = {**SOURCES_BY_ID, SYNTHETIC_SOURCE.id: SYNTHETIC_SOURCE}
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000, source_id=SYNTHETIC_SOURCE.id
            ),
        }
        breakdown = assemble_cost_breakdown(claims_by_field, synthetic_sources, as_of=TODAY)
        assert breakdown.estimated_additional_expenses.value == 0.0

    def test_a_published_official_hint_is_shown(self) -> None:
        claims_by_field = {
            "verified_charges": _field_claim("verified_charges", 100000),
            "estimated_additional_expenses_hint": _field_claim(
                "estimated_additional_expenses_hint", 15000
            ),
        }
        breakdown = assemble_cost_breakdown(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert breakdown.estimated_additional_expenses.value == 15000

    def test_no_hint_at_all_displays_zero_matching_what_the_summary_assumes(self) -> None:
        """The line item shown here must match what assemble_cost_summary
        actually computed net_to_arrange from -- a blank/None here next
        to a total that silently assumed zero would be a display lie."""
        claims_by_field = {"verified_charges": _field_claim("verified_charges", 100000)}
        breakdown = assemble_cost_breakdown(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        summary = assemble_cost_summary(claims_by_field, SOURCES_BY_ID, as_of=TODAY)
        assert breakdown.estimated_additional_expenses.value == 0.0
        assert (
            breakdown.estimated_additional_expenses.value == summary.estimated_additional_expenses
        )
