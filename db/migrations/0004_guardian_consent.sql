-- BCION Lite — guardian consent gate for under-18 sign-up
-- Source of truth: CLAUDE.md non-negotiable ("Real minor accounts stay
-- disabled until the consent and safeguarding workflow is reviewed by a
-- person"), docs/SECURITY.md "Consent & safeguarding (a launch gate, not
-- a checkbox)", and the owner's decision recorded in STATUS.md / this
-- session: an age gate at sign-up, and for anyone under 18, a guardian
-- email that must confirm via a separate emailed link before the
-- account activates. See app/api/guardian_consent.py and
-- app/api/auth.py for how this schema is actually used, and
-- app/notifications/ for the (currently logging-only) email sender.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via the SQL Editor or scripts/apply_migrations.py (see
-- db/migrations/README.md) — same as 0001/0002/0003.
--
-- **Named assumption (no threshold is stated anywhere in the docs):**
-- 18 — India's legal majority age (Indian Majority Act, 1875) — is used
-- as the minor/adult cutoff. See app/api/guardian_consent.py's
-- MINOR_AGE_THRESHOLD_YEARS, the one place this number is defined for
-- the application layer; flag to the owner if a different threshold is
-- ever wanted.
--
-- **Design note — why TWO new tables, not columns bolted onto
-- student_profiles (the task's own suggested default):** `student_profiles`
-- is populated later, during onboarding (`current_class` is `not null`
-- there, and nothing in this app creates a `student_profiles` row at
-- sign-up — see app/api/auth.py). `date_of_birth`/account status, by
-- contrast, are known and must be acted on at the exact moment of
-- sign-up. Bolting them onto `student_profiles` would force either (a)
-- making `current_class` nullable (a real schema regression for the
-- onboarding flow) or (b) inserting a half-filled "profile" row that
-- doesn't yet hold the data a profile is supposed to hold — both worse
-- than one small, single-purpose table (`student_accounts`) that owns
-- exactly the account-level state established at sign-up.
--
-- **Design note — `is_minor` deliberately has NO column at all**
-- (contra the task's literal "is_minor (computed or stored, your
-- call)" framing): a stored flag that ought to change the day a real
-- person turns 18 would either go silently stale (nobody flips it) or
-- need a nightly job to keep true — machinery this pilot does not need.
-- The gate that actually matters is `account_status`, set once at
-- sign-up/first sign-in and flipped once at guardian confirmation;
-- "is this person currently under 18" is a one-line computation from
-- `date_of_birth` wherever it's actually needed (ordinary code for
-- arithmetic — CLAUDE.md's own rule). `date_of_birth` itself is kept so
-- that computation is always possible later.
--
-- **Design note — why the token is guarded so much harder than a normal
-- own-row table (`saved_plans`/`student_profiles`'s pattern):** the
-- token in `guardian_consents` is a bearer credential — whoever holds it
-- can activate the account it belongs to. A normal "own row" RLS policy
-- (`using (auth.uid() = student_id)`) would let the STUDENT themselves
-- read their own row, including the token, and self-confirm their own
-- pending account with no guardian involved at all — defeating the
-- entire point of this feature. So `guardian_consents` gets NO select
-- policy at all (RLS enabled, zero policies = no access by default,
-- same pattern 0001_init.sql already uses for `reviewers`); a student's
-- own status is exposed only through `my_guardian_consent_status()`
-- below, a function that deliberately never selects the `token` column,
-- so there is no code path — not even a bug in some future RLS policy
-- change — that can leak it through the normal API. The only thing that
-- may ever read or act on a raw token is `confirm_guardian_consent()`,
-- also below, which is the confirmation endpoint's own server-side
-- lookup the task asked for, expressed as a Postgres function so it
-- works the same way whether called from app/web/consent_pages.py or
-- (defensively) directly.
--
-- **Design note — `account_active()`, applied to `saved_plans`/
-- `student_profiles` too (adversarial review, 2026-09-21):** everything
-- above enforces the gate on THIS migration's own two tables, but until
-- now nothing stopped a pending account's own, otherwise-valid access
-- token from reading/writing `saved_plans`/`student_profiles` directly —
-- those tables' own-row RLS policies (0001_init.sql/0002_saved_plans.sql)
-- only ever checked `auth.uid() = id`/`student_id`, with zero reference
-- to `account_status`. The ONLY thing standing between a pending minor
-- and their own data was `app.api.auth.authenticate()` never handing out
-- a `Session` in the first place — real today (every token this app's
-- own routes ever issue goes through it), but not a database-enforced
-- guarantee: any future auth path that mints or accepts a session
-- without funnelling through `authenticate()` (password reset, magic
-- link, OAuth, a future browser client talking to Supabase directly)
-- would silently bypass this entire gate for the tables that actually
-- hold a student's data, with nothing at the database layer to catch it
-- — exactly the "a caller holding a valid access token could bypass
-- application code entirely by calling Supabase's REST API directly"
-- risk `enforce_account_status_matches_age` already names below, just
-- never closed for these two tables. `account_active(uid)` (defined
-- alongside the RLS section at the bottom of this file, once
-- `student_accounts` already exists) mirrors `is_reviewer()`'s own
-- pattern (0001_init.sql) exactly, and is ANDed into both
-- `student_profiles_own_row` and `saved_plans_own_row`.

create type account_status as enum ('active', 'pending_guardian_consent');
create type guardian_consent_status as enum ('pending', 'confirmed', 'expired');

-- ============================================================
-- student_accounts — account-level state established at sign-up
-- ============================================================

create table student_accounts (
    id              uuid primary key references auth.users(id) on delete cascade,
    date_of_birth   date not null,
    account_status  account_status not null default 'active',
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Reuses touch_updated_at(), defined in 0002_saved_plans.sql (already
-- applied by the time this migration runs — see db/migrations/README.md
-- "append-only, apply in order").
create trigger student_accounts_touch_updated_at
before update on student_accounts
for each row execute function touch_updated_at();

-- Server-side enforcement that an under-18 account can never be inserted
-- as 'active' — the exact "enforced server-side, not by a button /
-- application code discipline" property docs/SECURITY.md asks for,
-- mirroring 0003_maker_checker.sql's enforce_claims_workflow() trigger.
-- Without this, a caller holding a valid access token for their own
-- under-18 account could bypass app/api/guardian_consent.py entirely by
-- calling Supabase's REST API directly (own-row RLS would otherwise
-- permit the insert) and simply declare themselves 'active'. A plain
-- CHECK constraint cannot express this (it would need current_date,
-- which is not IMMUTABLE and so is not allowed in a CHECK expression) —
-- a BEFORE INSERT trigger can.
create or replace function enforce_account_status_matches_age()
returns trigger as $$
declare
  v_age int;
begin
  v_age := extract(year from age(current_date, new.date_of_birth))::int;
  if v_age < 18 and new.account_status <> 'pending_guardian_consent' then
    raise exception
      'An under-18 account must be created as pending_guardian_consent, not % (named age threshold: app/api/guardian_consent.py MINOR_AGE_THRESHOLD_YEARS).',
      new.account_status;
  end if;
  return new;
end;
$$ language plpgsql;

create trigger student_accounts_enforce_status
before insert on student_accounts
for each row execute function enforce_account_status_matches_age();

-- ============================================================
-- guardian_consents — one row per guardian-confirmation request
-- ============================================================

create table guardian_consents (
    id              uuid primary key default gen_random_uuid(),
    student_id      uuid not null references auth.users(id) on delete cascade,
    guardian_email  text not null,
    -- Opaque, single-use, server-generated — NEVER the student's own
    -- access token. A BEFORE INSERT trigger below
    -- (enforce_guardian_consent_server_token) unconditionally overwrites
    -- this column on every insert, so it is NEVER, in fact, accepted
    -- from a client as input — whatever value (or none at all) a caller
    -- sends is silently replaced before the row is ever written. No
    -- DEFAULT is declared here on purpose: the trigger is the only thing
    -- that ever sets this column, so a default would be redundant at
    -- best and a false sense of safety at worst if the trigger were ever
    -- dropped without anyone noticing this comment.
    token           text not null unique,
    status          guardian_consent_status not null default 'pending',
    created_at      timestamptz not null default now(),
    confirmed_at    timestamptz,
    -- Named assumption: 72 hours (the task's own suggested window; no
    -- other figure is specified anywhere in the docs). Mirrored in
    -- app/api/guardian_consent.py's GUARDIAN_CONSENT_EXPIRY_HOURS, which
    -- is what the guardian-facing email text actually quotes. Also
    -- server-set by the same BEFORE INSERT trigger as `token` (not just
    -- a DEFAULT) so the database's own enforcement doesn't depend on the
    -- application always remembering to pass it, or on a client not
    -- passing a longer-lived value of its own.
    expires_at      timestamptz not null default (now() + interval '72 hours')
);

create index guardian_consents_student_idx on guardian_consents (student_id);
create index guardian_consents_token_idx on guardian_consents (token);

-- Security finding (adversarial review, 2026-09-21): the INSERT RLS
-- policy below constrains only `student_id` (`with check (auth.uid() =
-- student_id)`) — nothing stopped a caller from INSERTing a row for
-- their OWN student_id with a SELF-CHOSEN `token` and `guardian_email`,
-- then calling the anon-grantable confirm_guardian_consent(p_token) RPC
-- with that same self-chosen token, flipping their own account to
-- 'active' with zero real guardian involvement. This closes it the same
-- way enforce_account_status_matches_age() (above) closes the analogous
-- gap on student_accounts: a BEFORE INSERT trigger that server-generates
-- the bearer credential unconditionally, ignoring/overwriting whatever
-- the client sent. `pgcrypto` (enabled in 0001_init.sql) supplies
-- gen_random_bytes(); hex-encoded so the value is already URL-safe with
-- no percent-encoding surprises in the emailed confirm link
-- (app/notifications/guardian_consent_email.py). 32 random bytes (256
-- bits) matches the entropy app/api/guardian_consent.py used to generate
-- client-side before this fix (secrets.token_urlsafe(32)) — that
-- application-side generation is now dead code and has been removed;
-- app/api/guardian_consent.py's create_guardian_consent_request instead
-- reads the token back from this INSERT's own returned row, the same
-- way it already reads back a plan's generated id elsewhere in this
-- codebase (app/api/auth.py's _migrate_pending_plan).
create or replace function enforce_guardian_consent_server_token()
returns trigger as $$
begin
  new.token := encode(gen_random_bytes(32), 'hex');
  new.expires_at := now() + interval '72 hours';
  return new;
end;
$$ language plpgsql;

create trigger guardian_consents_enforce_server_token
before insert on guardian_consents
for each row execute function enforce_guardian_consent_server_token();

-- Security finding (adversarial review, 2026-09-21), MEDIUM: idempotency
-- against a duplicate guardian_consents insert was previously enforced
-- only in Python (create_guardian_consent_request catches a unique-
-- violation on the *student_accounts* insert, then returns before ever
-- reaching this table) — a direct API caller with a valid own-row access
-- token could bypass that entirely and INSERT unlimited guardian_consents
-- rows with arbitrary guardian_email values (a spam vector once a real
-- email provider is configured, app/notifications/logging_sender.py).
-- A partial unique index enforces "at most one *pending* request per
-- student" at the database layer regardless of caller, the same
-- "regardless of how it's reached" reasoning as the trigger above. Scoped
-- to status = 'pending' (not the whole student_id column) so a student
-- can still get a NEW pending request after an old one is confirmed or
-- expires — those terminal states are not "still outstanding".
create unique index guardian_consents_one_pending_per_student
  on guardian_consents (student_id)
  where status = 'pending';

-- A row must always be INSERTed exactly as 'pending', never-yet-confirmed
-- — mirrors 0003_maker_checker.sql's "must be inserted as draft" rule.
-- Without this, the own-row INSERT policy below (needed so a signed-in
-- student's own request can create their OWN pending-consent row) would
-- also let that same request insert status='confirmed' directly,
-- self-activating the account with no guardian involved at all.
create or replace function enforce_guardian_consent_insert_pending()
returns trigger as $$
begin
  if new.status <> 'pending' or new.confirmed_at is not null then
    raise exception
      'A guardian_consents row must be inserted as pending, unconfirmed — use confirm_guardian_consent() to advance it.';
  end if;
  return new;
end;
$$ language plpgsql;

create trigger guardian_consents_enforce_insert_pending
before insert on guardian_consents
for each row execute function enforce_guardian_consent_insert_pending();

-- ============================================================
-- Server-side-only functions (security definer — see the module-level
-- design note above for why these bypass RLS deliberately and narrowly,
-- mirroring 0001_init.sql's own is_reviewer() pattern)
-- ============================================================

-- "a student can read their own consent status" (task requirement),
-- WITHOUT ever exposing the token column through any path — the
-- function body itself never selects it, so there is nothing to
-- accidentally leak even if this function's grants were loosened later.
create or replace function my_guardian_consent_status()
returns table (
    status         guardian_consent_status,
    guardian_email text,
    created_at     timestamptz,
    expires_at     timestamptz,
    confirmed_at   timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select status, guardian_email, created_at, expires_at, confirmed_at
  from guardian_consents
  where student_id = auth.uid()
  order by created_at desc
  limit 1;
$$;

grant execute on function my_guardian_consent_status() to authenticated;

-- The confirmation endpoint's own server-side lookup (task requirement
-- #5), expressed as a database function rather than inline application
-- SQL so the "match the token, then flip both rows atomically" logic
-- cannot be bypassed by any client that can reach Postgres at all — not
-- just clients that go through app/web/consent_pages.py. Deliberately
-- anonymous-callable (grant to anon below): the guardian who clicks the
-- emailed link has no Supabase session whatsoever — the single-use,
-- unpredictable, expiring TOKEN is the only credential this action has,
-- the same trust model as any "magic link" flow. A caller who does not
-- already possess a valid, unexpired, still-pending token learns nothing
-- and changes nothing by calling this (always returns false, never
-- distinguishes wrong/expired/already-used — task requirement #5).
create or replace function confirm_guardian_consent(p_token text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_student_id uuid;
begin
  -- Bookkeeping only (does not change what this call returns): record a
  -- pending-but-aged-out row as 'expired' so its terminal state is
  -- visible to my_guardian_consent_status() instead of sitting in
  -- 'pending' forever looking unconfirmed-but-still-actionable.
  update guardian_consents
  set status = 'expired'
  where token = p_token and status = 'pending' and expires_at <= now();

  update guardian_consents
  set status = 'confirmed', confirmed_at = now()
  where token = p_token and status = 'pending' and expires_at > now()
  returning student_id into v_student_id;

  if v_student_id is null then
    return false;
  end if;

  update student_accounts
  set account_status = 'active'
  where id = v_student_id;

  return true;
end;
$$;

grant execute on function confirm_guardian_consent(text) to anon, authenticated;

-- ============================================================
-- Row-level security
-- ============================================================

alter table student_accounts   enable row level security;
alter table guardian_consents  enable row level security;

-- student_accounts: a student may read and create their own row (the
-- own-row INSERT is what lets app/api/guardian_consent.py's
-- create_guardian_consent_request(), running as the signed-in student,
-- write the FIRST row for that student). Deliberately NO update/delete
-- policy for authenticated/anon at all — once created, account_status
-- may only change via confirm_guardian_consent() above. Without this
-- omission, a student's own signed-in session could simply
-- `.update({"account_status": "active"})` their own row directly,
-- self-activating a pending account with no guardian confirmation at
-- all — the exact bypass this whole feature exists to prevent, and the
-- same reasoning 0003_maker_checker.sql already applied to `claims`
-- (a maker's own session must not also be able to approve their own
-- claim).
create policy student_accounts_select_own on student_accounts for select
  using (auth.uid() = id);

create policy student_accounts_insert_own on student_accounts for insert
  with check (auth.uid() = id);

-- guardian_consents: own-row INSERT only (creates the pending request;
-- the trigger above forces status='pending' regardless of what's sent).
-- NO select/update/delete policy at all, for anyone, ever — see the
-- module-level design note above for why even the owning student must
-- not be able to read this table directly (the token). RLS enabled with
-- zero matching policies means "no access", the same pattern
-- 0001_init.sql already uses for `reviewers`.
create policy guardian_consents_insert_own on guardian_consents for insert
  with check (auth.uid() = student_id);

-- ============================================================
-- account_active() — defense in depth on the OTHER own-row tables
-- (adversarial review, 2026-09-21; see the module-level design note
-- above for the full reasoning)
-- ============================================================

-- Mirrors is_reviewer()'s exact pattern (0001_init.sql): security
-- definer, `language sql stable`, no explicit grant (relies on the same
-- default PUBLIC execute privilege is_reviewer() itself relies on — this
-- migration has no evidence that's ever been revoked, since is_reviewer()
-- already works for the anon-readable sources/careers/pathways/claims
-- policies with no grant statement of its own).
--
-- Default-open (returns true) when the given uid has NO student_accounts
-- row at all: not every student has one — only an account created as a
-- self-declared minor ever gets one (create_guardian_consent_request, or
-- the no-guardian-email fail-closed branch in
-- app/api/guardian_consent.py's enforce_guardian_consent_gate). An 18+
-- student, a reviewer, or any legacy account predating this feature must
-- not be gated by a table that was never populated for them — confirmed
-- by reading exactly how/when a student_accounts row gets created
-- (app/api/guardian_consent.py, both call sites) before writing this.
create or replace function account_active(uid uuid)
returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(
    (select account_status = 'active' from student_accounts where id = uid),
    true
  );
$$;

-- Re-scope the two pre-existing own-row policies this gate must also
-- cover. DROP + CREATE, not ALTER POLICY (which cannot add a brand-new
-- WITH CHECK clause to a FOR ALL policy that already has one, only
-- replace an existing USING/WITH CHECK wholesale one at a time) — same
-- own-row shape each already had, with `account_active(auth.uid())`
-- ANDed into both the USING and WITH CHECK clauses so a pending
-- account's own-row access is denied at the database layer regardless of
-- how its token was obtained — true defense-in-depth, not just the one
-- funnel through app.api.auth.authenticate(). student_profiles_own_row
-- originates in 0001_init.sql, saved_plans_own_row in
-- 0002_saved_plans.sql — both already applied to any project this
-- migration runs against (append-only, in order), so both policies are
-- guaranteed to already exist by the time these statements run.
drop policy student_profiles_own_row on student_profiles;
create policy student_profiles_own_row on student_profiles for all
  using (auth.uid() = id and account_active(auth.uid()))
  with check (auth.uid() = id and account_active(auth.uid()));

drop policy saved_plans_own_row on saved_plans;
create policy saved_plans_own_row on saved_plans for all
  using (auth.uid() = student_id and account_active(auth.uid()))
  with check (auth.uid() = student_id and account_active(auth.uid()));

-- A tiny marker so tests/db/conftest.py can detect "is this migration
-- applied yet" the same way 0003_maker_checker.sql's
-- maker_checker_schema_version() does — student_accounts/guardian_consents
-- existing is itself sufficient (mirrors 0002's _saved_plans_table_exists
-- pattern), but this also captures the functions/triggers in one place a
-- single existence check on a table can't.
create or replace function guardian_consent_schema_version()
returns int language sql immutable as $$ select 4 $$;
