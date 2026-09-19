# Migrations

Plain, numbered, append-only SQL files. Never edit a migration once it's
been applied anywhere — write a new one (`0002_...sql`, etc.).

## Applying (on your own Supabase project — see `docs/DECISIONS.md`)
1. Create a project at [supabase.com](https://supabase.com) (Mumbai /
   `ap-south-1` region recommended — see `docs/SECURITY.md`'s residency
   table) or use the Supabase CLI's local dev stack if you have Docker.
2. Run `0001_init.sql` in the project's SQL editor (Dashboard → SQL
   Editor → paste → Run), or `supabase db push` if you're using the CLI
   with a linked project.
3. Copy `.env.example` to `.env` in the repo root and fill in your
   project's `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (Project
   Settings → API). Never commit `.env` or paste its values into chat.

## What `0001_init.sql` creates
Tables: `sources`, `careers`, `pathways`, `claims`, `student_profiles`,
`reviewers`. RLS policies enforcing: world-readable public knowledge base
(sources/careers/pathways/published claims), reviewer-only writes, and
strictly own-row access on `student_profiles`. See the file's own comments
for the M1-vs-M4 boundary on the maker-checker rule.

## Testing (`make test-db`)
Needs `SUPABASE_URL` set to a real project with this migration applied.
See `tests/db/` — currently skips with a clear reason if unconfigured,
so `make test-db` never silently reports green for a check that didn't
run.

## Applying automatically (`scripts/apply_migrations.py`)
Once you've added `DATABASE_URL` to your local `.env` (Project Settings
→ Database → Connection string → URI; fill in the password yourself —
never share it in chat), new migrations can be applied without the
dashboard:
```
python scripts/apply_migrations.py            # applies anything pending
python scripts/apply_migrations.py --dry-run  # shows what would run, does nothing
```
It tracks what's been applied in a `_schema_migrations` table so it's
safe to run repeatedly. This connects directly to Postgres (via
`psycopg`) — no Supabase management API, no MCP tool, nothing that could
reach any project other than the one `DATABASE_URL` points at.

**One-time bootstrap note:** `0001_init.sql` was applied manually via the
SQL Editor before this script existed. The first time `DATABASE_URL` is
available, that gets recorded in `_schema_migrations` as already-applied
(without re-running it) before the script is used normally — otherwise it
would try to re-run `0001_init.sql` and fail on "table already exists."
This is a one-off; every migration after `0001` goes through the script
normally.
