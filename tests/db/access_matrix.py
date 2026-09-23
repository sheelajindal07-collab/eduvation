"""The cross-user access matrix, as data (QA-6).

CLAUDE.md's non-negotiable — "Cross-user access (guest, student A,
student B, reviewer) is tested every time auth, RLS or publication
changes" — and docs/SECURITY.md's "Access matrix tested on every
auth/RLS/publication change: **guest, student A, student B, reviewer** ×
read/write/delete/export/storage" are, until this file, honoured by a
scatter of hand-written tests (tests/db/test_rls.py,
test_api_plans.py, test_guardian_consent.py, test_reviewer_console.py,
test_plan_actions.py, ...). Those remain the detailed, scenario-shaped
proofs. What they cannot do is answer "is EVERY table covered?" — a new
table added by a later migration simply never appears in them, and
nothing fails.

This file is the answer to that question: one row per (role, table,
operation), with the expected outcome and the policy it comes from.
tests/db/test_access_matrix.py turns every row into a parametrized test
and, separately, reads the live catalogue with psycopg and FAILS if a
public table exists that has no rows here (or has RLS switched off).
Omission stops being silent.

HOW TO READ A ROW
-----------------
Each row answers exactly one question:

    "Acting as <role>, over the ordinary RLS-scoped client a real
     request uses, can I <operation> THE CANONICAL TARGET ROW of
     <table>?"

The canonical target row is the point of the whole exercise, so it is
spelled out per table in `TABLE_TARGETS` below and re-stated in each
row's `why`. Two rules make the matrix a *cross-user* matrix rather
than four unrelated single-user matrices:

  1. For a student-owned table the canonical row always belongs to
     **student A**. So the `student_b` row of that table asks "can
     student B reach student A's data?" (must be no), and the
     `reviewer` row asks "does the reviewer role override the student
     vault?" (must also be no — docs/SECURITY.md).
  2. For an INSERT the canonical row is the row that does not exist
     yet, with the SAME ownership. So `student_b` + `insert` means
     "can student B create a row owned by student A?", not "can
     student B create their own row".

OUTCOME VOCABULARY (why "deny" is two values, not one)
------------------------------------------------------
Postgres denies in two structurally different ways, and collapsing them
would let a real regression hide:

  * `DENY_EMPTY` — no error, zero rows. A policy's USING clause did not
    match the target row, so the row was invisible (SELECT) or matched
    nothing to change (UPDATE/DELETE). This is the correct shape for a
    filtered read and for a write against a row you cannot see.
  * `DENY_ERROR` — the request was refused outright: a WITH CHECK
    violation on INSERT (SQLSTATE 42501, "new row violates row-level
    security policy"), or a missing table privilege (42501, "permission
    denied for table") on a table whose grants were revoked, or a
    PostgREST "table not found" for a table no API role can see at all.

An expectation of `DENY_EMPTY` where the database actually errors (or
the reverse) is a real change in behaviour and should be read, not
papered over: e.g. if `reviewers` ever stopped being `DENY_EMPTY` on
SELECT and became `DENY_ERROR`, that means its grants were revoked —
fine, but somebody decided it. `ERROR_OTHER` is never an expectation;
it is what the test reports when a deny happened for a reason that is
NOT authorisation (a foreign-key violation, a broken payload), so a
cell can never pass for the wrong reason.

WHAT AN INSERT CELL ASKS
------------------------
"Was the row written?", not "did the caller get the row back?". The
runner sends every insert with `Prefer: return=minimal` and then
confirms the row's existence separately (as the service role, a state
check). That distinction is not pedantry: Postgres applies a table's
SELECT policies to an `INSERT ... RETURNING` row, so on
`guardian_consents` — which deliberately has no SELECT policy for
anyone — a PERMITTED insert comes back as "new row violates row-level
security policy" if you ask for the row. db/migrations/
0005_guardian_consent_request_rpc.sql documents that exact failure
(it broke every under-18 sign-up on the live database) and the fix.
Recording it as a denial here would have written a false line into this
matrix, and a line that would have kept passing if the INSERT policy
were dropped tomorrow.

SOURCES FOR EVERY EXPECTATION
-----------------------------
Every `why` below cites the migration and the policy by name. Nothing
here was derived by running the suite and writing down what happened —
each row was read out of db/migrations/*.sql first, and the single cell
where the live stack first disagreed with that reading
(guardian_consents / insert / student A) was investigated until the
disagreement was explained, not edited until it went green: the policy
said ALLOW, the reading was right, and the probe was asking the wrong
question. See "WHAT AN INSERT CELL ASKS" above.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """The four principals docs/SECURITY.md names.

    Each maps to a fixture in tests/db/conftest.py — `guest_client`,
    `student_a`, `student_b`, `reviewer` — i.e. an ordinary RLS-scoped
    client. None of them is the service role, which bypasses RLS and
    would hide every bug this matrix exists to catch.
    """

    GUEST = "guest"
    STUDENT_A = "student_a"
    STUDENT_B = "student_b"
    REVIEWER = "reviewer"


class Operation(StrEnum):
    """docs/SECURITY.md's read/write/delete/export/storage, split the
    way the database actually distinguishes them (write is INSERT and
    UPDATE — they run through different policy clauses and fail in
    different shapes, so one "write" row would hide half the answer).
    """

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    # Not built in this pilot. Placeholder cells only — see
    # UNBUILT_OPERATIONS below.
    EXPORT = "export"
    STORAGE = "storage"


CORE_OPERATIONS: tuple[Operation, ...] = (
    Operation.SELECT,
    Operation.INSERT,
    Operation.UPDATE,
    Operation.DELETE,
)

UNBUILT_OPERATIONS: tuple[Operation, ...] = (Operation.EXPORT, Operation.STORAGE)


class Outcome(StrEnum):
    """See "OUTCOME VOCABULARY" in the module docstring."""

    ALLOW = "allow"
    DENY_EMPTY = "deny:empty"
    DENY_ERROR = "deny:error"
    #: Placeholder expectation for a capability this pilot has not built.
    #: Carried by an `xfail(strict=True)` test, so the day export or
    #: storage IS built the placeholder XPASSes and the run goes red.
    UNBUILT = "unbuilt"
    #: OBSERVED-ONLY, never an expectation: the operation failed for a
    #: reason that is not authorisation. Keeps a deny-cell from passing
    #: because the payload was broken rather than because RLS worked.
    ERROR_OTHER = "error:other"


@dataclass(frozen=True, slots=True)
class Cell:
    role: Role
    table: str
    operation: Operation
    expected: Outcome
    why: str


def cell_id(cell: Cell) -> str:
    """pytest's node id for a cell — `careers-select-guest-allow`."""
    return f"{cell.table}-{cell.operation.value}-{cell.role.value}-{cell.expected.value}"


