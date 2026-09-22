"""AI spend accounting against the live stack — db/migrations/0011_ai_usage.sql (AI-4).

Four things are proved here, in ascending order of how much they matter:

1. **The shape of the table**, read out of the live catalogue: the exact
   column list, and — separately and loudly — that no column exists whose
   name could hold a prompt, a question or an answer. CLAUDE.md's "no
   student data to development agents" is only true if the table an agent
   reads to debug spend cannot contain what a child typed. A comment in
   the migration is a promise; this is a check.

2. **The caps actually bind**, including under concurrency. Two
   simultaneous reservations must not both slip through a cap by one, so
   the concurrency test fires eight real connections at the same identity
   with exactly one call of headroom left and insists on exactly one
   winner. That test is also the one used for the revert-to-prove drill
   (`.claude/agents/migration-owner.md`): with the cap check removed from
   `ai_reserve` it fails, with the check restored it passes.

3. **Cross-user access** (CLAUDE.md: "Cross-user access (guest, student
   A, student B, reviewer) is tested every time auth, RLS or publication
   changes"). `ai_usage`'s sixteen table cells live in
   tests/db/access_matrix.py with the rest of the schema; what lives HERE
   is the same four-role question asked of `ai_usage_daily_totals`, which
   is a VIEW — and the matrix's guard reads `pg_tables`, which excludes
   views, so a matrix row for it would be a hard failure under
   BCION_REQUIRE_LIVE=1 rather than coverage.

4. **The Python wrapper and the database agree**, in particular on the
   identity digest. `app/ai/budget_db.py` hashes in Python and
   `ai_identity_hash()` hashes in SQL; if those two ever drift, an
   account silently stops seeing its own rows and every cap starts
   counting the wrong bucket. Asserted against the live function, not
   assumed from reading both.

WHAT THESE TESTS TOUCH, AND WHAT THEY PUT BACK
----------------------------------------------
`ai_usage_caps` is a single, installation-wide row. The two tests that
need a cap smaller than the seeded placeholder set it, and restore the
previous values in a `finally` — so running THIS file concurrently with
another copy of itself against one shared stack could interleave those
two tests. The migration lane runs on a stack of its own
(supabase/config.toml's third block), which is where that is answered;
flagged here because it is the one piece of global state in this file.

Every `ai_usage` row a test creates is deleted by that test, and rows
carry this run's `BCION_RUN_ID` in `template_id` so a human can tell an
interrupted run's leftovers from real traffic. Deleting them genuinely
frees the budget they consumed: every cap is computed from the rows that
exist right now, never from a separate counter.

`psycopg` is used for two things only — reading catalogue metadata, and
opening the genuinely-simultaneous connections the concurrency test
needs — and carries its own loopback check on `DATABASE_URL`, the same
second door tests/db/test_access_matrix.py guards for the same reason.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from typing import Any, NoReturn
from urllib.parse import urlsplit

import psycopg
import pytest
from postgrest.exceptions import APIError
from supabase import Client

from app.ai.budget import AIBudgetExceededError
from app.ai.budget_db import ACCOUNT, GUEST, AIRequestBudgetDB, AIUsageError, identity_digest
from tests.db.conftest import RUN_ID, _require_live

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

#: Every row this file creates carries it, so leftovers from an
#: interrupted run are identifiable at a glance.
TEMPLATE_ID = f"ai4-test-{RUN_ID}"

_MIGRATION_SKIP_REASON = (
    "db/migrations/0011_ai_usage.sql not yet applied to this stack. Apply "
    "db/migrations/*.sql (see db/migrations/README.md); a stale PostgREST "
    "schema cache looks identical and is reloaded by re-running the "
    "migrate step."
)


def _unavailable(reason: str) -> NoReturn:
    """Skip — or, under BCION_REQUIRE_LIVE=1, fail. Same rule as every
    other gate in tests/db: "green" must never mean "did not run"."""
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        _unavailable(
            "DATABASE_URL is not set, so the catalogue and concurrency checks cannot "
            "run. `make test-db-up` writes it into .env.test (mk/testdb.mk)."
        )
    host = (urlsplit(url).hostname or "").strip().lower()
    if host not in _LOOPBACK_HOSTS:
        pytest.fail(
            f"REFUSING TO CONNECT: DATABASE_URL points at {host!r}, which is not a "
            "local stack (CLAUDE.md). These tests create and delete rows.",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="module")
def sql() -> Iterator[psycopg.Connection[Any]]:
    """Catalogue reads and the concurrency test's extra connections."""
    with psycopg.connect(_database_url(), connect_timeout=10, autocommit=True) as connection:
        yield connection


