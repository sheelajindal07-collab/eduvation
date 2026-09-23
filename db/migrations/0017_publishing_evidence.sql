-- BCION Lite — PUB-2: identity enforcement, approval binding, source
-- versions, claim columns, tier + critical-authorised, first storage
-- bucket.
-- Source of truth: docs/CONTRACTS.md "Publishing evidence in Phase 1"
-- (the frozen content_hash field list, source_version, fast
-- re-approval), docs/DATA.md "Claims table" / "Publishing workflow" /
-- "Freshness tiers", CLAUDE.md's maker-checker and source non-negotiables,
-- .claude/agents/migration-owner.md.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0016.
--
-- **Real migration number used: 0017.** Reserved by running `ls
-- db/migrations/` fresh, in this session, immediately before writing this
-- file, and separately confirming (`git worktree list` + a scan of every
-- worktree's own `db/migrations/`) that no other worktree holds an
-- uncommitted migration above 0016 — the task card's own text named
-- "0011" only as a stale planning guess and explicitly said to confirm
-- fresh rather than trust it; 0001-0016 already existed on `main`
-- (0011 AI-4, 0012/0013 CONSENT-4, 0014 the account_active grant fix,
-- 0015 the AI identity-hash binding fix, 0016 SEC-6's grants hardening),
-- so 0017 is the next free number.
--
-- Dependency note: this migration references no CONSENT-4 object
-- (docs/DEVELOPMENT-PLAN.md's own ordering note for PUB-2) — confirmed by
-- writing it and finding that true, not assumed in advance.

-- ============================================================
-- 1. source_versions — insert-only history (docs/CONTRACTS.md
--    "Settled — source_version without PUB-6")
-- ============================================================
-- "In Phase 1 the importer creates one row per (source, checked-on date)
-- straight from the sources register CSV; there is no fetcher and no
-- stored document. A source_version is immutable once a claim references
-- it." Made unconditionally immutable here (no UPDATE/DELETE policy at
-- all, for any role, referenced or not) rather than conditionally on
-- being referenced — the stronger and simpler guarantee, and the same
-- "RLS-absence means no access" shape 0001_init.sql already uses for
-- `reviewers`. World-readable: this is evidence-trail metadata behind a
-- published fact (who checked what source, when), the same public-trust
-- category as `sources` itself, not a private field.
create table source_versions (
    id          uuid primary key default gen_random_uuid(),
    source_id   uuid not null references sources(id),
    checked_on  date not null,
    checked_by  text not null,  -- a person's identifier, same convention as claims.verifier
    status      text not null,  -- free-form for Phase 1 (no fetcher exists to define a fixed vocabulary yet)
    created_at  timestamptz not null default now()
);

create index source_versions_source_idx on source_versions (source_id);

alter table source_versions enable row level security;

create policy source_versions_select_all on source_versions for select using (true);
create policy source_versions_insert_reviewers on source_versions for insert
  with check (is_reviewer());
-- No UPDATE or DELETE policy anywhere on this table, ever — see the
-- comment above. Do not add one in a later migration without a
-- deliberate, documented decision to weaken this guarantee.

-- Defence in depth under the RLS policies above, same pattern
-- 0016_grants_hardening.sql already applied to every other public table:
-- anon has no legitimate reason to write here at all.
revoke insert, update, delete, truncate, references, trigger
  on table source_versions
  from anon;

-- ============================================================
-- 2. New claim columns docs/CONTRACTS.md's frozen content_hash field
--    list needs, that do not exist yet — plus the freshness tier
--    (docs/DATA.md "Freshness tiers": 1 Critical / 2 Cycle / 3 Annual).
-- ============================================================
-- NOTE on "tier": the task text pointed at RULES-9/SCOPE-4 as the prior
-- art for this convention. Read directly, neither invents a "tier"
-- concept at all — RULES-9 invents a `stage:<order>:*` claim-FIELD
-- naming convention (timeline stages) and SCOPE-4 is about currency
-- display; neither is a tier. The real, already-documented tier concept
-- is docs/DATA.md's own "Freshness tiers" table (1 Critical / 2 Cycle /
-- 3 Annual, each with its own review-due cadence) — that is what is
-- implemented here. Recorded as a stale-card correction, not silently
-- substituted.
create type claim_tier as enum ('critical', 'cycle', 'annual');

alter table claims
  add column unit               text,
  add column source_version_id  uuid references source_versions(id),
  add column section_reference  text,
  add column quote              text,
  add column tier                claim_tier not null default 'cycle',
  add column content_hash        text;
-- `tier` defaults to 'cycle', deliberately NOT 'critical': every claim
-- that exists before this migration runs was written under a schema that
-- had no such gate, and defaulting to the tier that actually restricts
-- WHO may publish would retroactively change what an existing reviewer
-- fixture/account can do — the previous release must keep working after
-- this migration (CLAUDE.md/migration-owner.md "expand/contract").
-- Content-carrying, not curation metadata, so it is added to `sources`'s
-- own already-existing freeze precedent below, not here.

-- ============================================================
-- 3. content_hash — computed server-side, from docs/CONTRACTS.md's own
--    frozen field list: "entity type, entity natural key, field, value,
--    unit, jurisdiction, academic cycle, source version, section
--    reference, quote." Read directly off that file, not guessed.
-- ============================================================
-- A plain, non-privileged helper (not SECURITY DEFINER — no elevated
-- rights are needed to hash ten already-visible-to-the-caller fields).
-- Left at this stack's default PostgREST RPC grant shape deliberately:
-- calling it directly leaks nothing and grants nothing (pure function,
-- no side effect, no table read) — unlike every SECURITY DEFINER
-- function in this schema, there is no "two gotchas" gap to close here.
-- `search_path` pinned anyway, matching this schema's now-universal
-- convention (0016) of cheap, unconditional insurance, not because
-- anything here is exploitable today.
create or replace function compute_claim_content_hash(
  p_entity_type        text,
  p_entity_id          uuid,
  p_field              text,
  p_value              jsonb,
  p_unit               text,
  p_jurisdiction       text,
  p_academic_cycle     text,
  p_source_version_id  uuid,
  p_section_reference  text,
  p_quote              text
) returns text
language sql immutable set search_path = public, extensions as $$
  select encode(
    extensions.digest(
      concat_ws(
        E'\x1e',  -- ASCII record separator: vanishingly unlikely to appear in real content, unlike a comma or pipe
        p_entity_type,
        p_entity_id::text,
        p_field,
        coalesce(p_value::text, ''),
        coalesce(p_unit, ''),
        coalesce(p_jurisdiction, ''),
        coalesce(p_academic_cycle, ''),
        coalesce(p_source_version_id::text, ''),
        coalesce(p_section_reference, ''),
        coalesce(p_quote, '')
      ),
      'sha256'
    ),
    'hex'
  );
$$;

-- One-time backfill for every row that existed before this migration —
-- explicit, not relying on the trigger below to be re-triggered some
-- other way. Harmless to run before or after the trigger is replaced:
-- it sets exactly the value the new trigger would also compute.
update claims
set content_hash = compute_claim_content_hash(
  entity_type, entity_id, field, value, unit, jurisdiction,
  academic_cycle, source_version_id, section_reference, quote
);

alter table claims alter column content_hash set not null;

-- ============================================================
-- 4. reviewers.critical_authorised
-- ============================================================
alter table reviewers
  add column critical_authorised boolean not null default false;
-- No RLS change needed: 0001_init.sql already leaves `reviewers` with
-- RLS enabled and NO policy at all ("no policy = no access by default,
-- which is the intended state here") — this new column is exactly as
-- protected as every other column already on that table, reachable only
-- through a SECURITY DEFINER function, never directly.

-- Same shape as is_reviewer() (0001_init.sql): no parameter, always
-- self-referential via auth.uid(), so it can never become the
-- "identity oracle" class of bug db/migrations/README.md documents for
-- a parameterised predicate — there is nothing here for a caller to pass
-- someone else's id into.
create or replace function is_critical_authorised_reviewer()
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from reviewers
    where user_id = auth.uid() and critical_authorised = true
  );
$$;

-- Two independent grant paths exist on this stack for a fresh
-- SECURITY DEFINER function (db/migrations/README.md's "two gotchas"):
-- the SQL-standard PUBLIC default, and this stack's own direct grant to
-- anon/authenticated. Only ever called from inside enforce_claims_workflow
-- on behalf of an already-`is_reviewer()`-gated, already-authenticated
-- caller — anon can never usefully reach it (auth.uid() is null there,
-- so it always answers false), but revoking anyway keeps this function's
-- own grant shape explicit rather than default-shaped, same discipline
-- 0016 applied everywhere else in this schema.
revoke execute on function is_critical_authorised_reviewer() from public;
revoke execute on function is_critical_authorised_reviewer() from anon;
grant execute on function is_critical_authorised_reviewer() to authenticated;

-- ============================================================
-- 5. enforce_claims_workflow() — identity binding, NULL-safe
--    self-approval, separate-steps rule, in-review auto-revert,
--    approved_draft_version, critical-tier gate, extended freeze list.
-- ============================================================
-- 0003's function, re-created in full (0008/0016's own established
-- pattern for touching this trigger) with every PUB-2 requirement folded
-- into the SAME single trigger — deliberately not split across several
-- BEFORE triggers on `claims`: Postgres fires multiple BEFORE triggers on
-- one table in alphabetical-by-name order, and the self-approval check
-- below MUST see the FORCED created_by/reviewed_by values, not whatever
-- a client sent — a second, separately-ordered trigger would make that
-- an ordering assumption instead of a guarantee. See 0003's own header
-- for the parts of this reasoning that are unchanged.
create or replace function enforce_claims_workflow()
returns trigger as $$
declare
  content_changed boolean;
begin
  -- PUB-2, item 4: content_hash is a derived value, not a business rule —
  -- computed for EVERY write, service_role included, unlike every check
  -- below (which stays behind the existing service_role exemption, same
  -- as 0003/0008, for test/fixture convenience).
  new.content_hash := compute_claim_content_hash(
    new.entity_type, new.entity_id, new.field, new.value, new.unit,
    new.jurisdiction, new.academic_cycle, new.source_version_id,
    new.section_reference, new.quote
  );

  if auth.role() = 'service_role' then
    return new;
  end if;

  if TG_OP = 'INSERT' then
    if new.status <> 'draft' then
      raise exception
        'A claim must be inserted as draft; use the review workflow to advance its status (docs/DATA.md "Publishing workflow").';
    end if;

    -- PUB-2, item 1: created_by is NEVER a client-supplied value, even
    -- if one is sent — forced to the caller's own identity. NULL-safe:
    -- a caller with no real authenticated session (auth.uid() null)
    -- cannot insert a claim AT ALL, rather than silently recording an
    -- unaccountable NULL "maker". RLS's own claims_insert_reviewers
    -- policy already requires is_reviewer(), which itself requires
    -- auth.uid(), so this should be unreachable in practice — kept as a
    -- defence-in-depth floor, not the only guard.
    if auth.uid() is null then
      raise exception
        'A claim cannot be inserted without an authenticated identity (created_by requires auth.uid()).';
    end if;
    new.created_by := auth.uid();
    return new;
  end if;

  -- TG_OP = 'UPDATE' from here on.

  -- PUB-2, item 1: created_by is frozen the instant a row exists. Checked
  -- before every other branch, including the superseded/published early
  -- returns below, so no status transition can smuggle a rewrite through.
  if new.created_by is distinct from old.created_by then
    raise exception
      'created_by is set once, at insert, and can never be rewritten (docs/CONTRACTS.md "Publishing evidence in Phase 1").';
  end if;

  if old.status = 'superseded' then
    raise exception 'A superseded claim is final and cannot be modified.';
  end if;

  -- The exact set of columns that make up a claim's recorded CONTENT —
  -- docs/CONTRACTS.md's frozen content_hash field list (entity type,
  -- entity natural key, field, value, unit, jurisdiction, academic
  -- cycle, source version, section reference, quote), plus the
  -- pre-existing 0003/0008 columns that were never part of that list but
  -- are still recorded facts, not curation metadata (source_id,
  -- verification_date, verifier, extracted_by, currency), PLUS `tier`
  -- (see fix note immediately below). `reviewed_by` is deliberately NOT
  -- content — it is who approved, not what was approved, and it is
  -- force-bound separately, below.
  --
  -- FIX (data-security-reviewer finding on the original PUB-2 diff,
  -- live-reproduced): `tier` was originally left OUT of this set on the
  -- theory that it is curation metadata, not content -- but the
  -- critical-tier gate below reads `new.tier` (the POST-update value) at
  -- the moment of publish, so a checker who is NOT critical_authorised
  -- could combine `status: 'published'` with `tier: 'cycle'` in the SAME
  -- update call against a claim that was actually submitted (and only
  -- ever reviewed) as tier='critical' -- laundering it past the gate in
  -- the very act of approving it, since a downgraded new.tier no longer
  -- reads as 'critical' by the time the gate checks it. Folding `tier`
  -- into `content_changed` gives it the exact same protection every
  -- other content field already had here: changing it in the SAME
  -- update that publishes is rejected outright by the "content cannot
  -- change in the same update that publishes it" branch below, before
  -- the critical-tier gate is ever reached. (Changing `tier` alone, in a
  -- separate step while still in_review, now also reverts the claim to
  -- draft for fresh review -- the same already-existing behaviour every
  -- other content field gets, and a deliberate, acceptable consequence
  -- of treating tier as content for this purpose, not a new mechanism.)
  content_changed :=
       new.value              is distinct from old.value
    or new.source_id          is distinct from old.source_id
    or new.verification_date  is distinct from old.verification_date
    or new.verifier            is distinct from old.verifier
    or new.entity_type          is distinct from old.entity_type
    or new.entity_id              is distinct from old.entity_id
    or new.field                   is distinct from old.field
    or new.extracted_by             is distinct from old.extracted_by
    or new.jurisdiction               is distinct from old.jurisdiction
    or new.academic_cycle              is distinct from old.academic_cycle
    or new.currency                      is distinct from old.currency
    or new.unit                          is distinct from old.unit
    or new.source_version_id              is distinct from old.source_version_id
    or new.section_reference               is distinct from old.section_reference
    or new.quote                            is distinct from old.quote
    or new.tier                             is distinct from old.tier;

  if old.status = 'published' then
    if new.status <> 'superseded' then
      raise exception
        'A published claim cannot be edited in place or un-published; supersede it with a new claim instead.';
    end if;
    if content_changed
       or new.approved_draft_version is distinct from old.approved_draft_version
       or new.reviewed_by is distinct from old.reviewed_by
    then
      raise exception
        'Superseding a published claim may only change status/superseded_by -- not its recorded content or who approved it. Create a new claim for the corrected value instead.';
    end if;
    return new;
  end if;

  if old.status = 'draft' and new.status not in ('draft', 'in_review') then
    raise exception
      'A draft may only stay draft or move to in_review (submitted) -- not directly to %.', new.status;
  end if;

  if old.status = 'in_review' then
    if new.status not in ('draft', 'in_review', 'published') then
      raise exception
        'An in_review claim may only go back to draft, stay in_review, or be published (approved) -- not %.', new.status;
    end if;

    if new.status = 'published' and content_changed then
      -- PUB-2, item: value change and approval must be separate steps.
      -- A single UPDATE that both edits content AND flips status to
      -- published is rejected outright -- otherwise the NEW content
      -- would go live under an approval a reviewer only ever looked at
      -- the OLD content for.
      raise exception
        'A claim''s content cannot change in the same update that publishes it -- edit and approval are separate steps (docs/CONTRACTS.md "Publishing evidence in Phase 1").';
    end if;

    if new.status <> 'published' and content_changed then
      -- PUB-2, item 5: an edit to an in_review claim's content is never
      -- silently approved-in-place -- it drops back to draft for a fresh
      -- review cycle, regardless of what status the caller asked for.
      new.status := 'draft';
    end if;
  end if;

  if new.status = 'published' then
    if auth.uid() is null then
      raise exception 'A claim cannot be published without an authenticated reviewer identity.';
    end if;
    -- PUB-2, item 2: reviewed_by is NEVER a client-supplied value either
    -- -- forced to the publishing caller's own identity, the same
    -- binding created_by already gets at insert.
    new.reviewed_by := auth.uid();

    -- PUB-2, item 3: NULL-safe self-approval check. `IS NOT DISTINCT
    -- FROM` (not `=`) so two NULLs compare as EQUAL (i.e. "the same
    -- identity", and therefore rejected) rather than as NULL/unknown,
    -- which a plain `=` would silently treat as "not distinct" -- with
    -- both sides now force-bound above this can never actually be
    -- reached with either side NULL, but the operator itself is the
    -- fix the task calls for, not the forcing alone.
    if new.reviewed_by is not distinct from new.created_by then
      raise exception
        'The author of a claim cannot approve their own claim (maker-checker, docs/DATA.md "Publishing workflow").';
    end if;

    if new.tier = 'critical' and not is_critical_authorised_reviewer() then
      raise exception
        'This claim is tier=critical; only a reviewer with critical_authorised=true may publish it (docs/DATA.md "Freshness tiers").';
    end if;

    -- PUB-2, item 6: a snapshot marker of what was actually approved --
    -- content_hash was already recomputed from new.* at the top of this
    -- same trigger invocation, so this is the exact content this
    -- publish action approved, not a stale or client-supplied value.
    new.approved_draft_version := new.content_hash;
  end if;

  return new;
end;
$$ language plpgsql security invoker set search_path = public;

-- ============================================================
-- 6. sources.source_type / sources.official_url — frozen once
--    referenced by any published claim.
-- ============================================================
create or replace function enforce_source_identity_freeze()
returns trigger as $$
begin
  if auth.role() = 'service_role' then
    return new;
  end if;

  if new.source_type is distinct from old.source_type
     or new.official_url is distinct from old.official_url
  then
    if exists (
      select 1 from claims
      where source_id = old.id and status = 'published'
    ) then
      raise exception
        'sources.source_type/official_url are frozen once this source is referenced by any published claim (docs/CONTRACTS.md "Publishing evidence in Phase 1").';
    end if;
  end if;

  return new;
end;
$$ language plpgsql security invoker set search_path = public;

create trigger sources_enforce_identity_freeze
before update on sources
for each row execute function enforce_source_identity_freeze();

-- ============================================================
-- 7. PRIVATE storage bucket: source-evidence — the first Supabase
--    Storage bucket this project has ever created.
-- ============================================================
-- Defensive/no-op on any stack where the Storage service itself is
-- switched off (this repo's own SHARED test stack,
-- supabase/config.toml, `[storage] enabled = false`) — Storage is a
-- separate container that creates its own `storage` schema on first
-- boot; a bare SQL migration cannot switch a disabled service on, and
-- applying this file must not hard-fail a stack that never asked for
-- it (CLAUDE.md/migration-owner.md: the previous release keeps working).
-- Runs for real wherever Storage IS enabled — this migration owner's own
-- dedicated stack (`.supabase-migration-2/supabase/config.toml`,
-- `[storage] enabled = true`, edited on that untracked copy only, never
-- the tracked repo-root file).
--
-- Purpose: the raw screenshot/PDF/HTML evidence behind a source_version
-- — reviewer-only, every operation, exactly like the reviewer-write
-- pattern 0001_init.sql already uses for sources/careers/pathways,
-- applied here to storage.objects instead of a plain table. There is no
-- student-facing reason to read this bucket at all, so it is PRIVATE
-- (bucket `public = false`) with no world-readable policy of any kind —
-- unlike `sources`/`source_versions`, which describe a source, this
-- bucket holds the raw captured document itself.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    -- Not `alter table storage.objects enable row level security` here:
    -- confirmed live (this migration owner's own dedicated stack) that
    -- RLS is already ON by default on a freshly-provisioned `storage`
    -- schema (the Storage extension's own bootstrap), and the plain
    -- `postgres` role this migration applies as does not own that table
    -- (`must be owner of table objects`, live-reproduced) — so this
    -- migration only ever ADDS policies, never touches the table's own
    -- RLS switch, which is both unnecessary and, for this role, an error.

    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values (
      'source-evidence',
      'source-evidence',
      false,
      15728640, -- 15 MB
      array['application/pdf', 'image/png', 'image/jpeg']::text[]
    )
    on conflict (id) do nothing;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'storage' and tablename = 'objects'
        and policyname = 'source_evidence_select_reviewers'
    ) then
      execute $policy$
        create policy source_evidence_select_reviewers on storage.objects
        for select using (bucket_id = 'source-evidence' and public.is_reviewer())
      $policy$;
    end if;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'storage' and tablename = 'objects'
        and policyname = 'source_evidence_insert_reviewers'
    ) then
      execute $policy$
        create policy source_evidence_insert_reviewers on storage.objects
        for insert with check (bucket_id = 'source-evidence' and public.is_reviewer())
      $policy$;
    end if;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'storage' and tablename = 'objects'
        and policyname = 'source_evidence_update_reviewers'
    ) then
      execute $policy$
        create policy source_evidence_update_reviewers on storage.objects
        for update using (bucket_id = 'source-evidence' and public.is_reviewer())
        with check (bucket_id = 'source-evidence' and public.is_reviewer())
      $policy$;
    end if;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'storage' and tablename = 'objects'
        and policyname = 'source_evidence_delete_reviewers'
    ) then
      execute $policy$
        create policy source_evidence_delete_reviewers on storage.objects
        for delete using (bucket_id = 'source-evidence' and public.is_reviewer())
      $policy$;
    end if;
  end if;
end;
$$;

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as every migration since 0003.
create or replace function publishing_evidence_schema_version()
returns int language sql immutable as $$ select 17 $$;