def _row(
    table: str,
    operation: Operation,
    *,
    guest: Outcome,
    student_a: Outcome,
    student_b: Outcome,
    reviewer: Outcome,
    why: str,
) -> tuple[Cell, ...]:
    """One line of the matrix: all four roles for one (table, operation).

    Keyword-only on purpose — a positional quartet of outcomes is
    exactly the kind of thing that gets silently transposed.
    """
    return (
        Cell(Role.GUEST, table, operation, guest, why),
        Cell(Role.STUDENT_A, table, operation, student_a, why),
        Cell(Role.STUDENT_B, table, operation, student_b, why),
        Cell(Role.REVIEWER, table, operation, reviewer, why),
    )


ALLOW = Outcome.ALLOW
EMPTY = Outcome.DENY_EMPTY
ERROR = Outcome.DENY_ERROR

SELECT = Operation.SELECT
INSERT = Operation.INSERT
UPDATE = Operation.UPDATE
DELETE = Operation.DELETE


#: What "the canonical target row" means, per table. The test module
#: seeds exactly these rows (as the service role, setup only) before
#: acting as the role under test.
TABLE_TARGETS: dict[str, str] = {
    "sources": "a synthetic-typed source row seeded by the fixture",
    "careers": "a seeded career row",
    "pathways": "a seeded pathway row hanging off that career",
    "claims": (
        "a seeded DRAFT claim on that career, from that synthetic source, "
        "with created_by set to a throwaway 'maker' user and reviewed_by null"
    ),
    "reviewers": "the reviewer-identity row of a throwaway user who is NOT the acting role",
    "student_profiles": "student A's profile row",
    "saved_plans": "student A's saved plan for the seeded pathway",
    "plan_actions": "a next-action row hanging off student A's saved plan",
    "student_accounts": "student A's account row (adult date of birth, status 'active')",
    "guardian_consents": (
        "student A's pending guardian-consent row (the one holding the bearer token)"
    ),
    "app_settings": "the single demo-mode flag row",
    "guest_sessions": "a guest session row (unreachable by any API role, so never actually seeded)",
    "guest_plans": "a guest plan row (unreachable by any API role, so never actually seeded)",
    "_schema_migrations": "the migration-bookkeeping row for 0001_init.sql",
    "ai_usage": (
        "student A's own reserved AI-spend row — `identity_hash` is the SHA-256 digest of "
        "student A's account id, which is what `ai_usage_select_own` derives from the "
        "caller's OWN JWT"
    ),
    "ai_usage_caps": (
        "the single AI spend-cap configuration row (unreachable by any API role, so never "
        "actually seeded)"
    ),
    "consents": (
        "a withdrawal consent row for student A (student_id = student A, action='withdrawn')"
    ),
    "pilot_invites": (
        "an unused, unexpired invite row (unreachable by any API role directly, so never "
        "actually a target any role can see)"
    ),
    "safeguarding_staff": (
        "the safeguarding-staff identity row of a throwaway user who is NOT the acting role"
    ),
    "safeguarding_flags": "a flag row concerning student A, raised under a placeholder category",
}


