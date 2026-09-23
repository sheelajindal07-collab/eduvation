"""SEC-6 — a standing exposure catalogue guard, independent of the access
matrix.

`tests/db/test_access_matrix.py` already asserts "every public table has
RLS enabled" as part of its own declarative-coverage guard. This file is
a SEPARATE, narrower-purpose catalogue check (per SEC-6's own task card)
that reads the same `pg_catalog` metadata directly over `psycopg` and
fails the run if:

1. ANY `public`-schema table has row-level security switched off.
2. ANY `public`-schema view is not `security_invoker` — with one named,
   reviewed exception (`ai_usage_daily_totals`, see
   `_ALLOWED_NON_INVOKER_VIEWS` below).
3. ANY storage bucket exists without at least one RLS policy on
   `storage.objects` that actually mentions it.

Deliberately duplicates test_access_matrix.py's table-RLS query rather
than importing it: this file must stand on its own as "the exposure
catalogue", not become unreadable if that file's own fixtures change
shape. Every `psycopg` connection here reads catalogue metadata ONLY —
never an application row, never a stand-in for a role's own access
(docs/SECURITY.md: "tests must NOT run as the database owner" is about
ASSERTIONS on behalf of a role; reading `pg_catalog` is not that).

Every check below has been revert-to-proved in this file itself
(`.claude/agents/migration-owner.md`'s own rule): weakened live, run
red, restored, run green again — see each `TestRevertToProve*` class.
The one exception is the storage-bucket check's revert-to-prove, which
runs at the LOGIC level (`buckets_without_a_policy`, called directly
with fabricated data) rather than against a real bucket: this pilot's
local stack has the Storage service switched off entirely
(`supabase/config.toml`), so there is no live bucket to create — see
that class's own docstring, and this migration owner's completion
report, for why that is the honest thing to say rather than skip the
question.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, NoReturn
from urllib.parse import urlsplit

import psycopg
import pytest

from tests.db.conftest import _require_live

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_MIGRATION_SKIP_REASON = (
    "db/migrations/0016_grants_hardening.sql not yet applied to this stack. "
    "Run `make test-db-up` against a stack with 0016 applied; see "
    "db/migrations/README.md. A stale PostgREST schema cache looks identical "
    "— `make test-db-migrate` reloads it."
)

#: Views that are DELIBERATELY `security_invoker = false`, each with a
#: reviewed, documented reason recorded both here and at the point the
#: view was created. A new non-invoker view that is NOT in this dict
#: fails the guard below — this dict is the only escape hatch, and
#: adding an entry to it without also adding the same reasoning to the
#: migration that creates the view is a review smell, not a fix.
_ALLOWED_NON_INVOKER_VIEWS: dict[str, str] = {
    "ai_usage_daily_totals": (
        "db/migrations/0011_ai_usage.sql: a deliberate RLS bypass for a "
        "reviewer-only aggregate over ai_usage (a reviewer owns none of "
        "those rows) — gated by the view's OWN `where is_reviewer()` "
        "clause plus a GRANT that excludes anon entirely, the same design "
        "family as a SECURITY DEFINER function. Reviewed and documented "
        "at the point it was created, not an oversight this guard exists "
        "to catch."
    ),
}


def _unavailable(reason: str) -> NoReturn:
    """Skip — or, under BCION_REQUIRE_LIVE=1, fail. Same rule as every
    other gate in tests/db: "green" must never mean "did not run"."""
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


def _database_url() -> str:
    """Loopback-only `DATABASE_URL`. This is a second door into the same
    database, independent of `tests/db/conftest.py`'s `SUPABASE_URL`
    guard (`tests/db/test_access_matrix.py` and
    `tests/db/test_ai_usage.py` each carry the identical check, for the
    identical reason: a safety property that only holds for one of two
    doors is not a safety property) — so it is re-stated here rather than
    imported, exactly as those two files already do."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        _unavailable(
            "DATABASE_URL is not set, so the exposure catalogue cannot be read. "
            "`make test-db-up` writes it into .env.test (mk/testdb.mk); see "
            ".env.test.example."
        )
    host = (urlsplit(url).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        pytest.fail(
            f"REFUSING TO CONNECT: DATABASE_URL points at {host!r}, which is not a "
            "local stack. This suite is only ever safe against the throwaway "
            "`supabase start` stack (CLAUDE.md) — this file additionally creates "
            "and drops scratch tables/views for its own revert-to-prove drills, "
            "which must never happen anywhere but a disposable stack.",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="module")
def sql() -> Iterator[psycopg.Connection[Any]]:
    """Catalogue reads (and this file's own scratch objects) only — never
    an application row, never a stand-in for a role's own access."""
    with psycopg.connect(_database_url(), connect_timeout=10, autocommit=True) as connection:
        yield connection


@pytest.fixture(autouse=True, scope="module")
def _migration_applied(sql: psycopg.Connection[Any]) -> None:
    row = sql.execute(
        "select to_regprocedure('public.grants_hardening_schema_version()')"
    ).fetchone()
    if row is None or row[0] is None:
        _unavailable(_MIGRATION_SKIP_REASON)


# ---------------------------------------------------------------------
# Catalogue readers — every one is a plain function so the
# TestRevertToProve* classes below can call it directly against a
# deliberately-broken live object, not just trust the fixture-driven
# tests to have exercised it.
# ---------------------------------------------------------------------
def _tables_without_rls(sql: psycopg.Connection[Any]) -> list[str]:
    rows = sql.execute(
        "select tablename from pg_tables where schemaname = 'public' and not rowsecurity"
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _views_not_security_invoker(sql: psycopg.Connection[Any]) -> list[str]:
    rows = sql.execute(
        """
        select c.relname
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind = 'v'
          and coalesce(
                (
                  select o.option_value::boolean
                  from pg_options_to_table(c.reloptions) o
                  where o.option_name = 'security_invoker'
                ),
                false
              ) = false
        """
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _storage_buckets(sql: psycopg.Connection[Any]) -> list[str]:
    """Bucket ids on this stack, or `[]` if the `storage` schema does not
    exist at all — this pilot's own stack (`supabase/config.toml`) leaves
    the Storage service off entirely, so `[]` is the expected, confirmed
    answer today, not an assumption this function makes on Storage's
    behalf."""
    exists = sql.execute("select to_regclass('storage.buckets')").fetchone()
    if exists is None or exists[0] is None:
        return []
    rows = sql.execute("select id from storage.buckets order by id").fetchall()
    return [str(row[0]) for row in rows]


def _storage_object_policy_texts(sql: psycopg.Connection[Any]) -> list[str]:
    """The USING + WITH CHECK SQL text of every RLS policy on
    `storage.objects` — `[]` if that table does not exist."""
    exists = sql.execute("select to_regclass('storage.objects')").fetchone()
    if exists is None or exists[0] is None:
        return []
    rows = sql.execute(
        "select coalesce(qual, '') || ' ' || coalesce(with_check, '') "
        "from pg_policies where schemaname = 'storage' and tablename = 'objects'"
    ).fetchall()
    return [str(row[0]) for row in rows]


def buckets_without_a_policy(bucket_ids: list[str], policy_texts: list[str]) -> list[str]:
    """Pure function, no database access: a bucket "has a policy" if at
    least one `storage.objects` policy's own SQL text mentions its id —
    Supabase's own convention for scoping a storage policy to one bucket
    is an ordinary `bucket_id = '...'` clause inside USING/WITH CHECK,
    not a separate grant. Exported so
    `TestRevertToProveStorageBucketPolicyLogic` below can exercise this
    exact logic directly, without a live Storage service anywhere."""
    return [bucket for bucket in bucket_ids if not any(bucket in text for text in policy_texts)]


# ---------------------------------------------------------------------
# 1. Every public table has RLS enabled
# ---------------------------------------------------------------------
class TestEveryPublicTableHasRowLevelSecurity:
    def test_no_public_table_has_rls_disabled(self, sql: psycopg.Connection[Any]) -> None:
        offenders = _tables_without_rls(sql)
        assert not offenders, (
            "These public tables have RLS switched OFF entirely, so every "
            "policy written for them is decorative and any API role can read "
            f"the lot: {', '.join(offenders)}. Add `alter table <t> enable row "
            "level security;` to a NEW migration (never edit an applied one)."
        )


class TestRevertToProveTableRLSCheck:
    """Weaken, observe red, restore, observe green — in the same test, on
    a scratch table nothing else in this schema references."""

    def test_a_table_with_rls_disabled_is_actually_caught(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        sql.execute("create table sec6_scratch_no_rls (id int)")
        try:
            offenders = _tables_without_rls(sql)
            assert "sec6_scratch_no_rls" in offenders, (
                "REVERT-TO-PROVE FAILED: a real table with RLS disabled was not "
                "flagged by _tables_without_rls — the catalogue check would pass "
                "vacuously."
            )
        finally:
            sql.execute("drop table sec6_scratch_no_rls")
        # Restored: the same query must now be clean again.
        assert "sec6_scratch_no_rls" not in _tables_without_rls(sql)


# ---------------------------------------------------------------------
# 2. Every view is security_invoker (one named, reviewed exception)
# ---------------------------------------------------------------------
class TestEveryViewIsSecurityInvoker:
    def test_every_non_invoker_view_is_a_named_reviewed_exception(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        offenders = _views_not_security_invoker(sql)
        unexplained = [view for view in offenders if view not in _ALLOWED_NON_INVOKER_VIEWS]
        assert not unexplained, (
            "These views are not security_invoker and are not in this file's "
            f"_ALLOWED_NON_INVOKER_VIEWS allow-list: {', '.join(unexplained)}. A "
            "non-invoker view runs with the VIEW OWNER's rights, bypassing RLS "
            "on whatever it reads — either add `with (security_invoker = true)` "
            "to the view, or, if the bypass is deliberate and reviewed the way "
            "ai_usage_daily_totals is, add a named entry here with the same "
            "reasoning stated in the migration that creates it."
        )


class TestRevertToProveViewSecurityInvokerCheck:
    def test_a_non_invoker_view_outside_the_allowlist_is_actually_caught(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        sql.execute(
            "create view sec6_scratch_view_not_invoker "
            "with (security_invoker = false) as select 1 as one"
        )
        try:
            offenders = _views_not_security_invoker(sql)
            unexplained = [v for v in offenders if v not in _ALLOWED_NON_INVOKER_VIEWS]
            assert "sec6_scratch_view_not_invoker" in unexplained, (
                "REVERT-TO-PROVE FAILED: a real non-invoker view outside the "
                "allow-list was not flagged — the catalogue check would pass "
                "vacuously."
            )
        finally:
            sql.execute("drop view sec6_scratch_view_not_invoker")
        assert "sec6_scratch_view_not_invoker" not in _views_not_security_invoker(sql)


# ---------------------------------------------------------------------
# 3. Every storage bucket has at least one policy
# ---------------------------------------------------------------------
class TestEveryStorageBucketHasAPolicy:
    def test_zero_storage_buckets_exist_today(self, sql: psycopg.Connection[Any]) -> None:
        """CONFIRMED, not assumed: a live query against this stack's own
        `pg_catalog`, not a reading of `supabase/config.toml`'s
        `[storage] enabled = false` line. If this ever fails, it means
        Storage has actually been turned on somewhere — the next test
        below is what then has to start doing real work."""
        buckets = _storage_buckets(sql)
        assert buckets == [], (
            f"Expected zero storage buckets (this pilot has never used Supabase "
            f"Storage — nothing under app/ imports a storage client, "
            f"docs/SECURITY.md). Found: {buckets}. Before relying on this being "
            "empty anywhere else, confirm every one of these has its own "
            "storage.objects policy (see the test below) and update this "
            "assertion deliberately — do not just delete it."
        )

    def test_every_bucket_that_exists_has_at_least_one_matching_policy(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        buckets = _storage_buckets(sql)
        if not buckets:
            pytest.skip(
                "zero storage buckets on this stack — see "
                "test_zero_storage_buckets_exist_today, which is what actually "
                "confirms that rather than assumes it"
            )
        uncovered = buckets_without_a_policy(buckets, _storage_object_policy_texts(sql))
        assert not uncovered, (
            f"These storage buckets have NO storage.objects RLS policy mentioning "
            f"them: {', '.join(uncovered)} — every object in each is either "
            "completely open or completely closed for every role, with no "
            "per-bucket distinction at all. Add a policy before shipping this."
        )


class TestRevertToProveStorageBucketPolicyLogic:
    """This pilot's own local stack has the Storage service switched off
    entirely (`supabase/config.toml`; confirmed by
    `test_zero_storage_buckets_exist_today` above), so there is no real
    bucket anywhere on it to create for a live revert-to-prove drill —
    standing up the Storage service purely to prove this one check would
    mean editing this migration-owner's own throwaway stack's config
    (`.supabase-migration-2/`, not a tracked file) well beyond what this
    card asked for, and is not done here.

    What IS done: `buckets_without_a_policy` — the exact function the
    live test above calls — is exercised directly against fabricated
    bucket/policy data, proving the DETECTION LOGIC is not vacuous even
    though this stack has never had a real bucket to run it against.
    Recorded plainly as the one check in this file whose revert-to-prove
    is at the logic level rather than a live database mutation — see
    this migration owner's own completion report.
    """

    def test_an_unprotected_bucket_is_actually_caught(self) -> None:
        uncovered = buckets_without_a_policy(
            bucket_ids=["public-assets", "private-uploads"],
            policy_texts=["bucket_id = 'public-assets'"],
        )
        assert uncovered == ["private-uploads"], (
            "REVERT-TO-PROVE FAILED: a bucket with no matching policy text was "
            "not flagged — this check would pass vacuously."
        )

    def test_a_fully_covered_set_of_buckets_passes(self) -> None:
        uncovered = buckets_without_a_policy(
            bucket_ids=["public-assets", "private-uploads"],
            policy_texts=[
                "bucket_id = 'public-assets'",
                "bucket_id = 'private-uploads' and auth.uid() = owner",
            ],
        )
        assert uncovered == []
