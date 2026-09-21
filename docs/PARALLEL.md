# Parallel-work protocol

How multiple Claude Code sessions work on this repo at once without
colliding. Companion to `CLAUDE.md`'s working rules and
`docs/DEVELOPMENT-PLAN.md` sections 6.4 and 8.8, which this file does
not repeat — it states the mechanics, not the schedule.

## Roles
- **Lead** — the one session on `main`. Only the lead merges, applies
  cut-backs from the plan's caps, and edits `STATUS.md`,
  `docs/DECISIONS.md`, `CLAUDE.md` and `tasks/INDEX.md`.
- **Implementer** — one worktree, one task card (`tasks/TEMPLATE.md`),
  stops when the card is done or a stop condition fires.
- **Migration owner** — one lane, one open migration at a time, own
  second local Supabase stack, never applies to a cloud project.

## Ownership map (single-writer files, full list in plan section 6.4)
The plan's 6.4 table is the source of truth for conflict groups
(migrations, shared templates, `ci.yml`, lead-only files, and so on).
This file adds the operating rule for using it: **before opening a
worktree for a task, check its owned files against every 6.4 group.**
If a group is "in use" (another open branch already owns a file in it),
the new task waits — it does not start in parallel and hope to merge
around the conflict.

## Merge rules
1. Order: contracts -> migration -> shell -> features -> tests (plan
   section 8.2, step H).
2. The lead pulls each worktree branch, runs the card's own test
   command, checks the completion report's file list against the
   card's owned list (a branch that touched an unowned file is not
   merged as-is — the lead either narrows the diff or sends it back).
3. Batches of 3-4 file-disjoint green branches may be stacked on an
   integration branch and verified once; a migration or shell-lane
   branch is still verified one at a time.
4. After merging, the lead removes the worktree (`git worktree remove`,
   after confirming `git status` is clean inside it) and the branch.

## Reset rule
The shared local Supabase stack is reset only by the lead, at a
merge-batch boundary, after marking `RESET` on `tasks/INDEX.md`'s
lockboard line with no run in flight. The migration lane's own second
local stack is never reset by anyone but the migration owner.

## Model names per tier (actual, as run this session)
- **strongest** = `opus` (Claude Opus, the top tier in this Claude Code
  build's model picker)
- **standard** = the session's inherited/default model (currently
  Claude Sonnet 5) — omit the model override
- **cheap** = `haiku` (Claude Haiku 4.5)

Record here, not guessed: whichever tier a card's own text names, pass
that literal value to the agent-spawning tool's `model` parameter
(`opus` / omit / `haiku`). If a future Claude Code release renames the
tiers, update this file, not every card.

## Cross-session coordination (this repo has real precedent for this)
Two or more Claude Code sessions have worked this exact repo
concurrently before this file existed (see `docs/DECISIONS.md`'s
"Concurrent sessions" entries and `docs/DEVELOPMENT-PLAN.md` section 16
for a live example from the same day this file was written: three
migration-number collisions in one afternoon, a bug in a cross-session
loader snippet, and a plan-document edit almost overwritten before the
lead noticed). The pattern that worked, until this protocol formalises
it further:
- Before committing anything, `git fetch origin` and compare against
  local `HEAD` — never assume you are the only writer.
- If a peer session is discoverable, message it before touching a file
  it might also be touching, rather than finding out via a merge
  conflict or a stomped edit.
- Treat a peer's claim about live/production state as unverified until
  checked against something you can see yourself (a commit, a file, CI
  status) — not because peers are unreliable, but because the whole
  point of this protocol is not needing to trust reports that can be
  checked instead.