# =====================================================================
# Public knowledge base — world-readable, reviewer-writable
# (db/migrations/0001_init.sql)
# =====================================================================
_PUBLIC_KB: tuple[Cell, ...] = (
    *_row(
        "sources",
        SELECT,
        guest=ALLOW,
        student_a=ALLOW,
        student_b=ALLOW,
        reviewer=ALLOW,
        why="0001 sources_select_all: `for select using (true)` — world-readable, guests included.",
    ),
    *_row(
        "sources",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ALLOW,
        why=(
            "0001 sources_write_reviewers: `for all ... with check (is_reviewer())`. A "
            "non-reviewer's insert fails the WITH CHECK outright (42501); no other policy "
            "grants INSERT."
        ),
    ),
    *_row(
        "sources",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 sources_write_reviewers is the only UPDATE policy; its USING "
            "(is_reviewer()) hides the row from `authenticated` non-reviewers (student_a, "
            "student_b), so their update matches zero rows rather than erroring. `guest` is "
            "DENY_ERROR, not DENY_EMPTY (db/migrations/0016_grants_hardening.sql): `anon` no "
            "longer holds UPDATE on `sources` at all (only SELECT), so a guest's request "
            "never reaches RLS — refused at the privilege check first, a STRONGER guarantee "
            "than the previous 'filtered to zero rows', not a weaker one."
        ),
    ),
    *_row(
        "sources",
        DELETE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 sources_write_reviewers, DELETE side — same USING clause as UPDATE. `guest` "
            "is DENY_ERROR for the same 0016_grants_hardening.sql reasoning as the UPDATE row "
            "directly above (`anon` lost DELETE on `sources` too)."
        ),
    ),
    *_row(
        "careers",
        SELECT,
        guest=ALLOW,
        student_a=ALLOW,
        student_b=ALLOW,
        reviewer=ALLOW,
        why="0001 careers_select_all: `for select using (true)`.",
    ),
    *_row(
        "careers",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ALLOW,
        why="0001 careers_write_reviewers: `with check (is_reviewer())`.",
    ),
    *_row(
        "careers",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 careers_write_reviewers: `using (is_reviewer())` filters the row away for "
            "`authenticated` non-reviewers. `guest` is DENY_ERROR, not DENY_EMPTY "
            "(0016_grants_hardening.sql: `anon` lost UPDATE on `careers`) — same reasoning as "
            "sources' UPDATE row above."
        ),
    ),
    *_row(
        "careers",
        DELETE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 careers_write_reviewers, DELETE side. `guest` is DENY_ERROR — same "
            "0016_grants_hardening.sql reasoning as the UPDATE row directly above."
        ),
    ),
    *_row(
        "pathways",
        SELECT,
        guest=ALLOW,
        student_a=ALLOW,
        student_b=ALLOW,
        reviewer=ALLOW,
        why="0001 pathways_select_all: `for select using (true)`.",
    ),
    *_row(
        "pathways",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ALLOW,
        why="0001 pathways_write_reviewers: `with check (is_reviewer())`.",
    ),
    *_row(
        "pathways",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 pathways_write_reviewers: `using (is_reviewer())`. `guest` is DENY_ERROR, "
            "not DENY_EMPTY (0016_grants_hardening.sql: `anon` lost UPDATE on `pathways`) — "
            "same reasoning as sources'/careers' UPDATE rows above; live-reproduced by "
            "tests/db/test_scope_columns.py's own "
            "`test_a_guest_cannot_write_a_pathway_jurisdiction`."
        ),
    ),
    *_row(
        "pathways",
        DELETE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 pathways_write_reviewers, DELETE side. `guest` is DENY_ERROR — same "
            "0016_grants_hardening.sql reasoning as the UPDATE row directly above."
        ),
    ),
)


# =====================================================================
# claims — the provenance table (0001 + 0003 + 0007)
# =====================================================================
# The canonical target is a DRAFT claim on purpose. A draft is the row
# that must never leak (CLAUDE.md: "Unapproved facts never reach public
# results"), and choosing 'draft' also makes these cells immune to
# `demo_mode()` (0007's extra SELECT policy only ever widens visibility
# to `status = 'in_review'` rows), so a concurrently-running
# tests/db/test_demo_mode.py flipping that global flag cannot change
# this file's answers.
_CLAIMS: tuple[Cell, ...] = (
    *_row(
        "claims",
        SELECT,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0001 claims_select_published: `using (status = 'published' or is_reviewer())`. "
            "The target is a DRAFT, so only a reviewer sees it. 0007's "
            "claims_select_demo_synthetic cannot widen this: it matches 'in_review' only. "
            "NOT covered by this cell, on purpose: that a PUBLISHED claim IS world-readable "
            "— the positive half — which tests/db/test_api_claims.py and "
            "tests/db/test_demo_mode.py own. This matrix is about who is kept out."
        ),
    ),
    *_row(
        "claims",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ALLOW,
        why=(
            "0001 claims_insert_reviewers: `with check (is_reviewer())`. The insert is made "
            "as status='draft' because 0003's enforce_claims_workflow() trigger (which fires "
            "BEFORE the RLS check) rejects any other insert status for every non-service "
            "caller — so a deny here is the RLS deny, not the trigger's."
        ),
    ),
    *_row(
        "claims",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=ALLOW,
        why=(
            "0003 claims_update_reviewers: `using (is_reviewer()) with check (is_reviewer() "
            "and (reviewed_by is distinct from created_by))`. The target claim carries a "
            "non-null created_by and a null reviewed_by precisely so the maker-checker WITH "
            "CHECK is satisfiable — with BOTH null, `null is distinct from null` is false and "
            "even a reviewer is denied (that self-approval shape is test_maker_checker.py's "
            "subject, not this matrix's). `guest` is DENY_ERROR, not DENY_EMPTY "
            "(0016_grants_hardening.sql: `anon` lost UPDATE on `claims`, keeping SELECT only) "
            "— live-reproduced by tests/db/test_scope_columns.py's own "
            "`test_a_guest_cannot_either`. `authenticated` (student_a, student_b) keeps its "
            "own UPDATE grant, so their write still just matches nothing, no error."
        ),
    ),
    *_row(
        "claims",
        DELETE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "NO delete policy exists on claims in any migration — 0001 adds select/insert/"
            "update, 0003 replaces update, 0007 adds a select. A claim is corrected by "
            "superseding it (0003's docstring), never by deletion, so nobody — reviewer "
            "included — can delete one through the API. `guest` is DENY_ERROR, not "
            "DENY_EMPTY (0016_grants_hardening.sql: `anon` lost DELETE on `claims` at the "
            "grant layer, on top of there being no DELETE policy either); `authenticated` "
            "(student_a, student_b, reviewer) keeps its own DELETE grant, so their attempt "
            "still just matches nothing, no error."
        ),
    ),
)


