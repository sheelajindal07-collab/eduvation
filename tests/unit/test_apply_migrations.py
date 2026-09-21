"""Unit tests for DATA-15: `--through NNNN` in scripts/apply_migrations.py.

Pure-function tests only — nothing here opens a database connection, so
this suite runs under `make test-unit` with no stack configured.

The acceptance line: "refuses files numbered above the bound and prints
what it skipped". The tests below cover both halves, plus the two
hardening properties the script's own docstring argues for (a mistyped
flag must stop the run rather than silently apply everything; an
unnumbered pending file must not be given the benefit of the doubt).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.apply_migrations import (
    Arguments,
    UnnumberedMigrationError,
    UsageError,
    migration_number,
    parse_args,
    split_at_bound,
)

# The real ledger's shape at the time this was written, plus the four the
# migration lane goes on to add. Paths only — nothing is read from disk.
PENDING = [
    Path("db/migrations/0007_demo_mode.sql"),
    Path("db/migrations/0008_jurisdiction_currency.sql"),
    Path("db/migrations/0009_guest_sessions.sql"),
    Path("db/migrations/0010_plan_actions.sql"),
]


def _names(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


# --------------------------------------------------------------------
# migration_number
# --------------------------------------------------------------------


def test_migration_number_reads_the_leading_digits() -> None:
    assert migration_number("0008_jurisdiction_currency.sql") == 8


def test_migration_number_ignores_leading_zeros() -> None:
    # A bound written as 0008 and a filename written as 0008 must compare
    # as the same integer, not as two different strings.
    assert migration_number("0008_x.sql") == migration_number("8_x.sql") == 8


def test_migration_number_is_none_without_an_nnnn_prefix() -> None:
    assert migration_number("init.sql") is None
    assert migration_number("rollback_0008.sql") is None


def test_migration_number_requires_the_underscore_separator() -> None:
    # Guards the specific near-miss the regex was tightened for: a file
    # that merely STARTS with digits is not a numbered migration, and
    # must never be silently placed against a bound.
    assert migration_number("0007.backup.sql") is None


# --------------------------------------------------------------------
# parse_args
# --------------------------------------------------------------------


def test_no_arguments_is_unbounded() -> None:
    assert parse_args([]) == Arguments(dry_run=False, through=None)


def test_dry_run_alone_still_works() -> None:
    """The historical invocation must not have changed."""
    assert parse_args(["--dry-run"]) == Arguments(dry_run=True, through=None)


def test_through_with_a_separate_value() -> None:
    assert parse_args(["--through", "0008"]) == Arguments(dry_run=False, through=8)


def test_through_with_an_equals_sign() -> None:
    assert parse_args(["--through=0008"]) == Arguments(dry_run=False, through=8)


def test_through_accepts_an_unpadded_number() -> None:
    assert parse_args(["--through", "8"]).through == 8


def test_through_combines_with_dry_run() -> None:
    assert parse_args(["--dry-run", "--through", "0008"]) == Arguments(
        dry_run=True, through=8
    )


def test_through_without_a_value_is_refused() -> None:
    with pytest.raises(UsageError, match="needs a migration number"):
        parse_args(["--through"])


@pytest.mark.parametrize("bad", ["abc", "", "  ", "8.5", "-1", "0x08", "8,9"])
def test_through_rejects_a_non_numeric_bound(bad: str) -> None:
    with pytest.raises(UsageError):
        parse_args(["--through", bad])


@pytest.mark.parametrize(
    "typo",
    ["--thruogh", "-through", "--Through", "--through-0008", "--apply", "0008"],
)
def test_a_mistyped_flag_stops_the_run(typo: str) -> None:
    """The whole point of DATA-15: the OLD parser tested
    `"--dry-run" in sys.argv` and ignored every other token, so any of
    these would have been discarded and the run would have applied EVERY
    pending migration while the operator believed it was bounded."""
    with pytest.raises(UsageError, match="unrecognised argument"):
        parse_args([typo, "0008"])


def test_a_mistyped_flag_is_refused_even_alongside_a_valid_bound() -> None:
    with pytest.raises(UsageError, match="unrecognised argument"):
        parse_args(["--through", "0008", "--frce"])


# --------------------------------------------------------------------
# split_at_bound
# --------------------------------------------------------------------


def test_no_bound_applies_everything() -> None:
    to_apply, refused = split_at_bound(PENDING, None)
    assert _names(to_apply) == _names(PENDING)
    assert refused == []


def test_bound_refuses_everything_above_it() -> None:
    to_apply, refused = split_at_bound(PENDING, 8)
    assert _names(to_apply) == [
        "0007_demo_mode.sql",
        "0008_jurisdiction_currency.sql",
    ]
    assert _names(refused) == [
        "0009_guest_sessions.sql",
        "0010_plan_actions.sql",
    ]


def test_the_bound_is_inclusive() -> None:
    """`--through 0008` means "apply up to AND INCLUDING 0008" — the
    sense docs/DEVELOPMENT-PLAN.md's batch table uses ("apply --through
    0008 from the staging-batch-A tag", where batch A IS 0007-0008)."""
    to_apply, _ = split_at_bound(PENDING, 8)
    assert "0008_jurisdiction_currency.sql" in _names(to_apply)


def test_a_bound_below_everything_applies_nothing() -> None:
    to_apply, refused = split_at_bound(PENDING, 6)
    assert to_apply == []
    assert _names(refused) == _names(PENDING)


def test_a_bound_above_everything_applies_everything() -> None:
    to_apply, refused = split_at_bound(PENDING, 9999)
    assert _names(to_apply) == _names(PENDING)
    assert refused == []


def test_numeric_not_lexicographic_comparison() -> None:
    """A string compare would put '10' before '9'. Only an integer
    compare gets a two-digit-to-four-digit ledger right."""
    pending = [Path("0009_a.sql"), Path("0010_b.sql")]
    to_apply, refused = split_at_bound(pending, 9)
    assert _names(to_apply) == ["0009_a.sql"]
    assert _names(refused) == ["0010_b.sql"]


def test_an_unnumbered_pending_file_refuses_the_whole_run() -> None:
    """Fail closed: the bound is only meaningful if every candidate can
    be placed against it, so a file that cannot be numbered stops
    everything rather than being applied or silently dropped."""
    pending = [Path("0007_demo_mode.sql"), Path("hotfix.sql")]
    with pytest.raises(UnnumberedMigrationError, match="hotfix.sql"):
        split_at_bound(pending, 8)


def test_an_unnumbered_file_is_fine_without_a_bound() -> None:
    """Unbounded behaviour is untouched — this script has always applied
    whatever `*.sql` it found, in sorted order."""
    pending = [Path("0007_demo_mode.sql"), Path("hotfix.sql")]
    to_apply, refused = split_at_bound(pending, None)
    assert _names(to_apply) == ["0007_demo_mode.sql", "hotfix.sql"]
    assert refused == []


def test_split_does_not_mutate_the_input_list() -> None:
    pending = list(PENDING)
    split_at_bound(pending, 8)
    assert pending == PENDING
