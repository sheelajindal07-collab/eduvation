-- BCION Lite — PUB-3: review/audit events, atomic publish and supersede
-- functions, saved_plans correction flag.
-- Source of truth: docs/DATA.md "Publishing workflow" item 4
-- ("corrections invalidate caches and flag any saved student plan that
-- used the old value"), docs/CONTRACTS.md "Publishing evidence in Phase
-- 1" (content_hash, approved_draft_version), CLAUDE.md's maker-checker
-- and cross-user-access non-negotiables, .claude/agents/migration-owner.md.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0017.
--
-- **Real migration number used: 0018.** Reserved by running `ls
-- db/migrations/` fresh, in this session, immediately before writing this
-- file (0017_publishing_evidence.sql, PUB-2, was the highest number on
-- `main`) — this card's own text guessed "0005", already stale by twelve
-- migrations before this session started, exactly the "planning
-- estimate, not a reservation" .claude/agents/migration-owner.md warns
-- about. Also confirmed via `git worktree list` plus a diff of every
-- worktree's own `db/migrations/` against `main`: every worktree still on
-- disk is either already merged (a zero/near-zero diff) or strictly
-- BEHIND `main`, so no other session holds an uncommitted migration above
-- 0017 — no other migration is open.
--
-- **A real, disclosed correction to this card's own assumption**: the
-- card describes docs/CONTRACTS.md's "Entity vocabulary" as lower-case
-- (`career`, `pathway`, ...). Read directly against the LIVE application
-- code before writing `supersede_claim()`'s own plan-flagging logic
-- below (app/ai/retrieval.py's `ENTITY_TYPE_PATHWAY = "Pathway"`,
-- app/planning/coverage.py's `_PATHWAY_ENTITY_TYPE = "Pathway"`, and
-- every `.eq("entity_type", "Pathway")` call across app/api and
-- app/web — a dozen-plus call sites, all Title-case, none lower-case)
-- shows the REAL, load-bearing, already-shipped convention is Title-case
-- (`"Pathway"`, `"Career"`) — docs/CONTRACTS.md's own text is stale on
-- this one point. Matching the doc instead of the live code would make
-- `supersede_claim()`'s own flagging mechanism a silent, permanent no-op
-- against every real row the running application ever writes. Matched to
-- the real code here; the doc/code mismatch itself is flagged in this
-- session's completion report for the lead, not silently "fixed" one way
-- or the other by this card.

-- ============================================================
-- 1. review_events / audit_events — insert-only, reviewer-readable,
--    never updatable or deletable by any role.
-- ============================================================
-- Deliberately modelled on `reviewers` (0001_init.sql), not on
-- `source_versions` (0017): RLS enabled, with a SELECT policy for
-- `is_reviewer()` but NO insert/update/delete policy AT ALL, for anyone,
-- including a reviewer. The only legitimate writer of either table is
-- `publish_claim()`/`supersede_claim()` below, which write it as a
-- necessary SIDE EFFECT of a real, already-authorised action they
-- performed — never a value a reviewer's own direct request chooses to
-- write. Making these tables genuinely insert-only (not just
-- update/delete-only) is what makes them trustworthy as a record of what
-- actually happened, rather than a shape a reviewer's own client could
-- forge or backdate.
create table review_events (
    id          uuid primary key default gen_random_uuid(),
    claim_id    uuid not null references claims(id) on delete cascade,
    actor_id    uuid not null references auth.users(id),
    action      text not null,  -- free-form, same reasoning as source_versions.status (0017): no
                                 -- fixed vocabulary is owned by this migration alone; 'published'
                                 -- and 'publish_conflict' are what THIS migration's own functions
                                 -- emit, not an exhaustive closed set for all future review actions.
    detail      jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index review_events_claim_idx on review_events (claim_id);

alter table review_events enable row level security;

create policy review_events_select_reviewers on review_events for select
  using (is_reviewer());
-- No insert/update/delete policy — see the header comment above. With
-- RLS enabled and zero applicable policies, Postgres denies every row for
-- every command: INSERT gets an outright WITH CHECK violation (ERROR,
-- same shape as `reviewers`' own INSERT cell), UPDATE/DELETE are
-- filtered to zero matching rows (EMPTY) for anyone `authenticated`,
-- reviewer included. `publish_claim()` below still writes real rows here
-- because it runs SECURITY DEFINER, owned by the same role that owns
-- this table — an owner bypasses RLS entirely, the exact mechanism
-- `is_critical_authorised_reviewer()` (0017) already uses to read
-- `reviewers`.

revoke all on table review_events from anon;
-- NOT `source_versions`' (0017) narrower revoke (write privileges only,
-- SELECT left alone) — that table is world-readable by design.
-- review_events is not: a guest has no legitimate reason to read it
-- either, exactly like `student_profiles`/`saved_plans`/`reviewers`
-- (0016_grants_hardening.sql's own "anon has no legitimate reason to
-- touch these AT ALL, not even a read RLS then quietly denies").
-- `authenticated` IS deliberately left alone: the real SELECT policy
-- above (`is_reviewer()`) is what is supposed to filter a signed-in
-- non-reviewer's read, and there is no insert/update/delete policy at
-- all for that role to hide behind either.

create table audit_events (
    id           uuid primary key default gen_random_uuid(),
    actor_id     uuid not null references auth.users(id),
    action       text not null,      -- see review_events.action's comment — same reasoning
    entity_type  text not null,      -- free text, same shape as claims.entity_type (0001):
                                      -- no FK, no CHECK — the closed vocabulary is an app-layer
                                      -- contract (docs/CONTRACTS.md "Entity vocabulary"), not a
                                      -- DB constraint, matching the table it is auditing.
    entity_id    uuid not null,
    detail       jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

create index audit_events_entity_idx on audit_events (entity_type, entity_id);

alter table audit_events enable row level security;

create policy audit_events_select_reviewers on audit_events for select
  using (is_reviewer());
-- Same "no insert/update/delete policy at all" shape as review_events
-- above, same reasoning.

revoke all on table audit_events from anon;
-- Same reasoning as review_events' own `revoke all` line above.

-- ============================================================
-- 2. saved_plans — the correction-flag columns
-- ============================================================
-- Additive columns only; no RLS change. The existing own-row policies
-- (0002_saved_plans.sql, tightened by 0012_admission_axis.sql) already
-- govern every column on this row, these three included — a student
-- reads/writes their own plan's flag exactly as they already read/write
-- its other columns, and student B / a reviewer are exactly as excluded
-- from these three columns as they already are from every other one.
-- `supersede_claim()` below writes them anyway, from OUTSIDE that RLS
-- (SECURITY DEFINER, owner-bypass) — see that function's own header for
-- why, and for the explicit column-list discipline that keeps it from
-- becoming a wider hole than that one, narrow, necessary crossing.
alter table saved_plans
  add column needs_review     boolean not null default false,
  add column flagged_at       timestamptz,
  add column flagged_reason   text;
-- `flagged_reason` is deliberately a short, stable machine code (e.g.
-- 'claim_superseded'), never a formatted sentence — docs/CONTRACTS.md's
-- own "Three eligibility outcomes" section already settles this pattern
-- for this codebase ("Reasons are machine codes ... resolved to English
-- or Hindi at the presentation layer; the engine never returns display
-- text") and there is no reason a correction-flag reason should be the
-- one place that differs. No presentation layer reads this column yet
-- (out of scope for this migration) — whoever builds the My-Plan
-- notification this unblocks should keep that convention.

-- ============================================================
-- 3. publish_claim(claim_id, expected_hash) — the stale-hash guard
-- ============================================================
-- SECURITY DEFINER, and here is exactly what that buys and what it
-- costs (.claude/agents/migration-owner.md "Definer functions"):
--
-- WHAT AN ORDINARY RLS-SCOPED REVIEWER COULD NOT DO WITHOUT THIS: insert
-- into `review_events` at all — that table has no insert policy for any
-- role (see above), by design, so a reviewer's own direct request could
-- never write a trustworthy log entry, only this function (running as
-- the table owner, bypassing RLS) can. That is the one, narrow reason
-- this needs elevated rights; it does not need them to update `claims`
-- itself (`claims_update_reviewers` already permits a reviewer's own
-- UPDATE there) — and BECAUSE it is SECURITY DEFINER, that policy's own
-- `using (is_reviewer())` gate is *also* bypassed by ownership the moment
-- this function touches `claims`, so the function body re-checks
-- `is_reviewer()` itself, explicitly, before doing anything — the same
-- re-check .claude/agents/migration-owner.md's reviewer is told to look
-- for.
--
-- THE RACE THIS GUARDS: `content_hash` (0017) does NOT change when a
-- claim's status moves from in_review to published — only a CONTENT edit
-- changes it. So the guard against two callers publishing the SAME claim
-- at once is NOT the hash (both legitimately hold the same, correct
-- hash) — it is `status = 'in_review'`, re-checked under a `select ...
-- for update` row lock, the same "lock the one row, recheck under the
-- lock" pattern `ai_reserve` (0011) already uses for its own cap check.
-- The hash guard is the SEPARATE, real "lost update" case this card also
-- names: the row was edited (which reverts it to draft and changes its
-- hash — 0017's own `enforce_claims_workflow`) after the caller loaded
-- it but before they called this.
--
-- THE TWO DIFFERENT OUTCOMES, ON PURPOSE: a genuine hash mismatch RAISES
-- (a single, deterministic caller error — there is only ever one such
-- caller, so nothing needs to survive a rollback). A STATUS conflict
-- (the row is no longer in_review — most often because a concurrent
-- caller already won the race) returns NULL and records a
-- 'publish_conflict' review_event INSTEAD of raising — Postgres has no
-- autonomous sub-transaction here: an INSERT followed by a RAISE in the
-- same statement would roll the INSERT back right along with everything
-- else the instant the RAISE propagates, which would make "yield exactly
-- one publish and one real audit/review row recording the conflict" (this
-- card's own acceptance line) impossible to satisfy for the losing
-- caller. Returning normally, with a persisted conflict row, is what
-- actually lets that row survive.
create or replace function publish_claim(p_claim_id uuid, p_expected_hash text)
returns claims
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row   claims;
  v_actor uuid := auth.uid();
begin
  if v_actor is null or not is_reviewer() then
    raise exception 'publish_claim: only an authenticated reviewer may publish a claim'
      using errcode = 'BCPB1';
  end if;

  select * into v_row from claims where id = p_claim_id for update;
  if not found then
    raise exception 'publish_claim: claim % does not exist', p_claim_id
      using errcode = 'BCPB2';
  end if;

  if v_row.status <> 'in_review' then
    -- Not (or no longer) awaiting review — most often another reviewer's
    -- concurrent publish_claim() call already won; could also be a
    -- caller error (never submitted, already superseded). Either way:
    -- record it, do not raise (see header), do not touch the row.
    insert into review_events (claim_id, actor_id, action, detail)
    values (
      p_claim_id, v_actor, 'publish_conflict',
      jsonb_build_object(
        'reason', 'not_in_review',
        'current_status', v_row.status,
        'expected_hash', p_expected_hash
      )
    );
    return null;
  end if;

  if v_row.content_hash <> p_expected_hash then
    raise exception
      'publish_claim: claim % has changed since it was loaded (content_hash mismatch) — reload and re-review before publishing',
      p_claim_id
      using errcode = 'BCPB3';
  end if;

  -- The actual publish. `enforce_claims_workflow()` (0017) still fires on
  -- this UPDATE exactly as it would for a reviewer's own direct request
  -- (triggers are not bypassed by SECURITY DEFINER, only RLS is) — it
  -- forces reviewed_by = auth.uid(), rejects self-approval, and enforces
  -- the critical-tier gate, all for free, from the SAME single mechanism
  -- every other publish path already goes through.
  update claims set status = 'published' where id = p_claim_id returning * into v_row;

  insert into review_events (claim_id, actor_id, action, detail)
  values (p_claim_id, v_actor, 'published', jsonb_build_object('content_hash', v_row.content_hash));

  return v_row;
end;
$$;

revoke execute on function publish_claim(uuid, text) from public;
revoke execute on function publish_claim(uuid, text) from anon;
grant execute on function publish_claim(uuid, text) to authenticated;

-- ============================================================
-- 4. supersede_claim(old_id, new_id) — the correction, atomically
-- ============================================================
-- SECURITY DEFINER, and here is exactly what that buys and what it
-- costs (.claude/agents/migration-owner.md "Definer functions"):
--
-- WHAT AN ORDINARY RLS-SCOPED REVIEWER COULD NOT DO WITHOUT THIS: write
-- to `saved_plans` AT ALL, for a student who is not themselves — that
-- table's own policies (0002/0012) are strictly own-row, "no reviewer
-- override, no cross-student access under any role" by explicit design
-- (0002's own comment). A correction to a published fact must be able to
-- flag EVERY affected student's plan, and there is no per-student
-- session available from a reviewer's own correction workflow to do that
-- from — only a narrowly-scoped, elevated function can cross that
-- boundary at all. This is the exact crossing this card names as its own
-- risk ("security definer functions cross into the student vault").
--
-- WHAT KEEPS THE CROSSING NARROW: (1) `is_reviewer()`/`auth.uid()` are
-- re-checked explicitly in the function body, for the same reason
-- `publish_claim()` above re-checks them — SECURITY DEFINER bypasses the
-- `claims_update_reviewers` RLS policy that would otherwise gate the
-- `claims` UPDATE below, so the function must replicate that gate itself.
-- (2) The `saved_plans` UPDATE below names an explicit column list —
-- `needs_review`, `flagged_at`, `flagged_reason` and nothing else — never
-- a `select *`/`update ... set row = ...` shape that could smuggle a
-- wider write through later without an obviously-visible diff. (3) The
-- return value is `plans_flagged` — an integer COUNT — never the flagged
-- rows themselves, so this function cannot become a channel for reading
-- one student's plan content back through a reviewer's own session; a
-- reviewer already cannot see whose plans were affected, only how many.
create or replace function supersede_claim(p_old_id uuid, p_new_id uuid)
returns table (old_claim_id uuid, new_claim_id uuid, plans_flagged integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_actor       uuid := auth.uid();
  v_old         claims;
  v_new         claims;
  v_pathway_ids uuid[];
  v_count       integer := 0;
begin
  if v_actor is null or not is_reviewer() then
    raise exception 'supersede_claim: only an authenticated reviewer may supersede a claim'
      using errcode = 'BCPB4';
  end if;

  if p_old_id = p_new_id then
    raise exception 'supersede_claim: a claim cannot supersede itself' using errcode = 'BCPB5';
  end if;

  -- Deterministic lock order (lowest id first), not call-argument order:
  -- avoids a deadlock if two concurrent supersede_claim calls ever name
  -- the same two claims in opposite order. Neither row's content is
  -- changed by this function except old's status/superseded_by, so
  -- holding both locks for the duration is cheap and safe.
  if p_old_id < p_new_id then
    select * into v_old from claims where id = p_old_id for update;
    select * into v_new from claims where id = p_new_id for update;
  else
    select * into v_new from claims where id = p_new_id for update;
    select * into v_old from claims where id = p_old_id for update;
  end if;

  if v_old.id is null then
    raise exception 'supersede_claim: claim % (old_id) does not exist', p_old_id
      using errcode = 'BCPB6';
  end if;
  if v_new.id is null then
    raise exception 'supersede_claim: claim % (new_id) does not exist', p_new_id
      using errcode = 'BCPB6';
  end if;

  if v_old.status <> 'published' then
    raise exception
      'supersede_claim: claim % is not published (status=%) — only a published claim can be superseded',
      p_old_id, v_old.status
      using errcode = 'BCPB7';
  end if;

  if v_new.status <> 'published' then
    raise exception
      'supersede_claim: replacement claim % must already be published (status=%), never a draft or in-review claim',
      p_new_id, v_new.status
      using errcode = 'BCPB8';
  end if;

  if v_new.entity_type is distinct from v_old.entity_type
     or v_new.entity_id is distinct from v_old.entity_id
     or v_new.field is distinct from v_old.field
  then
    raise exception
      'supersede_claim: replacement claim % is not the same fact as claim % (%.%.%) — entity_type/entity_id/field must match exactly, never a different fact',
      p_new_id, p_old_id, v_old.entity_type, v_old.field, v_old.entity_id
      using errcode = 'BCPB9';
  end if;

  if (v_old.tier = 'critical' or v_new.tier = 'critical') and not is_critical_authorised_reviewer() then
    raise exception
      'supersede_claim: this correction touches a tier=critical claim; only a critical_authorised reviewer may supersede it (docs/DATA.md "Freshness tiers")'
      using errcode = 'BCPBA';
  end if;

  -- The correction itself. enforce_claims_workflow() (0017) still fires
  -- here too: old.status='published' -> new.status='superseded' with no
  -- other content column touched is exactly the one legal move that
  -- trigger already allows for a published claim.
  update claims set status = 'superseded', superseded_by = p_new_id where id = p_old_id;

  -- Which saved_plans rows are traceably affected: the real, live
  -- entity_type convention (Title case — see this file's own header) has
  -- a direct answer for the two entity types a saved plan can actually be
  -- downstream of. Anything else (exam, institution, programme, ...) has
  -- no FK path from saved_plans today, so this is a deliberate, minimal,
  -- no-op for those — not a silent gap this migration is pretending to
  -- close.
  if v_old.entity_type = 'Pathway' then
    v_pathway_ids := array[v_old.entity_id];
  elsif v_old.entity_type = 'Career' then
    select coalesce(array_agg(id), array[]::uuid[]) into v_pathway_ids
      from pathways where career_id = v_old.entity_id;
  else
    v_pathway_ids := array[]::uuid[];
  end if;

  if array_length(v_pathway_ids, 1) > 0 then
    -- Named risk (data-security-reviewer, this card): write ONLY the
    -- flag columns, across every affected student's row, never read or
    -- return any other column. `saved_plans_touch_updated_at` (0002)
    -- still fires on this UPDATE like it would on any other — that is
    -- the same pre-existing, unrelated bookkeeping trigger every write to
    -- this table already carries, not a second mechanism this function
    -- introduces.
    update saved_plans
       set needs_review   = true,
           flagged_at     = now(),
           flagged_reason = 'claim_superseded'
     where pathway_id = any (v_pathway_ids);
    get diagnostics v_count = row_count;
  end if;

  insert into audit_events (actor_id, action, entity_type, entity_id, detail)
  values (
    v_actor, 'claim_superseded', 'claim', p_old_id,
    jsonb_build_object('superseded_by', p_new_id, 'plans_flagged', v_count)
  );

  return query select p_old_id, p_new_id, v_count;
end;
$$;

revoke execute on function supersede_claim(uuid, uuid) from public;
revoke execute on function supersede_claim(uuid, uuid) from anon;
grant execute on function supersede_claim(uuid, uuid) to authenticated;

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as every migration since 0003.
create or replace function publish_functions_schema_version()
returns int language sql immutable as $$ select 18 $$;
