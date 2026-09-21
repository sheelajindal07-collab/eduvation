#!/usr/bin/env python
"""Apply pending SQL migrations to the project's Postgres database directly.

Why this exists: the owner asked not to use the Supabase MCP tool or any
equivalent management-API automation for this project (docs/DECISIONS.md),
and asked to stop hand-pasting migration SQL into the dashboard's SQL
Editor each time. This script is the alternative: a plain, auditable
connection using a direct Postgres driver (psycopg) and nothing else — no
Supabase management API, no service that could reach any OTHER project.
Read it top to bottom; it does exactly what's on the page, once.

Usage:
    python scripts/apply_migrations.py                 # apply all pending
    python scripts/apply_migrations.py --dry-run       # show what would run
    python scripts/apply_migrations.py --through 0008  # stop AT 0008

Needs DATABASE_URL in the local .env (never in chat, never committed) —
Supabase: Project Settings -> Database -> Connection string -> URI (the
"Direct connection" or "Session pooler" string; either works for DDL).
Fill in the password placeholder yourself. This variable is intentionally
NOT read by the running application (app/core/config.py) — it grants
schema-level authority that a user-facing request must never have
(docs/SECURITY.md).

Tracking: creates a `_schema_migrations` table (filename, applied_at) so
re-running is safe — already-applied files are skipped, never re-run.

`--through NNNN` (DATA-15)
--------------------------
An UPPER BOUND on what this run may apply: every pending file whose
number is greater than NNNN is refused and listed, not applied. Without
it this script applies *every* pending file, which is the wrong default
for a staged rollout — the owner applies to dev, then staging, then
production from a tagged checkout, and a migration that has legitimately
merged to `main` for a *later* batch must not ride along early just
because it happens to be sitting in db/migrations/ (docs/DEVELOPMENT-PLAN.md
"Owner applies are bounded and tagged").

Two deliberate hardening choices, both of which exist because the bound
is a safety control and a safety control that fails open is worse than
none at all:

  * **Unknown arguments are a hard error.** This script used to test
    `"--dry-run" in sys.argv` and ignore everything else, so a typo —
    `--thruogh 0008`, `-through 0008`, `--through-0008` — would have been
    silently discarded and the run would have applied EVERY pending
    migration while the operator believed it was bounded. That is the
    exact accident `--through` exists to prevent, so anything this parser
    does not recognise stops the run instead.
  * **An unnumbered pending file is a hard error when --through is
    given.** The bound is only meaningful if every candidate file can
    actually be placed relative to it. A file this script cannot number
    cannot be proven to be at or below the bound, so it is never given
    the benefit of the doubt.

Neither changes the unbounded path: with no `--through`, behaviour is
exactly what it always was.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg
from pydantic_settings import BaseSettings, SettingsConfigDict

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

# Every migration in this repo is `NNNN_some_name.sql` (db/migrations/README.md).
# The trailing underscore is required on purpose: without it, a stray
# `0007.backup.sql` or `2026_notes.sql` would parse as a plausible-looking
# migration number and could be let through a bound it was never checked
# against.
_MIGRATION_NAME_RE = re.compile(r"^(\d+)_.+\.sql$")

_USAGE = (
    "usage: python scripts/apply_migrations.py [--dry-run] [--through NNNN]\n"
    "  --dry-run        list what would be applied; write nothing\n"
    "  --through NNNN   refuse to apply any migration numbered above NNNN"
)


class _MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str | None = None


class UsageError(Exception):
    """A bad command line. Raised, not printed, so the unit tests can
    assert on the message without capturing stdout."""


class UnnumberedMigrationError(Exception):
    """A pending file that `--through` cannot place relative to its bound."""


class Arguments:
    """Parsed command line. A tiny class rather than a tuple so the two
    fields are named at every call site."""

    def __init__(self, dry_run: bool = False, through: int | None = None) -> None:
        self.dry_run = dry_run
        self.through = through

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Arguments):
            return NotImplemented
        return self.dry_run == other.dry_run and self.through == other.through

    def __repr__(self) -> str:
        return f"Arguments(dry_run={self.dry_run!r}, through={self.through!r})"


def migration_number(filename: str) -> int | None:
    """The leading `NNNN` of a migration filename, or None if it has none.

    Leading zeros are ordinary (`0008` -> 8), so a bound written the way
    the filenames are written compares correctly against them.
    """
    match = _MIGRATION_NAME_RE.match(filename)
    return int(match.group(1)) if match else None


def _parse_bound(raw: str) -> int:
    """`--through`'s value. Digits only.

    Rejects a negative number, a float, whitespace-only, an empty string
    and anything else non-numeric, rather than letting `int()` coerce
    something surprising into a bound the operator did not intend. In
    particular this refuses `--through -1` outright instead of treating
    the next flag as a value.
    """
    text = raw.strip()
    if not text or not text.isdigit():
        raise UsageError(
            f"--through needs a migration number like 0008 or 8, not {raw!r}.\n{_USAGE}"
        )
    return int(text)


def parse_args(argv: list[str]) -> Arguments:
    """Strict parser: every token must be recognised (see module docstring)."""
    dry_run = False
    through: int | None = None

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--through":
            index += 1
            if index >= len(argv):
                raise UsageError(f"--through needs a migration number.\n{_USAGE}")
            through = _parse_bound(argv[index])
        elif arg.startswith("--through="):
            through = _parse_bound(arg.partition("=")[2])
        elif arg in {"-h", "--help"}:
            raise UsageError(_USAGE)
        else:
            raise UsageError(
                f"unrecognised argument {arg!r}. Refusing to run rather than "
                "ignore it: a mistyped --through would silently apply every "
                f"pending migration.\n{_USAGE}"
            )
        index += 1

    return Arguments(dry_run=dry_run, through=through)


def _pending_migrations(applied: set[str]) -> list[Path]:
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in applied]


def split_at_bound(
    pending: list[Path], through: int | None
) -> tuple[list[Path], list[Path]]:
    """Split `pending` into (to apply, refused by the bound).

    With no bound, everything is applied and nothing is refused — the
    historical behaviour, unchanged.

    With a bound, any pending file this script cannot number raises
    rather than being guessed at in either direction (see the module
    docstring).
    """
    if through is None:
        return list(pending), []

    unnumbered = [p.name for p in pending if migration_number(p.name) is None]
    if unnumbered:
        raise UnnumberedMigrationError(
            "--through was given, but these pending files have no NNNN_ "
            f"prefix this script can place against the bound: {', '.join(unnumbered)}. "
            "Refusing to apply anything — rename them to the NNNN_name.sql "
            "convention (db/migrations/README.md) or run without --through."
        )

    to_apply: list[Path] = []
    refused: list[Path] = []
    for path in pending:
        number = migration_number(path.name)
        assert number is not None  # guaranteed by the check above
        (to_apply if number <= through else refused).append(path)
    return to_apply, refused


def _report_refused(refused: list[Path], through: int) -> None:
    """Print what the bound held back. Always printed when non-empty —
    "nothing happened" and "four migrations were deliberately withheld"
    must never look the same in an operator's terminal."""
    if not refused:
        return
    print(f"--through {through:04d}: refusing {len(refused)} migration(s) above the bound:")
    for path in refused:
        print(f"  skipped (above --through {through:04d}): {path.name}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except UsageError as exc:
        print(exc, file=sys.stderr)
        return 2

    settings = _MigrationSettings()
    if not settings.database_url:
        print(
            "DATABASE_URL is not set in .env. See this script's docstring "
            "for where to find it in the Supabase dashboard.",
            file=sys.stderr,
        )
        return 1

    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists _schema_migrations (
                    filename text primary key,
                    applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()
            cur.execute("select filename from _schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

        pending = _pending_migrations(applied)

        try:
            to_apply, refused = split_at_bound(pending, args.through)
        except UnnumberedMigrationError as exc:
            print(exc, file=sys.stderr)
            return 1

        # Report the bound BEFORE the "nothing to apply" early return, so
        # `--through 0006` on a fully-applied database still tells the
        # operator what it held back instead of a bare "nothing to apply".
        if args.through is not None:
            _report_refused(refused, args.through)

        if not to_apply:
            if pending:
                print(
                    f"Nothing to apply at or below --through {args.through:04d} "
                    f"({len(pending)} pending migration(s), all above the bound)."
                )
            else:
                print("Nothing to apply — all migrations already recorded as applied.")
            return 0

        print(f"{len(to_apply)} pending migration(s): {', '.join(p.name for p in to_apply)}")
        if args.dry_run:
            print("--dry-run: not applying anything.")
            return 0

        for path in to_apply:
            print(f"Applying {path.name} ...")
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "insert into _schema_migrations (filename) values (%s)",
                    (path.name,),
                )
            conn.commit()
            print(f"  applied and recorded: {path.name}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
