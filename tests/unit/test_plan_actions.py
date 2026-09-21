"""Unit tests for app/planning/actions.py (AUTH-5).

Acceptance line: "Actions derive only from published claims; draft or
synthetic-unpublished never appear."

The deriver is pure, so every branch is reachable here with no database
— which matters, because the property being tested is a negative ("a
draft never produces an action") and a negative is only convincing if
the test can actually construct the forbidden input.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.data.models import Claim, ClaimStatus, Source, SourceType
from app.planning.actions import (
    ACTION_RULES,
    MAX_ACTIONS,
    NOT_VERIFIED_YET,
    action_keys,
    derive_next_actions,
    is_known_action_key,
)

TODAY = date(2026, 9, 21)

OFFICIAL = Source(
    id="source-official",
    authority_name="A Real Authority",
    official_url="https://example.invalid/official",
    source_type=SourceType.official,
)
SYNTHETIC = Source(
    id="source-synthetic",
    authority_name="Sample Authority [SAMPLE DATA]",
    official_url="https://example.invalid/sample",
    source_type=SourceType.synthetic,
)
SOURCES = {OFFICIAL.id: OFFICIAL, SYNTHETIC.id: SYNTHETIC}


def _claim(
    field: str,
    *,
    status: ClaimStatus = ClaimStatus.published,
    source_id: str = OFFICIAL.id,
) -> Claim:
    return Claim(
        id=f"claim-{field}-{status.value}",
        entity_type="pathway",
        entity_id="pathway-1",
        field=field,
        value="something",
        source_id=source_id,
        verification_date=TODAY,
        verifier="reviewer@example.org",
        status=status,
        review_due_date=date(2027, 3, 21),
    )


class TestOnlyPublishedClaimsProduceActions:
    @pytest.mark.parametrize(
        "status",
        [ClaimStatus.draft, ClaimStatus.in_review, ClaimStatus.superseded],
    )
    def test_an_unpublished_claim_never_produces_an_action(
        self, status: ClaimStatus
    ) -> None:
        """An action is an instruction to a child about their education.
        Deriving one from a draft would be telling them to go and do
        something nobody has checked."""
        result = derive_next_actions(
            {"entry_requirements": _claim("entry_requirements", status=status)}, SOURCES
        )
        assert result.actions == []
        assert result.reason == NOT_VERIFIED_YET

    def test_a_published_claim_produces_its_action(self) -> None:
        result = derive_next_actions(
            {"entry_requirements": _claim("entry_requirements")}, SOURCES
        )
        assert action_keys(result) == ["check_entry_requirements"]
        assert result.reason is None

    def test_a_synthetic_sourced_claim_never_produces_an_action(self) -> None:
        """Demo mode (db/migrations/0007_demo_mode.sql) deliberately puts
        `in_review` synthetic claims into the read path, so this module
        genuinely receives them. A sample row must never become an
        instruction."""
        result = derive_next_actions(
            {
                "entry_requirements": _claim(
                    "entry_requirements",
                    status=ClaimStatus.in_review,
                    source_id=SYNTHETIC.id,
                )
            },
            SOURCES,
        )
        assert result.actions == []
        assert result.reason == NOT_VERIFIED_YET

    def test_a_synthetic_source_is_refused_even_if_marked_published(self) -> None:
        """Belt-and-braces. The 0001 trigger makes this row impossible in
        the database, so this is testing that the module does not DEPEND
        on that — if the status check were the only gate, this would
        pass and nobody would notice until the trigger changed."""
        result = derive_next_actions(
            {
                "entry_requirements": _claim(
                    "entry_requirements", source_id=SYNTHETIC.id
                )
            },
            SOURCES,
        )
        assert result.actions == []

    def test_a_claim_with_no_readable_source_is_refused(self) -> None:
        """No source row means no citation, and docs/UI.md requires one
        alongside anything presented as verified."""
        result = derive_next_actions(
            {"entry_requirements": _claim("entry_requirements", source_id="missing")},
            SOURCES,
        )
        assert result.actions == []
        assert result.reason == NOT_VERIFIED_YET

    def test_published_and_draft_together_yields_only_the_published_one(self) -> None:
        result = derive_next_actions(
            {
                "entry_requirements": _claim("entry_requirements"),
                "documents_required": _claim(
                    "documents_required", status=ClaimStatus.draft
                ),
            },
            SOURCES,
        )
        assert action_keys(result) == ["check_entry_requirements"]


class TestAtMostThree:
    def test_never_more_than_three(self) -> None:
        """docs/UI.md: "next three actions". There are five rules, so
        this is a real cap and not a vacuous one."""
        assert len(ACTION_RULES) > MAX_ACTIONS
        result = derive_next_actions(
            {rule.claim_field: _claim(rule.claim_field) for rule in ACTION_RULES},
            SOURCES,
        )
        assert len(result.actions) == MAX_ACTIONS

    def test_the_first_three_rules_win(self) -> None:
        """Rule order is priority order — what do I need, when do I
        apply, what do I bring."""
        result = derive_next_actions(
            {rule.claim_field: _claim(rule.claim_field) for rule in ACTION_RULES},
            SOURCES,
        )
        assert action_keys(result) == [rule.action_key for rule in ACTION_RULES[:3]]

    def test_gaps_are_skipped_not_padded(self) -> None:
        """A missing high-priority claim must let a lower-priority one
        through, rather than leaving a hole or stopping early."""
        result = derive_next_actions(
            {
                "documents_required": _claim("documents_required"),
                "time_range": _claim("time_range"),
            },
            SOURCES,
        )
        assert action_keys(result) == ["gather_documents", "plan_for_duration"]


class TestNoClaimsAtAll:
    def test_no_claims_gives_not_verified_yet(self) -> None:
        """docs/CONTRACTS.md, "Settled — coverage": absence of a
        published claim reads "not verified yet" — never "no", never
        zero, never blank."""
        result = derive_next_actions({}, SOURCES)
        assert result.actions == []
        assert result.reason == NOT_VERIFIED_YET

    def test_an_empty_result_is_falsy(self) -> None:
        assert not derive_next_actions({}, SOURCES)

    def test_a_populated_result_is_truthy(self) -> None:
        assert derive_next_actions(
            {"entry_requirements": _claim("entry_requirements")}, SOURCES
        )

    def test_an_unrelated_published_claim_produces_nothing(self) -> None:
        """A claim on a field with no action rule is not an action.
        `verified_charges` is a real, published, cited fact — and still
        not something to go and do."""
        result = derive_next_actions({"verified_charges": _claim("verified_charges")}, SOURCES)
        assert result.actions == []
        assert result.reason == NOT_VERIFIED_YET


class TestCitations:
    def test_each_action_carries_its_evidence(self) -> None:
        """Server-owned, read off the claim and its source — never
        assembled by a caller, never produced by a model."""
        result = derive_next_actions(
            {"entry_requirements": _claim("entry_requirements")}, SOURCES
        )
        action = result.actions[0]
        assert action.source_authority == OFFICIAL.authority_name
        assert action.source_url == OFFICIAL.official_url
        assert action.verification_date == TODAY
        assert action.claim_field == "entry_requirements"


class TestActionKeyValidation:
    @pytest.mark.parametrize("rule", ACTION_RULES, ids=lambda r: r.action_key)
    def test_every_rule_key_is_known(self, rule: object) -> None:
        assert is_known_action_key(rule.action_key)  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "bad", ["", "something_else", "DROP TABLE plan_actions", "check_entry_requirement"]
    )
    def test_an_arbitrary_string_is_not_a_known_key(self, bad: str) -> None:
        """`plan_actions.action_key` is plain `text` with no enum behind
        it, so this check is the only thing stopping a caller storing
        free text on a table that deliberately holds none."""
        assert is_known_action_key(bad) is False

    def test_action_keys_are_unique(self) -> None:
        keys = [rule.action_key for rule in ACTION_RULES]
        assert len(keys) == len(set(keys))

    def test_claim_fields_are_unique(self) -> None:
        fields = [rule.claim_field for rule in ACTION_RULES]
        assert len(fields) == len(set(fields))

    def test_no_action_key_is_display_text(self) -> None:
        """docs/CONTRACTS.md's rule for reasons applies here: machine
        codes only, resolved to English or Hindi at the presentation
        layer."""
        for rule in ACTION_RULES:
            assert rule.action_key.islower()
            assert " " not in rule.action_key


class TestPurity:
    def test_the_input_is_not_mutated(self) -> None:
        claims = {"entry_requirements": _claim("entry_requirements")}
        before = dict(claims)
        derive_next_actions(claims, SOURCES)
        assert claims == before

    def test_the_same_input_always_gives_the_same_output(self) -> None:
        """No clock, no randomness, no I/O — so two calls agree and the
        result is safe to cache or compare."""
        claims = {rule.claim_field: _claim(rule.claim_field) for rule in ACTION_RULES}
        assert action_keys(derive_next_actions(claims, SOURCES)) == action_keys(
            derive_next_actions(claims, SOURCES)
        )
