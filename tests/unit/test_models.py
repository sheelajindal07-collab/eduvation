"""Tests for app/data/models.py and the synthetic-fixture discipline."""

from app.data.models import ClaimStatus, SourceType
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
