-- BCION Lite — jurisdiction / academic cycle / currency (SCOPE-3)
-- Source of truth: docs/CONTRACTS.md "Entity vocabulary" (jurisdiction is
-- one text code: ISO 3166-1 alpha-2 for a country, ISO 3166-2 for a
-- subdivision), "Money and currency" (ISO 4217, integer major units, no
-- FX conversion anywhere in Lite) and "Duration, dates, cycle, DOB"
-- (`academic_cycle` is a text LABEL, `YYYY` or `YYYY-YY`, stored exactly
-- as the source states it, compared as a string, never parsed).
--
-- Append-only: never edit this file once it has been applied anywhere.
-- Apply via scripts/apply_migrations.py — same as 0001-0007.
--
-- **Real number check (migration-owner rule):** the card names "0004, or
-- next number the lead assigns". `ls db/migrations/` at the moment this
-- was written shows 0001-0007, so the next genuinely free number is 0008.
--
-- ============================================================
-- THE RISK THIS FILE IS MOSTLY ABOUT
-- ============================================================
-- SCOPE-3's own risk line: "Omitting the freeze-trigger update lets a
-- published GBP fee be re-labelled INR in place - a maker-checker
-- bypass."
--
-- 0003_maker_checker.sql froze a published claim's recorded content by
-- listing, column by column, what may not change when a published row is
-- superseded. That list is a DENY-LIST, so every column added to
-- `claims` after 0003 is, by default, NOT frozen — silently editable in
-- place on a published row, with no error and no new draft cycle. Adding
-- `currency` without adding it to that list would mean a published fee
-- of 9000 GBP could be relabelled 9000 INR after approval, by a
-- reviewer, with the approval still attached: a real maker-checker
-- bypass, not a theoretical one.
--
-- So this migration re-creates `enforce_claims_workflow()` with all
-- three new columns added to the frozen list. The function body below is
-- 0003's, byte-for-byte, with exactly three lines added and nothing else
-- changed — including the service_role carve-out, which mirrors what RLS
-- already grants that role and is what lets existing test fixtures seed
-- pre-published claims (see 0003's own header for the full reasoning).
-- `create or replace function` swaps the body in place under the
-- existing `claims_enforce_workflow` trigger; the trigger itself is not
-- dropped or recreated, so there is no window in which `claims` has no
-- workflow trigger at all.
--
-- **If you add another column to `claims` in a later migration, add it to
-- that list in the same migration.** There is no way to make this list
-- self-maintaining without freezing columns that are legitimately
-- mutable (`status`, `superseded_by`, `reviewed_by`), so it stays
-- explicit and this comment stays with it.
--
-- **Known gap, deliberately NOT changed here (flagged to the lead
-- instead):** 0001_init.sql's forward-looking note says M4 would add "a
-- trigger that freezes approved_draft_version", but 0003's actual frozen
-- list does not include `approved_draft_version`, and neither does this
-- one. Adding it is a behaviour change beyond SCOPE-3's named column
-- list, and the migration-owner rule is to not touch this trigger's
-- logic without the complete list of what it must cover. Raised in the
-- completion report rather than silently fixed.

-- ============================================================
-- Columns
-- ============================================================
-- Named assumption (docs/CONTRACTS.md leaves scope phasing to SCOPE-1,
-- still with the owner): existing rows default to 'IN'. Every row that
-- exists when this runs was entered for the India-first pilot, so 'IN'
-- describes them correctly; it is a backfill of what is already true,
-- not a claim about coverage. Nothing here hardcodes a covered-set list,
-- which CONTRACTS.md explicitly forbids until SCOPE-1 is answered.
--
-- The CHECK constraints are shape-only, deliberately. They enforce the
-- FORM the contract fixes (ISO 3166-1 alpha-2 / 3166-2; ISO 4217;
-- YYYY or YYYY-YY) and nothing about which values are in scope — a
-- registry of valid country codes in a CHECK would be both a covered-set
-- list and a thing that goes stale.

alter table claims
  add column jurisdiction    text not null default 'IN',
  add column academic_cycle  text,
  add column currency        char(3);

-- ISO 3166-1 alpha-2 ("IN") or ISO 3166-2 ("IN-MH", "GB-ENG").
-- docs/CONTRACTS.md: "Jurisdiction is one text code: ISO 3166-1 alpha-2
-- for a country, ISO 3166-2 for a subdivision." Rejects free text
-- ("India", "Maharashtra") and lowercase, which is what makes a string
-- comparison between two jurisdictions meaningful at all.
alter table claims
  add constraint claims_jurisdiction_shape
  check (jurisdiction ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$');

-- ISO 4217, uppercase. The regex — rather than a bare `= upper(currency)`
-- — is doing a second job worth being explicit about: `char(3)` is
-- BLANK-PADDED, so a two-letter value like 'US' would be silently stored
-- as 'US ' and would pass an uppercase-only test. `^[A-Z]{3}$` rejects
-- the padded value, so a wrong-length currency code fails loudly at
-- write time instead of becoming a permanently odd row.
-- Nullable: docs/CONTRACTS.md, "A money claim with a null currency
-- renders not_available" — an unknown currency is a real state, and must
-- not be defaulted to INR, which would invent a fact.
alter table claims
  add constraint claims_currency_shape
  check (currency is null or currency ~ '^[A-Z]{3}$');

-- A LABEL, not a date: `2026` or `2026-27`, "stored exactly as the
-- source states it, compared as a string, never parsed"
-- (docs/CONTRACTS.md). Nullable — many facts are not cycle-scoped.
alter table claims
  add constraint claims_academic_cycle_shape
  check (academic_cycle is null or academic_cycle ~ '^[0-9]{4}(-[0-9]{2})?$');

alter table pathways
  add column jurisdiction text not null default 'IN';

alter table pathways
  add constraint pathways_jurisdiction_shape
  check (jurisdiction ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$');

-- A source's jurisdiction is the authority's remit (whose rules this
-- body actually speaks for), which is why it lives here and is not
-- derived from the claims that cite it.
alter table sources
  add column jurisdiction text not null default 'IN';

alter table sources
  add constraint sources_jurisdiction_shape
  check (jurisdiction ~ '^[A-Z]{2}(-[A-Z0-9]{1,3})?$');

-- Plain, NON-unique index. SCOPE-3's card is explicit that a unique
-- index here "breaks supersede ordering": superseding a published claim
-- deliberately leaves two rows for the same (entity, field) — the old
-- `superseded` one and its replacement — and any uniqueness touching
-- that shape would make a correction impossible to record.
create index claims_jurisdiction_idx on claims (jurisdiction);

-- ============================================================
-- The freeze trigger, re-created with the three new columns
-- ============================================================
-- 0003_maker_checker.sql's function, unchanged except for the three
-- added comparisons marked below. Read that file's header for why each
-- branch is the way it is; none of that reasoning changes here.
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
       -- SCOPE-3 additions. `is distinct from` (not `<>`) so a NULL on
       -- either side compares correctly: `currency <> old.currency` is
       -- NULL, not true, when one side is NULL, which would let a
       -- published claim's null currency be filled in after approval —
       -- exactly the in-place edit this branch exists to stop.
       or new.jurisdiction is distinct from old.jurisdiction
       or new.academic_cycle is distinct from old.academic_cycle
       or new.currency is distinct from old.currency
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

-- A marker so tests/db/conftest.py can detect "is this migration applied
-- yet" — same pattern as 0003-0007.
create or replace function scope_schema_version()
returns int language sql immutable as $$ select 8 $$;
