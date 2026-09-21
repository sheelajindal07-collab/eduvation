-- BCION Lite — DB-gated demo mode for clearly-labelled synthetic data
-- Source of truth: DATA-12's card; docs/CONTRACTS.md "Settled —
-- `is_sample`" ("a sample row can never be published, and carries a
-- visible label wherever it appears") and its flag list ("...plus the
-- demo-mode guard"); CLAUDE.md non-negotiable ("Synthetic fixtures are
-- clearly labelled and NEVER published as verified facts").
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py (see db/migrations/README.md) —
-- same as 0001-0006.
--
-- **Real number check (migration-owner rule):** the card and
-- docs/plan/inventory-1-product.md both call this "0005_demo_mode.sql".
-- `ls db/migrations/` at the moment this was written shows 0001-0006
-- already present and applied, so the next genuinely free number is
-- 0007 and that is what this file uses. The planning number was stale,
-- exactly as that rule anticipates.
--
-- ============================================================
-- What this is for
-- ============================================================
-- Staging needs to *show* something. Real verified content does not
-- exist yet (the content track is still producing it), and the one
-- thing that must never happen to make a demo work is publishing a
-- synthetic claim — `forbid_publishing_synthetic_claims()`
-- (0001_init.sql) exists precisely to make that impossible, and this
-- migration does not touch it, weaken it, or route around it. It is
-- still true after this migration that NO synthetic-sourced claim can
-- ever reach `published`, from any caller, by any path.
--
-- Instead, demo mode opens a second, much narrower window: while the
-- flag is on, an anonymous visitor may additionally see claims that are
-- BOTH still `in_review` AND sourced from a `synthetic` Source. Those
-- rows are visibly sample data by construction (their Source is a
-- synthetic one, which the read path surfaces as `is_sample` — see
-- app/api/compare.py's FieldValueOut), and they are the only extra rows
-- this opens up.
--
-- **The property that matters, stated as a negative:** a real,
-- non-synthetic draft must never become visible to a guest, in any
-- demo-mode state. The policy below ANDs three separate conditions to
-- get that, and tests/db/test_demo_mode.py checks each one by removing
-- it (revert-to-prove) rather than only checking the happy path:
--   1. `demo_mode()` is on — off is the default and the fail-closed state.
--   2. `status = 'in_review'` — never 'draft', never 'superseded'. A
--      claim nobody has even submitted for review is not demo material.
--   3. the claim's Source is `source_type = 'synthetic'` — the actual
--      "this is sample data" marker.
-- Drop any one of the three and a real draft leaks. All three are
-- required, in one policy, ANDed — never split across two policies,
-- because multiple PERMISSIVE policies on the same command are OR'd
-- together in Postgres, and two half-conditions OR'd is exactly the
-- bypass this comment exists to prevent anyone from "simplifying" into.

-- ============================================================
-- app_settings — one row, owner-writable only
-- ============================================================
-- Single-row by construction: `id` is a boolean primary key CHECKed to
-- be true, so there is exactly one possible key and a second INSERT is a
-- primary-key violation rather than a silently-ignored second row that
-- `demo_mode()` might or might not pick. Preferred over a settings
-- key/value table: this holds one operational flag, not a registry, and
-- a typed boolean column cannot be set to the string 'flase'.
create table app_settings (
    id          boolean primary key default true check (id),
    demo_mode   boolean not null default false,
    updated_at  timestamptz not null default now()
);

-- Reuses touch_updated_at(), defined in 0002_saved_plans.sql (already
-- applied by the time this migration runs — append-only, in order).
create trigger app_settings_touch_updated_at
before update on app_settings
for each row execute function touch_updated_at();

-- The row must exist from the start, explicitly OFF. `demo_mode()`
-- below also coalesces a missing row to false, so the fail-closed state
-- holds even if this row were ever deleted — two independent reasons the
-- answer is "off" unless somebody deliberately turned it on.
insert into app_settings (id, demo_mode) values (true, false);

alter table app_settings enable row level security;

-- NO policy is added on `app_settings`, deliberately — the same pattern
-- 0001_init.sql uses for `reviewers` and 0004 uses for the SELECT side
-- of `guardian_consents`: RLS enabled with zero matching policies means
-- "no access" by default, for anon and authenticated alike. Nobody
-- reads or writes this table through the API; only the `demo_mode()`
-- security-definer function below touches it.
--
-- Belt-and-braces on top of that (this is a kill switch, so two
-- independent mechanisms are worth the two lines): Supabase's default
-- privileges grant table-level rights on anything new in `public` to
-- `anon` and `authenticated`, and those grants are what PostgREST
-- consults before RLS is ever reached. Revoking them means a direct
-- REST call gets a flat permission-denied instead of an empty result
-- set — a clearer signal, and one that does not depend on the absence
-- of a policy staying absent through some future migration.
--
-- `service_role` is deliberately NOT revoked: that is the owner's own
-- direct/admin connection (docs/SECURITY.md — never used for a
-- user-facing request), and it is how the flag actually gets turned on
-- for a staging demo, and how tests/db/test_demo_mode.py flips it.
revoke all on table app_settings from anon, authenticated;

-- ============================================================
-- demo_mode() — the flag, readable without exposing the table
-- ============================================================
-- Mirrors `is_reviewer()`'s exact shape (0001_init.sql): `language sql
-- stable security definer set search_path = public`. The pinned
-- search_path is not decorative — a definer function runs with the
-- owner's rights, so an unpinned path would let a caller who can create
-- a schema shadow `app_settings` with their own table and dictate this
-- function's answer.
--
-- SECURITY DEFINER is what lets an RLS policy consult a table that the
-- calling role has no rights on at all. That is the whole point: the
-- answer to "is demo mode on" must be readable by the policy machinery
-- for every caller, while the table itself stays unreadable and
-- unwritable by every caller. An ordinary RLS-scoped caller could not
-- do this — it would see zero rows and coalesce to false, which would
-- make demo mode permanently and silently inert.
--
-- `coalesce(..., false)` is the fail-closed default: no row, no table
-- content, nothing to read — the answer is "off", never "on".
create or replace function demo_mode()
returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select s.demo_mode from app_settings s limit 1), false);
$$;

-- ============================================================
-- The extra claims SELECT policy
-- ============================================================
-- ADDITIVE. 0001_init.sql's `claims_select_published` ("status =
-- 'published' or is_reviewer()") is untouched and still does all the
-- work it did before; Postgres OR-combines multiple permissive SELECT
-- policies, so this one can only ever widen visibility, never narrow
-- it, and a reviewer's own view is unchanged.
--
-- The `exists` subquery against `sources` is the same shape
-- 0001_init.sql's own `forbid_publishing_synthetic_claims()` trigger
-- already uses to answer the same question, deliberately — one way of
-- asking "is this claim's source synthetic", not two that could drift
-- apart. `sources` is world-readable (`sources_select_all using (true)`,
-- 0001), so this resolves for an anonymous caller; and if some future
-- migration ever restricted `sources`, this subquery would return no
-- row and the policy would deny — the fail-closed direction.
create policy claims_select_demo_synthetic on claims for select
  using (
    demo_mode()
    and status = 'in_review'
    and exists (
      select 1
      from sources s
      where s.id = claims.source_id
        and s.source_type = 'synthetic'
    )
  );

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — the same pattern 0003/0004/0005/0006 each use, so the suite
-- skips cleanly rather than erroring in the window where this file has
-- merged but the stack it runs against has not had it applied.
create or replace function demo_mode_schema_version()
returns int language sql immutable as $$ select 7 $$;
