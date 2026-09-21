-- BCION Lite — guest server sessions (AUTH-4)
-- Source of truth: docs/CONTRACTS.md "Settled — guest state": "A guest
-- *plan* uses a server-side guest session (opaque id, httponly cookie)
-- over `guest_sessions`/`guest_plans`, merged into the account at
-- sign-up by a one-way, idempotent definer function. No birth year is
-- stored for a guest."
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0008.
--
-- **Real number check (migration-owner rule):** the card names
-- "provisional 0004". `ls db/migrations/` at the moment this was written
-- shows 0001-0008, so the next genuinely free number is 0009.
--
-- ============================================================
-- The threat this schema is shaped around
-- ============================================================
-- A guest has no Supabase Auth user, so there is no `auth.uid()` to
-- scope anything by. The ONLY thing separating guest X's saved routes
-- from guest Y's is a bearer token in a cookie. That makes every one of
-- the following load-bearing, not stylistic:
--
--   * **RLS deny-all on both tables, with zero policies AND the table
--     grants revoked.** There is no "own row" expression to write here
--     — a guest is not a database principal — so the tables are simply
--     unreachable by `anon`/`authenticated` through PostgREST at all.
--     The same pattern 0001 uses for `reviewers` and 0004 for
--     `guardian_consents`.
--   * **Every path in is a SECURITY DEFINER function with a pinned
--     `search_path`.** A definer function is a deliberate RLS bypass;
--     the card's own risk line says so ("an input bug leaks one guest's
--     plans to another"). So each one below resolves the caller's
--     session from the token FIRST, and every subsequent statement is
--     scoped by that resolved `session_id` — never by an id the caller
--     passed in. `delete_guest_plan` is the sharp edge: a DELETE keyed
--     on the plan id alone would let guest X delete guest Y's row by
--     guessing a uuid. It is keyed on BOTH, and
--     tests/db/test_guest_session.py checks exactly that.
--   * **The token is stored only as a SHA-256 hash.** A dump of
--     `guest_sessions` must not hand somebody every live guest's
--     session. This mirrors `guardian_consents`' bearer-credential
--     reasoning (0004), one step stronger: that table stores its token
--     in the clear because the emailed link has to be matched; here
--     nothing ever needs the original back, so nothing keeps it.
--   * **The token is generated INSIDE the database and returned once.**
--     No caller supplies it, so there is no client-chosen token to
--     spoof — the same structural fix 0005 made for
--     `create_guardian_consent_request` ("there is no student_id
--     parameter for a caller to even attempt to spoof").
--
-- `sha256()` is a CORE Postgres function (pg_catalog, since PG 11), NOT
-- a pgcrypto one, so unlike `gen_random_bytes` it needs no schema
-- qualification and cannot hit the failure 0006 exists to fix.
-- `gen_random_bytes` IS pgcrypto and IS qualified as
-- `extensions.gen_random_bytes`, exactly as 0006 taught.

-- ============================================================
-- Tables
-- ============================================================

create table guest_sessions (
    id          uuid primary key default gen_random_uuid(),
    -- SHA-256 of the raw token, hex. Never the token itself. `unique`
    -- both enforces one session per token and gives the lookup index
    -- every RPC below depends on.
    token_hash  text not null unique,
    created_at  timestamptz not null default now(),
    -- Named assumption: 7 days (AUTH-4's own figure; no other is
    -- specified anywhere). A guest plan is a convenience for finishing a
    -- decision in one sitting or two, not durable storage — durable
    -- storage is what an account is for.
    expires_at  timestamptz not null default (now() + interval '7 days')
);

create index guest_sessions_expires_idx on guest_sessions (expires_at);

-- Deliberately narrow: session, pathway, one number. NO notes column and
-- no free-text column of any kind — AUTH-4 says so explicitly, and the
-- reason is worth keeping next to the schema: a guest is anonymous and
-- un-consented, so there must be nowhere for a child to type their name,
-- their school or their situation. `saved_plans` has `notes` because an
-- account holder has been through consent; this table never will.
create table guest_plans (
    id                             uuid primary key default gen_random_uuid(),
    session_id                     uuid not null
                                     references guest_sessions(id) on delete cascade,
    -- "only existing pathway ids accepted" (AUTH-4 acceptance), enforced
    -- by the foreign key rather than by a check in application code.
    pathway_id                     uuid not null
                                     references pathways(id) on delete cascade,
    estimated_additional_expenses  numeric,
    created_at                     timestamptz not null default now(),
    -- Saving the same route twice is an idempotent no-op, not a second
    -- row; `save_guest_plan` below relies on this index for its upsert.
    unique (session_id, pathway_id),
    -- Named assumption: a non-negative amount below 10 crore. Bounds a
    -- nonsense or hostile value at the database layer as well as the
    -- application one; the figure is a sanity ceiling, not a product
    -- rule.
    constraint guest_plans_expenses_range check (
      estimated_additional_expenses is null
      or (estimated_additional_expenses >= 0
          and estimated_additional_expenses <= 100000000)
    )
);

create index guest_plans_session_idx on guest_plans (session_id);

-- "max 10 plans per session" (AUTH-4 acceptance), enforced by a trigger
-- rather than only inside `save_guest_plan`. A cap that lives only in
-- the function it guards stops being true the moment a second write path
-- exists — the same "regardless of how it's reached" reasoning
-- 0004_guardian_consent.sql applies to its own partial unique index.
create or replace function enforce_guest_plan_limit()
returns trigger as $$
declare
  v_count int;
begin
  -- Re-saving a route the session ALREADY holds is not a new row, so it
  -- must not be counted against the cap.
  --
  -- This is not a hypothetical nicety. `save_guest_plan` below is an
  -- `insert ... on conflict (session_id, pathway_id) do update`, and
  -- Postgres fires BEFORE INSERT triggers for the proposed row BEFORE it
  -- detects the conflict — so without this check, a session holding
  -- exactly ten routes could never revise any of their estimates: the
  -- update branch would trip a cap it does not actually exceed. Caught
  -- by tests/db/test_guest_session.py's
  -- `test_the_cap_does_not_block_updating_an_existing_plan`, which is
  -- why that test exists.
  if exists (
    select 1 from guest_plans
    where session_id = new.session_id and pathway_id = new.pathway_id
  ) then
    return new;
  end if;

  select count(*) into v_count from guest_plans where session_id = new.session_id;
  if v_count >= 10 then
    raise exception
      'A guest session may hold at most 10 saved routes; sign up for an account to save more.';
  end if;
  return new;
end;
$$ language plpgsql security invoker set search_path = public;

-- INSERT only: an UPDATE cannot increase the row count, so firing on
-- update would cost a count(*) per edit and buy nothing.
create trigger guest_plans_enforce_limit
before insert on guest_plans
for each row execute function enforce_guest_plan_limit();

-- ============================================================
-- Row-level security — deny all, for everyone
-- ============================================================
alter table guest_sessions enable row level security;
alter table guest_plans    enable row level security;

-- NO policies on either table, for any role, ever. RLS enabled with zero
-- matching policies means "no access" (0001's `reviewers` pattern). A
-- guest is not a database principal, so there is no own-row expression
-- that could be written here even in principle — the definer functions
-- below are the whole API.
--
-- The grants are revoked as well, for the same belt-and-braces reason as
-- `app_settings` (0007): PostgREST consults table privileges before RLS,
-- so this turns a direct REST call into a flat permission-denied rather
-- than a silently empty result set.
revoke all on table guest_sessions from anon, authenticated;
revoke all on table guest_plans    from anon, authenticated;

-- ============================================================
-- The only ways in — SECURITY DEFINER, pinned search_path
-- ============================================================

-- Resolve a raw token to a LIVE session id, or NULL.
--
-- Every other function below goes through this one, so "expired rows are
-- filtered on read" is true in exactly one place instead of being
-- repeated (and eventually forgotten) in four. NULL for absent, expired
-- and malformed alike: a caller who does not hold a valid token learns
-- nothing from the difference.
create or replace function guest_session_id(p_token text)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select s.id
  from guest_sessions s
  where s.token_hash = encode(sha256(convert_to(coalesce(p_token, ''), 'UTF8')), 'hex')
    and s.expires_at > now();
$$;

-- Not granted to anon/authenticated. It is an internal helper for the
-- functions below, which are themselves definer and so can call it
-- regardless; exposing it would hand a caller a token-probing oracle for
-- no benefit.
revoke all on function guest_session_id(text) from public, anon, authenticated;

-- Start a session. Returns the RAW token, exactly once, to be put
-- straight into an httponly cookie by app/web/guest_session.py and never
-- stored anywhere else.
--
-- Takes NO parameters on purpose: there is nothing for a caller to
-- supply, therefore nothing to spoof (0005's own structural argument).
-- 32 random bytes = 256 bits, the entropy AUTH-4 asks for.
create or replace function create_guest_session()
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_token text;
begin
  -- Opportunistic purge (AUTH-4: "purged opportunistically on create").
  -- Deliberately here rather than in a scheduled job: this pilot has no
  -- scheduler, and session creation is the one moment that is already a
  -- write and is naturally proportional to traffic. `guest_plans`
  -- cascades from `guest_sessions`, so this is the whole cleanup.
  delete from guest_sessions where expires_at <= now();

  v_token := encode(extensions.gen_random_bytes(32), 'hex');

  insert into guest_sessions (token_hash)
  values (encode(sha256(convert_to(v_token, 'UTF8')), 'hex'));

  return v_token;
end;
$$;

grant execute on function create_guest_session() to anon, authenticated;

-- Save (or update) one route for the calling session.
--
-- Returns true on success, false when the token does not resolve to a
-- live session — never an exception for a stale cookie, which is an
-- ordinary, expected state after seven days, not an error.
--
-- `on conflict (session_id, pathway_id) do update` makes saving the same
-- route twice idempotent: one row, its estimate refreshed.
create or replace function save_guest_plan(
  p_token text,
  p_pathway_id uuid,
  p_estimated_additional_expenses numeric default null
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session_id uuid;
begin
  v_session_id := guest_session_id(p_token);
  if v_session_id is null then
    return false;
  end if;

  -- Scoped by the RESOLVED session id, never by anything the caller
  -- passed. The only caller-supplied values that reach a WHERE clause
  -- anywhere in this file are the token (matched by hash) and a pathway
  -- id (constrained by a foreign key).
  insert into guest_plans (session_id, pathway_id, estimated_additional_expenses)
  values (v_session_id, p_pathway_id, p_estimated_additional_expenses)
  on conflict (session_id, pathway_id) do update
    set estimated_additional_expenses = excluded.estimated_additional_expenses;

  return true;
end;
$$;

grant execute on function save_guest_plan(text, uuid, numeric) to anon, authenticated;

-- List the calling session's routes. An unknown or expired token returns
-- zero rows, never an error and never somebody else's rows.
create or replace function list_guest_plans(p_token text)
returns table (
    id                             uuid,
    pathway_id                     uuid,
    estimated_additional_expenses  numeric,
    created_at                     timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select p.id, p.pathway_id, p.estimated_additional_expenses, p.created_at
  from guest_plans p
  where p.session_id = guest_session_id(p_token)
  order by p.created_at;
$$;

grant execute on function list_guest_plans(text) to anon, authenticated;

-- Remove one route.
--
-- **The IDOR this is shaped to prevent:** keyed on the plan id AND the
-- session resolved from the token, both. A DELETE on `id = p_plan_id`
-- alone would let any guest delete any other guest's saved route by
-- guessing a uuid — and because this runs SECURITY DEFINER, RLS would
-- not be there to stop it. Returns false when nothing matched, so a
-- caller cannot tell "that plan does not exist" from "that plan is not
-- yours".
create or replace function delete_guest_plan(p_token text, p_plan_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_session_id uuid;
  v_deleted int;
begin
  v_session_id := guest_session_id(p_token);
  if v_session_id is null then
    return false;
  end if;

  delete from guest_plans
  where id = p_plan_id
    and session_id = v_session_id;

  get diagnostics v_deleted = row_count;
  return v_deleted > 0;
end;
$$;

grant execute on function delete_guest_plan(text, uuid) to anon, authenticated;

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as 0003-0008.
create or replace function guest_session_schema_version()
returns int language sql immutable as $$ select 9 $$;
