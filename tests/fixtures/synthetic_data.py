"""SYNTHETIC TEST FIXTURES — NOT REAL DATA.

Every value here is fabricated for tests only. Names, fees and dates are
deliberately implausible (e.g. "Testonia") so they can never be mistaken
for a real, verified fact. Per CLAUDE.md and docs/DATA.md: synthetic
fixtures must never be published as verified facts, and the publishing
console must refuse to ever mark `SourceType.synthetic` claims as
`published`.
"""

from datetime import date

from app.data.models import (
    Career,
    Claim,
    ClaimStatus,
    Source,
    SourceType,
    StudentProfile,
)

SYNTHETIC_SOURCE = Source(
    id="src-synthetic-001",
    authority_name="TEST FIXTURE — not a real authority",
    official_url="https://example.invalid/not-a-real-source",
    source_type=SourceType.synthetic,
)

SYNTHETIC_CAREER = Career(
    id="career-synthetic-001",
    name="Test Pathway Technician (SYNTHETIC — not a real career record)",
    nco_anchor=None,
)

SYNTHETIC_CLAIM = Claim(
    id="claim-synthetic-001",
    entity_type="Career",
    entity_id=SYNTHETIC_CAREER.id,
    field="name",
    value=SYNTHETIC_CAREER.name,
    source_id=SYNTHETIC_SOURCE.id,
    verification_date=date(2026, 1, 1),
    verifier="test-fixture",
    status=ClaimStatus.draft,
    review_due_date=date(2099, 1, 1),
    extracted_by="human",
)

SYNTHETIC_STUDENT = StudentProfile(
    id="student-synthetic-001",
    current_class="Class 10",
    interests=["testing"],
    language="en",
    broad_location="Testonia (fixture)",
)