# =====================================================================
# reviewers — the identity table nothing may read (0001)
# =====================================================================
_REVIEWERS: tuple[Cell, ...] = (
    *_row(
        "reviewers",
        SELECT,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0001 enables RLS on reviewers and deliberately adds NO policy: 'only the "
            "is_reviewer() security-definer function touches it'. Zero matching policies "
            "means zero rows for `authenticated` — for a reviewer reading another reviewer's "
            "row too — a filtered read, not a privilege error, since `authenticated`'s own "
            "grants are untouched. `guest` is DENY_ERROR, not DENY_EMPTY "
            "(0016_grants_hardening.sql: `revoke all on table ... reviewers from anon` — "
            "`anon` now holds NOTHING on this table, not even SELECT, so a guest's request "
            "never reaches RLS at all)."
        ),
    ),
    *_row(
        "reviewers",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0001, no policy: an INSERT with no permissive policy fails the RLS check "
            "outright (42501) for `authenticated`. Self-promotion to reviewer is impossible "
            "through the API — only the service role can add a row. `guest` was ALREADY "
            "DENY_ERROR before 0016 (a WITH CHECK violation is always a 42501, never an empty "
            "result), so `anon`'s grant revocation (0016_grants_hardening.sql) is a no-op for "
            "this cell — it now fails at the privilege check instead of the RLS check, same "
            "observable outcome."
        ),
    ),
    *_row(
        "reviewers",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0001, no policy: nothing is visible to update for `authenticated`. `guest` is "
            "DENY_ERROR, not DENY_EMPTY — same 0016_grants_hardening.sql reasoning as the "
            "SELECT row above (`anon` holds no grant on this table at all)."
        ),
    ),
    *_row(
        "reviewers",
        DELETE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0001, no policy: nothing is visible to delete for `authenticated` (a reviewer "
            "cannot demote another). `guest` is DENY_ERROR — same 0016_grants_hardening.sql "
            "reasoning as the SELECT/UPDATE rows above."
        ),
    ),
)


