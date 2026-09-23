# Runbook — deleting a withdrawn account (staff-only, manual)

**CONSENT-10.** This is a step-by-step guide for a named staff member to
follow, by hand, in the Supabase dashboard. It is not automated and this
task does not build a deletion job — see "What this is NOT" below.

## When to use this

A student calls `POST /account/withdraw` (`app/api/account.py`), which
calls the database function `withdraw_account()`
(`db/migrations/0013_safeguarding_schema.sql`). That call, by itself,
does three things and nothing else:

1. Sets `student_accounts.account_status = 'frozen'`.
2. Sets `student_accounts.deletion_due_at = now() + 30 days`.
3. Appends one row to `consents` (`kind = 'account'`,
   `action = 'withdrawn'`).

No row is deleted at that point. The account is frozen, not gone: RLS
(already built by CONSENT-4 — `account_active()`/`is_admitted()` in the
`saved_plans`/`student_profiles` write policies) blocks every further
write for that account from the moment it is frozen. **A withdrawn
account's own `saved_plans`/`student_profiles` rows also become
unreadable to that account from that same moment** — a real, live-verified
gap between this task's own "freezing is not deleting" intent and the
current RLS shape; see `tests/db/test_withdrawal.py`'s
`TestFreezeDoesNotDeleteButDoesBlockReads` for the proof and this task's
own completion report for the open question this raises. It does not
change what this runbook does 30 days later.

This runbook is what happens **30 days after that**, once
`deletion_due_at` has passed. Today, finding which accounts are due is a
manual query (CONSENT-8's staff-facing deletion-due list does not exist
yet):

```sql
select id, deletion_due_at
from student_accounts
where account_status = 'frozen'
  and deletion_due_at <= now()
order by deletion_due_at asc;
```

Run this as the service role (Supabase SQL editor, or `psql` against the
project's connection string) — never with a student's own token, and
never logged anywhere with a student's real identifier attached
(CLAUDE.md: "no student data to development agents", "no secrets in repo
memory").

## What this is NOT

- **Not automated.** No cron job, no scheduled function, no code in this
  repo triggers a deletion. A named person decides, by hand, that a given
  account's 30 days are up and its deletion should proceed.
- **Not built by CONSENT-10.** This task (and `withdraw_account()`
  itself, CONSENT-4) only ever freezes. The actual deletion step below is
  AUTH-10's eventual subject if it becomes a real definer function;
  until then, it is this manual runbook only.
- **Not reversible.** Once the steps below are done, the account and
  everything the cascade below removes are gone. If there is ever a
  "the student changed their mind inside the 30 days" path, it has to run
  BEFORE this runbook (e.g. a support-desk process to flip
  `account_status` back to `'active'` and clear `deletion_due_at` — not
  built by this task either, and not something this runbook does).

## The actual deletion step

In the Supabase dashboard: **Authentication → Users → find the account by
its `id` (the UUID from the query above, not by searching a student's
real name/email if that can be avoided) → Delete user.** This is a real,
hard delete of the `auth.users` row — not a soft-delete, not an
anonymization.

### The exact cascade this triggers

Read from `db/migrations/*.sql`'s own foreign keys — not guessed. Every
one of these references `auth.users(id)`:

**Deleted automatically (`on delete cascade`):**

| Table | Column | Migration | What it holds for this student |
|---|---|---|---|
| `student_accounts` | `id` (PK) | `0004` | the frozen row itself |
| `student_profiles` | `id` (PK) | `0001` | profile fields |
| `saved_plans` | `student_id` | `0002` | every saved plan |
| `plan_actions` | *(via `saved_plans.id`, itself cascading)* | `0010` | next-action ticks on those plans |
| `guardian_consents` | `student_id` | `0004` | any guardian-consent request history |
| `consents` | `student_id` | `0013` | **including the very `'withdrawn'` row this runbook exists because of** — see "A known tension" below |
| `reviewers` | `user_id` (PK) | `0001` | only if this account was ALSO a reviewer |
| `safeguarding_staff` | `user_id` (PK) | `0013` | only if this account was ALSO safeguarding staff |
| `safeguarding_flags` | `student_id` | `0013` | any distress/safeguarding flags concerning this student |

**Set to NULL, not deleted (`on delete set null`):**

| Table | Column | Migration | Effect |
|---|---|---|---|
| `pilot_invites` | `used_by` | `0012` | the invite row survives; it loses the pointer to who redeemed it, but `used_at` (a timestamp, not an identity) is untouched, so the row still shows it was once used, just not by whom |

**Will BLOCK the delete if it exists — stop, do not force it (`references auth.users(id)` with no `on delete` clause, i.e. Postgres's default `NO ACTION`):**

| Table | Column | Migration | What happens |
|---|---|---|---|
| `claims` | `created_by` | `0001` | if this person ever authored a claim (a reviewer/content maker), the hard delete FAILS with a foreign-key-violation error rather than silently removing or nulling the claim's provenance |
| `claims` | `reviewed_by` | `0001` | same, if this person ever approved/rejected a claim as a checker |

If the delete fails this way: **stop, do not work around it in this
runbook.** `claims.created_by`/`reviewed_by` is the maker-checker
provenance trail (docs/DATA.md) — deciding whether/how to preserve or
clear it for a deleted identity is a real policy decision (does the
published fact's history need to survive with an anonymised maker, or
not at all?) that this runbook does not have the authority to make.
Escalate instead of nulling the column by hand. In practice this should
be rare: an ordinary student withdrawing their own consent is very
unlikely to also be a claims reviewer, but the constraint exists and this
runbook does not assume it can never fire.

**Not touched at all — no foreign key to `auth.users` exists:** the AI
usage ledger (`ai_usage`, `ai_usage_caps`, `db/migrations/0011_ai_usage.sql`
/`0015_ai_identity_binding.sql`) is keyed by a hashed identity, not a
direct reference to `auth.users(id)` — a deleted account's past AI-usage
rows are not removed by this step. If that ledger is ever expected to
forget a deleted student too, that is a separate, not-yet-built piece of
work; this runbook does not do it.

### A known tension, disclosed in 0013's own comment, worth repeating here

`db/migrations/0013_safeguarding_schema.sql`'s own header already flags
this: the design intent behind `consents` is "the append-only trail
survives as the record that a withdrawal happened" — but `consents.
student_id` is `on delete cascade`, so a real hard-delete of `auth.users`
removes that student's `'withdrawn'` row along with everything else. The
fact that a withdrawal ever happened does not outlive this runbook's own
final step, under the schema as it exists today. This was a deliberate,
disclosed trade-off (the alternative, `RESTRICT`, was tried and found to
break every ordinary account deletion for any user who ever has a
`consents` row at all — see that migration's own comment for the
live-reproduced failure) — not an oversight, but also not fixed by
CONSENT-10, since fixing it would mean changing that migration's own
`on delete` clause, and this task is not a migration owner.

## After deletion

Confirm the account is gone (the dashboard's own user list, or
`select 1 from auth.users where id = '<uuid>'` returning no row) and that
none of the cascade tables above still hold a row for that id (a stray
row after a successful delete would mean an unlisted foreign key this
runbook's own table above missed — treat that as a bug in this document,
not a shortcut to take).
