"""Unit tests for `app/planning/claim_diff.py` (AI-19, `tasks/BCI-022.md`).

Pure, no database, no AI provider, no pipeline — `compute_claim_diff`
takes two hand-built `DiffableClaim`s and this file asserts its output
directly.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.planning.claim_diff import (
    DIFF_ATTRIBUTES,
    ClaimDiff,
    DiffableClaim,
    compute_claim_diff,
)

_OLD_DATE = date(2026, 1, 1)
_NEW_DATE = date(2026, 6, 1)


def _diffable(
    *,
    claim_id: str = "claim-1",
    field: str = "minimum_age",
    value: object = 17,
    source_authority: str | None = "CBSE (test fixture)",
    verification_date: date = _OLD_DATE,
) -> DiffableClaim:
    return DiffableClaim(
        claim_id=claim_id,
        field=field,
        value=value,  # type: ignore[arg-type]
        source_authority=source_authority,
        verification_date=verification_date,
    )


class TestDiffAttributesVocabulary:
    def test_exactly_the_three_attributes_this_card_documents(self) -> None:
        assert DIFF_ATTRIBUTES == ("value", "source_authority", "verification_date")


class TestNoChange:
    def test_identical_claims_produce_no_changed_fields(self) -> None:
        superseded = _diffable()
        successor = _diffable(claim_id="claim-2")
        diff = compute_claim_diff(superseded, successor)
        assert diff.changed_fields == ()
        assert diff.has_changes is False

    def test_only_the_claim_id_differing_is_not_a_field_change(self) -> None:
        """`superseded_claim_id`/`successor_claim_id` are identity, not a
        diffed attribute -- two claims with different ids but identical
        value/source/date still have zero changed fields."""
        diff = compute_claim_diff(_diffable(claim_id="a"), _diffable(claim_id="b"))
        assert diff.changed_fields == ()
        assert diff.superseded_claim_id == "a"
        assert diff.successor_claim_id == "b"


class TestValueChangedOnly:
    def test_value_change_is_reported_alone(self) -> None:
        superseded = _diffable(value=17)
        successor = _diffable(value=18)
        diff = compute_claim_diff(superseded, successor)
        assert diff.changed_fields == ("value",)
        assert diff.old_value == 17
        assert diff.new_value == 18
        # Unchanged attributes still round-trip both sides, even though
        # they contribute no entry to changed_fields.
        assert diff.old_source_authority == diff.new_source_authority
        assert diff.old_verification_date == diff.new_verification_date

    def test_a_none_value_becoming_a_real_value_is_a_change(self) -> None:
        diff = compute_claim_diff(_diffable(value=None), _diffable(value="Class 12 pass"))
        assert diff.changed_fields == ("value",)
        assert diff.old_value is None
        assert diff.new_value == "Class 12 pass"

    def test_list_and_dict_values_compare_by_equality_not_identity(self) -> None:
        same_list = ["Physics", "Chemistry"]
        diff = compute_claim_diff(
            _diffable(value=list(same_list)), _diffable(value=list(same_list))
        )
        assert diff.changed_fields == ()

        diff_changed = compute_claim_diff(
            _diffable(value={"General": 50}), _diffable(value={"General": 60})
        )
        assert diff_changed.changed_fields == ("value",)


class TestSourceAuthorityChangedOnly:
    def test_source_authority_change_is_reported_alone(self) -> None:
        superseded = _diffable(source_authority="Old Board (test fixture)")
        successor = _diffable(source_authority="New Board (test fixture)")
        diff = compute_claim_diff(superseded, successor)
        assert diff.changed_fields == ("source_authority",)
        assert diff.old_source_authority == "Old Board (test fixture)"
        assert diff.new_source_authority == "New Board (test fixture)"
        assert diff.old_value == diff.new_value


class TestVerificationDateChangedOnly:
    def test_verification_date_change_is_reported_alone(self) -> None:
        superseded = _diffable(verification_date=_OLD_DATE)
        successor = _diffable(verification_date=_NEW_DATE)
        diff = compute_claim_diff(superseded, successor)
        assert diff.changed_fields == ("verification_date",)
        assert diff.old_verification_date == _OLD_DATE
        assert diff.new_verification_date == _NEW_DATE


class TestMultipleAttributesChanged:
    def test_changed_fields_follow_the_fixed_diff_attributes_order(self) -> None:
        """Order is `DIFF_ATTRIBUTES`'s own fixed order, regardless of
        which attributes actually changed."""
        superseded = _diffable(
            value=17, source_authority="Old Board", verification_date=_OLD_DATE
        )
        successor = _diffable(
            value=18, source_authority="New Board", verification_date=_NEW_DATE
        )
        diff = compute_claim_diff(superseded, successor)
        assert diff.changed_fields == ("value", "source_authority", "verification_date")
        assert diff.has_changes is True


class TestFieldIdentity:
    def test_field_is_the_superseded_claim_s_own_field_name(self) -> None:
        diff = compute_claim_diff(
            _diffable(field="minimum_age"), _diffable(field="minimum_age")
        )
        assert diff.field == "minimum_age"

    def test_claim_ids_are_taken_from_each_side_respectively(self) -> None:
        diff = compute_claim_diff(
            _diffable(claim_id="superseded-claim"), _diffable(claim_id="successor-claim")
        )
        assert diff.superseded_claim_id == "superseded-claim"
        assert diff.successor_claim_id == "successor-claim"


class TestImmutability:
    def test_diffable_claim_is_frozen(self) -> None:
        claim = _diffable()
        with pytest.raises(dataclasses.FrozenInstanceError):
            claim.value = 99  # type: ignore[misc]

    def test_claim_diff_is_frozen(self) -> None:
        diff = compute_claim_diff(_diffable(value=1), _diffable(value=2))
        with pytest.raises(dataclasses.FrozenInstanceError):
            diff.old_value = 100  # type: ignore[misc]

    def test_claim_diff_is_a_real_dataclass_instance(self) -> None:
        diff = compute_claim_diff(_diffable(), _diffable())
        assert dataclasses.is_dataclass(diff)
        assert isinstance(diff, ClaimDiff)


class TestPurity:
    def test_same_inputs_always_produce_an_equal_diff(self) -> None:
        superseded = _diffable(value=17)
        successor = _diffable(value=18)
        first = compute_claim_diff(superseded, successor)
        second = compute_claim_diff(superseded, successor)
        assert first == second
