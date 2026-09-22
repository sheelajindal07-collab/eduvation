-- BCION Lite — close account_active()'s cross-user identity-oracle gap
-- Source: adversarial re-review of CONSENT-4 (this branch, migration-owner
-- fix round, 2026-09-22) — a finding on ALREADY-MERGED, ALREADY-LIVE
-- db/migrations/0004_guardian_consent.sql, NOT a CONSENT-4 regression.
-- 0004 is applied to the real Mumbai staging project per STATUS.md's
-- Infrastructure table, so it is append-only exactly like every other
-- applied migration here — this is a new, additive, CREATE-OR-REPLACE
-- migration, never an edit to 0004_guardian_consent.sql itself.
--
-- **The finding, live-reproduced this session (see
-- tests/db/test_account_active_oracle.py's `TestAccountActiveOracleClosed`
-- for the regression tests, and its own revert-to-prove note):**
-- `account_active(uid uuid)` (0004) is `security definer` but has NO
-- explicit grant — it relies on the default PUBLIC execute privilege, a
-- deliberate-at-the-time design choice, reasoned in 0004's own comment as
-- "mirrors `is_reviewer()`'s pattern" — and its body never binds
-- `uid = auth.uid()`. That reasoning does not hold up: `is_reviewer()`
-- (0001_init.sql) takes ZERO parameters, so it can only ever answer for
-- the caller — it cannot be turned into a cross-user oracle no matter who
-- calls it. `account_active(uid)` takes an EXTERNALLY-CONTROLLED `uid`
-- with no internal binding at all, so ANY caller holding only the public
-- anon key — no session, no sign-in, nothing — can call
-- `POST /rest/v1/rpc/account_active` with an arbitrary victim's uid and
-- learn whether that account is active/pending/frozen/deletion-due: a
-- real cross-user information leak, live-confirmed against the local
-- stack (a session-less anon-key-only call returned HTTP 200 with a plain
-- true/false for an arbitrary real `student_accounts.id`). Exactly the
-- same class of bug this branch's own `is_admitted()`/
-- `is_safeguarding_staff()` fix rounds already closed
-- (0012_admission_axis.sql, 0013_safeguarding_schema.sql) — see those
-- files' own comments, and db/migrations/README.md's "identity oracle"
-- gotcha entry, for the full reasoning this fix mirrors exactly.
--
-- **The fix, same shape as is_admitted()/is_safeguarding_staff()
-- (`create or replace function` — safe on an existing function; the
-- signature is unchanged, so nothing that references it by name/args
-- needs to change):**
--   1. `and uid = auth.uid()` added to the body's own `where` clause — an
--      authenticated caller passing a DIFFERENT uid now gets the SAFE
--      DEFAULT (see below), never the target's real status.
--   2. `revoke execute ... from public` + `from anon`, then
--      `grant execute ... to authenticated` — closes the anon path at the
--      grant level too (BOTH revokes required, neither alone is enough —
--      see db/migrations/README.md's own gotcha entry for the two
--      independent paths that otherwise leave `anon` able to call this),
--      so an anon caller gets a flat 42501 instead of ever reaching the
--      function body at all.
--
-- **What must NOT change — every existing call site:** every real caller
-- in this schema — 0004's own `student_profiles_own_row`/
-- `saved_plans_own_row` (re-scoped again by 0012_admission_axis.sql into
-- `student_profiles_select_own`/`_insert_own`/`_update_own`/`_delete_own`
-- and `saved_plans_select_own`/`_insert_own`/`_update_own`/`_delete_own`),
-- and 0010_plan_actions.sql's `plan_actions_own_row` — ALWAYS calls this
-- as `account_active(auth.uid())`, always the caller's own id, never
-- anyone else's. For every one of those, `and uid = auth.uid()` is a
-- no-op: `uid` IS `auth.uid()` already. The only path this fix changes at
-- all is a DIRECT RPC call that passes someone else's uid explicitly —
-- never how any policy in this schema calls it.
--
-- **The "no student_accounts row at all" default is UNCHANGED for the
-- caller's OWN uid** (0004's own design note, lines ~68-91/383-391 of
-- that file): `account_active()` must still return `true` when the
-- CALLER has no `student_accounts` row — an 18+/legacy account with no
-- row must not be gated by a table that was never populated for them.
-- That default is preserved exactly for a caller asking about themselves.
--
-- **What a cross-user probe gets now, and why that is "safe" rather than
-- just "different":** `and uid = auth.uid()` makes the inner `select`
-- return no matching row whenever `uid <> auth.uid()` — the EXACT SAME
-- shape as "no student_accounts row exists at all", which
-- `coalesce(..., true)` already treated as `true` before this fix, for
-- an entirely different reason (a legacy/adult account never having a
-- row). So a cross-user probe now ALWAYS gets `true`, regardless of the
-- target's REAL status — constant, uninformative, and never the target's
-- actual active/pending/frozen/deletion-due state. This mirrors exactly
-- how 0012's `is_admitted()` fix works (that function's safe default is
-- `false`; this one's is `true` — each matches its own function's
-- pre-existing "no row" semantics, per this task's own instruction: never
-- change what a probe for someone else's uid returns as a VALUE, only
-- stop that value from ever being the real cross-user answer).
create or replace function account_active(uid uuid)
returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(
    (select account_status = 'active' from student_accounts where id = uid and uid = auth.uid()),
    true
  );
$$;

revoke execute on function account_active(uuid) from public;
revoke execute on function account_active(uuid) from anon;
grant execute on function account_active(uuid) to authenticated;

-- A tiny marker so tests/db/conftest.py can detect "is this migration
-- applied yet" — same pattern as 0003-0013.
create or replace function account_active_grant_fix_schema_version()
returns int language sql immutable as $$ select 14 $$;