# =====================================================================
# The student vault — own row, no reviewer override
# (0001 + 0002, re-scoped by 0004's account_active(); 0010)
# =====================================================================
_STUDENT_VAULT: tuple[Cell, ...] = (
    *_row(
        "student_profiles",
        SELECT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's student_profiles_select_own (split off the old `for all` "
            "student_profiles_own_row by CONSENT-4 — see 0012's own header for why: `for "
            "all` cannot be narrowed to 'write only', so gating writes on is_admitted() "
            "without touching read meant splitting SELECT into its own, unchanged policy): "
            "`using (auth.uid() = id and account_active(auth.uid()))`. Student A owns the "
            "row; student B and the reviewer are not A, so their read matches nothing. "
            "`guest` is DENY_ERROR, not DENY_EMPTY (migration-owner fix round, "
            "0014_account_active_grant_fix.sql): account_active() — pre-existing on "
            "already-merged 0004, closed here for a cross-user identity-oracle finding, see "
            "that migration's own header — lost its EXECUTE grant from `anon`. Postgres "
            "checks EXECUTE privilege on every function referenced anywhere in a policy's "
            "USING/WITH CHECK at query-analysis time, regardless of whether the row-matching "
            "would have short-circuited to zero rows at runtime — same shape as "
            "is_admitted()'s own DENY_ERROR cells elsewhere in this table. `authenticated` "
            "(student_b, reviewer) keeps its own EXECUTE grant, so their read still just "
            "matches nothing, no error. docs/SECURITY.md: the reviewer role governs the "
            "knowledge base, never the vault."
        ),
    ),
    *_row(
        "student_profiles",
        INSERT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0012's student_profiles_insert_own: `with check (auth.uid() = id and "
            "account_active(auth.uid()) and is_admitted(auth.uid()))` — CONSENT-4 ANDs "
            "is_admitted() into the write side of the old student_profiles_own_row policy "
            "(docs/CONSENT.md section 7, 'the gap CONSENT-4 must close'). Student A's ALLOW "
            "here depends on the access-matrix fixture seeding her an ACTIVE, ADMITTED "
            "student_accounts row first (tests/db/test_access_matrix.py's "
            "`_Seeds.admitted_account_id()`) — without that seed this cell would now be "
            "DENY, which is exactly the regression test_admission.py's own dedicated, "
            "NOT-YET-ADMITTED student proves separately. B and the reviewer are refused "
            "regardless (42501) because the row inserted is always OWNED BY A."
        ),
    ),
    *_row(
        "student_profiles",
        UPDATE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's student_profiles_update_own: same is_admitted()-ANDed shape as INSERT, "
            "in both the USING and WITH CHECK clauses. A's row is invisible to everyone "
            "else, so their update matches nothing. `guest` is DENY_ERROR, not DENY_EMPTY "
            "(adversarial-review fix, this session): Postgres checks EXECUTE privilege on "
            "every function referenced anywhere in a policy's USING/WITH CHECK — including "
            "is_admitted(), now revoked from `anon` (0012's own comment on that function) — "
            "at query-analysis time, regardless of whether the row-matching short-circuits "
            "to zero rows at runtime. `authenticated` (student_b, reviewer) keeps its own "
            "EXECUTE grant, so their update still just matches nothing, no error."
        ),
    ),
    *_row(
        "student_profiles",
        DELETE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's student_profiles_delete_own — same is_admitted()-ANDed USING clause. "
            "`guest` is DENY_ERROR for the same reason as the UPDATE row directly above — "
            "see that row's `why` for the full reasoning."
        ),
    ),
    *_row(
        "saved_plans",
        SELECT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's saved_plans_select_own (split off the old `for all` saved_plans_own_row "
            "by CONSENT-4, same reasoning as student_profiles_select_own above): `using "
            "(auth.uid() = student_id and account_active(auth.uid()))`. A saved plan is "
            "exactly as private as the profile it hangs off. `guest` is DENY_ERROR, not "
            "DENY_EMPTY — same 0014_account_active_grant_fix.sql reasoning as "
            "student_profiles_select_own's cell directly above (account_active() lost its "
            "EXECUTE grant from `anon`)."
        ),
    ),
    *_row(
        "saved_plans",
        INSERT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0012's saved_plans_insert_own: `with check (auth.uid() = student_id and "
            "account_active(auth.uid()) and is_admitted(auth.uid()))` — the other half of "
            "'the gap CONSENT-4 must close'. Same admitted-fixture dependency as "
            "student_profiles' INSERT row above."
        ),
    ),
    *_row(
        "saved_plans",
        UPDATE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's saved_plans_update_own — same is_admitted()-ANDed USING/WITH CHECK. "
            "`guest` is DENY_ERROR — same adversarial-review reasoning as "
            "student_profiles' UPDATE row above (EXECUTE on is_admitted() revoked from "
            "`anon`, checked at query-analysis time regardless of row match)."
        ),
    ),
    *_row(
        "saved_plans",
        DELETE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0012's saved_plans_delete_own — same is_admitted()-ANDed USING clause. `guest` "
            "is DENY_ERROR for the same reason as the UPDATE row directly above."
        ),
    ),
    *_row(
        "plan_actions",
        SELECT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0010 plan_actions_own_row: ownership is inherited from the parent plan — "
            "`exists (select 1 from saved_plans p where p.id = plan_actions.plan_id and "
            "p.student_id = auth.uid() and account_active(auth.uid()))`. `guest` is "
            "DENY_ERROR, not DENY_EMPTY (0014_account_active_grant_fix.sql: account_active() "
            "lost its EXECUTE grant from `anon` — same query-analysis-time reasoning as "
            "student_profiles_select_own/saved_plans_select_own above). `authenticated` "
            "(student_b, reviewer) keeps its own EXECUTE grant, so their read still just "
            "matches nothing, no error."
        ),
    ),
    *_row(
        "plan_actions",
        INSERT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "Same policy's WITH CHECK; the action inserted always hangs off student A's "
            "plan. `guest` was ALREADY DENY_ERROR before 0014 (a WITH CHECK violation is "
            "always a 42501, never an empty result — there is no 'insert zero rows' "
            "outcome), so account_active()'s grant change is a no-op for this cell."
        ),
    ),
    *_row(
        "plan_actions",
        UPDATE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "Same policy's USING clause. `guest` is DENY_ERROR — same "
            "0014_account_active_grant_fix.sql reasoning as the SELECT cell above."
        ),
    ),
    *_row(
        "plan_actions",
        DELETE,
        guest=ERROR,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "Same policy, DELETE side. `guest` is DENY_ERROR — same "
            "0014_account_active_grant_fix.sql reasoning as the SELECT/UPDATE cells above."
        ),
    ),
)


# =====================================================================
# The consent gate — deliberately narrower than "own row"
# (db/migrations/0004_guardian_consent.sql)
# =====================================================================
_CONSENT_GATE: tuple[Cell, ...] = (
    *_row(
        "student_accounts",
        SELECT,
        guest=EMPTY,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0004 student_accounts_select_own: `for select using (auth.uid() = id)`.",
    ),
    *_row(
        "student_accounts",
        INSERT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0004 student_accounts_insert_own: `for insert with check (auth.uid() = id)` — "
            "the row is created for student A. The row is inserted with an ADULT date of "
            "birth: 0004's enforce_account_status_matches_age() trigger would reject an "
            "under-18 row created as 'active', and that would be a trigger deny, not the "
            "access-control answer this cell is about."
        ),
    ),
    *_row(
        "student_accounts",
        UPDATE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0004 adds SELECT and INSERT policies only, and says why: with an UPDATE policy "
            "'a student's own signed-in session could simply .update({account_status: "
            "active}) their own row, self-activating a pending account'. So even the OWNER "
            "is denied — account_status only ever moves via confirm_guardian_consent()."
        ),
    ),
    *_row(
        "student_accounts",
        DELETE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0004 adds no DELETE policy either — deleting the row would erase the pending "
            "state itself, which is the same bypass as updating it."
        ),
    ),
    *_row(
        "guardian_consents",
        SELECT,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0004 grants INSERT and nothing else, deliberately: the row holds a bearer token "
            "and 'a normal own-row RLS policy would let the STUDENT themselves read their "
            "own row, including the token, and self-confirm'. So student A is denied their "
            "OWN row here — status comes from my_guardian_consent_status(), which never "
            "selects the token column."
        ),
    ),
    *_row(
        "guardian_consents",
        INSERT,
        guest=ERROR,
        student_a=ALLOW,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0004 guardian_consents_insert_own: `with check (auth.uid() = student_id)`; the "
            "row created is always student A's. The token and expiry sent by the caller are "
            "overwritten by 0004's enforce_guardian_consent_server_token() trigger, so an "
            "ALLOW here is 'may create a request', never 'may choose the credential'. NOTE: "
            "this is the cell that only reads true with `return=minimal` — ask for the row "
            "back and the table's absent SELECT policy turns A's permitted insert into a "
            "42501 (0005's docstring; see 'WHAT AN INSERT CELL ASKS' above)."
        ),
    ),
    *_row(
        "guardian_consents",
        UPDATE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0004: no UPDATE policy for anyone — only confirm_guardian_consent() advances a row.",
    ),
    *_row(
        "guardian_consents",
        DELETE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0004: no DELETE policy for anyone.",
    ),
)


