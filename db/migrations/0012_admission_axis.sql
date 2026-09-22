-- BCION Lite — the admission axis (CONSENT-4, part 1 of 2)
-- Source of truth: docs/CONSENT.md (frozen design), sections 2-4 and 7.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0011.
--
-- **Real number check (migration-owner rule):** `ls db/migrations/` at
-- the moment this file was FIRST written showed 0001-0010, so the free
-- numbers were believed to be 0011 and 0012 — WRONG by the time this
-- branch's own migration-owner fix round re-checked: `db/migrations/
-- 0011_ai_usage.sql` (AI-4) merged to `main` and was applied to the
-- shared local test stack while this branch was still mid-review, a real
-- collision with this file's original 0011. A fresh `ls db/migrations/`
-- at the fix-round session-open showed 0001-0011 (0011 now being AI-4's
-- ai_usage migration), so this file is renumbered 0011 -> 0012, and its
-- companion (formerly 0012_safeguarding_schema.sql) is renumbered 0012 ->
-- 0013. Every internal cross-reference in both files below was updated to
-- match. This task's own card text mentioned no specific number;
-- docs/CONSENT.md doesn't either.
--
-- **Why two migrations, not one (own judgement call):** this file adds
-- 'frozen' and 'deletion_due' to the existing `account_status` enum via
-- `ALTER TYPE ... ADD VALUE`. Postgres will not let a newly-added enum
-- value be USED (evaluated in a DML statement that actually executes)
-- inside the same transaction that added it — scripts/apply_migrations.py
-- runs one whole file as one transaction (single `cur.execute(sql)`,
-- committed once at the end), so any statement in THIS file that
-- actually ran a query comparing/assigning `'frozen'` or
-- `'deletion_due'` would raise "unsafe use of new value of enum type".
-- Defining a function whose BODY merely contains that literal is fine
-- (plpgsql bodies are not executed at CREATE time), but
-- `withdraw_account()` (0013) sets `account_status = 'frozen'` and, more
-- importantly, keeping the enum-widening step in its own file/transaction
-- removes any need to reason about which statements in a mixed file
-- would or wouldn't actually execute the new value — this migration
-- ADDS the values and does not evaluate them anywhere itself, and 0013
-- (a separate, later-committed transaction) is free to use them.
--
-- **What this file does NOT do:** it does not create, touch or gate
-- `consents`, `safeguarding_staff` or `safeguarding_flags` (0013), and it
-- does not build `withdraw_account()` (0013, needs 'frozen' at call
-- time, which is safe once 0012 has committed). It was originally
-- written database-layer-only, per this task's own card — that changed
-- mid-session: adversarial review found the database-only cut left every
-- real adult account permanently inadmissible (see this file's
-- `is_admitted()` comment below), which a database migration alone
-- cannot close (there is no admission-axis-specific application code to
-- touch from here). The minimum companion fix —
-- `app.api.guardian_consent.ensure_active_student_account` plus
-- `POST /auth/redeem-invite` — was added in app/api/ in the SAME session
-- as this file's own review-driven revision, not deferred to a separate
-- task, precisely so this migration's write-policy change never ships
-- without a way for anyone to actually become admitted.

-- ============================================================
-- account_status — extend the EXISTING enum additively
-- ============================================================
-- 0004_guardian_consent.sql created `account_status as enum ('active',
-- 'pending_guardian_consent')`. CONSENT-4's own card text said it
-- "creates" account_status; docs/CONSENT.md section 2 already flags that
-- as wrong and stale — this extends what 0004 created, it never drops or
-- recreates the type.
alter type account_status add value 'frozen';
alter type account_status add value 'deletion_due';

-- ============================================================
-- student_accounts — the admission axis + the withdrawal timer
-- ============================================================
-- `admitted_at`: writable ONLY by `redeem_invite()` below (no UPDATE
-- policy on student_accounts grants either anon or authenticated a path
-- to this column at all — see the RLS section at the bottom of this
-- file, which adds no new UPDATE policy, and the pre-existing 0004
-- policies already omit UPDATE entirely). A SECURITY DEFINER function
-- bypasses RLS via its owner's privileges, not via a grant, so no grant
-- statement is what "only redeem_invite can write this" actually means
-- here.
--
-- `deletion_due_at`: stamped by `withdraw_account()` (0013) when it
-- freezes an account, so a later, separate task (AUTH-10, not this one)
-- has a concrete time to act on. Added here (harmless on its own — a
-- plain timestamptz column, no enum dependency) so 0013 does not need
-- its own ALTER TABLE just to add one column next to the function that
-- uses it.
alter table student_accounts
  add column admitted_at     timestamptz,
  add column deletion_due_at timestamptz;

-- ------------------------------------------------------------
-- CRITICAL, adversarial-review fix (this session, post-merge-review):
-- self-admission bypass via a plain own-row INSERT.
-- ------------------------------------------------------------
-- 0004's `student_accounts_insert_own` policy (`with check (auth.uid() =
-- id)`) says nothing about `admitted_at`/`deletion_due_at` — a signed-in
-- caller's own-row INSERT against the REST API could set either directly
-- (`{"id": auth.uid(), ..., "admitted_at": now()}`), live-reproduced:
-- this made is_admitted() true and saved_plans/student_profiles writable
-- with zero real invite code ever redeemed, a complete bypass of
-- redeem_invite() below. Neither column is EVER legitimately set by an
-- INSERT in the first place — the only two writers, redeem_invite() and
-- withdraw_account() (0013), both use UPDATE, never INSERT, and both are
-- SECURITY DEFINER (so neither is affected by anything a BEFORE INSERT
-- trigger does). Mirrors `enforce_guardian_consent_server_token()`'s
-- (0004) exact shape: unconditionally overwrite on every INSERT rather
-- than trying to distinguish a "trusted" insert from an untrusted one.
--
-- `service_role` is exempt, exactly like `enforce_claims_workflow()`
-- (0003) and `enforce_jurisdiction_...` (0008) already carve it out —
-- this is what lets `tests/db/conftest.py`'s `admit_student()` and this
-- file's own test suite keep seeding an already-admitted row directly via
-- the service-role `admin_client` without walking a real invite-redemption
-- flow just to set up an unrelated test. A real client session is never
-- `service_role` (docs/SECURITY.md), so this carve-out does not touch the
-- guarantee that actually matters.
create or replace function enforce_student_accounts_insert_not_admitted()
returns trigger as $$
begin
  if auth.role() = 'service_role' then
    return new;
  end if;

  new.admitted_at := null;
  new.deletion_due_at := null;
  return new;
end;
$$ language plpgsql;

create trigger student_accounts_enforce_insert_not_admitted
before insert on student_accounts
for each row execute function enforce_student_accounts_insert_not_admitted();

-- ============================================================
-- is_admitted() — the predicate CONSENT-4 must AND into write policies
-- ============================================================
-- Deliberately FAILS CLOSED when `p_uid` has no `student_accounts` row
-- at all — the OPPOSITE default from `account_active()` (0004), which
-- fails OPEN (returns true) for the same "no row" case. That is not an
-- inconsistency, it is two different questions with two different safe
-- defaults:
--   * account_active() asks "is this account's CONSENT state okay" —
--     historically only ever populated for a self-declared minor, so an
--     18+/legacy account with no row must not be gated by a table that
--     was never populated for them (0004's own design note).
--   * is_admitted() asks "has this person been let into the pilot AT
--     ALL" — Phase 1 is invite-only (docs/CONSENT.md section 1), so
--     "no admission record" must mean "not admitted", never "admitted by
--     default". Defaulting this one open would silently readmit every
--     account with no student_accounts row — exactly the gap this whole
--     migration exists to close.
--
-- FORMERLY A KNOWN GAP, now closed (adversarial review finding, this
-- session, HIGH — see STATUS.md and this session's completion report):
-- app/api/auth.py used to only ever insert a `student_accounts` row for
-- a SELF-DECLARED MINOR (0004's design note — "only an account created
-- as a self-declared minor ever gets one"). An 18+ sign-up's
-- date_of_birth landed only in Supabase's own
-- `auth.users.raw_user_meta_data`, never in this table, which meant
-- `redeem_invite()` below had no row to stamp `admitted_at` onto for ANY
-- adult, ever — a real regression this migration's own write-policy
-- change would have introduced for the only population Phase 1 serves.
-- `app.api.guardian_consent.ensure_active_student_account` (called from
-- both `app.api.auth.sign_up`'s adult branch and
-- `enforce_guardian_consent_gate`'s first-sign-in bootstrap, for the
-- case sign-up itself returned no session) now creates that row —
-- `account_status='active'`, `admitted_at` still null — so `is_admitted()`
-- still correctly, safely returns false until a real invite code is
-- redeemed via the new `POST /auth/redeem-invite` route, rather than
-- forever. `is_admitted()`'s own fail-closed default (below) is
-- unchanged; only the missing row that made it unconditionally false for
-- every adult is fixed.
-- CRITICAL, adversarial-review fix (this session, post-merge-review):
-- unauthenticated/cross-user admission oracle. As first written, this
-- function had no grant restriction at all (unlike redeem_invite()/
-- withdraw_account() below, which explicitly `revoke ... from public,
-- anon`) — live-reproduced: a caller holding only the public anon key,
-- with NO session whatsoever, could call
-- `is_admitted({"p_uid": "<any real uid>"})` and learn whether that
-- account is admitted, and any signed-in `authenticated` caller could do
-- the same for an arbitrary OTHER user's uid (p_uid defaults to, but was
-- never restricted to, the caller's own auth.uid()). Two independent
-- fixes, both required (defense in depth, same reasoning as
-- redeem_invite()'s grant block):
--   1. `where id = p_uid and p_uid = auth.uid()` — the function itself
--      now refuses to answer for anyone but the caller. For every real
--      caller of this function (every RLS policy below always passes
--      `is_admitted(auth.uid())`, and Supabase's own default parameter
--      does the same) this is a no-op; it only changes the answer for an
--      explicit, other-uid probe, which now always evaluates to `false`
--      regardless of the target's real state.
--   2. The REVOKE-then-GRANT block below (mirrors redeem_invite()'s own,
--      see db/migrations/README.md's gotcha entry): closes the anon path
--      at the grant level too, so an anon caller gets a flat 42501
--      instead of ever reaching the function body at all.
create or replace function is_admitted(p_uid uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (
      select admitted_at is not null and account_status = 'active'
      from student_accounts
      where id = p_uid and p_uid = auth.uid()
    ),
    false
  );
$$;

revoke execute on function is_admitted(uuid) from public;
revoke execute on function is_admitted(uuid) from anon;
grant execute on function is_admitted(uuid) to authenticated;

-- ============================================================
-- pilot_invites — hashed codes only, never plaintext
-- ============================================================
-- One row per invite code the owner issues out of band (docs/CONSENT.md
-- section 3, step 1). Only `code_hash` (sha-256 hex digest, via
-- pgcrypto's `digest()` — pgcrypto itself already enabled in
-- 0001_init.sql) is ever stored; the plaintext code never enters this
-- table, this repo, or any log. Nothing in this migration inserts a real
-- code — issuing invites is an owner action via the SQL editor/psql,
-- explicitly out of scope for this database-layer task (see this file's
-- header and CONSENT-4's own completion report for the open question
-- this leaves).
create table pilot_invites (
    id          uuid primary key default gen_random_uuid(),
    code_hash   text not null unique,
    expires_at  timestamptz not null,
    used_by     uuid references auth.users(id) on delete set null,
    used_at     timestamptz,
    created_at  timestamptz not null default now()
);

create index pilot_invites_used_by_idx on pilot_invites (used_by);

-- Sealed table (0009_guest_sessions.sql's pattern, not 0001's
-- `reviewers`/0004's `guardian_consents` "RLS + zero policies" pattern):
-- REVOKE the default table grants on top of enabling RLS with no
-- policies, so a direct REST call gets a flat permission-denied instead
-- of an empty result set. Nothing about this table has a legitimate
-- direct-read or direct-write use from anon or authenticated — even a
-- FILTERED read (own-row style) makes no sense here, since an invite
-- code is not "owned" by anybody until it is redeemed, and a client
-- must never be able to browse hashes, expiries or usage state directly
-- (docs/CONSENT.md section 7: "a live invite code is credential-like").
-- `invite_is_valid()`/`redeem_invite()` below are SECURITY DEFINER and
-- so bypass this entirely via their owner's privileges, exactly as
-- `confirm_guardian_consent()` (0004) bypasses `guardian_consents`' own
-- lack of a SELECT policy.
alter table pilot_invites enable row level security;
revoke all on table pilot_invites from anon, authenticated;

-- ============================================================
-- invite_is_valid() — advisory-only, anon-callable, leaks nothing
-- ============================================================
-- docs/CONSENT.md section 3, step 2: checked at sign-up so a typo fails
-- immediately rather than after an email round trip. Returns a BARE
-- boolean (no row, no distinguishing "wrong code" from "expired" from
-- "already used" from "never existed") — every non-match takes the exact
-- same `exists (...) = false` path, so there is no timing or shape
-- signal beyond "this table has one hashed-equality lookup", which is
-- true regardless of the code's validity. Grants NOTHING: a true result
-- here changes no state and unlocks no write anywhere — only
-- `redeem_invite()`, called later with a real session, actually admits
-- anyone (section 3, step 4: "step 2 grants nothing").
create or replace function invite_is_valid(p_code text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from pilot_invites
    where code_hash = encode(extensions.digest(p_code, 'sha256'), 'hex')
      and used_by is null
      and expires_at > now()
  );
$$;

grant execute on function invite_is_valid(text) to anon, authenticated;

-- ============================================================
-- redeem_invite() — the ONLY way to become admitted
-- ============================================================
-- docs/CONSENT.md section 3, step 4, and section 4's contract:
--   * Requires `auth.uid()` — raises if called with no session, rather
--     than silently returning false, so a caller can tell "not signed
--     in" from "code didn't work".
--   * Checks the caller's OWN `student_accounts` row is 'active' BEFORE
--     touching `pilot_invites` at all, and returns false without
--     consuming the code if it isn't (no row, still
--     pending_guardian_consent, frozen, or deletion_due). This is
--     deliberately ordered first so a caller who could never be admitted
--     right now does not burn a real, possibly scarce invite code on an
--     attempt that was doomed before it started.
--   * The UPDATE on `pilot_invites` is the single-use gate: `used_by is
--     null` in the WHERE clause means a second call with the SAME code
--     matches zero rows and returns false — "a second call for an
--     already-used code must fail/return false, never silently re-stamp
--     admitted_at" (section 4).
--   * The final UPDATE on `student_accounts` also guards `admitted_at is
--     null`, so even a WEIRD second success (a different, still-valid
--     code redeemed by an already-admitted caller) cannot re-stamp
--     `admitted_at` with a fresh timestamp — the stamp itself is
--     idempotent, not just the code.
create or replace function redeem_invite(p_code text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_account_active boolean;
  v_invite_id uuid;
begin
  if v_uid is null then
    raise exception 'redeem_invite requires an authenticated session.';
  end if;

  select (account_status = 'active') into v_account_active
  from student_accounts
  where id = v_uid;

  if v_account_active is not true then
    return false;
  end if;

  update pilot_invites
  set used_by = v_uid, used_at = now()
  where code_hash = encode(extensions.digest(p_code, 'sha256'), 'hex')
    and used_by is null
    and expires_at > now()
  returning id into v_invite_id;

  if v_invite_id is null then
    return false;
  end if;

  update student_accounts
  set admitted_at = now()
  where id = v_uid and admitted_at is null;

  return true;
end;
$$;

-- REVOKE-then-GRANT, not a bare GRANT: a bare `grant ... to
-- authenticated` (0004's own `my_guardian_consent_status`/
-- `confirm_guardian_consent` pattern) is ADDITIVE, not restrictive, and
-- TWO independent things already make every new function callable by
-- `anon` before this migration ever runs — both confirmed live this
-- session by querying `information_schema.routine_privileges` after
-- each of two successive, each individually insufficient, fix attempts:
--   1. The SQL-standard default: a bare `create function` grants EXECUTE
--      to the pseudo-role PUBLIC, which every real role (including
--      `anon`) implicitly holds privileges through, regardless of its
--      own direct grants.
--   2. This Supabase stack's own setup additionally runs something
--      equivalent to `alter default privileges in schema public grant
--      execute on functions to anon, authenticated, service_role` — a
--      DIRECT grant to `anon` on top of (1).
-- Revoking only from `public` (attempt 1) left `anon`'s own direct grant
-- (2) in place; revoking only from `anon` (attempt 2) left PUBLIC's
-- default (1) in place — either alone, `guest_client.rpc("redeem_invite",
-- ...)` kept reaching this function's internal `auth.uid() is null`
-- check and being refused there (a raised P0001, functionally safe but
-- not a grant-level 42501, and one accidental future edit to that
-- internal check away from a real hole). BOTH revokes below are
-- required together; dropping either silently reopens the gap. The
-- internal check remains too, as genuine defense in depth alongside
-- these grants, not instead of them.
revoke execute on function redeem_invite(text) from public;
revoke execute on function redeem_invite(text) from anon;
grant execute on function redeem_invite(text) to authenticated;

-- ============================================================
-- The gap this migration closes: AND is_admitted() into saved_plans'
-- and student_profiles' EXISTING write policies
-- ============================================================
-- docs/CONSENT.md section 7, "THE GAP CONSENT-4 MUST CLOSE": "today an
-- un-admitted account with a confirmed email can still write saved_plans
-- and student_profiles. is_admitted() must be added (ANDed) into those
-- tables' existing write policies (do not touch their read policies
-- unless the design requires it)".
--
-- Both tables' own-row rule was, until now, ONE `for all` policy
-- covering all four operations (student_profiles_own_row, 0001, re-scoped
-- by 0004; saved_plans_own_row, 0002, re-scoped by 0004). `for all`
-- cannot be narrowed to "only INSERT/UPDATE/DELETE" — Postgres has no
-- "for all except select". Splitting SELECT into its own, UNCHANGED
-- policy and INSERT/UPDATE/DELETE into three policies that additionally
-- require `is_admitted(auth.uid())` is therefore not optional
-- decoration — it is the only way to satisfy "AND is_admitted() into
-- the write policies" while leaving "do not touch the read policy"
-- literally true rather than merely intended. `account_active(auth.uid())`
-- — 0004's own gate — is kept, unchanged, in every clause it was already
-- in: this is additive to the existing own-row check, not a replacement.
drop policy student_profiles_own_row on student_profiles;

create policy student_profiles_select_own on student_profiles for select
  using (auth.uid() = id and account_active(auth.uid()));

create policy student_profiles_insert_own on student_profiles for insert
  with check (auth.uid() = id and account_active(auth.uid()) and is_admitted(auth.uid()));

create policy student_profiles_update_own on student_profiles for update
  using (auth.uid() = id and account_active(auth.uid()) and is_admitted(auth.uid()))
  with check (auth.uid() = id and account_active(auth.uid()) and is_admitted(auth.uid()));

create policy student_profiles_delete_own on student_profiles for delete
  using (auth.uid() = id and account_active(auth.uid()) and is_admitted(auth.uid()));

drop policy saved_plans_own_row on saved_plans;

create policy saved_plans_select_own on saved_plans for select
  using (auth.uid() = student_id and account_active(auth.uid()));

create policy saved_plans_insert_own on saved_plans for insert
  with check (
    auth.uid() = student_id and account_active(auth.uid()) and is_admitted(auth.uid())
  );

create policy saved_plans_update_own on saved_plans for update
  using (auth.uid() = student_id and account_active(auth.uid()) and is_admitted(auth.uid()))
  with check (
    auth.uid() = student_id and account_active(auth.uid()) and is_admitted(auth.uid())
  );

create policy saved_plans_delete_own on saved_plans for delete
  using (auth.uid() = student_id and account_active(auth.uid()) and is_admitted(auth.uid()));

-- NOTE, flagged rather than fixed here (out of this task's named scope,
-- which is exactly "saved_plans' and student_profiles' EXISTING write
-- policies" — docs/CONSENT.md section 7 and this task's own card, both
-- verbatim): `plan_actions_own_row` (0010) governs plan_actions via an
-- EXISTS against `saved_plans` that checks `p.student_id = auth.uid()
-- and account_active(auth.uid())`, but NOT `is_admitted()`. An account
-- that somehow already holds a saved_plans row from before it needed
-- admission (or a future bug that let one through) could still write
-- plan_actions hanging off it. Left alone here rather than silently
-- widened beyond the two tables this task names — see CONSENT-4's
-- completion report.

-- A tiny marker so tests/db/conftest.py can detect "is this migration
-- applied yet" — same pattern as 0003-0011.
create or replace function admission_axis_schema_version()
returns int language sql immutable as $$ select 12 $$;
