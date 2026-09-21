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
python scripts/apply_migrations.py                 # applies anything pending
python scripts/apply_migrations.py --dry-run       # shows what would run, does nothing
python scripts/apply_migrations.py --through 0008  # applies up to AND INCLUDING 0008
```
It tracks what's been applied in a `_schema_migrations` table so it's
safe to run repeatedly. This connects directly to Postgres (via
`psycopg`) — no Supabase management API, no MCP tool, nothing that could
reach any project other than the one `DATABASE_URL` points at.

### `--through NNNN` — the upper bound (DATA-15)

Without it, this script applies **every** pending file. That is the
wrong default for a staged rollout: migrations merge to `main` in
batches, and a migration belonging to a *later* batch must not ride
along to staging early just because its file is sitting in this
directory. `--through` is the bound — anything numbered above it is
refused and **listed by name**, never silently dropped:

```
$ python scripts/apply_migrations.py --through 0008
--through 0008: refusing 2 migration(s) above the bound:
  skipped (above --through 0008): 0009_guest_sessions.sql
  skipped (above --through 0008): 0010_plan_actions.sql
2 pending migration(s): 0007_demo_mode.sql, 0008_jurisdiction_currency.sql
```

The bound is **inclusive** (`--through 0008` applies 0008) and compared
numerically, so `0010` correctly sorts above `0009`.

Two things it deliberately refuses outright, because a safety control
that fails open is worse than none:

- **An unrecognised argument** (`--thruogh 0008`, `-through 0008`) exits
  2 without connecting. The old parser ignored everything except
  `--dry-run`, so a typo here would have applied the whole ledger while
  the operator believed the run was bounded.
- **A pending `*.sql` with no `NNNN_` prefix**, while `--through` is in
  play, exits 1 without applying anything — the bound can only be
  trusted if every candidate file can be placed against it.

Combine with `--dry-run` to preview a bounded batch. Only the owner runs
this against a cloud project, from their own shell, always with
`--through`.

## Seeding sample content (`scripts/seed_synthetic.py`)

For dev and staging only. Inserts a few obviously-fictional careers,
pathways, sources and claims so there is something on the screen before
real verified content exists:

```
python scripts/seed_synthetic.py                    # insert or refresh
python scripts/seed_synthetic.py --dry-run          # show, write nothing
python scripts/seed_synthetic.py --purge            # remove exactly what it seeded
python scripts/seed_synthetic.py --enable-demo-mode # ... and turn demo mode on
```

Needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (the owner's admin
credential — the application itself never reads it).

Every seeded Source is `source_type = 'synthetic'` and every seeded
claim stops at `in_review`, so **nothing it writes can be published**:
`forbid_publishing_synthetic_claims()` in `0001_init.sql` refuses that
outright, for every caller including `service_role`. Seeded rows stay
invisible to visitors until demo mode is switched on
(`0007_demo_mode.sql`), which the script only does when explicitly
asked. Ids are UUIDv5 from a fixed namespace, so re-running rewrites the
same rows rather than adding a second copy — two runs give identical row
counts, and `--purge` deletes by id, never by name pattern.

**The production guard is two independent checks, both of which must
pass:**

| Check | Refuses when | Why alone it is not enough |
| --- | --- | --- |
| Environment | `APP_ENV=production` | A shell with a production URL and no `APP_ENV` set would pass |
| Target | `SUPABASE_URL`'s project ref matches `BCION_PRODUCTION_PROJECT_REF`, **or** the target is not loopback and its exact origin is not in `BCION_SEED_TARGET` | Relies on an allowlist somebody has to maintain |

Anything non-loopback and unrecognised is refused, never seeded on the
assumption that it is probably disposable. Set the two variable *values*
in your own environment — never in this repo.

**One-time bootstrap note:** `0001_init.sql` was applied manually via the
SQL Editor before this script existed. The first time `DATABASE_URL` is
available, that gets recorded in `_schema_migrations` as already-applied
(without re-running it) before the script is used normally — otherwise it
would try to re-run `0001_init.sql` and fail on "table already exists."
This is a one-off; every migration after `0001` goes through the script
normally.
