"""Live regression tests for the ACCOUNT identity-binding fix in
`db/migrations/0015_ai_identity_binding.sql` (BCI-024, AI-4 follow-up).

`ai_reserve()` and `ai_budget_remaining()` were introduced by
`db/migrations/0011_ai_usage.sql`, already merged to `main`. Both are
`security definer`, both are `grant execute ... to anon, authenticated`,
and both took `p_identity_hash` as a plain caller-supplied argument with
no check that it belonged to the calling session. `ai_identity_hash()`
(also anon-granted) is a pure, unpeppered sha256 with no secret in it, so
the hash of an ACCOUNT identity is computable by anyone who knows the
account's Supabase Auth uid — and that uid is not a secret.

The live reproduction this file is built to catch (verified by the lead
against merged code before BCI-024 was written; re-verified here by the
revert-to-prove drill, see below):

    select ai_identity_hash('<any known or guessed account uuid>');
    select ai_budget_remaining('account', '<that hash>');   -- a stranger's headroom
    select ai_reserve('account', '<that hash>', 't', 1);    -- burn a stranger's daily cap

both answerable by a caller holding nothing but the public anon key, with
no session at all. Exactly the same oracle CLASS that
`tests/db/test_account_active_oracle.py` covers for `account_active()`
(closed by 0014), and this file deliberately mirrors that file's shape.

After 0015: for `identity_kind = 'account'` the hash is DERIVED from
`auth.uid()` inside the function and the caller's argument is ignored as
an identity, so

  * a session-less caller gets BCAI3 (the malformed-call SQLSTATE both
    functions already used for every other validation failure — an
    anonymous caller has no account identity to bind to at all), and
  * an authenticated caller passing someone ELSE's hash transparently
    gets its OWN budget, and any reservation it makes is stamped with its
    OWN identity, never the victim's.

The GUEST path is deliberately unchanged and is proved unchanged here
(`TestGuestPathUnaffected`): a guest's identity is the opaque,
server-generated session token from `app/web/guest_session.py`, so
possessing it IS the credential and there is no `auth.uid()` to bind to
instead.

REVERT-TO-PROVE (.claude/agents/migration-owner.md)
---------------------------------------------------
Every assertion below was watched to FAIL with 0011's pre-fix function
bodies re-applied (extracted verbatim between that file's own
`-- BEGIN/END` sentinels) and to PASS again once 0015's bodies were
restored the same way. Both directions, both functions, recorded in
BCI-024's completion report. A security test that has never been seen to
fail proves nothing.

Skips as a whole — or fails, under `BCION_REQUIRE_LIVE=1` — until
0015 is applied to the stack this suite targets, via the
`ai_identity_binding_schema_version()` marker the migration creates. The
gate lives here rather than in `tests/db/conftest.py` because BCI-024
owns only the migration and this file.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any, NoReturn
from urllib.parse import urlsplit

import psycopg
import pytest
from postgrest.exceptions import APIError
from supabase import Client

from app.ai.budget_db import ACCOUNT, GUEST, AIRequestBudgetDB, AIUsageError, identity_digest
from tests.db.conftest import RUN_ID, _require_live

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

#: Every row this file creates carries it, so leftovers from an
#: interrupted run are identifiable at a glance — same convention as
#: tests/db/test_ai_usage.py.
TEMPLATE_ID = f"ai15-test-{RUN_ID}"

#: The SQLSTATE 0011 already used for "this call is malformed", which
#: 0015 reuses for "identity_kind 'account' with no auth.uid()". NOT
#: BCAI1 (budget exceeded) — conflating the two would turn a bug into a
#: silent, permanent AI outage that looks like an ordinary cap.
_PROTOCOL_SQLSTATE = "BCAI3"

_MIGRATION_SKIP_REASON = (
    "db/migrations/0015_ai_identity_binding.sql not yet applied to this "
    "stack. Apply db/migrations/*.sql (see db/migrations/README.md); a "
    "stale PostgREST schema cache looks identical and is reloaded by "
    "re-running the migrate step."
)


def _unavailable(reason: str) -> NoReturn:
    """Skip — or, under BCION_REQUIRE_LIVE=1, fail. Same rule as every
    other gate in tests/db: "green" must never mean "did not run"."""
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


def _database_url() -> str:
    """Loopback-only `DATABASE_URL`, for the catalogue checks.

    The same second door tests/db/test_ai_usage.py and
    tests/db/test_access_matrix.py keep for the same reason: psycopg does
    not go through `tests/db/conftest.py`'s `SUPABASE_URL` target guard,
    so it carries its own.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        _unavailable(
            "DATABASE_URL is not set, so the definer-function catalogue checks "
            "cannot run. `make test-db-up` writes it into .env.test (mk/testdb.mk)."
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
    """Catalogue reads only — never used to make an access assertion."""
    with psycopg.connect(_database_url(), connect_timeout=10, autocommit=True) as connection:
        yield connection


@pytest.fixture(autouse=True, scope="module")
def _migration_applied(sql: psycopg.Connection[Any]) -> None:
    row = sql.execute(
        "select to_regprocedure('public.ai_identity_binding_schema_version()')"
    ).fetchone()
    if row is None or row[0] is None:
        _unavailable(_MIGRATION_SKIP_REASON)


@pytest.fixture
def usage(admin_client: Client) -> Iterator[list[str]]:
    """Identity hashes whose `ai_usage` rows this test wants removed
    afterwards.

    Service role, TEARDOWN ONLY — never an assertion about what a real
    user can do (tests/db/conftest.py's contract for `admin_client`).
    Deleting the rows genuinely frees the budget they consumed: every cap
    is computed from the rows that exist right now, never from a separate
    counter.
    """
    hashes: list[str] = []
    yield hashes
    for identity_hash in hashes:
        admin_client.table("ai_usage").delete().eq("identity_hash", identity_hash).execute()


def _rows_for(admin_client: Client, identity_hash: str) -> list[dict[str, Any]]:
    """Every `ai_usage` row stamped with this identity hash. Service role
    on purpose: the question is "what did the DATABASE actually write",
    which is not a question about what any user may read."""
    return list(
        admin_client.table("ai_usage")
        .select("*")
        .eq("identity_hash", identity_hash)
        .execute()
        .data
    )


# =====================================================================
# 1. The account oracle, closed
# =====================================================================
class TestAccountIdentityBindingClosed:
    def test_session_less_caller_cannot_read_an_accounts_budget(
        self, guest_client: Client, student_a: tuple[str, Client]
    ) -> None:
        """THE live reproduction, on the read side: an anon-key-only
        client with no session at all, asking for an arbitrary real
        account's remaining budget by hashing that account's uid itself.

        Before 0015 this returned a real number (HTTP 200). After it, the
        call is refused as malformed (BCAI3) — a session with no
        `auth.uid()` has no account identity to bind to, so there is no
        answer it could correctly be given, and NOT answering is the
        point: any number here is a fact about a stranger.
        """
        victim_id, _victim_client = student_a
        victim_hash = identity_digest(victim_id)

        with pytest.raises(APIError) as caught:
            guest_client.rpc(
                "ai_budget_remaining",
                {"p_identity_kind": ACCOUNT, "p_identity_hash": victim_hash},
            ).execute()
        assert caught.value.code == _PROTOCOL_SQLSTATE, (
            "a session-less caller asking for an ACCOUNT budget must be refused as a "
            f"malformed call ({_PROTOCOL_SQLSTATE}), never answered with a real number "
            f"-- got {caught.value.code!r}"
        )

    def test_session_less_caller_cannot_reserve_against_an_account(
        self,
        admin_client: Client,
        guest_client: Client,
        student_a: tuple[str, Client],
        usage: list[str],
    ) -> None:
        """The same reproduction on the write side, which is the worse
        half: burning a stranger's per-identity daily cap is a cross-user
        denial of service, not just a leak.

        Asserts BOTH that the call is refused AND that nothing was
        written under the victim's identity — a refusal that still
        inserted a row would be no fix at all.
        """
        victim_id, _victim_client = student_a
        victim_hash = identity_digest(victim_id)
        usage.append(victim_hash)

        with pytest.raises(APIError) as caught:
            guest_client.rpc(
                "ai_reserve",
                {
                    "p_identity_kind": ACCOUNT,
                    "p_identity_hash": victim_hash,
                    "p_template_id": TEMPLATE_ID,
                    "p_calls": 1,
                },
            ).execute()
        assert caught.value.code == _PROTOCOL_SQLSTATE, (
            "a session-less caller must not be able to reserve against an ACCOUNT "
            f"identity -- got {caught.value.code!r}"
        )
        assert _rows_for(admin_client, victim_hash) == [], (
            "nothing may be written under the victim's identity hash by a caller who "
            "merely knew their (non-secret) account uuid"
        )

    def test_authenticated_caller_probing_another_account_gets_its_own_budget(
        self,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        usage: list[str],
    ) -> None:
        """THE core proof on the read side. Student A's budget is made
        DELIBERATELY DIFFERENT from student B's first (A spends some),
        so that a leaked answer and B's own answer are DISTINGUISHABLE --
        otherwise `probe == b_own` could just mean both happened to be
        the cap.

        B then calls `ai_budget_remaining('account', <A's hash>)` from
        its own signed-in session. Before 0015 that returned A's number.
        After it, B gets B's own, because the server derives the identity
        from B's `auth.uid()` and ignores the hash B sent.
        """
        a_id, a_client = student_a
        b_id, b_client = student_b
        usage.extend([identity_digest(a_id), identity_digest(b_id)])

        budget_a = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)
        budget_b = AIRequestBudgetDB.for_account(b_id, template_id=TEMPLATE_ID, client=b_client)

        budget_a.reserve_usage(calls=2)
        a_remaining = budget_a.remaining()
        b_remaining = budget_b.remaining()
        assert a_remaining != b_remaining, (
            "this test is only meaningful while A's and B's budgets differ; they are "
            f"both {a_remaining}, which means a GLOBAL cap is the binding constraint "
            "on this stack rather than the per-identity one. Reset the stack "
            "(`supabase db reset` + re-apply migrations) and re-run."
        )

        # The attack: B's own session, A's identity hash on the wire.
        probe = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=b_client)
        assert probe.identity_hash == identity_digest(a_id), (
            "sanity: the client really is sending A's hash, not B's -- otherwise this "
            "test would pass without exercising the binding at all"
        )
        assert probe.remaining() == b_remaining, (
            "student B passing student A's identity hash must get B's OWN remaining "
            f"budget ({b_remaining}), never A's ({a_remaining})"
        )

    def test_authenticated_caller_cannot_burn_another_accounts_cap(
        self,
        admin_client: Client,
        student_a: tuple[str, Client],
        student_b: tuple[str, Client],
        usage: list[str],
    ) -> None:
        """The core proof on the write side, and the strongest single
        assertion in this file: B reserves while sending A's identity
        hash. The reservation SUCCEEDS -- it is a legitimate reservation
        for B -- but it must be stamped with B's identity, and A's
        remaining budget must be completely untouched.
        """
        a_id, a_client = student_a
        b_id, b_client = student_b
        a_hash = identity_digest(a_id)
        b_hash = identity_digest(b_id)
        usage.extend([a_hash, b_hash])

        budget_a = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)
        a_remaining_before = budget_a.remaining()

        attacker = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=b_client)
        usage_id = attacker.reserve_usage(calls=1)

        rows = _rows_for(admin_client, a_hash)
        assert rows == [], (
            "student B's reservation must NOT be recorded against student A's identity "
            f"hash -- found {len(rows)} row(s) that would eat A's daily cap"
        )
        written = [row for row in _rows_for(admin_client, b_hash) if row["id"] == usage_id]
        assert written, (
            "the reservation B actually made must be stamped with B's OWN identity hash "
            "(derived from auth.uid()), not with the hash B sent"
        )
        assert written[0]["identity_kind"] == ACCOUNT

        # The row check above is the sharp proof; this is the same fact
        # seen from the caller's side. It is a bound rather than an
        # equality on purpose: B's reservation legitimately costs one
        # call of the GLOBAL daily/monthly headroom that every identity
        # genuinely shares, and `remaining()` is the smallest of the
        # three headrooms — so A may see one fewer when a global cap is
        # the binding constraint. What must never happen is A losing the
        # call from their own per-identity bucket, which is what "burn a
        # stranger's cap" meant and what `rows == []` above rules out.
        assert budget_a.remaining() >= a_remaining_before - 1, (
            "student A may lose at most the one call of shared GLOBAL headroom B "
            "really did spend -- never more, and never from A's own per-identity cap"
        )

    def test_a_reviewer_probing_a_students_budget_gets_its_own(
        self,
        reviewer: tuple[str, Client],
        student_a: tuple[str, Client],
        usage: list[str],
    ) -> None:
        """The fourth role of CLAUDE.md's four-role rule (guest, student
        A, student B, reviewer), which the three tests above cover the
        first three of.

        A reviewer is not a special case here and must not become one:
        docs/SECURITY.md scopes the reviewer role to the knowledge base,
        never the student vault, and 0011 already refused them an
        override on `ai_usage` itself. So a reviewer aiming these two
        functions at a student's identity gets exactly what any other
        signed-in caller gets — their own budget.
        """
        reviewer_id, reviewer_client = reviewer
        a_id, a_client = student_a
        usage.extend([identity_digest(a_id), identity_digest(reviewer_id)])

        budget_a = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)
        budget_reviewer = AIRequestBudgetDB.for_account(
            reviewer_id, template_id=TEMPLATE_ID, client=reviewer_client
        )
        budget_a.reserve_usage(calls=2)
        a_remaining = budget_a.remaining()
        reviewer_remaining = budget_reviewer.remaining()
        assert a_remaining != reviewer_remaining, (
            "this test is only meaningful while the two budgets differ; a GLOBAL cap "
            "is the binding constraint on this stack -- reset it and re-run"
        )

        probe = AIRequestBudgetDB.for_account(
            a_id, template_id=TEMPLATE_ID, client=reviewer_client
        )
        assert probe.remaining() == reviewer_remaining, (
            "a reviewer passing a student's identity hash must get the REVIEWER's own "
            f"remaining budget ({reviewer_remaining}), never the student's "
            f"({a_remaining}) -- a reviewer governs the knowledge base, never the "
            "student vault (docs/SECURITY.md)"
        )

    def test_an_accounts_own_budget_still_works_end_to_end(
        self, student_a: tuple[str, Client], usage: list[str]
    ) -> None:
        """No-regression proof for the ONLY call shape a real signed-in
        student ever makes: their own session, their own identity.
        Without this, every assertion above could be satisfied by a
        function that simply stopped working for accounts altogether.
        """
        a_id, a_client = student_a
        usage.append(identity_digest(a_id))
        budget = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)

        before = budget.remaining()
        assert before > 0, "a fresh account must start with headroom (0011's seeded caps)"

        usage_id = budget.reserve_usage(calls=1)
        assert budget.remaining() == before - 1, (
            "a reservation must cost the reserving account exactly what it reserved"
        )
        assert budget.settle(usage_id, calls_made=1, status="settled") is True, (
            "ai_settle is NOT touched by 0015 and must still settle a normal reservation"
        )
        assert budget.remaining() == before - 1

    def test_the_caller_s_own_row_is_still_readable_by_the_caller(
        self, student_a: tuple[str, Client], usage: list[str]
    ) -> None:
        """0011's `ai_usage_select_own` policy hashes `auth.uid()` the
        same way 0015 now does inside the two functions. If the two ever
        disagreed, an account would silently stop seeing the rows its own
        reservations create -- so the agreement is asserted against the
        live stack rather than assumed from reading both.
        """
        a_id, a_client = student_a
        usage.append(identity_digest(a_id))
        budget = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)
        usage_id = budget.reserve_usage(calls=1)

        own = a_client.table("ai_usage").select("*").eq("id", usage_id).execute().data
        assert [row["id"] for row in own] == [usage_id], (
            "the row 0015's derived identity wrote must be the same row 0011's RLS "
            "policy considers the caller's own"
        )


