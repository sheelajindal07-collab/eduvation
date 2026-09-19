-- BCION Lite — maker-checker enforcement (M4 first slice, tasks/BCI-005.md)
-- Source of truth: docs/DATA.md "Publishing workflow", CLAUDE.md
-- non-negotiable ("Every published fact has a source, a verification
-- date and a verifier. Unapproved facts never reach public results
-- (maker-checker, enforced server-side, not by a button)."), and
-- 0001_init.sql's own note above `claims_update_reviewers` flagging this
-- as the M4 follow-up.
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via the SQL Editor or scripts/apply_migrations.py (see
-- db/migrations/README.md) -- same as 0001/0002.

-- ============================================================
-- The workflow state machine, enforced in the database itself
-- ============================================================
-- docs/DATA.md's four steps, as code:
--   1. Draft    -- created (status = 'draft'). Nothing may ever be
--      inserted at any other status -- there is no "insert straight to
--      published" shortcut, from any client.
--   2. Review   -- a draft moves to 'in_review' (submitted), or back to
--      'draft' (sent back for revision) by a reviewer.
--   3. Publish  -- 'in_review' -> 'published' ONLY when reviewed_by is
--      set AND is a DIFFERENT person from created_by. This is the
--      specific gap 0001_init.sql's RLS policy left open at M1 -- fixed
--      here at the trigger level, where OLD vs NEW and full business
--      logic are actually expressible (RLS `with check` alone cannot
--      compare against the pre-update row).
--   4. Correction -- a 'published' claim's recorded content
--      (value/source/verification_date/entity identity/authorship) can
--      never change in place ("reviewer approval binds to the exact
--      draft content... any subsequent edit invalidates the approval").
--      The only legal move from 'published' is to 'superseded', paired
--      with inserting a brand-new claim for the corrected value
--      (superseded_by on the old row points at it). Cache invalidation
--      and flagging affected saved_plans on a correction are
--      application-level concerns, deliberately NOT built here --
--      tracked in tasks/BCI-005.md's "not done yet".
--
-- `service_role` (the owner/test-fixture connection, docs/SECURITY.md:
-- "the application never connects as the owner/service role for a
-- user-facing request") is exempt from this trigger entirely, mirroring
-- exactly what RLS already does for that role. This is what lets
-- existing test fixtures keep seeding pre-published claims directly via
-- the service-role admin_client (tests/db/conftest.py) without being
-- rewritten to walk the full draft->review->publish cycle just to set
-- up an unrelated test -- the same carve-out RLS bypass already grants,
-- not a new or weaker one. A real reviewer's own request never uses
-- service_role, so this exemption doesn't touch the guarantee that
-- actually matters.
--
-- Known limitation, not fixed here: this migration does not force
-- `created_by = auth.uid()` at insert time -- the publishing-console API
-- that will actually set these fields doesn't exist yet (tasks/BCI-005.md
-- "not done yet"), so a hard requirement on it now would be untestable
-- and premature. Until that API lands, `created_by`/`reviewed_by` are
-- trusted to be set honestly by whatever inserts/updates a claim.

create or replace function enforce_claims_workflow()
returns trigger as $$
begin
  if auth.role() = 'service_role' then
    return new;
  end if;

  if TG_OP = 'INSERT' then
    if new.status <> 'draft' then
      raise exception
        'A claim must be inserted as draft; use the review workflow to advance its status (docs/DATA.md "Publishing workflow").';
    end if;
    return new;
  end if;

  -- TG_OP = 'UPDATE' from here on.

  if old.status = 'superseded' then
    raise exception 'A superseded claim is final and cannot be modified.';
  end if;

  if old.status = 'published' then
    if new.status <> 'superseded' then
      raise exception
        'A published claim cannot be edited in place or un-published; supersede it with a new claim instead.';
    end if;
    if new.value is distinct from old.value
       or new.source_id is distinct from old.source_id
       or new.verification_date is distinct from old.verification_date
       or new.verifier is distinct from old.verifier
       or new.entity_type is distinct from old.entity_type
       or new.entity_id is distinct from old.entity_id
       or new.field is distinct from old.field
       or new.created_by is distinct from old.created_by
       or new.extracted_by is distinct from old.extracted_by
    then
      raise exception
        'Superseding a published claim may only change status/superseded_by -- not its recorded content. Create a new claim for the corrected value instead.';
    end if;
    return new;
  end if;

  if old.status = 'draft' and new.status not in ('draft', 'in_review') then
    raise exception
      'A draft may only stay draft or move to in_review (submitted) -- not directly to %.', new.status;
  end if;

  if old.status = 'in_review' and new.status not in ('draft', 'in_review', 'published') then
    raise exception
      'An in_review claim may only go back to draft, stay in_review, or be published (approved) -- not %.', new.status;
  end if;

  if new.status = 'published' then
    if new.reviewed_by is null then
      raise exception 'A claim cannot be published without a recorded reviewer.';
    end if;
    if new.reviewed_by = new.created_by then
      raise exception
        'The author of a claim cannot approve their own claim (maker-checker, docs/DATA.md "Publishing workflow").';
    end if;
  end if;

  return new;
end;
$$ language plpgsql security invoker set search_path = public;

create trigger claims_enforce_workflow
before insert or update on claims
for each row execute function enforce_claims_workflow();

-- Defense in depth alongside the trigger above (belt-and-suspenders, the
-- same pattern 0001_init.sql already uses for the synthetic-source
-- guarantee): RLS blocks a non-reviewer from even attempting the update,
-- and separately blocks the specific self-approval shape at the RLS
-- layer too, exactly as 0001_init.sql's own comment already planned.
drop policy if exists claims_update_reviewers on claims;
create policy claims_update_reviewers on claims for update
  using (is_reviewer())
  with check (is_reviewer() and (reviewed_by is distinct from created_by));

-- A tiny marker the test suite can call to detect "is this migration
-- applied yet" (tests/db/conftest.py's established pattern for 0002 --
-- _saved_plans_table_exists -- checks a new TABLE; this migration adds
-- no new table, only a trigger and a tightened policy, neither of which
-- is queryable through PostgREST directly, hence this marker).
create or replace function maker_checker_schema_version()
returns int language sql immutable as $$ select 3 $$;
