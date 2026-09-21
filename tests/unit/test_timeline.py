"""Tests for app/rules/timeline.py.

The single most important property here mirrors test_cost.py: an unknown
stage duration must make the total unknown (`None`), never a partial sum
presented as the real timeline. The second property, unique to this
engine, is that overlapping stages are genuinely subtracted rather than
blindly summed (Build Pack §6).
"""

import pytest

from app.rules.timeline import (
    BackupPathway,
    ParallelActivity,
    Stage,
    compute_timeline,
    expand_attempts,
)


class TestComputeTimelineBasics:
    def test_sequential_stages_sum_with_no_overlap(self) -> None:
        stages = [
            Stage("Class 12", duration_weeks=52),
            Stage("Degree", duration_weeks=208),
        ]
        result = compute_timeline(stages)
        assert result.total_weeks == 260
        assert result.complete is True

    def test_empty_stage_list_gives_none_total(self) -> None:
        result = compute_timeline([])
        assert result.total_weeks is None
        assert result.complete is False

    def test_zero_duration_stage_is_a_valid_edge_case(self) -> None:
        """Boundary: a stage that takes no time (e.g. an instant transfer
        between programmes) is not the same as an unknown stage."""
        stages = [Stage("Instant transition", duration_weeks=0), Stage("Degree", 208)]
        result = compute_timeline(stages)
        assert result.total_weeks == 208
        assert result.complete is True


class TestUnknownDurationNeverSilentlyDropped:
    def test_one_unknown_required_stage_gives_none_total(self) -> None:
        stages = [Stage("Class 12", duration_weeks=52), Stage("Degree", duration_weeks=None)]
        result = compute_timeline(stages)
        assert result.total_weeks is None
        assert result.complete is False
        assert result.unknown == (Stage("Degree", duration_weeks=None),)

    def test_unknown_optional_stage_also_gives_none_total(self) -> None:
        """`required=False` is a display distinction only (module
        docstring) — an optional stage the student's plan actually
        includes still can't be silently excluded from the total just
        because its duration isn't known yet."""
        stages = [
            Stage("Class 12", duration_weeks=52),
            Stage("Optional bridge course", duration_weeks=None, required=False),
        ]
        result = compute_timeline(stages)
        assert result.total_weeks is None
        assert result.complete is False

    def test_multiple_unknown_stages_all_reported(self) -> None:
        stages = [
            Stage("A", duration_weeks=None),
            Stage("B", duration_weeks=10),
            Stage("C", duration_weeks=None),
        ]
        result = compute_timeline(stages)
        assert result.total_weeks is None
        assert len(result.unknown) == 2


class TestOverlappingDurationsAreNotBlindlySummed:
    def test_overlap_reduces_the_naive_sum(self) -> None:
        """Build Pack §6's core example: an internship that starts
        before the degree's final semester ends."""
        stages = [
            Stage("Degree", duration_weeks=208),
            Stage("Internship", duration_weeks=26, overlap_weeks_with_previous=8),
        ]
        result = compute_timeline(stages)
        # Naive sum would be 234; 8 weeks run concurrently.
        assert result.total_weeks == 208 + 26 - 8
        assert result.total_weeks == 226

    def test_overlap_exceeding_previous_stage_duration_raises(self) -> None:
        stages = [
            Stage("Short prep", duration_weeks=4),
            Stage("Attempt", duration_weeks=10, overlap_weeks_with_previous=5),
        ]
        with pytest.raises(ValueError, match="exceeds one of their durations"):
            compute_timeline(stages)

    def test_overlap_exceeding_own_duration_raises(self) -> None:
        stages = [
            Stage("Prep", duration_weeks=20),
            Stage("Short attempt", duration_weeks=3, overlap_weeks_with_previous=5),
        ]
        with pytest.raises(ValueError, match="exceeds one of their durations"):
            compute_timeline(stages)

    def test_overlap_on_first_stage_raises(self) -> None:
        """There is no previous stage for the very first entry to
        overlap — a content-authoring error, not a value to guess at."""
        stages = [Stage("Class 12", duration_weeks=52, overlap_weeks_with_previous=4)]
        with pytest.raises(ValueError, match="can't overlap with a previous stage"):
            compute_timeline(stages)

    def test_overlap_exactly_equal_to_shorter_stage_is_allowed(self) -> None:
        """Boundary: overlap == the shorter of the two durations is the
        edge of validity, not over it."""
        stages = [
            Stage("Degree", duration_weeks=208),
            Stage("Internship", duration_weeks=8, overlap_weeks_with_previous=8),
        ]
        result = compute_timeline(stages)
        assert result.total_weeks == 208  # the internship adds nothing extra


