-- BCION Lite — SEC-6: grants and exposure hardening
-- Source: docs/SECURITY.md's access matrix, db/migrations/README.md's own
-- "two gotchas" entry (the PUBLIC-default / anon-direct-grant gap this
-- file exists to close on every function it still applies to), CLAUDE.md
-- ("cross-user access is tested every time auth, RLS or publication
-- changes"). Append-only, additive, no table/column/function BODY
-- changes anywhere in this file — only GRANT/REVOKE statements and two
-- ALTER FUNCTION ... SET search_path calls that touch no function body.
--
-- Real migration number used: 0016. Reserved by running `ls
-- db/migrations/` fresh, in this session, immediately before writing
-- this file — 0001 through 0015 already existed on `main` (0011 AI-4,
-- 0012/0013 CONSENT-4, 0014 the account_active grant fix, 0015 the AI
-- identity-hash binding fix), so 0016 was the next free number. The
-- task card that named this work guessed 0014; that number was already
-- taken twice over by the time this session started, exactly the
-- "planning estimate, not a reservation" .claude/agents/migration-owner.md
-- warns about — confirmed with a fresh `ls`, not trusted from the card.
--
-- Every grant/revoke decision below was checked LIVE, on this
-- migration-owner's own throwaway second stack (bcion-lite-migration-2,
-- supabase/config.toml's reserved ports; never the shared bcion-lite-test
-- stack), by querying information_schema.routine_privileges /
-- role_table_grants BEFORE writing a single statement here — not
-- reasoned from memory or from reading old migration files alone. See
-- this migration owner's own completion report for the exact queries.

-- ============================================================
-- 1. Anon table-privilege reduction — the GRANT layer underneath RLS
-- ============================================================
-- Confirmed live before writing this: this Supabase stack grants anon
-- and authenticated ALL SEVEN table privileges (SELECT/INSERT/UPDATE/
-- DELETE/TRUNCATE/REFERENCES/TRIGGER) on every public-schema table by
-- default. RLS is the ONLY thing standing between anon and a write on
-- the four "public knowledge zone" tables below today —
-- `sources_write_reviewers` / `careers_write_reviewers` /
-- `pathways_write_reviewers` (0001_init.sql) all gate on `is_reviewer()`,
-- and `claims_insert_reviewers` / `claims_update_reviewers` (0001,
-- tightened 0003) do the same. A guest (anon) has no legitimate reason to
-- write here at all — a reviewer always authenticates first
-- (`is_reviewer()` reads `auth.uid()`, which anon never has) — so this
-- closes the GRANT layer as defence in depth: even a dropped or
-- misconfigured SELECT-shaped policy could no longer hand anon a write
-- on its own. SELECT is deliberately untouched: these four tables are
-- the world-readable public knowledge base (docs/UI.md; 0001's own
-- `..._select_all using (true)` policies), and a guest reading published
-- content is the entire point of this pilot.
revoke insert, update, delete, truncate, references, trigger
  on table sources, careers, pathways, claims
  from anon;