# =====================================================================
# Tables no API role may touch at all — grants revoked, not just RLS
# (0007 app_settings, 0009 guest_sessions/guest_plans) — plus the
# migration bookkeeping table, which was never granted in the first place
# =====================================================================
def _no_api_access(table: str, why: str) -> tuple[Cell, ...]:
    """All sixteen cells of a table that anon/authenticated hold no
    privilege on: PostgREST refuses before RLS is ever consulted, so
    every operation is DENY_ERROR rather than a silent empty result."""
    return tuple(
        cell
        for operation in CORE_OPERATIONS
        for cell in _row(
            table,
            operation,
            guest=ERROR,
            student_a=ERROR,
            student_b=ERROR,
            reviewer=ERROR,
            why=why,
        )
    )


_SEALED: tuple[Cell, ...] = (
    *_no_api_access(
        "app_settings",
        why=(
            "0007: RLS enabled with NO policy, AND `revoke all on table app_settings from "
            "anon, authenticated` — 'a direct REST call gets a flat permission-denied "
            "instead of an empty result set'. The demo-mode kill switch is service-role "
            "only; demo_mode() reads it as a security-definer function."
        ),
    ),
    *_no_api_access(
        "guest_sessions",
        why=(
            "0009: deny-all RLS (no policies) plus revoked grants. 'A guest is not a "
            "database principal', so the only way in is the definer RPCs "
            "(create_guest_session / save_guest_plan / list_guest_plans / "
            "delete_guest_plan), which tests/db/test_guest_session.py covers."
        ),
    ),
    *_no_api_access(
        "guest_plans",
        why=(
            "0009: same deny-all RLS plus revoked grants as guest_sessions. This is the "
            "table holding one guest's saved routes, so a direct read by anybody — "
            "including a signed-in student — must fail at the privilege layer."
        ),
    ),
    *_no_api_access(
        "_schema_migrations",
        why=(
            "Not created by a migration at all: scripts/apply_migrations.py creates it to "
            "record which files have been applied. anon/authenticated were never granted "
            "anything on it, so PostgREST refuses every operation (permission denied, or a "
            "'not found in the schema cache' 404 — both are authorisation answers, neither "
            "is a row). Listed here because the guard in test_access_matrix.py demands that "
            "EVERY public table be accounted for, including the ones nobody thought of as "
            "application tables."
        ),
    ),
    *_no_api_access(
        "pilot_invites",
        why=(
            "0012: RLS enabled with NO policy, AND `revoke all on table pilot_invites from "
            "anon, authenticated` — the same belt-and-suspenders shape 0007/0009 use for "
            "app_settings/guest_sessions/guest_plans, chosen here because docs/CONSENT.md "
            "section 7 treats a live invite code as 'credential-like': there is no "
            "legitimate direct read (even filtered) or write of this table by any client "
            "role. invite_is_valid()/redeem_invite() are SECURITY DEFINER and bypass this "
            "entirely via their owner's privileges, exactly as confirm_guardian_consent() "
            "(0004) bypasses guardian_consents' own lack of a SELECT policy."
        ),
    ),
)