class TestExpandAttempts:
    def test_single_attempt_has_no_gap_applied(self) -> None:
        stage = expand_attempts(
            attempt_duration_weeks=52, num_attempts=1, gap_between_attempts_weeks=12
        )
        assert stage.duration_weeks == 52

    def test_multiple_attempts_include_gaps_between_but_not_after(self) -> None:
        stage = expand_attempts(
            attempt_duration_weeks=52, num_attempts=3, gap_between_attempts_weeks=12
        )
        # 3 attempts of 52 weeks, 2 gaps of 12 weeks (never a trailing gap).
        assert stage.duration_weeks == 52 * 3 + 12 * 2
        assert stage.duration_weeks == 180

    def test_zero_attempts_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            expand_attempts(attempt_duration_weeks=52, num_attempts=0)

    def test_negative_attempts_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            expand_attempts(attempt_duration_weeks=52, num_attempts=-1)

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValueError, match="not be negative"):
            expand_attempts(attempt_duration_weeks=-1, num_attempts=2)

    def test_expanded_attempt_stage_composes_into_a_timeline(self) -> None:
        """The whole point: the result plugs straight into
        compute_timeline like any other stage."""
        attempts = expand_attempts(
            attempt_duration_weeks=52, num_attempts=2, gap_between_attempts_weeks=8
        )
        result = compute_timeline([Stage("Class 12", 52), attempts])
        assert result.total_weeks == 52 + (52 * 2 + 8)


class TestParallelActivitiesNeverAddToTotal:
    def test_parallel_activity_present_but_excluded_from_total(self) -> None:
        """The core rule for this dataclass, mirroring cost.py's
        potential-assistance guarantee: a parallel activity is visible
        for awareness but categorically absent from the arithmetic."""
        stages = [Stage("Degree", duration_weeks=208)]
        activities = [ParallelActivity("Coaching classes", duration_weeks=104)]
        result = compute_timeline(stages, parallel_activities=activities)
        assert result.total_weeks == 208
        assert result.parallel_activities[0].duration_weeks == 104
        assert result.parallel_activities[0].name == "Coaching classes"

    def test_parallel_activity_with_unknown_duration_does_not_block_total(self) -> None:
        stages = [Stage("Degree", duration_weeks=208)]
        activities = [ParallelActivity("Maybe a certification", duration_weeks=None)]
        result = compute_timeline(stages, parallel_activities=activities)
        assert result.total_weeks == 208
        assert result.complete is True

    def test_no_parallel_activities_is_the_default(self) -> None:
        result = compute_timeline([Stage("Degree", duration_weeks=208)])
        assert result.parallel_activities == ()


