-- BCION Lite — fix the guardian-consent token trigger's pgcrypto lookup
-- Source of truth: db/migrations/ (append-only; 0004 and 0005 are live in
-- production and must never be edited retroactively — see README.md).
--
-- **The bug this closes** (found live, 2026-09-21, the first time the
-- guardian-consent suite ever ran against a real database):
-- 0004_guardian_consent.sql's BEFORE INSERT trigger function
-- `enforce_guardian_consent_server_token()` calls `gen_random_bytes(32)`
-- unqualified. 0001_init.sql does `create extension if not exists
-- "pgcrypto"`, but Supabase installs extension functions into the
-- `extensions` schema, not `public` (confirmed live on this project:
-- `select n.nspname from pg_proc p join pg_namespace n on
-- p.pronamespace = n.oid where p.proname = 'gen_random_bytes'` returns
-- `extensions`). PostgREST sessions don't have `extensions` on their
-- search_path, so EVERY insert into `guardian_consents` — through the raw
-- RLS path and through 0005's RPC alike, since the trigger fires on both —
-- failed with `function gen_random_bytes(integer) does not exist` (42883).
-- (`gen_random_uuid()` was never affected: it is a core Postgres function
-- since v13, not a pgcrypto one.)
--
-- **The fix:** schema-qualify the call. Deliberately NOT a
-- `set search_path = public, extensions` on the function instead: a
-- qualified call cannot be shadowed by anything earlier on a search path,
-- and it keeps this function's name resolution independent of whatever the
-- calling session's path happens to be. Function body is otherwise
-- byte-for-byte what 0004 defined; the trigger itself
-- (`guardian_consents_enforce_server_token`) is untouched — `create or
-- replace function` swaps the body in place under the existing trigger.

create or replace function enforce_guardian_consent_server_token()
returns trigger as $$
begin
  new.token := encode(extensions.gen_random_bytes(32), 'hex');
  new.expires_at := now() + interval '72 hours';
  return new;
end;
$$ language plpgsql;

-- Marker function, same pattern as 0003/0004/0005 — lets
-- app.api.guardian_consent.guardian_consent_schema_is_live() and
-- tests/db/conftest.py detect "is this migration applied yet", so the gate
-- stays fail-closed (clean 503, not a 500) anywhere 0004/0005 are applied
-- but this fix is not.
create or replace function guardian_consent_token_fix_schema_version()
returns int language sql immutable as $$ select 6 $$;
