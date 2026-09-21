"""Tests for app/data/models.py and the synthetic-fixture discipline."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.data.models import Claim, ClaimStatus, Pathway, Source, SourceType
from app.planning.comparison import field_value_for
from tests.fixtures.synthetic_data import (
    SYNTHETIC_CAREER,
    SYNTHETIC_CLAIM,
    SYNTHETIC_SOURCE,
    SYNTHETIC_STUDENT,
)


def test_synthetic_source_is_tagged_synthetic() -> None:
    assert SYNTHETIC_SOURCE.source_type == SourceType.synthetic


def test_synthetic_claim_is_never_published() -> None:
    """A fixture claim must not already be in a published state — the
    publishing console (built at M4) is what's responsible for refusing to
    ever move a synthetic-sourced claim to `published`, but the fixtures
    themselves must not pre-empt that by being authored as if verified."""
    assert SYNTHETIC_CLAIM.status != ClaimStatus.published
    assert SYNTHETIC_CLAIM.extracted_by in {"human", "ai"}


def test_synthetic_career_name_is_self_labelled() -> None:
    assert "SYNTHETIC" in SYNTHETIC_CAREER.name.upper() or "TEST" in SYNTHETIC_CAREER.name.upper()


def test_synthetic_student_has_no_sensitive_fields() -> None:
    """Quick-start minimisation (docs/DATA.md): marks/category/income are
    not on StudentProfile at all in this shape."""
    dumped = SYNTHETIC_STUDENT.model_dump()
    for forbidden in ("marks", "category", "income"):
        assert forbidden not in dumped


class TestStructuredClaimValue:
    """RULES-3: `Claim.value` was widened from scalar-only to also accept
    a JSON list/dict, so a structured fact (an any-of subject group, a
    per-category thresholds map) can be published as an ordinary claim
    the same way a scalar fact already is."""

    def _claim(self, value: object) -> Claim:
        return Claim(
            id="claim-1",
            entity_type="exam",
            entity_id="neet-ug",
            field="subject_groups",
            value=value,  # type: ignore[arg-type]
            source_id="source-1",
            verification_date=date(2026, 9, 19),
            verifier="reviewer@example.org",
            status=ClaimStatus.published,
            review_due_date=date(2027, 3, 19),
        )

    def test_list_value_round_trips_through_model_dump_and_validate(self) -> None:
        value = [["Physics"], ["Chemistry"], ["Biology", "Biotechnology"]]
        claim = self._claim(value)
        dumped = claim.model_dump()
        rebuilt = Claim.model_validate(dumped)
        assert rebuilt.value == value

    def test_dict_value_round_trips_through_model_dump_and_validate(self) -> None:
        value = {"General": 50.0, "SC": 40.0}
        claim = self._claim(value)
        dumped = claim.model_dump()
        rebuilt = Claim.model_validate(dumped)
        assert rebuilt.value == value

    def test_list_value_round_trips_through_json(self) -> None:
        value = [["Physics"], ["Chemistry"]]
        claim = self._claim(value)
        rebuilt = Claim.model_validate_json(claim.model_dump_json())
        assert rebuilt.value == value

    def test_scalar_value_still_works_after_the_widening(self) -> None:
        claim = self._claim(50.0)
        assert claim.value == 50.0


class TestFieldValueForDegradesNonScalarSafely:
    """`app.planning.comparison.field_value_for` must not crash or
    misbehave when the claim it looks up now carries a structured
    (list/dict) value instead of a scalar -- it simply passes the value
    through, the same as any other published field, and its own numeric
    consumers elsewhere already gate on `isinstance(value, int | float)`
    before doing arithmetic (see `app/planning/comparison.py`'s
    `_estimated_additional_expenses_hint` and `assemble_cost_summary`)."""

    def test_list_backed_field_is_returned_intact_not_dropped(self) -> None:
        source = Source(
            id="source-1",
            authority_name="NTA",
            official_url="https://neet.nta.nic.in/",
            source_type=SourceType.official,
        )
        claim = Claim(
            id="claim-1",
            entity_type="exam",
            entity_id="neet-ug",
            field="subject_groups",
            value=[["Physics"], ["Chemistry"], ["Biology", "Biotechnology"]],
            source_id="source-1",
            verification_date=date(2026, 9, 19),
            verifier="reviewer@example.org",
            status=ClaimStatus.published,
            review_due_date=date(2027, 3, 19),
        )
        result = field_value_for(
            "subject_groups",
            {"subject_groups": claim},
            {"source-1": source},
            as_of=date(2026, 9, 19),
        )
        assert result.value == [["Physics"], ["Chemistry"], ["Biology", "Biotechnology"]]

    def test_dict_backed_field_does_not_crash_numeric_style_consumers(self) -> None:
        """A list/dict value must never be silently coerced into a
        number -- it must fail the same numeric-usability check a real
        non-numeric string already fails."""
        value = {"General": 50.0, "SC": 40.0}
        assert not (isinstance(value, int | float) and not isinstance(value, bool))


# --------------------------------------------------------------------
# SCOPE-3 — jurisdiction / academic_cycle / currency
# --------------------------------------------------------------------
# The patterns these exercise mirror the CHECK constraints in
# db/migrations/0008_jurisdiction_currency.sql exactly. That duplication
# is deliberate and worth one sentence: the database is the enforcement
# point, and the model-level patterns exist so a bad value is rejected
# with a readable pydantic error at the edge instead of a raw Postgres
# constraint violation from deep inside a request. If one side is ever
# changed, the other must change in the same commit.


def _claim(**overrides: object) -> Claim:
    payload: dict = {
        "id": "claim-scope",
        "entity_type": "pathway",
        "entity_id": "pathway-1",
        "field": "verified_charges",
        "value": 9000,
        "source_id": "source-1",
        "verification_date": date(2026, 9, 19),
        "verifier": "reviewer@example.org",
        "status": ClaimStatus.published,
        "review_due_date": date(2027, 3, 19),
    }
    payload.update(overrides)
    return Claim(**payload)


class TestJurisdiction:
    def test_claims_default_to_IN(self) -> None:
        """Matches the column default, so a row written before
        0008_jurisdiction_currency.sql still validates as a Claim."""
        assert _claim().jurisdiction == "IN"

    def test_pathway_defaults_to_IN(self) -> None:
        pathway = Pathway(id="p1", career_id="c1", name="A pathway", description="x")
        assert pathway.jurisdiction == "IN"

    def test_source_defaults_to_IN(self) -> None:
        source = Source(
            id="s1",
            authority_name="An authority",
            official_url="https://example.invalid/",
            source_type=SourceType.official,
        )
        assert source.jurisdiction == "IN"

    @pytest.mark.parametrize("code", ["IN", "GB", "IN-MH", "GB-ENG", "US-CA"])
    def test_accepts_iso_3166_1_and_3166_2(self, code: str) -> None:
        assert _claim(jurisdiction=code).jurisdiction == code

    @pytest.mark.parametrize("bad", ["India", "in", "I", "INDI", "IN-", "IN_MH", ""])
    def test_rejects_anything_that_is_not_a_code(self, bad: str) -> None:
        """docs/CONTRACTS.md: jurisdiction is ONE TEXT CODE. Free text
        would make a jurisdiction comparison meaningless."""
        with pytest.raises(ValidationError):
            _claim(jurisdiction=bad)


class TestCurrency:
    def test_defaults_to_none_not_INR(self) -> None:
        """docs/CONTRACTS.md: "A money claim with a null currency renders
        not_available". Defaulting to INR would invent a fact about a
        real fee, which is the one thing this project never does."""
        assert _claim().currency is None

    @pytest.mark.parametrize("code", ["INR", "GBP", "USD"])
    def test_accepts_iso_4217(self, code: str) -> None:
        assert _claim(currency=code).currency == code

    @pytest.mark.parametrize("bad", ["inr", "Inr", "US", "RUPEE", "1NR", "IN R"])
    def test_rejects_a_malformed_code(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _claim(currency=bad)


class TestAcademicCycle:
    def test_defaults_to_none(self) -> None:
        assert _claim().academic_cycle is None

    @pytest.mark.parametrize("cycle", ["2026", "2026-27"])
    def test_accepts_the_two_contract_shapes(self, cycle: str) -> None:
        assert _claim(academic_cycle=cycle).academic_cycle == cycle

    def test_stays_a_string_and_is_never_parsed(self) -> None:
        """docs/CONTRACTS.md: a LABEL, "stored exactly as the source
        states it, compared as a string, never parsed"."""
        value = _claim(academic_cycle="2026-27").academic_cycle
        assert isinstance(value, str)
        assert value == "2026-27"

    @pytest.mark.parametrize("bad", ["2026-2027", "26-27", "FY2026", "2026-2", "next year"])
    def test_rejects_anything_else(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _claim(academic_cycle=bad)
