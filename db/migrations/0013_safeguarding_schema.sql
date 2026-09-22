-- BCION Lite — safeguarding schema + withdrawal (CONSENT-4, part 2 of 2)
-- Source of truth: docs/CONSENT.md (frozen design), sections 4-6.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0012.
--
-- Renumbered 0012 -> 0013 in the same migration-owner fix round that
-- renumbered this file's companion 0011 -> 0012 (see that file's own
-- header for the full collision story: `0011_ai_usage.sql`, AI-4,
-- merged to `main` and applied to the shared test stack while this
-- branch was still mid-review).
--
-- Depends on 0012_admission_axis.sql having already been APPLIED (a
-- separate, already-committed transaction) — this file is the one that
-- actually USES the `'frozen'` enum value 0012 added, which Postgres
-- only allows once the transaction that added it has committed (see
-- 0012's own header for the full "why two files" reasoning).
--
-- Builds ONLY the schema, RLS and the three remaining function-contract
-- items (`is_safeguarding_staff()`, `withdraw_account()`, plus the
-- `consents`/`safeguarding_staff`/`safeguarding_flags` tables) — never
-- the distress-keyword DETECTION logic (Phase 2, not this task; see
-- docs/CONSENT.md section 6) and never actual deletion execution
-- (AUTH-10, not this task; see `withdraw_account()`'s own comment below).

-- ============================================================
-- consents — append-only, one row per grant or withdrawal
-- ============================================================
-- Column design (the task's own "design the exact columns needed"):
--   * `kind`   — WHAT was granted or withdrawn. Free TEXT, not an enum,
--     on purpose: docs/CONSENT.md section 8 names four Phase-2 kinds
--     (marks, category/income, parent summary, contacting an
--     institution) that are not this task's to define precisely, and an
--     enum would force guessing their exact spelling now. CONSENT-4
--     itself only ever writes 'account' (the whole-account withdrawal,
--     via `withdraw_account()` below).
--   * `action`  — exactly two values today, both definitional and
--     unlikely to grow casually, so this one IS an enum
--     (`consent_action`), matching this schema's existing convention
--     for a small closed vocabulary (source_type, claim_status,
--     account_status, guardian_consent_status).
--   * `wording_version` — which version of the consent text the student
--     saw. Not validated against a real registry here (none exists yet);
--     `withdraw_account()` below uses a placeholder version, flagged as
--     a named assumption in that function's own comment.
--   * `student_id` — `on delete cascade`, same as every other
--     student-linked table in this schema (student_profiles, saved_plans,
--     student_accounts, guardian_consents). A first draft of this
--     migration deliberately left this as the default (NO ACTION /
--     effectively RESTRICT) instead, reasoning that docs/CONSENT.md
--     section 6's "the append-only consents trail survives as the record
--     that a withdrawal happened" meant a cascade must never be allowed
--     to erase it. Live-verified wrong (this session, running
--     tests/db/test_access_matrix.py's own throwaway-user teardown
--     against this migration): RESTRICT does not "make AUTH-10 choose
--     consciously" the way that reasoning assumed — it actively BREAKS
--     every ordinary `auth.admin.delete_user()` call for any user who
--     ever has a `consents` row, full stop, including this repo's own
--     test fixtures (`student_a`'s teardown started failing with
--     "Database error deleting user" the moment a test seeded a
--     `consents` row for that user). CASCADE restored, matching every
--     other table here. The real tension this leaves is now explicitly
--     AUTH-10's to resolve when it builds actual deletion: hard-deleting
--     `auth.users` WILL take this row with it, so "the trail survives"
--     needs a different mechanism there (e.g. anonymising/soft-deleting
--     the account rather than hard-deleting `auth.users`, or copying the
--     fact of a withdrawal somewhere that doesn't reference the user row
--     at all) — CONSENT-4 performs no deletion itself, so it does not
--     have to pick that mechanism, but this comment is where the next
--     person looks so the tension isn't rediscovered the hard way again.
create type consent_action as enum ('granted', 'withdrawn');

create table consents (
    id               uuid primary key default gen_random_uuid(),
    student_id       uuid not null references auth.users(id) on delete cascade,
    kind             text not null,
    action           consent_action not null,
    wording_version  text not null,
    created_at       timestamptz not null default now()
);

create index consents_student_idx on consents (student_id);

alter table consents enable row level security;

-- Own-row SELECT only — docs/CONSENT.md section 6: "students ... read
-- zero rows of ... other people's consents" implies a student DOES read
-- their OWN. Deliberately NO insert/update/delete policy for anyone,
-- including the owning student: "one row per grant or withdrawal" is
-- enforced by having no client-reachable write path at all, not by a
-- trigger — the ONLY writer today is `withdraw_account()` below, a
-- SECURITY DEFINER function that bypasses RLS via its owner's
-- privileges, exactly the same mechanism `confirm_guardian_consent()`
-- (0004) uses to write `student_accounts` despite that table having no
-- client-reachable UPDATE policy either. A future Phase-2
-- consent-granting flow gets its OWN definer function when it is built;
-- it is not built here.
create policy consents_select_own on consents for select
  using (auth.uid() = student_id);

-- ============================================================
-- safeguarding_staff — mirrors `reviewers` (0001) exactly
-- ============================================================
create table safeguarding_staff (
    user_id   uuid primary key references auth.users(id) on delete cascade,
    added_at  timestamptz not null default now()
);

alter table safeguarding_staff enable row level security;
-- No policy at all, same reasoning 0001_init.sql gives for `reviewers`:
-- "only the is_safeguarding_staff() security-definer function touches
-- it". RLS enabled + zero policies means zero rows for SELECT/UPDATE/
-- DELETE (a filtered read, not a privilege error) and a 42501 for
-- INSERT (no permissive policy at all) — the exact same shape
-- tests/db/access_matrix.py already documents for `reviewers`.

-- CRITICAL, adversarial-review fix (this session, post-merge-review):
-- same unauthenticated/cross-user oracle bug as 0012's is_admitted() (see
-- that migration's own comment on its is_admitted() for the full
-- live-verified finding and reasoning — identical fix, mirrored here).
-- Live-reproduced: an anon-key-only caller with no session at all could
-- call `is_safeguarding_staff({"p_uid": "<any real uid>"})` and learn
-- whether that account is on the safeguarding team, defeating this
-- table's whole point (RLS enabled, ZERO policies, "nobody, including
-- staff, can read it directly" — see the table's own comment above). The
-- `and p_uid = auth.uid()` clause plus the REVOKE-then-GRANT block below
-- close it the same two ways: the function itself now only ever answers
-- for the caller, and anon loses EXECUTE at the grant level too.
create or replace function is_safeguarding_staff(p_uid uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from safeguarding_staff where user_id = p_uid and p_uid = auth.uid()
  );
$$;

revoke execute on function is_safeguarding_staff(uuid) from public;
revoke execute on function is_safeguarding_staff(uuid) from anon;
grant execute on function is_safeguarding_staff(uuid) to authenticated;

-- ============================================================
-- safeguarding_flags — category and ids ONLY, never message text
-- ============================================================
-- Deliberately minimal: this task builds the TABLE, its RLS and
-- is_safeguarding_staff() — not the Phase-2 distress-keyword detection
-- logic that will eventually insert rows here (docs/CONSENT.md section
-- 6). `category` is free TEXT rather than an enum for the same reason
-- `consents.kind` is: the real category vocabulary is a Phase-2 product
-- decision, not this task's to freeze into a type now. `context_id` is
-- an optional, untyped pointer to whatever future Phase-2 content
-- triggered the flag (left nullable and uninterpreted on purpose — this
-- task has no such content to point at yet). No message text column
-- exists here, ever — that is the entire point ("category and ids ONLY,
-- never message text").
create table safeguarding_flags (
    id          uuid primary key default gen_random_uuid(),
    student_id  uuid not null references auth.users(id) on delete cascade,
    category    text not null,
    context_id  uuid,
    created_at  timestamptz not null default now()
);

create index safeguarding_flags_student_idx on safeguarding_flags (student_id);

alter table safeguarding_flags enable row level security;

-- Staff-only visibility (docs/CONSENT.md section 6): the STUDENT the
-- flag concerns is deliberately NOT granted a SELECT policy on their own
-- row here — unlike every other own-row table in this schema. A
-- distress flag is exactly the kind of record a student must not be
-- able to see was raised about them (it could tip off self-harm risk
-- mitigation, or simply be frightening with zero support attached), and
-- content reviewers get no override either — "the reviewer role governs
-- the knowledge base, never the vault" (docs/SECURITY.md, already the
-- rule for student_profiles/saved_plans; safeguarding_flags is even
-- narrower than the vault).
create policy safeguarding_flags_select_staff on safeguarding_flags for select
  using (is_safeguarding_staff());

-- No INSERT/UPDATE/DELETE policy for anyone: Phase-2's detection logic
-- (not built here) will need its own write path (a definer function, or
-- the application's own service-role-equivalent credential, which
-- bypasses RLS regardless of policy) when it exists.

-- ============================================================
-- withdraw_account() — freeze now, actual deletion is AUTH-10's job
-- ============================================================
-- docs/CONSENT.md section 4: "sets frozen, stamps deletion_due_at =
-- now() + interval '30 days', appends a withdrawal row to consents.
-- Never deletes inline." This function does exactly those three things
-- and nothing else — no row in `auth.users`, `student_accounts`,
-- `saved_plans` or anywhere else is ever deleted by CONSENT-4.
--
-- Idempotency: raises rather than silently no-op-ing on a second call —
-- "returns void" gives this function no other channel to say "nothing
-- happened" (unlike redeem_invite()'s boolean). Guarding on `account_
-- status <> 'frozen'` (rather than allowing a repeat freeze) stops a
-- second call from re-stamping `deletion_due_at` to a LATER time
-- (extending the 30-day window indefinitely by calling this twice) and
-- from inserting a second, redundant 'withdrawn' consents row.
--
-- Same shape as redeem_invite() used to have (0012's header, now fixed
-- there by `ensure_active_student_account`): if the caller has no
-- `student_accounts` row at all, there is nothing to freeze, and this
-- function raises rather than recording a 'withdrawn' consents row for
-- an account state change that never actually happened. Every adult
-- account now gets a row at sign-up/first-sign-in (0012), so this is a
-- narrower residual than before — it remains reachable only for a
-- pre-existing account from before that fix, or an account whose
-- best-effort row-creation failed and was only logged (see that
-- function's own docstring) — not solved differently here, since this
-- function's own contract (raise, don't silently no-op) is already the
-- correct behaviour for "there is nothing to withdraw."
--
-- **Named assumption:** `wording_version = 'v1'` — no consent-wording
-- registry exists yet in this codebase, so there is nothing to look this
-- value up against. Flagged for the owner the same way 0004 already
-- flags its own named assumptions (the 18-year age threshold, the
-- 72-hour token expiry).
create or replace function withdraw_account()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_updated int;
begin
  if v_uid is null then
    raise exception 'withdraw_account requires an authenticated session.';
  end if;

  update student_accounts
  set account_status = 'frozen',
      deletion_due_at = now() + interval '30 days'
  where id = v_uid and account_status <> 'frozen';

  get diagnostics v_updated = row_count;

  if v_updated = 0 then
    raise exception
      'withdraw_account: no student_accounts row to withdraw for this caller, or it is already frozen.';
  end if;

  insert into consents (student_id, kind, action, wording_version)
  values (v_uid, 'account', 'withdrawn', 'v1');
end;
$$;

-- Same REVOKE-then-GRANT reasoning as 0012's redeem_invite() — see that
-- migration's comment for the live-verified finding this fixes. BOTH
-- `public` and `anon` must be revoked from by name; either alone leaves
-- the other's grant in place.
revoke execute on function withdraw_account() from public;
revoke execute on function withdraw_account() from anon;
grant execute on function withdraw_account() to authenticated;

-- A tiny marker so tests/db/conftest.py can detect "is this migration
-- applied yet" — same pattern as 0003-0012.
create or replace function safeguarding_schema_version()
returns int language sql immutable as $$ select 13 $$;
