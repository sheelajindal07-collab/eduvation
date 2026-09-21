-- BCION Lite — current decision + next actions (AUTH-5)
-- Source of truth: docs/UI.md "My Plan: current decision, next three
-- actions, saved alternatives"; Lite Build Pack §6.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0009.
--
-- **Real number check (migration-owner rule):** the card names
-- "provisional 0005". `ls db/migrations/` at the moment this was written
-- shows 0001-0009, so the next genuinely free number is 0010.

-- ============================================================
-- saved_plans.is_current — exactly one current decision per student
-- ============================================================
-- docs/UI.md's My Plan screen has ONE "current decision" and a list of
-- saved alternatives. Two rows flagged current is not a cosmetic
-- problem: the screen would have to pick one arbitrarily, and a student
-- would see a different answer to "what did I decide?" depending on row
-- order.
--
-- Default false, so every row that exists when this runs is an
-- alternative and nobody's decision is invented for them.
alter table saved_plans
  add column is_current boolean not null default false;

-- PARTIAL unique index: unique across `student_id` only among rows where
-- `is_current` is true. A plain `unique (student_id, is_current)` would
-- be wrong in the other direction — it would also allow only ONE
-- non-current plan per student, i.e. no saved alternatives at all, which
-- is most of what the screen is for.
--
-- Note what this does NOT do: it does not clear a student's previous
-- current plan for them. Switching is two statements (clear, then set),
-- which app/api/plans.py does in that order; the index is what makes a
-- half-finished switch fail loudly instead of leaving two.
create unique index saved_plans_one_current_per_student
  on saved_plans (student_id)
  where is_current;

-- ============================================================
-- plan_actions — the "next three actions" checklist
-- ============================================================
-- `action_key` is a MACHINE KEY (`check_entry_requirements`, ...), never
-- display text — docs/CONTRACTS.md's rule for reasons applies here for
-- the same reason: the English and the Hindi are the presentation
-- layer's business, and a stored sentence cannot be re-translated.
--
-- Which actions exist at all is decided in ordinary code
-- (app/planning/actions.py) from PUBLISHED claims, never stored here as
-- content. This table records only whether a student has ticked one off.
create table plan_actions (
    id          uuid primary key default gen_random_uuid(),
    plan_id     uuid not null references saved_plans(id) on delete cascade,
    action_key  text not null,
    done        boolean not null default false,
    -- Server-owned: set, cleared and preserved by the trigger below, so
    -- a client cannot claim to have done something last week.
    done_at     timestamptz,
    created_at  timestamptz not null default now(),
    -- Ticking the same action twice is an update, not a second row.
    unique (plan_id, action_key)
);

create index plan_actions_plan_idx on plan_actions (plan_id);

-- `done_at` is derived from `done`, never accepted from a caller.
--
-- Without this the column is just a timestamp a client sends, which
-- makes it useless as a record of anything. The three cases are
-- deliberate: newly done -> now(); already done and staying done ->
-- keep the ORIGINAL time (re-ticking must not silently reset it, and a
-- client must not be able to rewrite it); not done -> null, so an
-- un-ticked action never carries a completion time.
create or replace function set_plan_action_done_at()
returns trigger as $$
begin
  if new.done then
    if TG_OP = 'UPDATE' and old.done then
      new.done_at := old.done_at;
    else
      new.done_at := now();
    end if;
  else
    new.done_at := null;
  end if;
  return new;
end;
$$ language plpgsql security invoker set search_path = public;

create trigger plan_actions_set_done_at
before insert or update on plan_actions
for each row execute function set_plan_action_done_at();

-- ============================================================
-- Row-level security — own row, via the parent plan
-- ============================================================
-- `plan_actions` has no `student_id` of its own: ownership is a property
-- of the plan it hangs off. Duplicating `student_id` onto this table
-- would create a second copy of the same fact that could drift out of
-- step with the first, and then two different answers to "whose is
-- this?".
--
-- Both `p.student_id = auth.uid()` AND `account_active(auth.uid())` are
-- stated explicitly rather than left to the parent's own policy. A
-- subquery inside a policy does apply the referenced table's RLS, so
-- saved_plans_own_row (0004) would cover both transitively — but
-- "covered transitively by another migration's policy" is not something
-- a reader of this file can verify, and it would silently stop being
-- true if that policy were ever restructured. Stated here, this policy
-- is correct on its own terms.
--
-- `account_active` specifically matters: without it, a pending minor's
-- account — gated out of `saved_plans` and `student_profiles` by 0004 —
-- would have an unguarded side door into data hanging off their own
-- plan. That is exactly the gap 0004's own design note describes
-- closing for those two tables, applied to the new one rather than
-- forgotten for it.
alter table plan_actions enable row level security;

create policy plan_actions_own_row on plan_actions for all
  using (
    exists (
      select 1
      from saved_plans p
      where p.id = plan_actions.plan_id
        and p.student_id = auth.uid()
        and account_active(auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from saved_plans p
      where p.id = plan_actions.plan_id
        and p.student_id = auth.uid()
        and account_active(auth.uid())
    )
  );

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as 0003-0009.
create or replace function plan_actions_schema_version()
returns int language sql immutable as $$ select 10 $$;
