# Migrations

Plain, numbered, append-only SQL files. Never edit a migration once it's
been applied anywhere — write a new one (`0002_...sql`, etc.).

## Two gotchas worth knowing before writing a new one

**`grant execute ... to authenticated` alone does NOT stop `anon` from
calling a function too** — live-verified, CONSENT-4 (0012/0013, renumbered
from 0011/0012 mid-review after `0011_ai_usage.sql`, AI-4, took the 0011
slot on `main`). This
Supabase stack grants EXECUTE on every new `public`-schema function
through TWO independent paths that a bare `grant ... to authenticated`
never touches: the SQL-standard default (EXECUTE to the pseudo-role
`PUBLIC`, which every role implicitly holds through) and this stack's own
`alter default privileges` setup (a DIRECT grant to `anon`/`authenticated`
/`service_role`). If a function must NOT be `anon`-callable, revoke from
**both** `public` and `anon` by name before granting to `authenticated` —
either revoke alone silently leaves the other grant in place. See
`0012_admission_axis.sql`'s `redeem_invite()` grant block for the full
live-verified reasoning and the exact statements.

**pgcrypto's functions (`gen_random_bytes`, `digest`, ...) live in the
`extensions` schema, not `public`**, on this stack — a bare, unqualified
call inside a `set search_path = public` function fails with "function
... does not exist". Schema-qualify (`extensions.digest(...)`), the same
fix `0006_guardian_consent_token_pgcrypto_schema.sql` already applied for
`gen_random_bytes`.

**A `security definer` predicate function that takes `p_uid uuid default
auth.uid()` is an identity oracle unless BOTH grants are revoked AND the
body is pinned to the caller** — live-verified, CONSENT-4 (0012/0013),
found by adversarial review AFTER the first merge, not before. The same
class of bug, pre-existing on already-merged `main`, was later found in
`account_active(uid)` (0004_guardian_consent.sql) too — see
`0014_account_active_grant_fix.sql`'s own header. The grant
mistake above (bare `grant ... to authenticated` not stopping `anon`) is
about WHO can call the function at all; this is a second, independent
mistake about WHAT it will answer once someone can: `is_admitted(p_uid)`/
`is_safeguarding_staff(p_uid)` were written to be called from inside RLS
policies as `is_admitted(auth.uid())` — always the caller's own id — but
nothing stopped a DIRECT RPC call from passing a DIFFERENT uid, turning
an internal RLS predicate into a per-uid probe of another account's
admission/staff status. The default parameter alone does not protect
this — a caller can always override a default. Two fixes, together, same
as redeem_invite()'s: revoke `public`/`anon` (grant to `authenticated`
only, as above) AND add `and p_uid = auth.uid()` to the function body's
own `where` clause, so even an `authenticated` caller passing someone
else's uid gets `false`, never the real answer. Test this by calling the
RPC with an explicit `p_uid` that is NOT the caller's own id, from BOTH
an anon client and a different authenticated client — a bare "call it
with no arguments as yourself" test cannot catch this class of bug at
all.

**Touching `storage.buckets`/`storage.objects`? Guard it with
`to_regclass('storage.buckets') is not null`, and don't `alter table
storage.objects enable row level security`** — live-verified,
`0017_publishing_evidence.sql` (PUB-2), this project's first-ever
Storage bucket. Two things this stack's own shape gets wrong if you
assume the cloud/dashboard defaults: (1) Storage is a separate service
this repo's SHARED test stack (`supabase/config.toml`) leaves entirely
OFF — the `storage` schema does not exist there at all, so a bare
`insert into storage.buckets ...` in a migration would hard-fail every
future apply on that stack. Wrap any storage DDL in `do $$ begin if
to_regclass('storage.buckets') is not null then ... end if; end $$;` so
the same migration file is a clean no-op there and does real work on a
stack that has Storage on (a migration owner's own dedicated copy of
`supabase/config.toml`, `[storage] enabled = true`, edited on that
untracked copy only — see that file's own header for how to make one).
(2) RLS is already ON by default on a freshly-provisioned `storage`
schema, and the plain `postgres` role `scripts/apply_migrations.py`
connects as does not even OWN `storage.objects` — `alter table
storage.objects enable row level security` fails outright with `must be
owner of table objects`, live-reproduced. Only ADD policies; never
touch that table's own RLS switch.

**A migration that changes WHO ends up as `created_by`/`reviewed_by` on
a row can break test teardown ordering that used to be safe** —
live-reproduced, `0017_publishing_evidence.sql` forcing
`claims.created_by` to the actual calling identity (rather than trusting
whatever a test payload claimed) turned
`tests/db/test_access_matrix.py`'s `claims-insert-reviewer-allow` cell
red at teardown: `supabase_auth_admin ERROR: update or delete on table
"users" violates foreign key constraint "claims_created_by_fkey"`. The
reviewer fixture that row now (correctly) references is created LAZILY,
inside the test body, i.e. AFTER the seeding fixture that was supposed
to clean the row up — so pytest's LIFO teardown deleted the user before
the row referencing it. Not a migration bug (the forcing is correct and
required); fixed in the test file by cleaning up seeded rows explicitly
before the test function returns, rather than trusting fixture-teardown
order across two independent fixture systems. Worth checking for on any
migration that starts binding a column to `auth.uid()` for the first
time — a payload field a test used to control now silently does
something else.

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