@pytest.fixture(autouse=True, scope="module")
def _migration_applied(sql: psycopg.Connection[Any]) -> None:
    row = sql.execute("select to_regprocedure('public.ai_usage_schema_version()')").fetchone()
    if row is None or row[0] is None:
        _unavailable(_MIGRATION_SKIP_REASON)


@pytest.fixture
def usage(admin_client: Client) -> Iterator[list[str]]:
    """Identity hashes whose rows this test wants removed afterwards.

    Service role, teardown only — never an assertion about what a real
    user can do (tests/db/conftest.py's contract for `admin_client`).
    """
    hashes: list[str] = []
    yield hashes
    for identity_hash in hashes:
        admin_client.table("ai_usage").delete().eq("identity_hash", identity_hash).execute()


def _fresh_identity(usage: list[str], kind: str = GUEST) -> AIRequestBudgetDB:
    """A budget handle for an identity no other test has ever used, with
    its rows registered for cleanup."""
    budget = AIRequestBudgetDB(
        identity_kind=kind, identity=f"ai4-{uuid.uuid4().hex}", template_id=TEMPLATE_ID
    )
    usage.append(budget.identity_hash)
    return budget


def _caps(admin_client: Client) -> dict[str, Any]:
    rows = admin_client.table("ai_usage_caps").select("*").execute().data
    assert rows, "ai_usage_caps must hold exactly one configuration row (0011 seeds it)."
    return dict(rows[0])


# =====================================================================
# 1. The shape of the table
# =====================================================================
_EXPECTED_AI_USAGE_COLUMNS = {
    "id",
    "identity_kind",
    "identity_hash",
    "template_id",
    "calls_reserved",
    "calls_made",
    "status",
    "selection_ids",
    "verification_ids",
    "created_at",
}

#: Any column whose name contains one of these could hold what a student
#: typed or what a model replied. None may ever exist on this table.
_FORBIDDEN_COLUMN_WORDS = (
    "prompt",
    "answer",
    "question",
    "response",
    "reply",
    "completion",
    "message",
    "content",
    "text",
    "body",
)


def _columns(sql: psycopg.Connection[Any], relation: str) -> set[str]:
    rows = sql.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'public' and table_name = %s",
        (relation,),
    ).fetchall()
    return {str(row[0]) for row in rows}


