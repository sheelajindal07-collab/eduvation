-- BCION Lite — AI spend accounting: reservation, settlement, caps (AI-4)
-- Source of truth: tasks/BCI-010.md; docs/SECURITY.md "AI / LLM
-- controls" ("atomic per-request spend reservation; global + per-account
-- spend caps; graceful fallback to deterministic tools at the cap");
-- CLAUDE.md ("one hosted AI provider behind an adapter, spend-capped").
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0010.
--
-- **Real number check (migration-owner rule):** the card deliberately
-- fixes no number ("do not hardcode 0011, 0012 or 0013"). `ls
-- db/migrations/` on this branch at session open (2026-09-22) shows
-- 0001-0010, so the next genuinely free number is 0011 and that is what
-- this file uses. A peer lane (CONSENT-4) holds a migration of its own on
-- another branch; whichever merges second renames its file, which is a
-- pure rename because nothing here has been applied to any cloud project.
--
-- ============================================================
-- What this table is NOT allowed to contain
-- ============================================================
-- There is no prompt column and no answer column in `ai_usage`, and
-- there never may be one. This is a hard requirement, not a style
-- choice: CLAUDE.md's "No student data to development agents" is only
-- true if the accounting table an agent reads to debug spend cannot
-- contain a student's question or the model's reply about it. What is
-- recorded is: which template ran, how many provider calls it reserved
-- and made, whether it settled, and — as opaque ids — which retrieved
-- records grounded it. Nothing a person typed, nothing a model wrote.
--
-- The identity is stored as a SHA-256 hex digest of the account id or
-- the guest-session token, never the raw identifier — the same reasoning
-- 0009_guest_sessions.sql applies to `guest_sessions.token_hash`: a dump
-- of this table must not hand somebody a list of who asked what, when.
-- `ai_reserve` below REFUSES anything that is not a 64-character hex
-- digest, so "we forgot to hash it" fails loudly at the door instead of
-- being discovered later in a backup.
--
-- ============================================================
-- Why reservation is a two-call protocol
-- ============================================================
-- `ai_reserve` runs BEFORE the provider is called and writes a
-- `reserved` row inside one transaction that also checks every cap; the
-- caller only invokes the provider if that returns an id. `ai_settle`
-- runs after, recording what actually happened. A crash between the two
-- leaves a `reserved` row, which counts against the caps at its
-- RESERVED size — i.e. the failure mode is "we under-spend after a
-- crash", never "a runaway loop spends without a trace". That direction
-- is deliberate: this is a circuit breaker, and a circuit breaker that
-- fails open is not one.

-- ============================================================
-- The caps, as configuration rather than as code
-- ============================================================
-- One row, single-row-enforced the same way 0007_demo_mode.sql does it
-- (`id boolean primary key check (id)` — only `true` is a legal key, so
-- a second row is impossible rather than merely discouraged).
--
-- The numbers live here and not in the body of `ai_reserve` so that
-- changing a cap is an UPDATE by the owner, not a new migration and a
-- redeploy — and so that this file does not pretend to know figures it
-- has no authority over.
create table ai_usage_caps (
    id                       boolean primary key default true check (id),
    -- Provider calls one identity (one account, or one guest session)
    -- may reserve per UTC day.
    per_identity_daily_calls int not null check (per_identity_daily_calls > 0),
    -- Provider calls the whole installation may reserve per UTC day.
    global_daily_calls       int not null check (global_daily_calls > 0),
    -- ... and per UTC calendar month. The monthly figure is the one that
    -- corresponds to a rupee ceiling (`ai_monthly_spend_cap_inr` in
    -- app/core/config.py); this table counts CALLS, which is the
    -- mechanical thing a database can enforce.
    global_monthly_calls     int not null check (global_monthly_calls > 0),
    updated_at               timestamptz not null default now(),
    -- Cheap, real invariants: a per-identity cap above the global daily
    -- cap, or a daily cap above the monthly one, is a typo that would
    -- silently disable the tighter limit.
    constraint ai_usage_caps_daily_ge_identity
      check (global_daily_calls >= per_identity_daily_calls),
    constraint ai_usage_caps_monthly_ge_daily
      check (global_monthly_calls >= global_daily_calls)
);

