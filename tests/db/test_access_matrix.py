"""Runs tests/db/access_matrix.py against the live stack, and guards it.

Three things live here, in ascending order of how much they matter:

1. **One parametrized test per matrix cell.** Acting as guest / student
   A / student B / reviewer, over the same RLS-scoped clients
   tests/db/conftest.py already builds for every other file in this
   directory. Never as the service role — that bypasses RLS and would
   turn this whole file green for the wrong reason (docs/SECURITY.md:
   "tests must NOT run as the database owner").

2. **The guard** (`psycopg`, straight at the local Postgres): every
   table in the `public` schema must have row-level security enabled,
   and must be covered by the matrix. This is what makes the matrix
   *declarative* rather than merely long — a table added by a future
   migration and forgotten here fails the run instead of quietly
   enjoying no coverage at all.

3. **Placeholders for export and storage**, the two operations
   docs/SECURITY.md's matrix names that this pilot has not built.
   `xfail(strict=True)`, so they fail-as-expected today and go RED the
   day the capability appears (see access_matrix.py's own note).

WHERE THE SERVICE ROLE IS AND IS NOT USED
-----------------------------------------
`admin_client` (service role) seeds and deletes the target rows, which
is exactly the contract tests/db/conftest.py states for it: "TEST
SETUP/TEARDOWN ONLY — never used to make an assertion about what a real
user can or can't do". Two consequences are deliberate:

  * Every seed asserts the row it just wrote came back. A "deny" cell
    proves nothing if the row it was denied access to never existed, so
    that possibility is closed at seed time, not hoped about.
  * After a `DENY_EMPTY` update or delete, the seeded row is re-read as
    the service role to confirm it is STILL THERE. That is a check on
    the state of the database, not on anybody's permissions — the deny
    itself was already established by the role's own empty response.

`psycopg` connects as the local stack's superuser and is used ONLY to
read catalogue metadata (`pg_tables`, `pg_proc`) for the guard. It never
touches application rows and never stands in for a role.

One more thing that is not decoration: every client a cell touches is
released at teardown (`_release`). 224 cells is enough volume that the
leaked refresh-token threads behind each signed-in client will otherwise
exhaust the process — see that function's own docstring for the measured
numbers.

The psycopg connection carries its own loopback check on `DATABASE_URL`,
independent of the `SUPABASE_URL` guard in tests/db/conftest.py: this is
a second door into the same database, and a safety property that only
holds for one of the two doors is not a safety property.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import urlsplit

import psycopg
import pytest
from postgrest.exceptions import APIError
from postgrest.types import ReturnMethod
from supabase import Client

from app.ai.budget_db import identity_digest
from tests.db.access_matrix import (
    CORE_CELLS,
    TABLE_TARGETS,
    UNBUILT_CELLS,
    Cell,
    Operation,
    Outcome,
    Role,
    cell_id,
    missing_coverage,
    tables_not_in_database,
)
from tests.db.conftest import (
    _require_live,  # the one definition of "skips are failures now"; see conftest
    run_email,
    run_name,
)

# --------------------------------------------------------------------
# Shared vocabulary
# --------------------------------------------------------------------
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

#: SQLSTATE / PostgREST codes that mean "you were refused", as opposed
#: to "your request was broken". 42501 covers both shapes Postgres uses:
#: `new row violates row-level security policy` (a WITH CHECK failure)
#: and `permission denied for table` (a revoked grant). PGRST205 is
#: PostgREST's "not found in the schema cache", which is what a table no
#: API role holds any privilege on looks like from outside.
_AUTHORISATION_ERROR_CODES = frozenset({"42501", "PGRST205"})

_GUARDIAN_EMAIL = "qa6-matrix-guardian@example.invalid"
#: Comfortably adult, so db/migrations/0004's
#: `enforce_account_status_matches_age()` trigger is not the thing under
#: test when a `student_accounts` row is created as 'active'.
_ADULT_DOB = "1990-01-01"


def _unavailable(reason: str) -> NoReturn:
    """Skip — or, under BCION_REQUIRE_LIVE=1, fail — exactly like the
    per-migration gates in tests/db/conftest.py do. "Green" must never
    be able to mean "did not run"."""
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


# --------------------------------------------------------------------
# The live catalogue (psycopg — metadata only)
# --------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Catalogue:
    tables: frozenset[str]
    rls_disabled: tuple[str, ...]
    function_names: frozenset[str]
    #: None when the stack has no storage schema at all (this one does
    #: not: supabase/config.toml leaves the storage service off).
    storage_bucket_count: int | None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        _unavailable(
            "DATABASE_URL is not set, so the RLS/coverage guard cannot read the "
            "catalogue. `make test-db-up` writes it into .env.test from the local "
            "stack (mk/testdb.mk); see .env.test.example."
        )
    host = (urlsplit(url).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        # Never a skip: a non-local target is a refusal, not a gap.
        pytest.fail(
            f"REFUSING TO CONNECT: DATABASE_URL points at {host!r}, which is not a "
            "local stack. The same rule tests/db/conftest.py applies to SUPABASE_URL "
            "applies here — this suite is only ever safe against the throwaway "
            "`supabase start` stack (CLAUDE.md).",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def catalogue() -> Catalogue:
    """Catalogue metadata only — never application rows."""
    with (
        psycopg.connect(_database_url(), connect_timeout=10) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("select tablename, rowsecurity from pg_tables where schemaname = 'public'")
        rows = cursor.fetchall()
        cursor.execute(
            "select p.proname from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public'"
        )
        functions = frozenset(str(row[0]) for row in cursor.fetchall())
        cursor.execute("select to_regclass('storage.buckets')")
        storage_row = cursor.fetchone()
        buckets: int | None = None
        if storage_row is not None and storage_row[0] is not None:
            cursor.execute("select count(*) from storage.buckets")
            count_row = cursor.fetchone()
            buckets = int(count_row[0]) if count_row is not None else 0
    return Catalogue(
        tables=frozenset(str(name) for name, _rls in rows),
        rls_disabled=tuple(sorted(str(name) for name, rls in rows if not rls)),
        function_names=functions,
        storage_bucket_count=buckets,
    )


# --------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------
class TestTheGuard:
    """What stops this matrix from rotting into a list of the tables
    somebody happened to think about in September 2026."""

    def test_every_public_table_has_row_level_security_enabled(
        self, catalogue: Catalogue
    ) -> None:
        assert not catalogue.rls_disabled, (
            "These public tables have RLS switched OFF entirely, so every policy "
            "written for them is decorative and any API role can read the lot: "
            f"{', '.join(catalogue.rls_disabled)}. Add `alter table <t> enable row "
            "level security;` to the migration that created each one (never edit an "
            "applied migration — write a new numbered file)."
        )

    def test_every_public_table_is_covered_by_the_matrix(self, catalogue: Catalogue) -> None:
        gaps = missing_coverage(catalogue.tables)
        report = "\n".join(f"  {table}: {', '.join(missing)}" for table, missing in gaps.items())
        assert not gaps, (
            "Every table in the public schema needs a row in "
            "tests/db/access_matrix.py for all four roles and all four operations. "
            f"Missing:\n{report}\n"
            "This failure is the entire point of the guard: a table added by a "
            "migration and never added here would otherwise have NO cross-user "
            "coverage at all, and nothing would say so (CLAUDE.md: cross-user access "
            "is tested every time auth, RLS or publication changes)."
        )

    def test_the_matrix_names_no_table_this_stack_does_not_have(
        self, catalogue: Catalogue
    ) -> None:
        """The other direction. Not a matrix bug in the normal case — it
        means this stack is behind on db/migrations/, which is the same
        condition tests/db/conftest.py's per-file gates skip for."""
        missing = tables_not_in_database(catalogue.tables)
        if missing:
            _unavailable(
                f"The matrix covers tables this stack does not have: {', '.join(missing)}. "
                "Run `make test-db-up` (or `make test-db-reset`) to apply "
                "db/migrations/*.sql; see db/migrations/README.md."
            )

    def test_every_matrix_table_is_seedable_and_documented(self) -> None:
        """A self-check that needs no database: adding a table to the
        matrix without telling this file how to build its target row
        would otherwise fail 16 times with an unhelpful KeyError."""
        tables = sorted({cell.table for cell in CORE_CELLS})
        unbuildable = [table for table in tables if table not in _PROBE_BUILDERS]
        undocumented = [table for table in tables if table not in TABLE_TARGETS]
        assert not unbuildable, (
            f"These matrix tables have no probe builder in _PROBE_BUILDERS: {unbuildable}. "
            "Add one that says how to seed the canonical target row and what an insert "
            "into that table looks like."
        )
        assert not undocumented, (
            f"These matrix tables have no entry in access_matrix.TABLE_TARGETS: "
            f"{undocumented}. Every expectation is about a specific row; say which one."
        )


