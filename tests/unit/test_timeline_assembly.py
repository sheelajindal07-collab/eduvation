"""Tests for app/planning/timeline_assembly.py (RULES-9).

Mirrors tests/unit/test_comparison.py's shape: hand-built `Claim`/
`Source` objects, no I/O. The safety-relevant property here is the same
one app/rules/timeline.py's own module docstring names as the single
most important rule in this whole feature: an unpublished/draft stage
claim's duration must degrade to `None` (never a guessed number) AND
the stage itself must still appear (never silently dropped) — proven
here at the pure-function level; tests/db/test_web_timeline_page.py
proves the same thing end-to-end against a real seeded draft claim.
"""

from __future__ import annotations

from datetime import date

from app.data.models import Claim, ClaimStatus, Source, SourceType
from app.planning.timeline_assembly import stages_from_claims
from app.rules.timeline import compute_timeline

TODAY = date(2026, 9, 22)

OFFICIAL_SOURCE = Source(
    id="src-1",
    authority_name="GSEB",
    official_url="https://gseb.example.invalid",
    source_type=SourceType.official,
)


def _claim(
    field: str,
    value: object,
    *,
    status: ClaimStatus = ClaimStatus.published,
    claim_id: str | None = None,
    source_id: str = OFFICIAL_SOURCE.id,
    verification_date: date = TODAY,
) -> Claim:
    return Claim(
        id=claim_id or f"claim-{field}",
        entity_type="Pathway",
        entity_id="pathway-1",
        field=field,
        value=value,  # type: ignore[arg-type]
        source_id=source_id,
        verification_date=verification_date,
        verifier="test-reviewer",
        status=status,
        review_due_date=date(2099, 1, 1),
    )


SOURCES = {OFFICIAL_SOURCE.id: OFFICIAL_SOURCE}


