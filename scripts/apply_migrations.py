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
    python scripts/apply_migrations.py           # apply all pending
    python scripts/apply_migrations.py --dry-run # show what would run

Needs DATABASE_URL in the local .env (never in chat, never committed) —
Supabase: Project Settings -> Database -> Connection string -> URI (the
"Direct connection" or "Session pooler" string; either works for DDL).
Fill in the password placeholder yourself. This variable is intentionally
NOT read by the running application (app/core/config.py) — it grants
schema-level authority that a user-facing request must never have
(docs/SECURITY.md).

Tracking: creates a `_schema_migrations` table (filename, applied_at) so
re-running is safe — already-applied files are skipped, never re-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from pydantic_settings import BaseSettings, SettingsConfigDict

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


class _MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str | None = None


def _pending_migrations(applied: set[str]) -> list[Path]:
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in applied]


def main() -> int:
    dry_run = "--dry-run" in sys.argv

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
        if not pending:
            print("Nothing to apply — all migrations already recorded as applied.")
            return 0

        print(f"{len(pending)} pending migration(s): {', '.join(p.name for p in pending)}")
        if dry_run:
            print("--dry-run: not applying anything.")
            return 0

        for path in pending:
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