# =====================================================================
# 2. The guest path, deliberately unchanged
# =====================================================================
class TestGuestPathUnaffected:
    def test_a_guests_own_reserve_and_remaining_still_work(
        self, guest_client: Client, usage: list[str]
    ) -> None:
        """The guest path keeps trusting the caller-supplied hash, by
        design: a guest's identity is the opaque, server-generated
        session token from `app/web/guest_session.py`, so possessing it
        IS the credential, and a guest has no `auth.uid()` to bind to
        instead. This is the named proof that 0015 did not break it.
        """
        token = f"ai15-guest-{uuid.uuid4().hex}"
        budget = AIRequestBudgetDB(
            identity_kind=GUEST, identity=token, template_id=TEMPLATE_ID, client=guest_client
        )
        usage.append(budget.identity_hash)

        before = budget.remaining()
        assert before > 0, "a fresh guest identity must start with headroom"

        usage_id = budget.reserve_usage(calls=1)
        assert budget.remaining() == before - 1
        assert budget.settle(usage_id, calls_made=1, status="settled") is True

    def test_two_guests_keep_separate_buckets(
        self, guest_client: Client, usage: list[str]
    ) -> None:
        """A guest cannot reach another guest's bucket without that
        guest's token -- which was already true before 0015 (the hash is
        of an unguessable server-generated token, not of anything
        public) and must stay true after it. Proved the only way it can
        be: one guest spending must not move another guest's headroom.
        """
        first = AIRequestBudgetDB(
            identity_kind=GUEST,
            identity=f"ai15-guest-{uuid.uuid4().hex}",
            template_id=TEMPLATE_ID,
            client=guest_client,
        )
        second = AIRequestBudgetDB(
            identity_kind=GUEST,
            identity=f"ai15-guest-{uuid.uuid4().hex}",
            template_id=TEMPLATE_ID,
            client=guest_client,
        )
        usage.extend([first.identity_hash, second.identity_hash])

        second_before = second.remaining()
        first.reserve_usage(calls=2)

        first_after = first.remaining()
        second_after = second.remaining()
        assert first_after < second_after, (
            "two guest identities must have SEPARATE per-identity buckets: after one "
            f"spends 2 calls it must have less headroom than the other ({first_after} "
            f"vs {second_after}). Equal values mean a GLOBAL cap is the binding "
            "constraint on this stack, which makes this test vacuous -- reset the "
            "stack (`supabase db reset` + re-apply migrations) and re-run."
        )
        assert second_after >= second_before - 2, (
            "one guest's spend may only cost another guest the GLOBAL headroom they "
            "genuinely share, never anything out of the other's own bucket"
        )

    def test_a_guest_identity_cannot_reach_an_accounts_bucket(
        self,
        admin_client: Client,
        guest_client: Client,
        student_a: tuple[str, Client],
        usage: list[str],
    ) -> None:
        """The identity-kind escape hatch, closed by construction rather
        than by a new check: `identity_kind` is part of the cap key, so
        calling as a GUEST while supplying an ACCOUNT-derived hash spends
        a ('guest', <hash>) bucket that is not the ('account', <hash>)
        one. Worth an explicit test because 'guest' is the path 0015
        deliberately left trusting the caller's hash, and that must not
        become a way back into the account space.
        """
        a_id, a_client = student_a
        a_hash = identity_digest(a_id)
        usage.append(a_hash)

        budget_a = AIRequestBudgetDB.for_account(a_id, template_id=TEMPLATE_ID, client=a_client)
        a_remaining_before = budget_a.remaining()

        spoof = AIRequestBudgetDB(
            identity_kind=GUEST, identity=a_id, template_id=TEMPLATE_ID, client=guest_client
        )
        assert spoof.identity_hash == a_hash, "sanity: the same digest, a different kind"
        spoof.reserve_usage(calls=1)

        account_rows = [
            row for row in _rows_for(admin_client, a_hash) if row["identity_kind"] == ACCOUNT
        ]
        assert account_rows == [], (
            "a 'guest' call carrying an account-derived hash must never land in the "
            "ACCOUNT identity space"
        )
        assert budget_a.remaining() >= a_remaining_before - 1, (
            "the only budget a guest can cost an account is the one call of GLOBAL "
            "headroom they genuinely share -- not the account's per-identity bucket"
        )


