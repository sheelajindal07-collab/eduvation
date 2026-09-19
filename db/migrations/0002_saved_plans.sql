-- BCION Lite — saved plans (M3, tasks/BCI-004.md)
-- Source of truth for the shape here: Lite Build Pack §6 ("Student
-- work: saved_plans, plan_versions, reminders"), docs/UI.md ("My Plan:
-- current decision, next three actions, saved alternatives").
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via the SQL Editor or scripts/apply_migrations.py (see
-- db/migrations/README.md) -- same as 0001_init.sql.

-- ============================================================
-- Saved plans
-- ============================================================
-- One row per (student, pathway) the student has chosen to save. Full
-- version history (plan_versions) is deliberately deferred to a later
-- task -- this is the first slice (tasks/BCI-004.md); `updated_at`
-- tracks the last edit for now, not a full audit trail.

create table saved_plans (
    id                              uuid primary key default gen_random_uuid(),
    student_id                     uuid not null references auth.users(id) on delete cascade,
    pathway_id                     uuid not null references pathways(id) on delete cascade,
    -- The same per-request assumption GET /compare already accepts
    -- (app/api/compare.py's estimated_additional_expenses override),
    -- now persisted per saved plan instead of per-request only.
    estimated_additional_expenses  numeric,
    notes                          text,
    created_at                     timestamptz not null default now(),
    updated_at                     timestamptz not null default now(),
    unique (student_id, pathway_id)
);

create index saved_plans_student_idx on saved_plans (student_id);

-- Keep updated_at honest without relying on every caller to set it.
create or replace function touch_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger saved_plans_touch_updated_at
before update on saved_plans
for each row execute function touch_updated_at();

-- ============================================================
-- Row-level security
-- ============================================================
-- Strictly own-row, identical pattern to student_profiles
-- (0001_init.sql) -- no reviewer override, no cross-student access
-- under any role. A saved plan is exactly as sensitive as the profile
-- it's attached to.

alter table saved_plans enable row level security;

create policy saved_plans_own_row on saved_plans for all
  using (auth.uid() = student_id) with check (auth.uid() = student_id);