class TestBackupPathwaysComposeIndependently:
    def test_backup_pathway_has_its_own_independent_total(self) -> None:
        """A backup never shares arithmetic with the primary path it's
        an alternative to (Build Pack §6: 'backup transitions')."""
        primary = compute_timeline([Stage("Attempt engineering entrance", 52)])
        backup = BackupPathway(
            name="Switch to allied health degree",
            stages=(Stage("Allied health degree", duration_weeks=156),),
        )
        backup_result = compute_timeline(list(backup.stages))
        assert primary.total_weeks == 52
        assert backup_result.total_weeks == 156
        assert backup.name == "Switch to allied health degree"

    def test_backup_pathway_with_unknown_duration_stage_gives_none_total(self) -> None:
        """A backup's own stage list is fed straight back into
        compute_timeline, so an unknown duration inside it must be just
        as honest as an unknown duration in the primary path — never
        silently dropped just because it's a fallback plan."""
        backup = BackupPathway(
            name="Switch to allied health degree",
            stages=(
                Stage("Bridge course", duration_weeks=None),
                Stage("Allied health degree", duration_weeks=156),
            ),
        )
        backup_result = compute_timeline(list(backup.stages))
        assert backup_result.total_weeks is None
        assert backup_result.complete is False
        assert backup_result.unknown == (Stage("Bridge course", duration_weeks=None),)


class TestManyStagesMixedOverlaps:
    def test_ten_plus_stages_with_mixed_overlapping_and_non_overlapping(self) -> None:
        """A long real-world pathway: some stages overlap their
        predecessor, most don't, some overlap by zero explicitly. The
        total must equal the naive sum minus exactly the declared
        overlaps, no more and no less."""
        stages = [
            Stage("Class 8", duration_weeks=52),
            Stage("Class 9", duration_weeks=52),
            Stage("Class 10", duration_weeks=52),
            Stage("Board exam prep", duration_weeks=12, overlap_weeks_with_previous=4),
            Stage("Class 11", duration_weeks=52),
            Stage("Class 12", duration_weeks=52),
            Stage("Entrance coaching", duration_weeks=26, overlap_weeks_with_previous=10),
            Stage("Entrance exam attempts", duration_weeks=20),
            Stage("Degree year 1", duration_weeks=52),
            Stage("Degree year 2", duration_weeks=52),
            Stage("Internship", duration_weeks=16, overlap_weeks_with_previous=6),
            Stage("Degree year 3", duration_weeks=52, overlap_weeks_with_previous=0),
        ]
        result = compute_timeline(stages)
        naive_sum = sum(s.duration_weeks for s in stages)  # type: ignore[misc]
        total_overlap = 4 + 10 + 6
        assert result.total_weeks == naive_sum - total_overlap
        assert result.complete is True
        assert len(result.stages) == 12


class TestExpandAttemptsZeroGap:
    def test_zero_gap_between_attempts_is_just_the_attempts_summed(self) -> None:
        """An explicit zero gap (back-to-back attempts, e.g. consecutive
        exam sittings with no break) must not raise and must contribute
        nothing extra — distinct from omitting the gap argument."""
        stage = expand_attempts(
            attempt_duration_weeks=10, num_attempts=4, gap_between_attempts_weeks=0
        )
        assert stage.duration_weeks == 40

    def test_zero_gap_matches_default_gap_omitted(self) -> None:
        explicit = expand_attempts(
            attempt_duration_weeks=8, num_attempts=3, gap_between_attempts_weeks=0
        )
        default = expand_attempts(attempt_duration_weeks=8, num_attempts=3)
        assert explicit.duration_weeks == default.duration_weeks == 24


class TestParallelActivityListWithManyEntries:
    def test_five_plus_parallel_activities_all_reported_none_affect_total(self) -> None:
        stages = [Stage("Degree", duration_weeks=208)]
        activities = [
            ParallelActivity("Coaching classes", duration_weeks=104),
            ParallelActivity("Part-time certification", duration_weeks=52),
            ParallelActivity("Language course", duration_weeks=26),
            ParallelActivity("Volunteering", duration_weeks=None),
            ParallelActivity("Sports commitment", duration_weeks=200),
            ParallelActivity("Online electives", duration_weeks=12),
        ]
        result = compute_timeline(stages, parallel_activities=activities)
        assert result.total_weeks == 208
        assert result.complete is True
        assert len(result.parallel_activities) == 6
        assert [a.name for a in result.parallel_activities] == [
            "Coaching classes",
            "Part-time certification",
            "Language course",
            "Volunteering",
            "Sports commitment",
            "Online electives",
        ]