class TestBasicAssembly:
    def test_two_fully_published_stages_in_order(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 52),
            "stage:2:name": _claim("stage:2:name", "Bachelor's degree"),
            "stage:2:duration_weeks": _claim("stage:2:duration_weeks", 208),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert [s.name for s in stages] == ["Class 12", "Bachelor's degree"]
        assert [s.duration_weeks for s in stages] == [52, 208]

    def test_source_claim_id_is_the_duration_claims_own_id(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim(
                "stage:1:duration_weeks", 52, claim_id="the-duration-claim"
            ),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert stages[0].source_claim_id == "the-duration-claim"

    def test_empty_claims_gives_no_stages(self) -> None:
        assert stages_from_claims({}, {}, as_of=TODAY) == []

    def test_unrelated_claim_fields_are_ignored(self) -> None:
        claims = {"verified_charges": _claim("verified_charges", 85000)}
        assert stages_from_claims(claims, SOURCES, as_of=TODAY) == []

    def test_numeric_order_not_alphabetical(self) -> None:
        """`stage:10` must sort after `stage:9` — alphabetically it would
        sort right after `stage:1`."""
        claims = {
            "stage:2:name": _claim("stage:2:name", "Second"),
            "stage:10:name": _claim("stage:10:name", "Tenth"),
            "stage:9:name": _claim("stage:9:name", "Ninth"),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert [s.name for s in stages] == ["Second", "Ninth", "Tenth"]


class TestDraftDurationNeverSilentlyDropsTheStage:
    """The core safety property this task exists for."""

    def test_draft_duration_gives_unknown_duration_but_keeps_the_stage(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim(
                "stage:1:duration_weeks", 52, status=ClaimStatus.draft
            ),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert len(stages) == 1
        assert stages[0].name == "Class 12"
        assert stages[0].duration_weeks is None
        assert stages[0].source_claim_id is None

    def test_missing_duration_claim_entirely_also_gives_unknown_duration(self) -> None:
        claims = {"stage:1:name": _claim("stage:1:name", "Class 12")}
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert stages[0].duration_weeks is None

    def test_draft_duration_makes_compute_timeline_total_unknown(self) -> None:
        """End-to-end at the pure-function level: a stage assembled with
        an unknown duration makes the WHOLE timeline's total unknown,
        via app/rules/timeline.py's own pre-existing rule -- this module
        adds no second copy of that logic."""
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 52),
            "stage:2:name": _claim("stage:2:name", "Bachelor's degree"),
            "stage:2:duration_weeks": _claim(
                "stage:2:duration_weeks", 208, status=ClaimStatus.draft
            ),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        result = compute_timeline(stages)
        assert result.total_weeks is None
        assert result.complete is False
        assert [s.name for s in result.unknown] == ["Bachelor's degree"]

    def test_draft_name_skips_the_whole_slot_even_with_a_published_duration(self) -> None:
        """The name claim is the anchor: with no verified name, there is
        no non-invented fact left to show for that slot at all."""
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12", status=ClaimStatus.draft),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 52),
        }
        assert stages_from_claims(claims, SOURCES, as_of=TODAY) == []

    def test_blank_published_name_also_skips_the_slot(self) -> None:
        claims = {"stage:1:name": _claim("stage:1:name", "   ")}
        assert stages_from_claims(claims, SOURCES, as_of=TODAY) == []


class TestKind:
    def test_published_optional_kind_sets_required_false(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Bridge course"),
            "stage:1:kind": _claim("stage:1:kind", "optional"),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.kind == "optional"
        assert stage.required is False
        assert stage.display_kind == "optional"

    def test_published_required_kind_sets_required_true(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:kind": _claim("stage:1:kind", "required"),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.kind == "required"
        assert stage.required is True

    def test_absent_kind_defaults_to_required_true_kind_none(self) -> None:
        claims = {"stage:1:name": _claim("stage:1:name", "Class 12")}
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.kind is None
        assert stage.required is True
        assert stage.display_kind == "required"  # via Stage's own fallback

    def test_content_claim_can_never_assert_user_assumption(self) -> None:
        """`"user_assumption"` means the STUDENT added the stage
        themselves (app/rules/timeline.py's `Stage.kind` docstring) — a
        pathway's own published content can never claim to be that."""
        claims = {
            "stage:1:name": _claim("stage:1:name", "Extra attempt"),
            "stage:1:kind": _claim("stage:1:kind", "user_assumption"),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.kind is None
        assert stage.required is True

    def test_draft_kind_claim_degrades_to_none(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Bridge course"),
            "stage:1:kind": _claim("stage:1:kind", "optional", status=ClaimStatus.draft),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.kind is None
        assert stage.required is True


class TestOverlap:
    def test_published_overlap_is_used(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Degree"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 208),
            "stage:2:name": _claim("stage:2:name", "Internship"),
            "stage:2:duration_weeks": _claim("stage:2:duration_weeks", 26),
            "stage:2:overlap_weeks_with_previous": _claim(
                "stage:2:overlap_weeks_with_previous", 8
            ),
        }
        stages = stages_from_claims(claims, SOURCES, as_of=TODAY)
        assert stages[1].overlap_weeks_with_previous == 8
        result = compute_timeline(stages)
        assert result.total_weeks == 208 + 26 - 8

    def test_absent_overlap_defaults_to_zero(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 52),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.overlap_weeks_with_previous == 0

    def test_unpublished_overlap_also_defaults_to_zero(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", 52),
            "stage:2:name": _claim("stage:2:name", "Internship"),
            "stage:2:duration_weeks": _claim("stage:2:duration_weeks", 26),
            "stage:2:overlap_weeks_with_previous": _claim(
                "stage:2:overlap_weeks_with_previous", 8, status=ClaimStatus.draft
            ),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[1]
        assert stage.overlap_weeks_with_previous == 0


class TestMalformedValuesDegradeRatherThanRaise:
    def test_non_numeric_duration_value_is_unknown_but_still_provenanced(self) -> None:
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim(
                "stage:1:duration_weeks", "fifty-two", claim_id="malformed-claim"
            ),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.duration_weeks is None
        assert stage.source_claim_id == "malformed-claim"

    def test_non_string_name_value_skips_the_slot(self) -> None:
        claims = {"stage:1:name": _claim("stage:1:name", 12345)}
        assert stages_from_claims(claims, SOURCES, as_of=TODAY) == []

    def test_boolean_duration_value_is_never_treated_as_a_number(self) -> None:
        """`bool` is an `int` subclass in Python -- must not sneak past
        the numeric gate the way `format_inr(True)` famously could."""
        claims = {
            "stage:1:name": _claim("stage:1:name", "Class 12"),
            "stage:1:duration_weeks": _claim("stage:1:duration_weeks", True),
        }
        stage = stages_from_claims(claims, SOURCES, as_of=TODAY)[0]
        assert stage.duration_weeks is None
