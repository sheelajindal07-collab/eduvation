"""Timeline engine — Lite Build Pack §6, docs/SECURITY.md quality gate
("overlapping durations").

Deterministic. No model tokens. Build Pack §6: "Remaining education,
optional preparation, user-chosen attempts, training or internship,
parallel activities, backup transitions; durations are not blindly added
because preparation, applications and internships overlap."

**The single most safety-critical rule in this module:** a stage with an
unknown duration must never be silently dropped from the total — the
total becomes `None` (unknown), never a confident-looking number that's
quietly missing a piece. This mirrors `app/rules/cost.py`'s
`sum_verified_charges` on purpose: both engines refuse to turn "we don't
know" into "zero".

Unit: whole weeks (`int`). Weeks are the finest grain the source material
(entrance-exam cycles, application windows) is ever specified in, and an
integer avoids the rounding drift that fractional months/years would
invite (docs/SECURITY.md: "rounding" is its own listed test case).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    """One stage of a pathway (a year of study, an entrance-exam cycle, an
    internship, ...).

    `required` vs optional is a *display* distinction only (Build Pack
    §6: "required stages, optional stages ... distinguished") — it does
    not change how a stage is summed. A stage's presence in the list
    means the student's specific plan includes it, so if its duration is
    unknown the total is unknown too, regardless of `required`. Callers
    who want to show "what if I skip this" build a second, shorter list
    and call `compute_timeline` again rather than relying on optional
    stages being silently excluded here.

    `overlap_weeks_with_previous` is how this stage overlaps the stage
    immediately before it in the list (Build Pack §6: "preparation,
    applications and internships overlap") — e.g. an internship that
    starts 8 weeks before the final semester ends. It must not exceed
    either stage's own duration; `compute_timeline` raises if it does,
    since that would mean a stage overlapping a period longer than it (or
    the previous stage) actually lasts — a content-authoring error to
    catch in tests, not a student input to degrade gracefully on.
    """

    name: str
    duration_weeks: int | None
    required: bool = True
    overlap_weeks_with_previous: int = 0
    source_claim_id: str | None = None


@dataclass(frozen=True)
class ParallelActivity:
    """An activity that runs alongside the main path (coaching classes
    during a degree, a part-time certification, ...). Shown for
    awareness only — Build Pack §6 lists "parallel activities" as
    distinct from the sequential stages, and this engine's job is to
    never let one silently inflate the timeline the way an unconditional
    sum would. There is deliberately no arithmetic here: a parallel
    activity never appears in `total_weeks`, the same way
    `app/rules/cost.py`'s potential assistance never appears in
    `net_to_arrange`."""

    name: str
    duration_weeks: int | None = None
    source_claim_id: str | None = None


@dataclass(frozen=True)
class BackupPathway:
    """A named alternative stage sequence, for when an attempt doesn't
    work out (Build Pack §6: "backup transitions"; docs/UI.md: "an
    unsuccessful attempt offers 'Revise this scenario', never a failure
    badge"). Deliberately just a label plus its own stage list — its
    timeline is computed by passing `stages` to `compute_timeline` like
    any other pathway, so a backup never shares arithmetic with the
    primary path it's an alternative to."""

    name: str
    stages: tuple[Stage, ...]


@dataclass(frozen=True)
class TimelineResult:
    stages: tuple[Stage, ...]
    parallel_activities: tuple[ParallelActivity, ...]
    total_weeks: int | None
    """`None` when any stage's duration is unknown — never a partial sum
    presented as if it were the whole timeline."""
    complete: bool

    @property
    def unknown(self) -> tuple[Stage, ...]:
        return tuple(s for s in self.stages if s.duration_weeks is None)


def compute_timeline(
    stages: list[Stage],
    parallel_activities: list[ParallelActivity] | None = None,
) -> TimelineResult:
    """Sum a pathway's stages into one total, honest about incompleteness
    and about overlap.

    `total_weeks = sum(stage durations) - sum(overlaps)`. Overlap is
    validated, not silently clamped: an overlap longer than either
    adjacent stage's own duration means the input data is wrong, and
    hiding that would risk an under-count nobody can see.
    """
    parallel = tuple(parallel_activities or ())

    if not stages:
        return TimelineResult(
            stages=(), parallel_activities=parallel, total_weeks=None, complete=False
        )

    if any(s.duration_weeks is None for s in stages):
        return TimelineResult(
            stages=tuple(stages),
            parallel_activities=parallel,
            total_weeks=None,
            complete=False,
        )

    total = 0
    previous: Stage | None = None
    for stage in stages:
        assert stage.duration_weeks is not None  # narrowed by the guard above
        overlap = stage.overlap_weeks_with_previous
        if overlap:
            if previous is None:
                raise ValueError(
                    f"{stage.name!r} can't overlap with a previous stage — "
                    "it's the first one, so there's nothing before it."
                )
            assert previous.duration_weeks is not None
            if overlap > previous.duration_weeks or overlap > stage.duration_weeks:
                raise ValueError(
                    f"Stage {stage.name!r} overlaps its previous stage by {overlap} weeks, "
                    f"which exceeds one of their durations "
                    f"({previous.name}={previous.duration_weeks}w, "
                    f"{stage.name}={stage.duration_weeks}w)."
                )
        total += stage.duration_weeks - overlap
        previous = stage

    return TimelineResult(
        stages=tuple(stages), parallel_activities=parallel, total_weeks=total, complete=True
    )


def expand_attempts(
    *,
    attempt_duration_weeks: int,
    num_attempts: int,
    gap_between_attempts_weeks: int = 0,
    name: str | None = None,
    source_claim_id: str | None = None,
) -> Stage:
    """Build a single `Stage` for "user-chosen attempts" (Build Pack §6)
    — e.g. a student planning for up to 3 entrance-exam cycles.

    `num_attempts` attempts of `attempt_duration_weeks` each, with
    `gap_between_attempts_weeks` between consecutive attempts (results
    announcement, re-registration, ...) — the gap applies `num_attempts -
    1` times, never after the last attempt.
    """
    if num_attempts < 1:
        raise ValueError(f"num_attempts must be at least 1, got {num_attempts}.")
    if attempt_duration_weeks < 0 or gap_between_attempts_weeks < 0:
        raise ValueError("Durations must not be negative.")

    total = attempt_duration_weeks * num_attempts + gap_between_attempts_weeks * (num_attempts - 1)
    label = name or (f"{num_attempts} attempt" + ("s" if num_attempts != 1 else ""))
    return Stage(name=label, duration_weeks=total, source_claim_id=source_claim_id)