# --------------------------------------------------------------------
# Role clients (conftest.py's fixtures, released after use)
# --------------------------------------------------------------------
def _release(client: Client) -> None:
    """Give back the OS resources one supabase client is holding.

    Measured, not precautionary (2026-09-22, local stack, Python 3.12 on
    Windows): without it, `pytest tests/db` climbs to ~256 live threads
    and ~510 live httpx clients partway through this file and then dies
    with `OSError: [Errno 24] Too many open files`, taking every test
    file after it down as well — 24 failed, 221 errors. With it, the
    same run sits at 2-3 threads and ~30 clients throughout.

    The mechanism: signing a user in starts a refresh-token
    `threading.Timer` (supabase_auth's `_start_auto_refresh_token`)
    whose callback closes over the auth client, so a LIVE THREAD keeps
    the whole client reachable — it is not garbage, and no amount of
    `gc.collect()` will reclaim it or its pooled sockets. Cancelling the
    timer is therefore the load-bearing line; the two closes just return
    the sockets immediately rather than at the next collection.

    Cancelling also removes a smaller, real nuisance: a timer that fires
    after tests/db/conftest.py has deleted the throwaway user it belongs
    to logs a failed token refresh from a background thread, in the
    middle of some unrelated test's output.

    This file can only do this for the clients IT uses. The clients are
    created by tests/db/conftest.py's fixtures, which every file in this
    directory shares, so the durable fix belongs there — flagged to the
    lead rather than done here, since that file is not this task's to
    change. Releasing after use is safe for a shared fixture because
    those fixtures are function-scoped and their own teardown only ever
    uses `admin_client`, never the client handed to the test.
    """
    auth = getattr(client, "auth", None)
    timer = getattr(auth, "_refresh_token_timer", None)
    if timer is not None:
        with contextlib.suppress(Exception):
            timer.cancel()
        with contextlib.suppress(Exception):
            auth._refresh_token_timer = None
    if auth is not None:
        with contextlib.suppress(Exception):
            auth.close()
    # `postgrest` is built lazily on first `.table()`; touching the
    # public property would construct one just to close it.
    postgrest = getattr(client, "_postgrest", None)
    if postgrest is not None:
        with contextlib.suppress(Exception):
            postgrest.aclose()


