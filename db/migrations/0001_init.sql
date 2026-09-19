-- BCION Lite — initial schema (M1 "data foundation", tasks/BCI-002.md)
-- Source of truth for the shapes here: docs/DATA.md, docs/SECURITY.md.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Write a new numbered migration instead (docs/ARCHITECTURE.md
-- "Deployment flow"). Apply via the Supabase SQL editor or
-- `supabase db push` on your own project — not through an agent's
-- management-API access (docs/DECISIONS.md, "Infrastructure accounts").

create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- ============================================================
-- Enums
-- ============================================================

create type source_type as enum ('official', 'institution_self_declared', 'synthetic');
create type claim_status as enum ('draft', 'in_review', 'published', 'superseded');

-- ============================================================
-- Public knowledge base (docs/ARCHITECTURE.md "public knowledge zone")
-- ============================================================

create table sources (
    id              uuid primary key default gen_random_uuid(),
    authority_name  text not null,
    official_url    text not null,
    source_type     source_type not null,
    created_at      timestamptz not null default now()
);

create table careers (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    nco_anchor  text,
    created_at  timestamptz not null default now()
);

create table pathways (
    id           uuid primary key default gen_random_uuid(),
    career_id    uuid not null references careers(id) on delete cascade,
    name         text not null,
    description  text not null,
    created_at   timestamptz not null default now()
);

-- Claims: the provenance mechanism (docs/DATA.md "Claims table"). Every
-- fact-bearing field on a real entity is backed by a row here — never
-- embedded loose on the entity itself. A fact without a claim cannot be
-- published, by construction: there is nowhere else to put "published."
create table claims (
    id                      uuid primary key default gen_random_uuid(),
    entity_type             text not null,
    entity_id               uuid not null,
    field                   text not null,
    value                   jsonb,
    source_id               uuid not null references sources(id),
    verification_date       date not null,
    verifier                text not null,  -- a person's identifier — never "ai" (see extracted_by)
    status                  claim_status not null default 'draft',
    review_due_date         date not null,
    superseded_by           uuid references claims(id),
    approved_draft_version  text,
    extracted_by            text not null default 'human' check (extracted_by in ('human', 'ai')),
    created_by              uuid references auth.users(id),   -- the "maker"
    reviewed_by             uuid references auth.users(id),   -- the "checker"
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index claims_entity_idx on claims (entity_type, entity_id, field);
create index claims_status_idx on claims (status);

-- A synthetic-sourced claim must never be published — enforced in the
-- database, not only in application code (docs/DATA.md "Synthetic
-- fixtures"; CLAUDE.md non-negotiable).
create or replace function forbid_publishing_synthetic_claims()
returns trigger as $$
begin
  if new.status = 'published' then
    if exists (
      select 1 from sources s
      where s.id = new.source_id and s.source_type = 'synthetic'
    ) then
      raise exception 'A claim sourced from a synthetic Source can never be published (docs/DATA.md)';
    end if;
  end if;
  return new;
end;
$$ language plpgsql;

create trigger claims_forbid_synthetic_publish
before insert or update on claims
for each row execute function forbid_publishing_synthetic_claims();

-- ============================================================
-- Student vault (docs/DATA.md minimisation; docs/SECURITY.md)
-- ============================================================

create table student_profiles (
    id             uuid primary key references auth.users(id) on delete cascade,
    current_class  text not null,
    interests      text[] not null default '{}',
    language       text not null default 'en',
    broad_location text,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

-- ============================================================
-- Reviewers (who "is_reviewer()" for RLS purposes)
-- ============================================================

create table reviewers (
    user_id   uuid primary key references auth.users(id) on delete cascade,
    added_at  timestamptz not null default now()
);

create or replace function is_reviewer()
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from reviewers where user_id = auth.uid());
$$;

-- ============================================================
-- Row-level security
-- ============================================================
-- The application connects as a restricted role and passes the signed-in
-- user's access token on every request (docs/SECURITY.md, Lite Build Pack §4) —
-- these policies are what actually enforces access, not application code.

alter table sources           enable row level security;
alter table careers           enable row level security;
alter table pathways          enable row level security;
alter table claims            enable row level security;
alter table student_profiles  enable row level security;
alter table reviewers         enable row level security;
-- No policy is added on `reviewers` itself: nobody reads or writes it
-- directly through the API; only the `is_reviewer()` security-definer
-- function touches it. Absence of a policy with RLS enabled means "no
-- access" by default, which is the intended state here.

-- sources / careers / pathways: world-readable (guests included, per
-- docs/UI.md), reviewer-writable only.
create policy sources_select_all on sources for select using (true);
create policy sources_write_reviewers on sources for all
  using (is_reviewer()) with check (is_reviewer());

create policy careers_select_all on careers for select using (true);
create policy careers_write_reviewers on careers for all
  using (is_reviewer()) with check (is_reviewer());

create policy pathways_select_all on pathways for select using (true);
create policy pathways_write_reviewers on pathways for all
  using (is_reviewer()) with check (is_reviewer());

-- claims: published rows are world-readable; draft/in_review/superseded
-- are reviewer-only — never shown to a student as if they were facts.
create policy claims_select_published on claims for select
  using (status = 'published' or is_reviewer());

create policy claims_insert_reviewers on claims for insert
  with check (is_reviewer());

create policy claims_update_reviewers on claims for update
  using (is_reviewer()) with check (is_reviewer());
-- NOTE — M1 baseline only. This does not yet enforce "author cannot
-- approve their own claim" (maker <> checker, docs/DATA.md "Publishing
-- workflow"). That is tightened at M4 alongside the publishing console:
-- the M4 migration adds `with check (is_reviewer() and (reviewed_by is
-- distinct from created_by))` plus a trigger that freezes
-- approved_draft_version and rejects further edits without a new draft
-- cycle. Tracked so M1's RLS tests are not mistaken for M4's guarantee.

-- student_profiles: strictly own-row only — no reviewer override, no
-- cross-student access under any role.
create policy student_profiles_own_row on student_profiles for all
  using (auth.uid() = id) with check (auth.uid() = id);
