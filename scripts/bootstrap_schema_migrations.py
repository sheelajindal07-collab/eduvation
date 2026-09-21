#!/usr/bin/env python
"""One-time bootstrap: record 0001-0004 as already-applied in
_schema_migrations WITHOUT re-running them, since they were applied by
hand via the SQL Editor before scripts/apply_migrations.py existed (see
that script's own docstring and db/migrations/README.md "One-time
bootstrap note"). Run this once, yourself, in a terminal where you've
loaded DATABASE_URL into just that session — never through an agent.

Usage:
    python scripts/bootstrap_schema_migrations.py

Idempotent: safe to re-run (uses ON CONFLICT DO NOTHING), so running it
twice by mistake does nothing the second time.
"""

from __future__ import annotations

import sys

import psycopg
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALREADY_APPLIED_BY_HAND = [
    "0001_init.sql",
    "0002_saved_plans.sql",
    "0003_maker_checker.sql",
    "0004_guardian_consent.sql",
]


class _MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str | None = None


def main() -> int:
    settings = _MigrationSettings()
    if not settings.database_url:
        print(
            "DATABASE_URL is not set. Load it into this terminal session "
            "first (see scripts/apply_migrations.py's docstring for where "
            "to find it), then re-run this script.",
            file=sys.stderr,
        )
        return 1

    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists _schema_migrations (
                filename text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )
        conn.commit()
        for name in _ALREADY_APPLIED_BY_HAND:
            cur.execute(
                "insert into _schema_migrations (filename) values (%s) "
                "on conflict (filename) do nothing",
                (name,),
            )
        conn.commit()
        cur.execute("select filename from _schema_migrations order by filename")
        rows = [r[0] for r in cur.fetchall()]

    print(f"_schema_migrations now contains {len(rows)} row(s):")
    for name in rows:
        print(f"  - {name}")
    print(
        "\nDone. Now run: python scripts/apply_migrations.py --dry-run "
        "to confirm only 0005 shows as pending."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