class _ClientPool:
    """Hands out conftest.py's RLS-scoped clients and remembers them, so
    every one this test touched can be released at teardown.

    Lazy on purpose (`getfixturevalue`, not a fixture argument): a cell
    about the public knowledge base must not pay for a student sign-up
    it never uses.
    """

    def __init__(self, request: pytest.FixtureRequest) -> None:
        self._request = request
        self._opened: dict[int, Client] = {}

    def _remember(self, client: Client) -> Client:
        self._opened[id(client)] = client
        return client

    def acting(self, role: Role) -> Client:
        if role is Role.GUEST:
            guest: Client = self._request.getfixturevalue("guest_client")
            return self._remember(guest)
        return self._remember(self.user(role.value)[1])

    def user(self, fixture_name: str) -> tuple[str, Client]:
        """`student_a` / `student_b` / `reviewer` — (user id, client).
        `getfixturevalue` caches, so asking twice in one test is the
        same user, not a second sign-up."""
        user_id, client = self._request.getfixturevalue(fixture_name)
        return str(user_id), self._remember(client)

    def release_all(self) -> None:
        for client in self._opened.values():
            _release(client)
        self._opened.clear()


@pytest.fixture
def clients(request: pytest.FixtureRequest) -> Iterator[_ClientPool]:
    pool = _ClientPool(request)
    try:
        yield pool
    finally:
        pool.release_all()