# =====================================================================
# 3. The definer functions themselves
# =====================================================================
class TestDefinerFunctionsStayPinned:
    """`.claude/agents/migration-owner.md`: a `SECURITY DEFINER` function
    runs with elevated rights regardless of who calls it, so its
    `search_path` must be pinned explicitly rather than inherited from
    the caller or the database default. Asserted from the live
    catalogue, because this is the one property of these two functions
    that no behavioural test above could notice being lost.
    """

    @pytest.mark.parametrize("function_name", ["ai_reserve", "ai_budget_remaining"])
    def test_still_security_definer_with_a_pinned_search_path(
        self, sql: psycopg.Connection[Any], function_name: str
    ) -> None:
        row = sql.execute(
            "select p.prosecdef, p.proconfig from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and p.proname = %s",
            (function_name,),
        ).fetchone()
        assert row is not None, f"{function_name} must exist in the public schema"
        prosecdef, proconfig = row
        assert prosecdef is True, f"{function_name} must still be SECURITY DEFINER"
        assert proconfig is not None and "search_path=public" in proconfig, (
            f"{function_name} must pin search_path explicitly (got {proconfig!r}) -- an "
            "unpinned definer function is a privilege-escalation primitive"
        )

    def test_ai_settle_was_not_touched(self, sql: psycopg.Connection[Any]) -> None:
        """BCI-024 scopes `ai_settle` OUT: it takes an opaque reservation
        uuid the caller must already hold, which is a different,
        already-documented and already-accepted residual risk class
        (0011's own note). Its argument list must therefore be exactly
        what 0011 left it -- this catches a future 'while we are here'
        edit as much as an accidental one in this migration.
        """
        row = sql.execute(
            "select pg_get_function_identity_arguments(p.oid) from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and p.proname = 'ai_settle'"
        ).fetchall()
        assert len(row) == 1, "exactly one ai_settle overload must exist"
        assert row[0][0] == (
            "p_usage_id uuid, p_calls_made integer, p_status text, "
            "p_selection_ids uuid[], p_verification_ids uuid[]"
        ), "ai_settle's signature must be unchanged by 0015"


# =====================================================================
# 4. The Python wrapper's own vocabulary
# =====================================================================
def test_the_client_reports_a_session_less_account_call_as_a_protocol_error(
    guest_client: Client, student_a: tuple[str, Client]
) -> None:
    """`app/ai/budget_db.py` maps BCAI3 onto `AIUsageError` ("used
    incorrectly"), never onto `AIBudgetExceededError`. Reusing BCAI3 for
    the new "no auth.uid()" refusal was chosen precisely so that stays
    true without touching the client: a caller that mistook this for a
    cap would silently degrade to "AI unavailable" forever instead of
    failing loudly.
    """
    victim_id, _victim_client = student_a
    budget = AIRequestBudgetDB.for_account(
        victim_id, template_id=TEMPLATE_ID, client=guest_client
    )
    with pytest.raises(AIUsageError):
        budget.remaining()
    with pytest.raises(AIUsageError):
        budget.reserve_usage(calls=1)
