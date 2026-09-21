-- BCION Lite — server-side RPC for creating a guardian-consent request
-- Source of truth: db/migrations/0004_guardian_consent.sql (already live
-- in production — append-only, never edited retroactively; see
-- db/migrations/README.md) and app/api/guardian_consent.py's
-- create_guardian_consent_request, which this migration changes the
-- implementation of (not the Python function's name or signature).
--
-- **Why this RPC exists at all (read this before "fixing" it by adding a
-- SELECT policy to `guardian_consents` — that would defeat the whole
-- point of that table having none; see 0004's own module-level design
-- note on the token):**
--
-- app/api/guardian_consent.py's create_guardian_consent_request used to
-- do two plain `client.table(...).insert(...).execute()` calls, running
-- as the signed-in student. supabase-py's `.insert().execute()` defaults
-- to `Prefer: return=representation` — it asks PostgREST to hand back the
-- inserted row via `INSERT ... RETURNING`. PostgreSQL applies a table's
-- SELECT policies to rows produced by INSERT...RETURNING, not just the
-- INSERT policy's WITH CHECK to the write itself (this is documented
-- Postgres RLS behaviour, not a PostgREST quirk). `guardian_consents` has
-- zero SELECT policies (deliberately, per 0004) for ANY role, so that
-- RETURNING re-select was denied and the ENTIRE insert failed with "new
-- row violates row-level security policy for table guardian_consents" —
-- even though the INSERT's own WITH CHECK (`auth.uid() = student_id`)
-- was satisfied. Confirmed live: the identical insert succeeds with the
-- row actually written when sent with `Prefer: return=minimal` instead
-- (i.e. "don't ask for the row back"). Net effect: on the live database,
-- EVERY under-18 sign-up/sign-in that reached this function raised an
-- unhandled `APIError` — the guardian-consent gate was completely broken
-- for the exact population (minors) CLAUDE.md's non-negotiable exists to
-- protect.
--
-- The fix is not "add a SELECT policy" (that hands the token to the
-- owning student directly, self-defeating 0004's entire design) and not
-- "ask supabase-py for return=minimal" (the Python layer still needs the
-- freshly-generated token to build the guardian's confirmation email, and
-- there is no way to read it back afterward — there is still no SELECT
-- policy). The fix is to do the insert, and read the value INSERT itself
-- produced, in the SAME statement, INSIDE a SECURITY DEFINER function
-- that runs as the function owner rather than through PostgREST's
-- RLS-scoped REST call — no RETURNING-through-REST round trip, so no
-- SELECT policy is ever needed for this to work. Mirrors
-- `confirm_guardian_consent()`'s own existing pattern in
-- 0004_guardian_consent.sql exactly (same file, same reasoning: some
-- operations on this table can only ever be expressed as a function, not
-- as a client-side `.table()` call).
--
-- Determining the calling student from `auth.uid()` INSIDE the function
-- (never accepting a client-supplied student_id) is also a real security
-- improvement over 0004's own insert-RLS shape, not just a workaround:
-- previously "this insert is for the right student" was enforced by a
-- WITH CHECK policy comparing a client-supplied value to auth.uid()
-- (correct, but a value that has to be checked); here there is no
-- student_id parameter for a caller to even attempt to spoof — the
-- function structurally cannot act on any student but the caller.
--
-- Does not touch 0004_guardian_consent.sql (live in production, must
-- never be edited retroactively) — the table, its RLS policies
-- (`guardian_consents_insert_own` stays exactly as-is, still needed as
-- defense-in-depth for any other INSERT path that isn't this RPC) and its
-- BEFORE INSERT triggers (`enforce_guardian_consent_server_token`,
-- `enforce_guardian_consent_insert_pending`, both still fire on this
-- RPC's own insert — SECURITY DEFINER bypasses RLS, not triggers) are
-- all unchanged.

-- ============================================================
-- create_guardian_consent_request(p_date_of_birth, p_guardian_email)
-- ============================================================
--
-- Returns the freshly-generated token, or NULL when a pending request
-- already existed for this student (idempotent — mirrors the Python
-- layer's previous "already existed, not an error, no second email"
-- handling of a unique-violation, now expressed as ON CONFLICT ... DO
-- NOTHING instead of a caught exception). Never re-reads a PRIOR
-- request's token: that is the entire point of `guardian_consents` having
-- no SELECT policy — not even this RPC's own caller gets to read back a
-- request it didn't just create in this same call.
create or replace function create_guardian_consent_request(
  p_date_of_birth date,
  p_guardian_email text
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_student_id uuid;
  v_token text;
begin
  v_student_id := auth.uid();
  if v_student_id is null then
    raise exception
      'create_guardian_consent_request must be called by an authenticated session (auth.uid() is null).';
  end if;

  -- Idempotent against a concurrent duplicate call (two sign-in requests
  -- racing the same lazy-create path) — same reasoning
  -- app/api/guardian_consent.py's create_guardian_consent_request used to
  -- apply via a caught unique-violation on this table. `id` is a plain
  -- (non-partial) primary-key index, so a bare `on conflict (id)` target
  -- is correct.
  insert into student_accounts (id, date_of_birth, account_status)
  values (v_student_id, p_date_of_birth, 'pending_guardian_consent')
  on conflict (id) do nothing;

  -- The BEFORE INSERT triggers on guardian_consents
  -- (enforce_guardian_consent_server_token,
  -- enforce_guardian_consent_insert_pending — both defined in
  -- 0004_guardian_consent.sql, untouched here) still fire on this insert:
  -- they overwrite token/expires_at server-side and force status
  -- ='pending' regardless of what this function passes, exactly as they
  -- do for the RLS-scoped INSERT path. `guardian_consents_one_pending_
  -- per_student` (0004) is a PARTIAL unique index on (student_id) where
  -- status = 'pending', so the ON CONFLICT target below must repeat that
  -- same predicate to match it (a plain `on conflict (student_id)` would
  -- not match a partial index and would error at function-creation time).
  insert into guardian_consents (student_id, guardian_email)
  values (v_student_id, p_guardian_email)
  on conflict (student_id) where status = 'pending' do nothing
  returning token into v_token;

  return v_token;
end;
$$;

-- Narrow grant on principle: an anonymous caller has no auth.uid() to
-- act on anyway (the function would just raise), but this matches
-- 0004_guardian_consent.sql's own narrow-grant style
-- (my_guardian_consent_status() is authenticated-only for the same
-- reason; only confirm_guardian_consent() — a magic-link-style endpoint
-- with no session at all — is granted to anon).
grant execute on function create_guardian_consent_request(date, text) to authenticated;

-- Marker function, same pattern as guardian_consent_schema_version()
-- (0004) / maker_checker_schema_version() (0003) — lets
-- tests/db/conftest.py (or any future caller) detect "is this migration
-- applied yet" without depending on a table that already existed before
-- this migration ran.
create or replace function guardian_consent_request_rpc_schema_version()
returns int language sql immutable as $$ select 5 $$;