# --------------------------------------------------------------------
# Seeding (service role — setup and teardown only)
# --------------------------------------------------------------------
class _Seeds:
    """Builds the canonical target row for one cell, and takes it away
    again afterwards.

    Every builder is memoised, so a table that needs a pathway (which
    needs a career) seeds each parent exactly once per test. Teardown is
    LIFO, i.e. children before parents, which matters for the one
    relationship the schema does not cascade: `claims.created_by`
    references `auth.users` with no `on delete cascade` (0001_init.sql),
    so the claim must go before the user who made it.
    """

    def __init__(self, admin: Client, clients: _ClientPool) -> None:
        self._admin = admin
        self._clients = clients
        self._undo: list[Callable[[], None]] = []
        self._memo: dict[str, str] = {}

    # -- plumbing ----------------------------------------------------
    def _insert(self, table: str, payload: dict[str, Any], pk: str = "id") -> str:
        response = self._admin.table(table).insert(payload).execute()
        assert response.data, (
            f"seeding {table} returned no row — every 'deny' expectation below would "
            "then be vacuously true, so this is a hard stop, not a warning"
        )
        key = str(response.data[0][pk])
        self.delete_later(table, pk, key)
        return key

    def delete_later(self, table: str, pk: str, value: Any) -> None:
        self.delete_later_where(table, {pk: value})

    def delete_later_where(self, table: str, filters: dict[str, Any]) -> None:
        """Register a teardown delete for a row that may or may not
        exist yet — deleting nothing is a no-op, so this is registered
        BEFORE an insert probe runs rather than after, and therefore
        also catches a row created by a surprise ALLOW on a cell that
        expected a deny."""

        def _drop() -> None:
            query = self._admin.table(table).delete()
            for column, value in filters.items():
                query = query.eq(column, value)
            query.execute()

        self._undo.append(_drop)

    def _once(self, name: str, build: Callable[[], str]) -> str:
        if name not in self._memo:
            self._memo[name] = build()
        return self._memo[name]

    def cleanup(self) -> None:
        for undo in reversed(self._undo):
            try:
                undo()
            except Exception as exc:  # noqa: BLE001 — cleanup must never mask a result
                print(f"[access-matrix] cleanup step failed: {exc}")  # noqa: T201
        self._undo.clear()

    def row_exists(self, table: str, pk: str, value: Any) -> bool:
        """State check, not a permissions check — see the module
        docstring. Used to prove a denied UPDATE/DELETE really was a
        no-op rather than a silent success."""
        return self.rows_exist(table, {pk: value})

    def rows_exist(self, table: str, filters: dict[str, Any]) -> bool:
        query = self._admin.table(table).select("*")
        for column, value in filters.items():
            query = query.eq(column, value)
        return bool(query.execute().data)

    # -- the people --------------------------------------------------
    def student_a_id(self) -> str:
        """Student A's user id, whichever role is acting — the owner of
        every canonical row in the student vault, so student B's and the
        reviewer's cells have somebody real to fail against."""
        return self._clients.user("student_a")[0]

    def maker_id(self) -> str:
        """A throwaway user who is nobody in this test: used as a
        claim's author, and as the subject of the `reviewers` row. No
        sign-in, so this costs one GoTrue call rather than three."""

        def _build() -> str:
            created = self._admin.auth.admin.create_user(
                {
                    "email": run_email("qa6-matrix-maker"),
                    "password": uuid.uuid4().hex,
                    "email_confirm": True,
                }
            )
            user_id = str(created.user.id)
            self._undo.append(lambda: self._admin.auth.admin.delete_user(user_id))
            return user_id

        return self._once("maker", _build)

    # -- the rows ----------------------------------------------------
    def source_id(self) -> str:
        return self._once(
            "source",
            lambda: self._insert(
                "sources",
                {
                    "authority_name": run_name("QA-6 ACCESS MATRIX — not a real authority"),
                    "official_url": "https://example.invalid/qa-6-access-matrix",
                    "source_type": "synthetic",
                },
            ),
        )

    def career_id(self) -> str:
        return self._once(
            "career",
            lambda: self._insert(
                "careers", {"name": run_name("QA-6 access matrix career (SYNTHETIC)")}
            ),
        )

    def pathway_id(self) -> str:
        return self._once(
            "pathway",
            lambda: self._insert(
                "pathways",
                {
                    "career_id": self.career_id(),
                    "name": run_name("QA-6 access matrix pathway (SYNTHETIC)"),
                    "description": "Synthetic fixture for the cross-user access matrix.",
                },
            ),
        )

    def claim_id(self) -> str:
        return self._once("claim", lambda: self._insert("claims", self.claim_payload()))

    def claim_payload(self) -> dict[str, Any]:
        """A DRAFT claim with a real author and no reviewer yet.

        `created_by` is deliberately non-null: 0003's
        `claims_update_reviewers` requires `reviewed_by is distinct from
        created_by`, and with both null that is FALSE — a reviewer would
        be denied for maker-checker reasons that have nothing to do with
        the access question this matrix asks.
        """
        return {
            "entity_type": "Career",
            "entity_id": self.career_id(),
            "field": "name",
            "value": "QA-6 access matrix probe (SYNTHETIC, never published)",
            "source_id": self.source_id(),
            "verification_date": "2026-01-01",
            "verifier": run_name("qa-6-access-matrix"),
            "status": "draft",
            "review_due_date": "2099-01-01",
            "created_by": self.maker_id(),
        }

    def reviewer_row_id(self) -> str:
        return self._once(
            "reviewer_row",
            lambda: self._insert("reviewers", {"user_id": self.maker_id()}, pk="user_id"),
        )

    def profile_id(self) -> str:
        return self._once(
            "profile",
            lambda: self._insert("student_profiles", self.profile_payload()),
        )

    def profile_payload(self) -> dict[str, Any]:
        return {"id": self.student_a_id(), "current_class": "Class 10", "language": "en"}

    def plan_id(self) -> str:
        return self._once("plan", lambda: self._insert("saved_plans", self.plan_payload()))

    def plan_payload(self) -> dict[str, Any]:
        return {
            "student_id": self.student_a_id(),
            "pathway_id": self.pathway_id(),
            "notes": "QA-6 access matrix probe",
        }

    def action_id(self) -> str:
        return self._once("action", lambda: self._insert("plan_actions", self.action_payload()))

    def action_payload(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id(), "action_key": "check_entry_requirements"}

    def account_id(self) -> str:
        return self._once(
            "account", lambda: self._insert("student_accounts", self.account_payload())
        )

    def account_payload(self) -> dict[str, Any]:
        return {
            "id": self.student_a_id(),
            "date_of_birth": _ADULT_DOB,
            "account_status": "active",
        }

    def consent_id(self) -> str:
        return self._once(
            "consent", lambda: self._insert("guardian_consents", self.consent_payload())
        )

    def consent_payload(self) -> dict[str, Any]:
        # `token`/`expires_at` are omitted deliberately: 0004's
        # enforce_guardian_consent_server_token() trigger sets both, and
        # sending one would be pretending a client can choose the
        # credential.
        return {"student_id": self.student_a_id(), "guardian_email": _GUARDIAN_EMAIL}


