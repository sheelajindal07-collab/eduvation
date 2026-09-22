-- BCION Lite — bind the ACCOUNT identity of ai_reserve/ai_budget_remaining
-- to the caller's own session (BCI-024, AI-4 security follow-up)
--
-- Source: tasks/BCI-024.md — a finding verified by the lead directly
-- against ALREADY-MERGED db/migrations/0011_ai_usage.sql (AI-4). NOT an
-- AI-4 regression; a gap in the original design of that file.
--
-- Append-only, exactly like every other file here: this is a new,
-- additive `create or replace function` migration on the same two
-- function signatures, never an edit to 0011_ai_usage.sql itself. Same
-- shape as 0014_account_active_grant_fix.sql, which closed the same
-- oracle CLASS on `account_active()` a few hours earlier — read that
-- file's header for the house style this one follows.
--
-- **Real number check (migration-owner rule).** The card reserves 0015
-- and says to re-verify anyway. `ls db/migrations/` in this session
-- (2026-09-22, this worktree) shows 0001-0014 and nothing above it, and
-- no other open branch carries a db/migrations/ change, so 0015 is
-- genuinely the next free number and is what this file uses.
--
-- ============================================================
-- The finding
-- ============================================================
-- `ai_reserve(p_identity_kind, p_identity_hash, p_template_id, p_calls)`
-- and `ai_budget_remaining(p_identity_kind, p_identity_hash)` are both
-- SECURITY DEFINER, both `grant execute ... to anon, authenticated`, and
-- both took `p_identity_hash` as a plain caller-supplied argument with no
-- check that it belongs to the calling session. `ai_identity_hash(text)`
-- (also anon-granted, by design) is a pure, unpeppered sha256 of whatever
-- text it is handed — deterministic, no secret involved.
--
-- For `identity_kind = 'guest'` that is fine BY DESIGN, and stays
-- unchanged below: a guest's identity is the opaque, server-generated
-- session token `app/web/guest_session.py`'s `create_guest_session()`
-- mints into an httponly cookie. Possessing that token IS the credential,
-- so anyone able to compute its hash already had to hold the token, and a
-- guest has no `auth.uid()` to bind to instead. 0011's own reasoning —
-- "a guest is not a database principal" — is still the right answer.
--
-- For `identity_kind = 'account'` it was a real, reproduced exposure.
-- `app/ai/budget_db.py`'s `for_account()` docstring says it plainly: the
-- identity is the account's Supabase Auth user id, "the same value
-- `auth.uid()` returns". That uid is NOT a secret — it is a UUID that
-- appears in ordinary API responses to its owner, not a bearer token. So
-- any caller holding only the public anon key could:
--
--     select ai_identity_hash('<a known or guessed account uuid>');
--     select ai_budget_remaining('account', '<that hash>');   -- a stranger's headroom
--     select ai_reserve('account', '<that hash>', 't', 1);    -- burn a stranger's daily cap
--
-- — the first a cross-user information leak, the second a cross-user
-- denial of service against the per-identity daily cap. Live-reproduced:
-- `ai_budget_remaining` returned a real number for an arbitrary uid with
-- no session at all.
--
-- `ai_settle` is deliberately NOT part of this fix and is not touched.
-- It takes an opaque reservation uuid the caller must already hold — a
-- different, already-documented, already-accepted residual risk class
-- (0011's own "KNOWN RESIDUAL RISK" note; docs/DECISIONS.md 2026-09-22),
-- not this one. Widening this migration to cover it would be a redesign,
-- not a fix.
--
-- Practical exposure today is nil (`AI_ENABLED` is false everywhere and
-- no real usage rows exist), which is exactly why this could be closed
-- calmly and additively — but it had to close before AI-12 ever flips
-- that flag on staging.
--
-- ============================================================
-- The fix
-- ============================================================
-- For `identity_kind = 'account'`, the identity hash is now DERIVED, not
-- accepted: whatever the caller sent in `p_identity_hash` is ignored as
-- an identity and `ai_identity_hash(auth.uid()::text)` is used instead.
-- There is no argument a caller can pass that makes either function
-- answer for, or spend against, an account other than the one whose JWT
-- is on the connection. That is the same conclusion 0011's own
-- `ai_usage_select_own` RLS policy already reached for SELECT ("A client
-- never supplies `identity_hash` to a select — if it did, the hash would
-- be a bearer credential"); these two functions simply never had it
-- applied to them.
--
-- A null `auth.uid()` with `identity_kind = 'account'` — a genuinely
-- session-less caller claiming to be an account — raises BCAI3, the
-- malformed-call SQLSTATE both functions already use for every other
-- argument-validation failure. This is deliberately NOT a new error
-- class: an anonymous caller has no account identity to bind to at all,
-- so the call is malformed in exactly the sense BCAI3 already means, and
-- `app/ai/budget_db.py`'s `_translate()` already maps BCAI3 onto
-- `AIUsageError` ("the reservation protocol was used incorrectly"),
-- never onto `AIBudgetExceededError`. Reporting it as a cap instead
-- would turn a bug into a silent, permanent AI outage — the exact
-- confusion 0011's own BCAI1/BCAI3 split exists to prevent.
--
-- **The `p_identity_hash` SHAPE check is kept for both kinds, on
-- purpose.** For the account path the value is no longer trusted as an
-- identity, so the check is no longer load-bearing for access control —
-- but 0011's header calls it out as a deliberate property ("`ai_reserve`
-- REFUSES anything that is not a 64-character hex digest, so 'we forgot
-- to hash it' fails loudly at the door instead of being discovered later
-- in a backup"), and a caller that sends a RAW account uuid is a bug
-- worth failing loudly on whether or not the server would have ignored
-- the value anyway. Keeping it also means this migration changes nothing
-- about how a malformed call is reported. Every real caller
-- (`app/ai/budget_db.py`) always sends a proper digest, so no legitimate
-- call shape is affected.
--
-- **No grant changes, unlike 0014.** 0014 could revoke `anon` outright
-- because `account_active()` has no legitimate anonymous caller. These
-- two functions DO have one: a guest is an anon-key caller, and the
-- guest path is the reason this pair is anon-granted at all. So `anon`
-- keeps `execute` here, and the binding above is what makes that safe —
-- an anon caller may still reserve and query a GUEST budget it holds the
-- token for, and can no longer touch an ACCOUNT budget at all. The card
-- scopes this narrowly on purpose: no grant, table, policy or other
-- function is touched.
--
-- **Client compatibility: none required.** `app/ai/budget_db.py` already
-- sends `identity_digest(account_id)` for the account case, which for a
-- caller signed in AS that account is byte-identical to what the server
-- now derives — the server simply stops taking the client's word for it.
-- The one behaviour that does change is a session-less caller asking for
-- an ACCOUNT budget (an anon PostgREST client with no JWT), which now
-- raises BCAI3 instead of silently answering. That is the vulnerability,
-- not a feature: see this migration's companion test file
-- `tests/db/test_ai_identity_binding.py`, and the note in BCI-024's
-- completion report about the two pre-existing tests in
-- tests/db/test_ai_usage.py that rely on it.
--
-- ============================================================
-- SECURITY DEFINER, restated for this file (migration-owner rule)
-- ============================================================
-- Both functions stay SECURITY DEFINER with `search_path` pinned
-- explicitly to `public` — never the caller's, never the database
-- default. An unpinned definer function is a privilege-escalation
-- primitive: the caller would choose which schema's `ai_usage` and
-- `ai_identity_hash` it resolves to. `auth.uid()` is schema-qualified
-- for the same reason, and works normally inside a definer function
-- (SECURITY DEFINER changes the executing ROLE, not the session GUCs
-- PostgREST sets the JWT claims in — the same thing 0014's
-- `account_active()` relies on).
--
-- What they can do that an ordinary RLS-scoped caller cannot, and why it
-- is necessary — unchanged from 0011, restated so this file stands alone:
--   * `ai_reserve` INSERTs into `ai_usage`, which no API role holds any
--     write grant on. That is the point: a reservation must be
--     unforgeable and must be written by the same transaction that
--     checked the caps, so the caps cannot be raced.
--   * both READ `ai_usage_caps` (revoked from every API role — it is the
--     spend kill switch) and aggregate across EVERY identity's rows. Two
--     of the three caps are installation-wide and cannot be computed
--     from inside one caller's own RLS slice; widening the SELECT policy
--     so they could would hand every student a view of everyone else's
--     usage.
-- Neither returns row content — one uuid, one integer — so neither is a
-- read channel for anything else in the table. After this migration
-- neither can be aimed at another account at all.
--
-- The `-- BEGIN/END` sentinels around each function are load-bearing for
-- the revert-to-prove drill (.claude/agents/migration-owner.md), exactly
-- as in 0011: they let the weakened-then-restored version of one function
-- be re-applied from this file verbatim without re-running the whole
-- migration. THIS file's copies supersede 0011's for that drill — 0011's
-- are the pre-fix bodies.

-- ============================================================
-- ai_reserve — identity bound for accounts, unchanged for guests
-- ============================================================
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
  v_identity_hash  text;
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

  -- ==========================================================
  -- 0015: the identity binding. Everything below this block uses
  -- v_identity_hash and never p_identity_hash again.
  -- ==========================================================
  if p_identity_kind = 'account' then
    if auth.uid() is null then
      raise exception
        'ai_reserve: identity_kind ''account'' requires a signed-in caller; this session has no auth.uid() to bind the identity to'
        using errcode = 'BCAI3';
    end if;
    -- The caller's p_identity_hash is IGNORED here, deliberately: an
    -- account id is not a secret, so accepting a hash of one would make
    -- that hash a bearer credential for someone else's budget.
    v_identity_hash := ai_identity_hash(auth.uid()::text);
  else
    -- Guest: the token the hash was derived from IS the credential, and
    -- there is no auth.uid() for a guest session to bind to instead.
    v_identity_hash := p_identity_hash;
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
     and u.identity_hash = v_identity_hash
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
  values (p_identity_kind, v_identity_hash, p_template_id, p_calls, 'reserved')
  returning id into v_usage_id;

  return v_usage_id;
end;
$$;
-- END ai_reserve

-- ============================================================
-- ai_budget_remaining — same binding, same reasoning
-- ============================================================
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
  v_identity_hash  text;
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

  -- 0015: identity binding, identical to ai_reserve's above. A read is
  -- just as much of an oracle as a write here — "how much has this
  -- account got left today" is precisely the fact that must not be
  -- readable for a stranger's uid.
  if p_identity_kind = 'account' then
    if auth.uid() is null then
      raise exception
        'ai_budget_remaining: identity_kind ''account'' requires a signed-in caller; this session has no auth.uid() to bind the identity to'
        using errcode = 'BCAI3';
    end if;
    v_identity_hash := ai_identity_hash(auth.uid()::text);
  else
    v_identity_hash := p_identity_hash;
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
     and u.identity_hash = v_identity_hash
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

-- `create or replace function` preserves existing privileges, so 0011's
-- `grant execute ... to anon, authenticated` on both functions still
-- stands and is deliberately NOT restated or changed — see the "No grant
-- changes, unlike 0014" note in this file's header for why `anon` must
-- keep execute on this pair.

-- A marker so tests/db/test_ai_identity_binding.py can detect "is this
-- migration applied yet" — same pattern as 0003-0014. It lives in this
-- file (rather than as a new check in tests/db/conftest.py) because
-- BCI-024 owns only this migration and its own test file; that test file
-- gates itself on this function.
create or replace function ai_identity_binding_schema_version()
returns int language sql immutable as $$ select 15 $$;