-- PLACEHOLDER VALUES — these are test-sized numbers, not a decision.
-- tasks/BCI-010.md says so explicitly ("use small placeholder caps
-- suitable for testing; the lead sets real values later"). They are
-- small on purpose so tests/db/test_ai_usage.py can actually reach a cap
-- in a few calls instead of simulating hundreds. Whoever sets the real
-- figures does it with an UPDATE, not by editing this applied file.
insert into ai_usage_caps (
    id, per_identity_daily_calls, global_daily_calls, global_monthly_calls
) values (true, 5, 50, 500);

-- No API role may see or change the caps: this is the spend kill switch,
-- and a client that can read it learns exactly how many calls are left to
-- burn, while a client that can write it has no cap at all. Same
-- belt-and-braces shape as 0007's `app_settings` — RLS on with no policy
-- AND the grants revoked, so PostgREST answers with a flat
-- permission-denied rather than an empty result set.
alter table ai_usage_caps enable row level security;
revoke all on table ai_usage_caps from anon, authenticated;

-- ============================================================
-- The ledger
-- ============================================================
create table ai_usage (
    id                 uuid primary key default gen_random_uuid(),
    -- 'account' = a signed-in student; 'guest' = a guest session. The
    -- two share a table because the caps are shared; they never share an
    -- identity space, because the hash inputs are different kinds of
    -- thing (an account uuid vs a session token).
    identity_kind      text not null check (identity_kind in ('account', 'guest')),
    -- SHA-256 hex of the account id or guest-session token. NEVER the
    -- raw identifier (see the header). Enforced as a shape here and
    -- re-checked in `ai_reserve`.
    identity_hash      text not null check (identity_hash ~ '^[0-9a-f]{64}$'),
    -- Which prompt template ran — a machine key (app/ai/prompts.py),
    -- never the prompt text itself.
    template_id        text not null,
    calls_reserved     int not null check (calls_reserved > 0),
    calls_made         int not null default 0 check (calls_made >= 0),
    status             text not null check (status in ('reserved', 'settled', 'failed')),
    -- Opaque ids of the retrieved records that grounded the answer, kept
    -- so a published answer can be traced back to what it was built
    -- from. Ids only: no titles, no values, no text. Deliberately NOT
    -- foreign keys — a claim or source may legitimately be superseded or
    -- deleted later, and a spend record must not stop being a record of
    -- what was spent when that happens.
    selection_ids      uuid[],
    verification_ids   uuid[],
    created_at         timestamptz not null default now(),
    -- A settled or failed row must carry a settlement; a reserved row
    -- must not have been "used up" yet beyond what it reserved.
    constraint ai_usage_calls_made_within_reservation
      check (calls_made <= calls_reserved)
);

-- The two indexes every cap query below uses, and nothing else.
create index ai_usage_identity_day_idx on ai_usage (identity_kind, identity_hash, created_at);
create index ai_usage_created_at_idx   on ai_usage (created_at);

-- ============================================================
-- Deriving the identity hash — one definition, used by SQL and Python
-- ============================================================
-- Both the RLS policy below and app/ai/budget_db.py must agree on what
-- "this account's rows" means, byte for byte. Writing the digest
-- expression twice is how those two silently drift apart, so it is
-- written once, here.
--
-- Not SECURITY DEFINER: it touches no table and needs no privilege. It
-- is a pure function of its argument, and sha256() is a core
-- (pg_catalog) function since PG 11 — not a pgcrypto one — so it cannot
-- hit the schema-qualification failure 0006 exists to fix.
create or replace function ai_identity_hash(p_identity text)
returns text
language sql
immutable
set search_path = public
as $$
  select encode(sha256(convert_to(coalesce(p_identity, ''), 'UTF8')), 'hex');
$$;

grant execute on function ai_identity_hash(text) to anon, authenticated;

-- ============================================================
-- Row-level security
-- ============================================================
alter table ai_usage enable row level security;

-- SELECT is granted; INSERT/UPDATE/DELETE are not, for either API role.
-- The only legitimate writers are the two definer functions below, and
-- "only they may write" is enforced at the PRIVILEGE layer rather than
-- by an RLS policy that happens to match nothing: a missing grant is a
-- flat permission-denied that no future permissive policy can
-- accidentally widen.
revoke all on table ai_usage from anon, authenticated;
grant select on table ai_usage to anon, authenticated;

-- A signed-in account sees its own rows and nothing else.
--
-- The identity is derived from the caller's own JWT (`auth.uid()`) and
-- hashed HERE. A client never supplies `identity_hash` to a select —
-- if it did, the hash would be a bearer credential, and knowing another
-- student's account id (which is not a secret; it appears in ordinary
-- application data) would be enough to read their AI history.
--
-- Guests are denied by construction and not by omission: a guest has no
-- `auth.uid()`, so this policy is false for them, and there is no second
-- policy. A guest identity is a session token that the database only
-- ever sees hashed, so there is nothing a guest could be matched against
-- even in principle — the same "a guest is not a database principal"
-- conclusion 0009_guest_sessions.sql reached.
--
-- A reviewer is NOT given an override here. docs/SECURITY.md: the
-- reviewer role governs the knowledge base, never the student vault.
-- What a reviewer gets instead is the identity-free aggregate view at
-- the bottom of this file.
create policy ai_usage_select_own on ai_usage for select
  using (
    identity_kind = 'account'
    and auth.uid() is not null
    and identity_hash = ai_identity_hash(auth.uid()::text)
  );