@pytest.fixture
def seeds(clients: _ClientPool, admin_client: Client) -> Iterator[_Seeds]:
    fixtures = _Seeds(admin_client, clients)
    try:
        yield fixtures
    finally:
        # Runs BEFORE the `clients` pool is released (this fixture is set
        # up after it, so it is finalised first) — and it only ever uses
        # `admin_client`, which the pool never touches.
        fixtures.cleanup()




# --------------------------------------------------------------------
# What each table's probe looks like
# --------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Probe:
    pk: str
    #: The canonical target row's key. None for an INSERT, where the
    #: whole point is that the row does not exist yet.
    target: Any
    insert_payload: dict[str, Any]
    update_payload: dict[str, Any]
    #: Equality filters that identify the row `insert_payload` would
    #: create. Used for two things, both because an INSERT here is sent
    #: with `Prefer: return=minimal` and therefore echoes nothing back
    #: (see `_execute`): tearing the row down afterwards, and confirming
    #: — as the service role, a state check — that an ALLOW really did
    #: write it. None means "no row could ever be created here, and
    #: there is nothing safe to delete": `app_settings` holds a single
    #: pre-existing row that this test must never remove, and
    #: `_schema_migrations` is not reachable through PostgREST by any
    #: role at all, service role included.
    insert_filter: dict[str, Any] | None = None


def _unique(label: str) -> str:
    """A run-tagged name that is also unique to THIS call.

    `run_name` alone is deterministic for a given label, which is fine
    for a row seeded once per test but not for the row an INSERT probe
    creates: two cells (or two pytest-xdist workers of one run, which
    share a RUN_ID by design) would otherwise produce identical names
    and each other's cleanup could delete the other's row mid-test.
    """
    return run_name(f"{label} {uuid.uuid4().hex[:8]}")


def _probe_sources(operation: Operation, seeds: _Seeds) -> _Probe:
    authority = _unique("QA-6 matrix insert probe — not a real authority")
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.source_id(),
        insert_payload={
            "authority_name": authority,
            "official_url": "https://example.invalid/qa-6-insert-probe",
            "source_type": "synthetic",
        },
        update_payload={"authority_name": _unique("QA-6 matrix probe (updated)")},
        insert_filter={"authority_name": authority},
    )


def _probe_careers(operation: Operation, seeds: _Seeds) -> _Probe:
    name = _unique("QA-6 matrix insert probe career (SYNTHETIC)")
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.career_id(),
        insert_payload={"name": name},
        update_payload={"name": _unique("QA-6 matrix probe career (updated, SYNTHETIC)")},
        insert_filter={"name": name},
    )


def _probe_pathways(operation: Operation, seeds: _Seeds) -> _Probe:
    name = _unique("QA-6 matrix insert probe pathway (SYNTHETIC)")
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.pathway_id(),
        insert_payload={
            "career_id": seeds.career_id(),
            "name": name,
            "description": "Synthetic fixture for the cross-user access matrix.",
        },
        update_payload={"description": "Updated by the QA-6 access matrix probe."},
        insert_filter={"name": name},
    )


def _probe_claims(operation: Operation, seeds: _Seeds) -> _Probe:
    # Inserted as 'draft' because 0003's enforce_claims_workflow()
    # trigger fires BEFORE the RLS check and refuses any other insert
    # status — a deny here has to be the RLS deny.
    payload = seeds.claim_payload()
    payload["verifier"] = _unique("qa-6-access-matrix insert probe")
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.claim_id(),
        insert_payload=payload,
        update_payload={"verifier": _unique("qa-6-access-matrix (updated)")},
        insert_filter={"verifier": payload["verifier"]},
    )


def _probe_reviewers(operation: Operation, seeds: _Seeds) -> _Probe:
    # A REAL user id, not a random uuid: this must fail because no
    # policy allows the write, not because a foreign key was broken.
    maker = seeds.maker_id()
    return _Probe(
        pk="user_id",
        target=None if operation is Operation.INSERT else seeds.reviewer_row_id(),
        insert_payload={"user_id": maker},
        update_payload={"added_at": "2026-01-01T00:00:00+00:00"},
        insert_filter={"user_id": maker},
    )