-- student_profiles, saved_plans, reviewers: anon has no legitimate
-- reason to touch these AT ALL, not even a read RLS then quietly denies.
-- student_profiles / saved_plans are strictly own-row (0001 / 0002, only
-- reachable once signed in); `reviewers` has RLS enabled with NO policy
-- at all (0001's own comment: "no policy ... means no access by default,
-- which is the intended state here") — an anon-writable GRANT underneath
-- a policy-free table is exactly the shape of accident this migration
-- exists to close before it can ever matter. Mirrors the exact
-- `revoke all on table X from anon, authenticated` pattern this ledger
-- already uses for `app_settings` (0007), `guest_sessions` /
-- `guest_plans` (0009) and `ai_usage_caps` / `pilot_invites` (0011 /
-- 0012) — `authenticated` is deliberately NOT touched here: a signed-in
-- student's own-row access to student_profiles/saved_plans is real and
-- RLS (not the grant layer) is what is supposed to scope it.
revoke all on table student_profiles, saved_plans, reviewers from anon;

-- ============================================================
-- 2. SECURITY DEFINER EXECUTE — close the PUBLIC/anon default,
--    confirm what's already correct, fix what wasn't
-- ============================================================
-- Every function named below runs SECURITY DEFINER — elevated rights,
-- regardless of who calls it (see each function's own migration for
-- what it needs that for). Two independent things make a bare `create
-- function` reachable by every role on this Supabase stack unless
-- explicitly closed (db/migrations/README.md's own "two gotchas" entry;
-- re-confirmed live in THIS session, on this migration's own stack,
-- before a single statement below was written): (1) the SQL-standard
-- default — EXECUTE to the pseudo-role PUBLIC, which every real role
-- implicitly holds through; (2) this stack's own `alter default
-- privileges` setup, a DIRECT grant to anon/authenticated/service_role
-- on every new public-schema function. A bare `revoke ... from public`
-- alone leaves anon's own direct grant (2) in place — several functions
-- below showed `anon` in `information_schema.routine_privileges` going
-- into this migration despite already carrying a `grant execute ... to
-- authenticated` line in their own file (that line is ADDITIVE, never
-- restrictive — see 0012_admission_axis.sql's own `redeem_invite()` note,
-- the first place this repo hit exactly this gap).
--
-- CONFIRMED ALREADY CORRECT — live-verified going into this migration
-- (revoke public + revoke anon + grant authenticated only, or fully
-- locked with no grant to any API role) — deliberately UNTOUCHED here,
-- per this card's own instruction not to blindly re-apply a blanket
-- revoke that could break an already-correct grant:
--   is_admitted(uuid)               -- 0012, tightened same day
--   is_safeguarding_staff(uuid)     -- 0013, tightened same day
--   redeem_invite(text)             -- 0012
--   withdraw_account()              -- 0013
--   account_active(uuid)            -- 0004, tightened by 0014
--   guest_session_id(text)          -- 0009: revoked from public/anon/
--                                      authenticated entirely; only
--                                      other SECURITY DEFINER functions
--                                      in this file ever call it
--   is_reviewer()                   -- 0001. EXPLICITLY EXEMPT (this
--                                      card's own instruction): every
--                                      anon-readable RLS policy that
--                                      calls it (sources/careers/pathways
--                                      /claims' own SELECT policies)
--                                      needs anon to hold EXECUTE on it,
--                                      and it answers `false` safely for
--                                      anyone it wasn't built for — there
--                                      is no cross-user probe here,
--                                      unlike is_admitted's pre-fix shape.
--   maker_checker_schema_version()  -- 0003. EXPLICITLY EXEMPT per this
--                                      card — but also, confirmed by
--                                      reading its own definition before
--                                      writing this, not actually
--                                      SECURITY DEFINER at all
--                                      (`language sql immutable`, no
--                                      elevated rights, `prosecdef =
--                                      false` live-confirmed): the
--                                      exemption is moot, it was never in
--                                      scope for this revoke to begin
--                                      with.
--
-- FOUND NOT YET CORRECT, FIXED HERE — the same class of gap as
-- is_admitted's pre-fix state, just never applied to these two 0004/0005
-- functions: both already carry a `grant execute ... to authenticated`
-- in their own file, but neither ever revoked public or anon, so anon
-- has held EXECUTE on both since the day each was created (confirmed
-- live: both showed `anon` in routine_privileges going into this
-- migration). Neither is meant to be anon-callable —
-- `create_guardian_consent_request()` only ever runs "as the signed-in
-- student" (0005's own docstring), and `my_guardian_consent_status()`
-- answers `where student_id = auth.uid()`, which is simply never true
-- for anon (`auth.uid()` is null there) — so this closes a real,
-- previously-open exposure with no behaviour change for the one caller
-- each was actually built for.
revoke execute on function my_guardian_consent_status() from public;
revoke execute on function my_guardian_consent_status() from anon;
grant execute on function my_guardian_consent_status() to authenticated;

revoke execute on function create_guardian_consent_request(date, text) from public;
revoke execute on function create_guardian_consent_request(date, text) from anon;
grant execute on function create_guardian_consent_request(date, text) to authenticated;

-- DELIBERATELY ANON-CALLABLE, KEPT THAT WAY — each already carries an
-- explicit `grant execute ... to anon, authenticated` for a real,
-- documented reason (a guardian confirming consent has no session at
-- all; a guest plan / invite check / AI reservation happens before or
-- without sign-in). Revoking PUBLIC only closes the pseudo-role default
-- for every OTHER role this stack could ever add (`dashboard_user`, a
-- future read-only reporting role, ...) — it changes nothing for anon or
-- authenticated, whose grants are already explicit and are restated here
-- for the same reason 0011's `ai_usage_daily_totals` states
-- `security_invoker = false` explicitly rather than leaving it to a
-- default: making the load-bearing choice explicit, not default-shaped.
revoke execute on function confirm_guardian_consent(text) from public;
grant execute on function confirm_guardian_consent(text) to anon, authenticated;

revoke execute on function invite_is_valid(text) from public;
grant execute on function invite_is_valid(text) to anon, authenticated;

revoke execute on function create_guest_session() from public;
grant execute on function create_guest_session() to anon, authenticated;

revoke execute on function save_guest_plan(text, uuid, numeric) from public;
grant execute on function save_guest_plan(text, uuid, numeric) to anon, authenticated;

revoke execute on function list_guest_plans(text) from public;
grant execute on function list_guest_plans(text) to anon, authenticated;

revoke execute on function delete_guest_plan(text, uuid) from public;
grant execute on function delete_guest_plan(text, uuid) to anon, authenticated;

revoke execute on function ai_reserve(text, text, text, int) from public;
grant execute on function ai_reserve(text, text, text, int) to anon, authenticated;

revoke execute on function ai_settle(uuid, int, text, uuid[], uuid[]) from public;
grant execute on function ai_settle(uuid, int, text, uuid[], uuid[]) to anon, authenticated;

revoke execute on function ai_budget_remaining(text, text) from public;
grant execute on function ai_budget_remaining(text, text) to anon, authenticated;

-- `demo_mode()` had NO explicit grant statement anywhere in 0007 — it
-- was reachable purely through the two stack defaults described above.
-- It MUST stay anon-callable: `app/api/explore.py`'s `_demo_mode()`
-- calls it as whatever role the visitor is, including a guest, and
-- `claims_select_demo_synthetic` (0007) evaluates it inside an
-- anon-readable SELECT policy on `claims`. Restated explicitly here
-- rather than left default-shaped, same reasoning as the block above —
-- and, unlike that block, this is the first time this function's grants
-- have ever been written down anywhere.
revoke execute on function demo_mode() from public;
grant execute on function demo_mode() to anon, authenticated;

-- ============================================================
-- 3. Pin search_path on the two functions that never got one
-- ============================================================
-- Neither is SECURITY DEFINER (both run with the caller's own rights;
-- confirmed live, `prosecdef = false` for both, before writing this) —
-- neither carries the "elevated rights, hostile schema" risk a definer
-- function does. Pinned anyway, on this card's own instruction and as
-- the same cheap, unconditional insurance every OTHER function in this
-- schema already has (`is_reviewer()`, `demo_mode()`, `account_active()`,
-- ai_identity_hash()`, ... — every one of them was written with `set
-- search_path = public` from the day it was created): a future `create
-- schema` plus a role that could put a same-named object earlier in an
-- unqualified caller's search_path is a risk this removes for good,
-- rather than one this migration merely declines to introduce today.
-- `alter function`, not `create or replace` — neither function's BODY
-- changes, only its own pinned configuration, so this is exactly as
-- additive as every REVOKE/GRANT statement above it.
alter function forbid_publishing_synthetic_claims() set search_path = public;
alter function touch_updated_at() set search_path = public;

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as every migration since 0003.
create or replace function grants_hardening_schema_version()
returns int language sql immutable as $$ select 16 $$;