-- ============================================================
-- ai_reserve — the atomic half that runs BEFORE the provider
-- ============================================================
-- SECURITY DEFINER, `search_path` pinned to `public` (never the
-- caller's, never the database default — an unpinned definer function is
-- a privilege-escalation primitive, since the caller chooses which
-- schema's `ai_usage` it writes to).
--
-- What it can do that an ordinary RLS-scoped caller cannot, and why:
--   * INSERT into `ai_usage`, which no API role holds a grant on. That
--     is the entire point: a reservation must be unforgeable and must be
--     written by the same transaction that checked the caps.
--   * READ `ai_usage_caps` and aggregate across EVERY identity's rows.
--     A global cap cannot be checked from inside one caller's own slice
--     of the table, and widening the policy so it could would hand every
--     student a view of everyone else's usage.
-- It returns exactly one uuid and never any row content, so it is not a
-- read channel for anything the caller could not already see.
--
-- CONCURRENCY. Two simultaneous callers must not both slip through a cap
-- by one. `select ... for update` on the single caps row is the
-- serialisation point: the second transaction blocks on that lock until
-- the first has inserted and committed, so the counts it then reads
-- already include the first one's reservation. This is cheap precisely
-- because there is only ever one row to lock, and it is the row every
-- reservation must read anyway.
--
-- The `-- BEGIN/END ai_reserve` sentinels are load-bearing for the
-- revert-to-prove drill (`.claude/agents/migration-owner.md`): they let
-- the weakened-then-restored version of this one function be re-applied
-- from this file verbatim, without re-running the whole migration.
-- BEGIN ai_reserve
create or replace function ai_reserve(
  p_identity_kind text,
  p_identity_hash text,
  p_template_id   text,
  p_calls         int
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_caps           ai_usage_caps%rowtype;
  v_day_start      timestamptz := date_trunc('day', now() at time zone 'UTC') at time zone 'UTC';
  v_month_start    timestamptz := date_trunc('month', now() at time zone 'UTC') at time zone 'UTC';
  v_identity_today int;
  v_global_today   int;
  v_global_month   int;
  v_usage_id       uuid;
begin
  -- Argument validation first, and as its own SQLSTATE ('BCAI3'): a
  -- malformed call is a programming error, and must never be reported to
  -- a caller as "budget exceeded" — that would turn a bug into a silent,
  -- permanent AI outage that looks like an ordinary cap.
  if p_identity_kind is null or p_identity_kind not in ('account', 'guest') then
    raise exception 'ai_reserve: identity_kind must be ''account'' or ''guest'', not %',
      coalesce(p_identity_kind, '<null>') using errcode = 'BCAI3';
  end if;

  if p_identity_hash is null or p_identity_hash !~ '^[0-9a-f]{64}$' then
    raise exception
      'ai_reserve: identity_hash must be a SHA-256 hex digest (ai_identity_hash()), never a raw account id or session token'
      using errcode = 'BCAI3';
  end if;

  if p_template_id is null or length(btrim(p_template_id)) = 0 then
    raise exception 'ai_reserve: template_id is required' using errcode = 'BCAI3';
  end if;

  if p_calls is null or p_calls < 1 then
    raise exception 'ai_reserve: calls must be at least 1, not %',
      coalesce(p_calls::text, '<null>') using errcode = 'BCAI3';
  end if;

  select * into v_caps from ai_usage_caps where id for update;
  if not found then
    raise exception
      'ai_usage_caps holds no configuration row, so no cap can be checked; refusing to reserve'
      using errcode = 'BCAI3';
  end if;

  -- What a row "costs" against a cap: a reservation costs what it
  -- reserved until it settles, then what it actually made. Counting a
  -- reserved row at zero would let a burst of concurrent reservations
  -- pass the cap together and only be noticed afterwards, which is the
  -- exact hole the two-call protocol exists to close.
  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_identity_today
    from ai_usage u
   where u.identity_kind = p_identity_kind
     and u.identity_hash = p_identity_hash
     and u.created_at >= v_day_start;

  if v_identity_today + p_calls > v_caps.per_identity_daily_calls then
    raise exception
      'AI budget exceeded: this identity has used % of % calls today and asked for % more',
      v_identity_today, v_caps.per_identity_daily_calls, p_calls
      using errcode = 'BCAI1', hint = 'per_identity_daily_calls';
  end if;

  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_global_today
    from ai_usage u
   where u.created_at >= v_day_start;

  if v_global_today + p_calls > v_caps.global_daily_calls then
    raise exception
      'AI budget exceeded: % of % calls used across all identities today, and % more were asked for',
      v_global_today, v_caps.global_daily_calls, p_calls
      using errcode = 'BCAI1', hint = 'global_daily_calls';
  end if;

  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_global_month
    from ai_usage u
   where u.created_at >= v_month_start;

  if v_global_month + p_calls > v_caps.global_monthly_calls then
    raise exception
      'AI budget exceeded: % of % calls used across all identities this month, and % more were asked for',
      v_global_month, v_caps.global_monthly_calls, p_calls
      using errcode = 'BCAI1', hint = 'global_monthly_calls';
  end if;

  insert into ai_usage (identity_kind, identity_hash, template_id, calls_reserved, status)
  values (p_identity_kind, p_identity_hash, p_template_id, p_calls, 'reserved')
  returning id into v_usage_id;

  return v_usage_id;
end;
$$;
-- END ai_reserve

grant execute on function ai_reserve(text, text, text, int) to anon, authenticated;

-- ============================================================
-- ai_settle — the half that runs AFTER the provider
-- ============================================================
-- SECURITY DEFINER with the same pinned `search_path`, for the same
-- reason: no API role may UPDATE `ai_usage` directly, so settlement has
-- to happen through a function that can. It can write exactly one row,
-- identified by an id the caller must already hold, and only while that
-- row is still `reserved`.
--
-- Two guards are load-bearing rather than defensive-by-habit:
--   * only a `reserved` row may be settled — a second settlement could
--     otherwise rewrite history, or (worse) reduce a recorded spend;
--   * `calls_made` may never exceed `calls_reserved` — "reserve one,
--     report five" would make the reservation protocol decorative.
-- Both raise rather than clamp: quietly recording a smaller number than
-- actually happened is the failure this whole table exists to prevent.
--
-- KNOWN RESIDUAL RISK, flagged for the lead rather than solved here:
-- anyone who can call this and can GUESS a reservation's uuid could
-- settle it as `failed, 0 calls` and free that headroom. It is a 122-bit
-- guess, the window is only until the legitimate settlement lands, and
-- closing it properly means a settlement secret returned by `ai_reserve`
-- — a design decision beyond this card.
-- BEGIN ai_settle
create or replace function ai_settle(
  p_usage_id         uuid,
  p_calls_made       int,
  p_status           text,
  p_selection_ids    uuid[],
  p_verification_ids uuid[]
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_reserved int;
  v_updated  int;
begin
  if p_status is null or p_status not in ('settled', 'failed') then
    raise exception 'ai_settle: status must be ''settled'' or ''failed'', not %',
      coalesce(p_status, '<null>') using errcode = 'BCAI3';
  end if;

  if p_calls_made is null or p_calls_made < 0 then
    raise exception 'ai_settle: calls_made must be zero or more, not %',
      coalesce(p_calls_made::text, '<null>') using errcode = 'BCAI3';
  end if;

  select u.calls_reserved into v_reserved
    from ai_usage u
   where u.id = p_usage_id
     and u.status = 'reserved'
   for update;

  -- No such reservation, or it has already been settled. False rather
  -- than an exception: an unknown id and an already-settled id are
  -- deliberately indistinguishable to the caller (0009's
  -- `delete_guest_plan` reasoning), and a retry after a successful
  -- settlement is an ordinary event, not an error.
  if not found then
    return false;
  end if;

  if p_calls_made > v_reserved then
    raise exception
      'ai_settle: % calls reported against a reservation of % — settle within the reservation, or reserve again',
      p_calls_made, v_reserved using errcode = 'BCAI2';
  end if;

  update ai_usage
     set calls_made       = p_calls_made,
         status           = p_status,
         selection_ids    = p_selection_ids,
         verification_ids = p_verification_ids
   where id = p_usage_id
     and status = 'reserved';

  get diagnostics v_updated = row_count;
  return v_updated > 0;
end;
$$;
-- END ai_settle

grant execute on function ai_settle(uuid, int, text, uuid[], uuid[]) to anon, authenticated;

-- ============================================================
-- ai_budget_remaining — "how many calls are still allowed?"
-- ============================================================
-- DEVIATION FROM THE CARD, stated plainly: tasks/BCI-010.md names two
-- definer functions, and this is a third. It exists because the same
-- card requires `app/ai/budget_db.py` to have "the exact same call
-- shape" as `app/ai/budget.py`'s `AIRequestBudget`, which has
-- `remaining()` as well as `reserve()` — and `remaining()` cannot be
-- answered from inside one caller's RLS slice, because two of the three
-- caps are global. The alternatives were to widen the SELECT policy so
-- every caller could count everyone else's rows (much worse), or to ship
-- a `remaining()` that lies. The lead should confirm this third function
-- at merge.
--
-- It is read-only, `stable`, returns a single integer, and leaks exactly
-- one thing: how much headroom is left — which is the same fact the
-- planned "AI unavailable today" banner shows every visitor anyway.
-- BEGIN ai_budget_remaining
create or replace function ai_budget_remaining(
  p_identity_kind text,
  p_identity_hash text
)
returns int
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_caps           ai_usage_caps%rowtype;
  v_day_start      timestamptz := date_trunc('day', now() at time zone 'UTC') at time zone 'UTC';
  v_month_start    timestamptz := date_trunc('month', now() at time zone 'UTC') at time zone 'UTC';
  v_identity_today int;
  v_global_today   int;
  v_global_month   int;
begin
  if p_identity_kind is null or p_identity_kind not in ('account', 'guest') then
    raise exception 'ai_budget_remaining: identity_kind must be ''account'' or ''guest'', not %',
      coalesce(p_identity_kind, '<null>') using errcode = 'BCAI3';
  end if;

  if p_identity_hash is null or p_identity_hash !~ '^[0-9a-f]{64}$' then
    raise exception
      'ai_budget_remaining: identity_hash must be a SHA-256 hex digest (ai_identity_hash()), never a raw account id or session token'
      using errcode = 'BCAI3';
  end if;

  select * into v_caps from ai_usage_caps where id;
  if not found then
    -- Fail closed. No configuration means no permission to spend, not
    -- unlimited permission to spend.
    return 0;
  end if;

  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_identity_today
    from ai_usage u
   where u.identity_kind = p_identity_kind
     and u.identity_hash = p_identity_hash
     and u.created_at >= v_day_start;

  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_global_today
    from ai_usage u
   where u.created_at >= v_day_start;

  select coalesce(sum(case when u.status = 'reserved' then u.calls_reserved else u.calls_made end), 0)
    into v_global_month
    from ai_usage u
   where u.created_at >= v_month_start;

  return greatest(0, least(
    v_caps.per_identity_daily_calls - v_identity_today,
    v_caps.global_daily_calls       - v_global_today,
    v_caps.global_monthly_calls     - v_global_month
  ));
end;
$$;
-- END ai_budget_remaining

grant execute on function ai_budget_remaining(text, text) to anon, authenticated;

-- ============================================================
-- ai_usage_daily_totals — what a reviewer may see
-- ============================================================
-- Counts and totals per day, per template, per status. NO identity
-- column of any kind: not the hash, not the row ids, nothing that can be
-- joined back to a person. `identity_kind` is kept because "guests vs
-- accounts" is a genuinely useful operational split and is a category of
-- two values, not an identifier.
--
-- `security_invoker = false` is stated explicitly rather than left to
-- the default, because it is the load-bearing choice here: the view must
-- read `ai_usage` past that table's own RLS (a reviewer owns none of
-- those rows), which makes this view a deliberate RLS bypass in the same
-- family as a SECURITY DEFINER function. Its gate is therefore inside
-- the view: `where is_reviewer()` (0001's definer function). A
-- non-reviewer who somehow reaches the view gets zero rows, not
-- everyone's totals. A view needs no `search_path` pinning to be safe —
-- its query tree is resolved to OIDs at creation time, so a caller's
-- search_path cannot redirect `ai_usage` or `is_reviewer` at query time.
--
-- Deliberately NOT added to tests/db/access_matrix.py's MATRIX: that
-- file's guard reads `pg_tables`, which excludes views, and under
-- BCION_REQUIRE_LIVE=1 a matrix row naming a non-table is a hard
-- failure. The four cross-user expectations for this view are explicit
-- assertions in tests/db/test_ai_usage.py instead.
create view ai_usage_daily_totals
with (security_invoker = false) as
select
    (u.created_at at time zone 'UTC')::date as usage_day,
    u.identity_kind,
    u.template_id,
    u.status,
    count(*)::bigint             as reservations,
    sum(u.calls_reserved)::bigint as calls_reserved,
    sum(u.calls_made)::bigint     as calls_made
from ai_usage u
where is_reviewer()
group by 1, 2, 3, 4;

revoke all on ai_usage_daily_totals from anon, authenticated;
-- `authenticated` only: a guest is not a reviewer and never can be, so
-- there is no reason for the anon role to hold a grant at all. The
-- is_reviewer() gate inside the view is what separates a reviewer from
-- an ordinary signed-in student.
grant select on ai_usage_daily_totals to authenticated;

-- A marker so a test file can detect "is this migration applied yet" —
-- same pattern as 0003-0010. `ai_usage` itself is selectable by
-- `authenticated`, but only for rows they own, so a "select from it"
-- existence check would be ambiguous.
create or replace function ai_usage_schema_version()
returns int language sql immutable as $$ select 11 $$;