def _probe_student_profiles(operation: Operation, seeds: _Seeds) -> _Probe:
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.profile_id(),
        insert_payload=seeds.profile_payload(),
        update_payload={"current_class": "Class 12"},
        insert_filter={"id": seeds.student_a_id()},
    )


def _probe_saved_plans(operation: Operation, seeds: _Seeds) -> _Probe:
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.plan_id(),
        insert_payload=seeds.plan_payload(),
        update_payload={"notes": "QA-6 access matrix probe (updated)"},
        insert_filter={"student_id": seeds.student_a_id(), "pathway_id": seeds.pathway_id()},
    )


def _probe_plan_actions(operation: Operation, seeds: _Seeds) -> _Probe:
    payload = seeds.action_payload()
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.action_id(),
        insert_payload=payload,
        update_payload={"done": True},
        insert_filter={"plan_id": payload["plan_id"], "action_key": payload["action_key"]},
    )


def _probe_student_accounts(operation: Operation, seeds: _Seeds) -> _Probe:
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.account_id(),
        insert_payload=seeds.account_payload(),
        # A no-op value on purpose: if this ever stopped being denied,
        # the test must not be the thing that activates an account.
        update_payload={"account_status": "active"},
        insert_filter={"id": seeds.student_a_id()},
    )


def _probe_guardian_consents(operation: Operation, seeds: _Seeds) -> _Probe:
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else seeds.consent_id(),
        insert_payload=seeds.consent_payload(),
        update_payload={"guardian_email": "qa6-matrix-elsewhere@example.invalid"},
        insert_filter={"student_id": seeds.student_a_id()},
    )


def _probe_app_settings(operation: Operation, seeds: _Seeds) -> _Probe:
    # The single row (`id boolean primary key check (id)`) already
    # exists; nothing to seed. `demo_mode: false` is the fail-closed
    # value, so even a catastrophic regression here cannot turn demo
    # mode ON from a test. `insert_filter` is None precisely BECAUSE the
    # only possible key is the live row's: registering a cleanup would
    # mean deleting the real demo-mode flag row at teardown.
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else True,
        insert_payload={"id": True, "demo_mode": False},
        update_payload={"demo_mode": False},
    )


def _probe_guest_sessions(operation: Operation, seeds: _Seeds) -> _Probe:
    # Deliberately not seeded: no API role holds any privilege on this
    # table, so the refusal happens before any row is considered.
    token_hash = f"qa6-matrix-{uuid.uuid4().hex}"
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else str(uuid.uuid4()),
        insert_payload={"token_hash": token_hash},
        update_payload={"token_hash": f"qa6-matrix-{uuid.uuid4().hex}"},
        insert_filter={"token_hash": token_hash},
    )


def _probe_guest_plans(operation: Operation, seeds: _Seeds) -> _Probe:
    # A REAL pathway id (seeded), not a random one: if the grants on this
    # table were ever restored, the insert must then fail on RLS — the
    # access answer — rather than on a broken foreign key, which
    # `_observe` would report as ERROR_OTHER and which would tell nobody
    # anything about access.
    session_id = str(uuid.uuid4())
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else str(uuid.uuid4()),
        insert_payload={
            "session_id": session_id,
            "pathway_id": seeds.pathway_id(),
            "estimated_additional_expenses": 0,
        },
        update_payload={"estimated_additional_expenses": 0},
        insert_filter={"session_id": session_id},
    )


def _probe_schema_migrations(operation: Operation, seeds: _Seeds) -> _Probe:
    # `insert_filter` is None: PostgREST exposes this table to no role
    # at all — not even the service role holds a grant on it — so there
    # is no cleanup this file could perform even if an insert somehow
    # landed. The filename is one no migration will ever have, so a
    # stray row could not be mistaken for an applied migration.
    return _Probe(
        pk="filename",
        target=None if operation is Operation.INSERT else "0001_init.sql",
        insert_payload={"filename": "qa6-access-matrix-probe-never-applied.sql"},
        update_payload={"applied_at": "2026-01-01T00:00:00+00:00"},
    )


