# Task card template

One card per task id, created by copying this file. A card is the actual
authorisation to work — under CLAUDE.md's conflict order, an approved
card outranks `docs/DEVELOPMENT-PLAN.md` and the inventories. Implementers
read only their own card, `.claude/agents/implementer.md` (or
`migration-owner.md`) and the one `docs/CONTRACTS.md` section named on
the card — never the build pack, the DPR, `docs/DEVELOPMENT-PLAN.md`,
`docs/plan/*` or `docs/DECISIONS.md`.

```
# <ID> - <title>

Model tier: strongest | standard | cheap
Wave: <0-5 | float | P2 | P3>
Worktree: <branch name>, or "no, on main" for a lead-only card

## What to build
<2-6 sentences, plain description, drawn from the inventory entry and
this plan's wave notes. No file the implementer needs to go find this
in themselves - name every file directly.>

## Owned files
<exact paths this card may create or edit. Nothing else.>

## Forbidden files
STATUS.md, docs/DECISIONS.md, CLAUDE.md, tasks/INDEX.md, .claude/**,
.env, .env.local, the owner-only key file, /etc/eduvation/**
<plus any file from a 6.4 conflict group this card does not own>

## Contract section
<the one docs/CONTRACTS.md heading this card may read, once it exists>

## Start condition
<copied from the plan's wave table for this task - do not start early>

## Reserved migration number
<NNNN, or "n/a" - migration cards only; reserve at session-open time by
checking `ls db/migrations/`, not from a number written weeks earlier>

## Tests
<exact make targets or pytest paths to run. State plainly if make test-db
or e2e is off-limits (true for every card before QA-2 lands).>

## Stop conditions
- Needs a file outside the owned list
- The same failure survives two fixes (report and stop; the lead
  reproduces and diagnoses - CLAUDE.md rule)
- The contract section this card depends on does not exist yet or is
  unclear

## Completion report format
- Files touched
- Test counts and skip counts, exactly as run
- Proposed STATUS.md / docs/DECISIONS.md lines, if any (never written
  directly - those files are lead-only)
- Anything DEPLOY-18's registry or an owned contract missed
```

## Notes for the lead filling a card

- Copy the inventory entry's acceptance criteria in the lead's own words,
  not a link to the inventory file - implementers never open it.
- A migration card never lists a fixed number from an old draft. The
  ledger has moved twice already in this plan's own lifetime (0004 to
  0006) from other sessions creating migrations against the live
  project while this was being written. Reserve the number when the
  session actually opens.
- A card whose inventory text names a lead-only file (`CLAUDE.md`,
  `STATUS.md`, `docs/DECISIONS.md`) has that file removed from its owned
  list; the implementer returns proposed lines in its completion report
  and the lead applies them at merge.
