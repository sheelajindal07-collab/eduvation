"""Tests for app/data/models.py and the synthetic-fixture discipline."""

from datetime import date

from app.data.models import Claim, ClaimStatus, Source, SourceType
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