def _probe_ai_usage(operation: Operation, seeds: _Seeds) -> _Probe:
    # The canonical row belongs to STUDENT A, keyed by the SHA-256 digest
    # of their account id — the same value `ai_usage_select_own` derives
    # from a caller's own JWT (db/migrations/0011_ai_usage.sql). Seeded as
    # the service role rather than through `ai_reserve()` on purpose: the
    # question this table's cells ask is about access, and going through
    # the definer function would make a busy stack's spend caps able to
    # fail the setup.
    identity_hash = identity_digest(seeds.student_a_id())
    template_id = _unique("qa-6-access-matrix insert probe")
    target = (
        None
        if operation is Operation.INSERT
        else seeds._once(
            "ai_usage",
            lambda: seeds._insert(
                "ai_usage",
                {
                    "identity_kind": "account",
                    "identity_hash": identity_hash,
                    "template_id": run_name("qa-6-access-matrix"),
                    "calls_reserved": 1,
                    "status": "reserved",
                },
            ),
        )
    )
    return _Probe(
        pk="id",
        target=target,
        insert_payload={
            "identity_kind": "account",
            "identity_hash": identity_hash,
            "template_id": template_id,
            "calls_reserved": 1,
            "status": "reserved",
        },
        # A no-op value: if this ever stopped being denied, the test must
        # not be the thing that rewrites a recorded spend upwards.
        update_payload={"calls_made": 0},
        insert_filter={"template_id": template_id},
    )


def _probe_ai_usage_caps(operation: Operation, seeds: _Seeds) -> _Probe:
    # The single row (`id boolean primary key check (id)`) is seeded by
    # the migration itself; nothing to create. `insert_filter` is None for
    # the same reason as `app_settings`: the only possible key is the live
    # row's, so registering a cleanup would mean deleting the real AI
    # spend caps at teardown. The update payload touches `updated_at`
    # only — a cell that expects a deny must never be the thing that
    # raises a spend cap if the deny ever breaks.
    return _Probe(
        pk="id",
        target=None if operation is Operation.INSERT else True,
        insert_payload={
            "id": True,
            "per_identity_daily_calls": 1,
            "global_daily_calls": 1,
            "global_monthly_calls": 1,
        },
        update_payload={"updated_at": "2026-01-01T00:00:00+00:00"},
    )


_PROBE_BUILDERS: dict[str, Callable[[Operation, _Seeds], _Probe]] = {
    "sources": _probe_sources,
    "careers": _probe_careers,
    "pathways": _probe_pathways,
    "claims": _probe_claims,
    "reviewers": _probe_reviewers,
    "student_profiles": _probe_student_profiles,
    "saved_plans": _probe_saved_plans,
    "plan_actions": _probe_plan_actions,
    "student_accounts": _probe_student_accounts,
    "guardian_consents": _probe_guardian_consents,
    "app_settings": _probe_app_settings,
    "guest_sessions": _probe_guest_sessions,
    "guest_plans": _probe_guest_plans,
    "_schema_migrations": _probe_schema_migrations,
    "ai_usage": _probe_ai_usage,
    "ai_usage_caps": _probe_ai_usage_caps,
}


# --------------------------------------------------------------------
# Acting as a role, and reading what happened
# --------------------------------------------------------------------
def _execute(client: Client, table: str, operation: Operation, probe: _Probe) -> Any:
    query = client.table(table)
    if operation is Operation.SELECT:
        return query.select("*").eq(probe.pk, probe.target).execute()
    if operation is Operation.INSERT:
        # `Prefer: return=minimal` — "do not hand the row back" — and
        # this is load-bearing, not a micro-optimisation.
        #
        # supabase-py's default is `return=representation`, which makes
        # PostgREST run INSERT ... RETURNING, and Postgres applies the
        # table's SELECT policies to a RETURNING row as well as the
        # INSERT policy's WITH CHECK to the write. On a table with no
        # SELECT policy at all (`guardian_consents`, deliberately — the
        # row holds a bearer token) that turns a PERMITTED insert into
        # "new row violates row-level security policy", which is
        # indistinguishable from a real access denial. 0005's own
        # docstring documents this after it broke every under-18
        # sign-up on the live database, with the fix confirmed live:
        # "the identical insert succeeds with the row actually written
        # when sent with `Prefer: return=minimal`".
        #
        # Asking for the row back would therefore have recorded "a
        # student may not create their own guardian-consent request" in
        # this matrix — false, and worse, a cell that would keep
        # passing if the INSERT policy were dropped tomorrow.
        return query.insert(probe.insert_payload, returning=ReturnMethod.minimal).execute()
    if operation is Operation.UPDATE:
        return query.update(probe.update_payload).eq(probe.pk, probe.target).execute()
    if operation is Operation.DELETE:
        return query.delete().eq(probe.pk, probe.target).execute()
    raise AssertionError(f"{operation} has no live probe — it is a placeholder cell")