# =====================================================================
# CONSENT-4 — the admission axis's own tables + safeguarding
# (db/migrations/0012_admission_axis.sql, 0013_safeguarding_schema.sql)
# =====================================================================
_CONSENT_4: tuple[Cell, ...] = (
    *_row(
        "consents",
        SELECT,
        guest=EMPTY,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0013 consents_select_own: `for select using (auth.uid() = student_id)`. "
            "docs/CONSENT.md section 6: students read their OWN consent history; 'other "
            "people's consents' — student B's and the reviewer's read of student A's "
            "withdrawal row — are refused, and the reviewer role has no override here any "
            "more than it does over the rest of the vault."
        ),
    ),
    *_row(
        "consents",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0013 adds no INSERT policy at all, deliberately — not even for the owning "
            "student: 'one row per grant or withdrawal' (append-only) is enforced by there "
            "being NO client-reachable write path whatsoever, the same way "
            "guardian_consents' token column is protected by omission rather than a check. "
            "The only writer is withdraw_account(), a SECURITY DEFINER function that "
            "bypasses RLS via its owner's privileges, not a grant — so even student A, "
            "inserting a row for themselves, is refused (42501) through the ordinary API."
        ),
    ),
    *_row(
        "consents",
        UPDATE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0013 adds no UPDATE policy (a FOR SELECT policy does not extend to UPDATE's "
            "own row-visibility check) — same 'no applicable policy' shape "
            "guardian_consents' UPDATE cells already document: the row is filtered to "
            "nothing for this operation, so the update matches zero rows rather than "
            "erroring. Append-only in practice: nothing can ever change a consents row "
            "once written."
        ),
    ),
    *_row(
        "consents",
        DELETE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0013, DELETE side — same reasoning as UPDATE above.",
    ),
    *_row(
        "safeguarding_staff",
        SELECT,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0013: RLS enabled with NO policy at all, mirroring `reviewers` (0001) exactly "
            "— 'only is_safeguarding_staff() touches it'. Zero matching policies means zero "
            "rows for every role, including a role that happens to itself be safeguarding "
            "staff reading someone ELSE's row (this matrix's four canonical roles never "
            "include a safeguarding-staff member, the same scope limit already true for "
            "`reviewers`' own target row)."
        ),
    ),
    *_row(
        "safeguarding_staff",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0013, no policy: an INSERT with no permissive policy fails the RLS check "
            "outright (42501). Self-promotion to safeguarding staff is impossible through "
            "the API — only the service role can add a row, same as `reviewers`."
        ),
    ),
    *_row(
        "safeguarding_staff",
        UPDATE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0013, no policy: nothing is visible to update.",
    ),
    *_row(
        "safeguarding_staff",
        DELETE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0013, no policy: nothing is visible to delete.",
    ),
    *_row(
        "safeguarding_flags",
        SELECT,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0013 safeguarding_flags_select_staff: `for select using "
            "(is_safeguarding_staff())`. Staff-only, docs/CONSENT.md section 6: 'students "
            "AND content reviewers read ZERO rows of safeguarding_flags'. The target row "
            "concerns student A herself, and even SHE is denied — this is deliberately "
            "narrower than the rest of the student vault (student_profiles/saved_plans), "
            "where the OWNING student is always the one role that IS allowed. `guest` is "
            "DENY_ERROR, not DENY_EMPTY, since the adversarial-review fix that closed "
            "is_safeguarding_staff()'s anon-key admission/staff oracle (0013's own comment "
            "on that function) revoked its EXECUTE grant from `anon` entirely — an anon "
            "caller now gets 'permission denied for function is_safeguarding_staff' (42501) "
            "evaluating this policy's USING clause, a stronger deny than the previous "
            "'filtered to zero rows'. `authenticated` (student_a/b, reviewer) keeps its own "
            "EXECUTE grant, so their RLS check still just filters to zero rows as before."
        ),
    ),
    *_row(
        "safeguarding_flags",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0013 adds no INSERT policy: the Phase-2 distress-keyword detection logic that "
            "will someday write these rows is not built by this task (docs/CONSENT.md "
            "section 6) and gets its own write path when it exists. No permissive policy "
            "means 42501 for every role today, including a safeguarding-staff member."
        ),
    ),
    *_row(
        "safeguarding_flags",
        UPDATE,
        guest=ERROR,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0013, no UPDATE policy — same 'FOR SELECT does not extend to UPDATE' reasoning "
            "as consents above: filtered to zero rows, not an error for `authenticated` "
            "roles (student_a/b, reviewer). `guest` is the one exception, DENY_ERROR not "
            "DENY_EMPTY (adversarial-review fix, this session, live-observed): PostgREST's "
            "UPDATE still touches this table's own (only) policy, "
            "safeguarding_flags_select_staff — `using (is_safeguarding_staff())` — while "
            "planning the request, and `anon` lost EXECUTE on is_safeguarding_staff() "
            "entirely (0013's own comment on that function), so the guest role gets a flat "
            "42501 'permission denied for function' rather than reaching the 'no UPDATE "
            "policy' zero-match case at all."
        ),
    ),
    *_row(
        "safeguarding_flags",
        DELETE,
        guest=EMPTY,
        student_a=EMPTY,
        student_b=EMPTY,
        reviewer=EMPTY,
        why="0013, DELETE side — same reasoning as UPDATE above.",
    ),
)