class TestTheTableHoldsNoStudentData:
    def test_ai_usage_has_exactly_the_documented_columns(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        assert _columns(sql, "ai_usage") == _EXPECTED_AI_USAGE_COLUMNS

    def test_ai_usage_has_no_column_that_could_hold_a_prompt_or_an_answer(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        """The hard requirement from tasks/BCI-010.md and CLAUDE.md, as a
        check rather than a comment: this table is read by agents, so a
        prompt or answer column here is student data handed to an agent.
        A correction would be a NEW migration dropping the column — never
        an edit to an applied file."""
        offenders = sorted(
            column
            for column in _columns(sql, "ai_usage")
            if any(word in column.lower() for word in _FORBIDDEN_COLUMN_WORDS)
        )
        assert not offenders, (
            f"ai_usage has column(s) that could hold prompt or answer text: {offenders}. "
            "No such column may ever exist on this table (CLAUDE.md: no student data to "
            "development agents; db/migrations/0011_ai_usage.sql's header)."
        )

    def test_the_aggregate_view_exposes_no_identity(self, sql: psycopg.Connection[Any]) -> None:
        columns = _columns(sql, "ai_usage_daily_totals")
        assert columns == {
            "usage_day",
            "identity_kind",
            "template_id",
            "status",
            "reservations",
            "calls_reserved",
            "calls_made",
        }
        assert "identity_hash" not in columns
        assert "id" not in columns

    def test_sql_and_python_hash_an_identity_identically(
        self, sql: psycopg.Connection[Any]
    ) -> None:
        """If these two ever drift, an account silently stops seeing its
        own rows and every cap counts the wrong bucket."""
        for identity in ("", "a", str(uuid.uuid4()), "a token with spaces and ünïcode"):
            row = sql.execute("select ai_identity_hash(%s)", (identity,)).fetchone()
            assert row is not None
            assert row[0] == identity_digest(identity), identity


# =====================================================================
# 2. The caps, and the two-call protocol
# =====================================================================
class TestReserveAndSettle:
    def test_a_reservation_is_recorded_and_then_settled(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        budget = _fresh_identity(usage)
        usage_id = budget.reserve_usage(calls=2)

        rows = (
            admin_client.table("ai_usage")
            .select("*")
            .eq("id", usage_id)
            .execute()
            .data
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "reserved"
        assert rows[0]["calls_reserved"] == 2
        assert rows[0]["calls_made"] == 0
        assert rows[0]["identity_hash"] == budget.identity_hash
        assert budget.identity not in str(rows[0]), (
            "the raw identity must never reach the database — only its digest"
        )

        selection = [str(uuid.uuid4())]
        verification = [str(uuid.uuid4()), str(uuid.uuid4())]
        assert budget.settle(
            usage_id, calls_made=2, selection_ids=selection, verification_ids=verification
        )

        settled = admin_client.table("ai_usage").select("*").eq("id", usage_id).execute().data[0]
        assert settled["status"] == "settled"
        assert settled["calls_made"] == 2
        assert settled["selection_ids"] == selection
        assert settled["verification_ids"] == verification

    def test_settling_a_second_time_changes_nothing(self, usage: list[str]) -> None:
        budget = _fresh_identity(usage)
        usage_id = budget.reserve_usage(calls=1)
        assert budget.settle(usage_id, calls_made=1) is True
        assert budget.settle(usage_id, calls_made=0, status="failed") is False

    def test_settling_an_unknown_reservation_is_false_not_an_error(self, usage: list[str]) -> None:
        budget = _fresh_identity(usage)
        assert budget.settle(str(uuid.uuid4()), calls_made=1) is False

    def test_a_settlement_may_not_exceed_its_reservation(self, usage: list[str]) -> None:
        budget = _fresh_identity(usage)
        usage_id = budget.reserve_usage(calls=1)
        with pytest.raises(AIUsageError):
            budget.settle(usage_id, calls_made=5)

    def test_a_failed_call_is_recorded_as_failed(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        budget = _fresh_identity(usage)
        usage_id = budget.reserve_usage(calls=1)
        assert budget.settle(usage_id, calls_made=0, status="failed") is True
        row = admin_client.table("ai_usage").select("*").eq("id", usage_id).execute().data[0]
        assert row["status"] == "failed"
        assert row["calls_made"] == 0

    def test_a_raw_identifier_is_refused_at_the_door(self, guest_client: Client) -> None:
        """`ai_reserve` takes a digest, never an account id or a session
        token. "We forgot to hash it" must fail loudly here rather than
        be discovered in a backup."""
        with pytest.raises(APIError) as caught:
            guest_client.rpc(
                "ai_reserve",
                {
                    "p_identity_kind": GUEST,
                    "p_identity_hash": str(uuid.uuid4()),
                    "p_template_id": TEMPLATE_ID,
                    "p_calls": 1,
                },
            ).execute()
        assert caught.value.code == "BCAI3"

    def test_an_unknown_identity_kind_is_refused(self, usage: list[str]) -> None:
        with pytest.raises(AIUsageError):
            AIRequestBudgetDB(identity_kind="reviewer", identity="x")


class TestTheCaps:
    def test_remaining_counts_down_and_reserve_refuses_at_the_cap(
        self, usage: list[str]
    ) -> None:
        budget = _fresh_identity(usage)
        # Read the headroom rather than assuming the placeholder cap: a
        # busy stack's global usage could legitimately make it smaller,
        # and "the cap binds" is the claim, not "the cap is 5".
        start = budget.remaining()
        assert start >= 1, "no headroom at all to test with — is another run mid-flight?"

        for used in range(start):
            assert budget.remaining() == start - used
            budget.reserve()

        assert budget.remaining() == 0
        with pytest.raises(AIBudgetExceededError):
            budget.reserve()

    def test_a_reservation_larger_than_the_remaining_headroom_is_refused_whole(
        self, usage: list[str]
    ) -> None:
        """No partial reservations: asking for more than is left reserves
        nothing at all, rather than as much as would fit."""
        budget = _fresh_identity(usage)
        before = budget.remaining()
        with pytest.raises(AIBudgetExceededError):
            budget.reserve_usage(calls=before + 1)
        assert budget.remaining() == before

    def test_one_identity_cannot_spend_another_identitys_headroom(
        self, usage: list[str]
    ) -> None:
        spender = _fresh_identity(usage)
        bystander = _fresh_identity(usage)
        for _ in range(spender.remaining()):
            spender.reserve()
        with pytest.raises(AIBudgetExceededError):
            spender.reserve()
        # The per-identity cap is per identity; the bystander is untouched
        # (the global caps are far above one identity's cap).
        assert bystander.remaining() > 0
        bystander.reserve()

    def test_the_global_daily_cap_stops_an_identity_with_headroom_to_spare(
        self, admin_client: Client, sql: psycopg.Connection[Any], usage: list[str]
    ) -> None:
        """A cap that only ever counted the caller's own rows would let
        a hundred guests spend a hundred identities' worth of budget.

        Lowers the installation-wide daily cap to "one more call than has
        been used so far", spends that one call as identity #1, and shows
        identity #2 — which has its own full per-identity headroom — is
        refused anyway. The previous configuration is restored in a
        `finally`; this is the one test in this file that writes to the
        shared `ai_usage_caps` row.
        """
        before = _caps(admin_client)
        first = _fresh_identity(usage)
        second = _fresh_identity(usage)
        used_today = _global_calls_used_today(sql)
        try:
            admin_client.table("ai_usage_caps").update(
                {
                    # Also lowered, so the refusal below cannot be the
                    # per-identity cap wearing the global cap's coat.
                    "per_identity_daily_calls": 1,
                    "global_daily_calls": used_today + 1,
                    "global_monthly_calls": used_today + 1,
                }
            ).eq("id", True).execute()

            first.reserve()
            with pytest.raises(AIBudgetExceededError) as caught:
                second.reserve()
            assert "across all identities" in str(caught.value), (
                "the refusal must come from a GLOBAL cap — this identity has spent nothing: "
                f"{caught.value}"
            )
        finally:
            admin_client.table("ai_usage_caps").update(
                {
                    "per_identity_daily_calls": int(before["per_identity_daily_calls"]),
                    "global_daily_calls": int(before["global_daily_calls"]),
                    "global_monthly_calls": int(before["global_monthly_calls"]),
                }
            ).eq("id", True).execute()
        restored = _caps(admin_client)
        for column in ("per_identity_daily_calls", "global_daily_calls", "global_monthly_calls"):
            assert restored[column] == before[column], f"{column} was not restored"

    def test_the_caps_are_configuration_not_code(self, admin_client: Client) -> None:
        """One row, and the values `ai_reserve` uses come from it — so
        the lead can set real figures with an UPDATE rather than a new
        migration."""
        rows = admin_client.table("ai_usage_caps").select("*").execute().data
        assert len(rows) == 1
        caps = rows[0]
        assert caps["per_identity_daily_calls"] <= caps["global_daily_calls"]
        assert caps["global_daily_calls"] <= caps["global_monthly_calls"]


def _global_calls_used_today(sql: psycopg.Connection[Any]) -> int:
    """Calls charged across every identity so far today, computed with
    exactly the expression `ai_reserve` uses — a reservation costs what
    it reserved until it settles, then what it actually made."""
    row = sql.execute(
        "select coalesce(sum(case when status = 'reserved' then calls_reserved "
        "else calls_made end), 0) from ai_usage "
        "where created_at >= date_trunc('day', now() at time zone 'UTC') at time zone 'UTC'"
    ).fetchone()
    return int(row[0]) if row is not None else 0


# =====================================================================
# 3. Concurrency — the revert-to-prove subject
# =====================================================================
class TestConcurrency:
    def test_simultaneous_reservations_cannot_both_slip_through_the_cap(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        """Eight real connections, one call of headroom, exactly one
        winner.

        This is the test the revert-to-prove drill uses
        (`.claude/agents/migration-owner.md`): with the cap check removed
        from `ai_reserve` all eight succeed and this fails; with the
        `select ... for update` on the caps row plus the cap check in
        place, seven are refused with SQLSTATE BCAI1.
        """
        cap = int(_caps(admin_client)["per_identity_daily_calls"])
        budget = _fresh_identity(usage)
        for _ in range(cap - 1):
            budget.reserve()
        assert budget.remaining() == 1

        url = _database_url()
        workers = 8
        start = threading.Barrier(workers)
        granted: list[str] = []
        refused: list[str] = []
        lock = threading.Lock()

        def attempt() -> None:
            with psycopg.connect(url, connect_timeout=10, autocommit=True) as connection:
                start.wait(timeout=30)
                try:
                    row = connection.execute(
                        "select ai_reserve(%s, %s, %s, 1)",
                        (budget.identity_kind, budget.identity_hash, TEMPLATE_ID),
                    ).fetchone()
                except psycopg.Error as exc:
                    with lock:
                        refused.append(str(exc.sqlstate))
                    return
            with lock:
                granted.append(str(row[0]) if row else "")

        threads = [threading.Thread(target=attempt) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert len(granted) == 1, (
            f"{len(granted)} of {workers} simultaneous reservations were granted against a "
            f"cap with ONE call of headroom left (refusals: {refused}). Two callers slipping "
            "through a cap together is the exact race `select ... for update` on the single "
            "ai_usage_caps row exists to close."
        )
        assert refused == ["BCAI1"] * (workers - 1), (
            f"the other {workers - 1} attempts must be refused as budget-exceeded (BCAI1), "
            f"not for some other reason: {refused}"
        )
        assert budget.remaining() == 0


# =====================================================================
# 4. Cross-user access
# =====================================================================
# `ai_usage`'s sixteen table cells are in tests/db/access_matrix.py. What
# is here is the same four-role question asked of the aggregate VIEW
# (which the matrix's pg_tables-based guard cannot carry), plus the
# account-scoped read the matrix states as one ALLOW/DENY pair and which
# is worth spelling out against a second student's row.
class TestCrossUserAccess:
    def test_an_account_sees_its_own_rows_and_no_other_students(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        reviewer: tuple[str, Client],
        guest_client: Client,
        usage: list[str],
    ) -> None:
        student_a_id, client_a = student_a
        _student_b_id, client_b = student_b
        _reviewer_id, client_reviewer = reviewer

        budget_a = AIRequestBudgetDB.for_account(
            student_a_id, template_id=TEMPLATE_ID, client=client_a
        )
        usage.append(budget_a.identity_hash)
        usage_id = budget_a.reserve_usage(calls=1)

        own = client_a.table("ai_usage").select("*").eq("id", usage_id).execute().data
        assert [row["id"] for row in own] == [usage_id], (
            "student A must be able to read their own AI-usage row "
            "(0011 ai_usage_select_own)"
        )

        assert client_b.table("ai_usage").select("*").eq("id", usage_id).execute().data == [], (
            "student B must never see student A's AI-usage row"
        )
        assert (
            client_reviewer.table("ai_usage").select("*").eq("id", usage_id).execute().data == []
        ), "a reviewer governs the knowledge base, never the student vault (docs/SECURITY.md)"
        assert guest_client.table("ai_usage").select("*").eq("id", usage_id).execute().data == [], (
            "a guest has no auth.uid(), so ai_usage_select_own matches nothing for them"
        )

    def test_a_guests_own_rows_are_invisible_to_the_guest_too(
        self, guest_client: Client, usage: list[str]
    ) -> None:
        """A guest has no durable identity to check ownership against, so
        the honest answer is "no rows for anyone" rather than a policy
        matching on something a client could supply."""
        budget = _fresh_identity(usage, kind=GUEST)
        usage_id = budget.reserve_usage(calls=1)
        assert guest_client.table("ai_usage").select("*").eq("id", usage_id).execute().data == []

    def test_no_api_role_may_write_ai_usage_directly(
        self, student_a: tuple[str, Client], guest_client: Client, usage: list[str]
    ) -> None:
        """The two definer functions are the only way in. Weakening this
        (granting insert to `authenticated`) is one of the revert-to-prove
        drills."""
        student_a_id, client_a = student_a
        budget_a = AIRequestBudgetDB.for_account(
            student_a_id, template_id=TEMPLATE_ID, client=client_a
        )
        usage.append(budget_a.identity_hash)
        usage_id = budget_a.reserve_usage(calls=1)

        forged = {
            "identity_kind": ACCOUNT,
            "identity_hash": budget_a.identity_hash,
            "template_id": TEMPLATE_ID,
            "calls_reserved": 1,
            "status": "reserved",
        }
        for label, client in (("student A", client_a), ("a guest", guest_client)):
            with pytest.raises(APIError) as caught:
                client.table("ai_usage").insert(forged).execute()
            assert caught.value.code == "42501", f"{label}'s direct insert must be refused"

        with pytest.raises(APIError) as caught:
            client_a.table("ai_usage").update({"calls_made": 99}).eq("id", usage_id).execute()
        assert caught.value.code == "42501", "student A must not be able to rewrite their own spend"

        with pytest.raises(APIError) as caught:
            client_a.table("ai_usage").delete().eq("id", usage_id).execute()
        assert caught.value.code == "42501", "a spend record must not be deletable by its subject"

    def test_nobody_but_the_owner_can_read_or_change_the_caps(
        self,
        student_a: tuple[str, Client],
        reviewer: tuple[str, Client],
        guest_client: Client,
    ) -> None:
        """The caps are the kill switch: reading them tells a caller
        exactly how much there is left to burn, writing them removes the
        cap entirely."""
        _student_a_id, client_a = student_a
        _reviewer_id, client_reviewer = reviewer
        for label, client in (
            ("a guest", guest_client),
            ("student A", client_a),
            ("a reviewer", client_reviewer),
        ):
            with pytest.raises(APIError) as caught:
                client.table("ai_usage_caps").select("*").execute()
            assert caught.value.code in {"42501", "PGRST205"}, f"{label} must not read the caps"
            with pytest.raises(APIError) as caught:
                client.table("ai_usage_caps").update({"global_daily_calls": 10_000}).eq(
                    "id", True
                ).execute()
            assert caught.value.code in {"42501", "PGRST205"}, f"{label} must not raise the caps"

    def test_only_a_reviewer_may_read_the_aggregate_view(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        reviewer: tuple[str, Client],
        guest_client: Client,
        usage: list[str],
    ) -> None:
        """The four-role answer for `ai_usage_daily_totals`, which is a
        view and therefore cannot live in tests/db/access_matrix.py's
        MATRIX (its guard reads `pg_tables`).

        guest: refused outright (no grant to `anon`). student A and
        student B: zero rows (the view's own `is_reviewer()` gate).
        reviewer: the day's totals — and no identity column to join them
        back to anyone.
        """
        _student_a_id, client_a = student_a
        _student_b_id, client_b = student_b
        _reviewer_id, client_reviewer = reviewer

        budget = _fresh_identity(usage)
        budget.reserve_usage(calls=1)

        with pytest.raises(APIError) as caught:
            guest_client.table("ai_usage_daily_totals").select("*").execute()
        assert caught.value.code in {"42501", "PGRST205"}, "a guest holds no grant on the view"

        assert client_a.table("ai_usage_daily_totals").select("*").execute().data == [], (
            "a signed-in student is not a reviewer: the view's is_reviewer() gate "
            "must give them zero rows"
        )
        assert client_b.table("ai_usage_daily_totals").select("*").execute().data == []

        totals = (
            client_reviewer.table("ai_usage_daily_totals")
            .select("*")
            .eq("template_id", TEMPLATE_ID)
            .execute()
            .data
        )
        assert totals, "a reviewer must see the aggregate totals"
        assert sum(int(row["calls_reserved"]) for row in totals) >= 1
        for row in totals:
            assert "identity_hash" not in row