def _observe(
    client: Client, table: str, operation: Operation, probe: _Probe
) -> tuple[Outcome, str]:
    """Run one cell and classify the result. See access_matrix.py's
    "OUTCOME VOCABULARY"."""
    try:
        response = _execute(client, table, operation, probe)
    except APIError as exc:
        detail = f"SQLSTATE/code {exc.code!r}: {exc.message!r}"
        if exc.code in _AUTHORISATION_ERROR_CODES:
            return Outcome.DENY_ERROR, detail
        return Outcome.ERROR_OTHER, detail

    if operation is Operation.INSERT:
        # Nothing comes back from a `return=minimal` insert, so "it did
        # not raise" is the whole client-side signal. The caller
        # re-checks the database itself for any cell that expects ALLOW.
        return Outcome.ALLOW, "accepted (return=minimal, so no row echoed)"

    rows = list(response.data or [])
    if not rows:
        return Outcome.DENY_EMPTY, "no error, zero rows"
    return Outcome.ALLOW, f"{len(rows)} row(s)"


@pytest.mark.parametrize("cell", CORE_CELLS, ids=cell_id)
def test_access_matrix_cell(
    cell: Cell, clients: _ClientPool, catalogue: Catalogue, seeds: _Seeds
) -> None:
    if cell.table not in catalogue.tables:
        _unavailable(
            f"{cell.table} is not in this stack's public schema — db/migrations/*.sql "
            "are not all applied. Run `make test-db-up`; see db/migrations/README.md."
        )

    probe = _PROBE_BUILDERS[cell.table](cell.operation, seeds)
    if cell.operation is Operation.INSERT and probe.insert_filter is not None:
        # Registered BEFORE the attempt, so a row created by a cell that
        # expected a deny is still cleaned up when the assertion fails.
        seeds.delete_later_where(cell.table, probe.insert_filter)

    client = clients.acting(cell.role)
    observed, detail = _observe(client, cell.table, cell.operation, probe)

    assert observed is cell.expected, (
        f"\nACCESS MATRIX CELL: {cell.role.value} / {cell.table} / {cell.operation.value}"
        f"\n  expected : {cell.expected.value}"
        f"\n  observed : {observed.value} ({detail})"
        f"\n  target   : {TABLE_TARGETS[cell.table]}"
        f"\n  why      : {cell.why}"
        "\nEither the policy changed (fix db/migrations — never edit an applied file) "
        "or the expectation in tests/db/access_matrix.py is wrong. Do not 'fix' this "
        "by editing the expectation until you have read the policy it cites."
    )

    # Two state checks (service role, never a permissions assertion —
    # see the module docstring), because "the client did not complain"
    # is not by itself evidence about the database.
    if (
        cell.expected is Outcome.DENY_EMPTY
        and cell.operation in (Operation.UPDATE, Operation.DELETE)
        and probe.target is not None
    ):
        assert seeds.row_exists(cell.table, probe.pk, probe.target), (
            f"{cell.role.value} was told they changed zero rows of {cell.table}, but the "
            "target row is gone — the write was NOT actually a no-op."
        )

    if (
        cell.expected is Outcome.ALLOW
        and cell.operation is Operation.INSERT
        and probe.insert_filter is not None
    ):
        assert seeds.rows_exist(cell.table, probe.insert_filter), (
            f"{cell.role.value}'s insert into {cell.table} was accepted, but no matching "
            f"row exists ({probe.insert_filter}). An ALLOW cell has to mean the row was "
            "actually written."
        )


# --------------------------------------------------------------------
# export / storage — not built, and loudly so
# --------------------------------------------------------------------
def _export_surfaces(catalogue: Catalogue) -> list[str]:
    """Anything that looks like a data export: an HTTP route or a
    database function whose name says so."""
    from app.main import app

    routes = [
        str(path)
        for route in app.routes
        if "export" in (path := getattr(route, "path", "")).lower()
    ]
    return routes + sorted(name for name in catalogue.function_names if "export" in name.lower())


def _capability_is_built(operation: Operation, catalogue: Catalogue) -> list[str]:
    if operation is Operation.EXPORT:
        return _export_surfaces(catalogue)
    if operation is Operation.STORAGE:
        count = catalogue.storage_bucket_count
        return [f"{count} storage bucket(s)"] if count else []
    raise AssertionError(f"{operation} is not a placeholder capability")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "export and storage are in docs/SECURITY.md's access matrix but are NOT built "
        "in BCION Lite. These placeholders are expected to fail. strict=True means the "
        "day one of them IS built, this xfail becomes an XPASS and the run goes red — "
        "at which point replace the placeholder with four real per-role cells in "
        "tests/db/access_matrix.py."
    ),
)
@pytest.mark.parametrize("cell", UNBUILT_CELLS, ids=cell_id)
def test_unbuilt_capability_placeholder(cell: Cell, catalogue: Catalogue) -> None:
    surfaces = _capability_is_built(cell.operation, catalogue)
    assert surfaces, (
        f"No {cell.operation.value} capability exists yet, so there is nothing for the "
        f"{cell.role.value} row of the access matrix to assert. {cell.why}"
    )