# =====================================================================
# AI spend accounting — readable by its own account, writable by nobody
# (db/migrations/0011_ai_usage.sql)
# =====================================================================
# Two tables with deliberately different shapes:
#
#   * `ai_usage` is the only table in this matrix where SELECT is granted
#     but no write is. The two SECURITY DEFINER functions (`ai_reserve`,
#     `ai_settle`) are the sole way a row is created or changed, so
#     "nobody may write" is enforced by the missing GRANT — a flat
#     permission-denied that no future permissive policy can widen by
#     accident — rather than by a policy that happens to match nothing.
#   * `ai_usage_caps` is the spend kill switch and is sealed outright,
#     exactly like `app_settings`: reading it tells a caller how much
#     budget is left to burn; writing it removes the cap.
#
# NOT covered here, deliberately: the `ai_usage_daily_totals` aggregate
# view, which is what a reviewer gets instead of row access. The guard in
# test_access_matrix.py reads `pg_tables`, which excludes views, so a row
# here would be a hard failure under BCION_REQUIRE_LIVE=1 rather than
# coverage. Its four per-role expectations are explicit assertions in
# tests/db/test_ai_usage.py
# (`test_only_a_reviewer_may_read_the_aggregate_view`).
_AI_USAGE: tuple[Cell, ...] = (
    *_row(
        "ai_usage",
        SELECT,
        guest=EMPTY,
        student_a=ALLOW,
        student_b=EMPTY,
        reviewer=EMPTY,
        why=(
            "0011 ai_usage_select_own: `using (identity_kind = 'account' and auth.uid() is "
            "not null and identity_hash = ai_identity_hash(auth.uid()::text))`. The hash is "
            "derived from the caller's own JWT, never supplied by the client, so knowing "
            "another student's account id buys nothing. A guest has no auth.uid() at all; a "
            "reviewer gets the identity-free `ai_usage_daily_totals` view instead, covered "
            "in tests/db/test_ai_usage.py, not here (the guard reads pg_tables, which "
            "excludes views)."
        ),
    ),
    *_row(
        "ai_usage",
        INSERT,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "0011 grants SELECT and only SELECT to anon/authenticated (`revoke all ... ; "
            "grant select ...`). A reservation may only be created by the SECURITY DEFINER "
            "`ai_reserve()`, which checks the caps in the same transaction — so even student "
            "A cannot write their OWN row here (42501). An insert that worked would be an "
            "uncapped call."
        ),
    ),
    *_row(
        "ai_usage",
        UPDATE,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "Same missing grant, UPDATE side: settlement happens through `ai_settle()`, which "
            "refuses to report more calls than were reserved and refuses to settle a row "
            "twice. A caller who could UPDATE directly could rewrite their own recorded "
            "spend to zero. PRIVILEGE denial, so an error rather than an empty result."
        ),
    ),
    *_row(
        "ai_usage",
        DELETE,
        guest=ERROR,
        student_a=ERROR,
        student_b=ERROR,
        reviewer=ERROR,
        why=(
            "Same missing grant, DELETE side. A spend record that its own subject can delete "
            "is not a record; deleting rows is also how a cap would be reset, since every cap "
            "is computed from the rows that exist."
        ),
    ),
    *_no_api_access(
        "ai_usage_caps",
        why=(
            "0011: RLS enabled with NO policy, AND `revoke all on table ai_usage_caps from "
            "anon, authenticated` — the same sealed shape as 0007's `app_settings`. The caps "
            "are the AI spend kill switch: a client that can read them learns exactly how "
            "much is left to burn, and one that can write them has no cap at all. Only the "
            "definer functions (running as owner) and the service role read this row."
        ),
    ),
)


# =====================================================================
# Not built in this pilot — placeholders that fail loudly when built
# =====================================================================
# docs/SECURITY.md's matrix names five operations: read/write/delete/
# **export**/**storage**. Neither exists in BCION Lite today — there is
# no export route and no Supabase Storage bucket. Skipping them would
# make "the matrix is complete" a lie by omission and, worse, a silent
# one: the day somebody ships a CSV export of a student's plan, or a
# bucket for a scanned marksheet, nothing here would notice.
#
# So each is a cell with `Outcome.UNBUILT`, carried by an
# `xfail(strict=True)` test that asserts the capability EXISTS. Today
# that assertion fails, so the cell xfails. The moment export or storage
# is built the assertion starts passing, the strict xfail turns the XPASS
# into a failure, and whoever built it has to come back here and write
# the four real per-role expectations.
_UNBUILT: tuple[Cell, ...] = tuple(
    Cell(
        role,
        table="not-built",
        operation=operation,
        expected=Outcome.UNBUILT,
        why=(
            f"docs/SECURITY.md's matrix includes {operation.value}, and BCION Lite has not "
            f"built it. Placeholder only: xfail(strict=True), so this goes red the day "
            f"{operation.value} exists and these four cells have not been filled in with "
            "real per-role expectations."
        ),
    )
    for operation in UNBUILT_OPERATIONS
    for role in Role
)


MATRIX: tuple[Cell, ...] = (
    *_PUBLIC_KB,
    *_CLAIMS,
    *_REVIEWERS,
    *_STUDENT_VAULT,
    *_CONSENT_GATE,
    *_CONSENT_4,
    *_SEALED,
    *_AI_USAGE,
    *_UNBUILT,
)

#: The cells that run against the live database.
CORE_CELLS: tuple[Cell, ...] = tuple(c for c in MATRIX if c.operation in CORE_OPERATIONS)

#: The export/storage placeholders.
UNBUILT_CELLS: tuple[Cell, ...] = tuple(c for c in MATRIX if c.expected is Outcome.UNBUILT)

#: Every table the matrix claims to cover.
COVERED_TABLES: frozenset[str] = frozenset(c.table for c in CORE_CELLS)


def missing_coverage(live_tables: frozenset[str]) -> dict[str, list[str]]:
    """Every live public table with no matrix row, or an incomplete one.

    The guard test turns a non-empty result into a failure. "Incomplete"
    is checked as well as "absent" on purpose: a table with one lonely
    `guest`/`select` row would otherwise satisfy a bare "has at least one
    row" check while saying nothing at all about student B or a reviewer.
    """
    gaps: dict[str, list[str]] = {}
    for table in sorted(live_tables):
        covered = {(c.role, c.operation) for c in CORE_CELLS if c.table == table}
        if not covered:
            gaps[table] = ["no rows in the matrix at all"]
            continue
        wanted = [
            f"{role.value}/{operation.value}"
            for operation in CORE_OPERATIONS
            for role in Role
            if (role, operation) not in covered
        ]
        if wanted:
            gaps[table] = wanted
    return gaps


def tables_not_in_database(live_tables: frozenset[str]) -> list[str]:
    """Matrix tables the live database does not have — i.e. this stack is
    behind on migrations (or a table was dropped and the matrix kept a
    stale row)."""
    return sorted(COVERED_TABLES - live_tables)
