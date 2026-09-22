"""Database-backed spend cap for the AI adapter (AI-4).

The same job as `app/ai/budget.py`'s `AIRequestBudget` — "may I make
another provider call?" — answered by Postgres instead of by a counter in
this process. Same call shape on purpose (`reserve()`, `remaining()`), so
the swap is one import line in whoever constructs the budget, not a
rewrite of `app/ai/grounding.py`. That module calls `budget.reserve()`
with no arguments and catches nothing; this class keeps both of those
facts true.

WHY A DATABASE COUNTER AT ALL
-----------------------------
`app/ai/budget.py` says it plainly: a process-local counter is the right
amount of engineering for one worker process, and "a future multi-worker
deployment would need to move this to a shared counter (e.g. a Postgres
row, mirroring the jobs table already used elsewhere)". This is that
shared counter. It also buys two things the in-memory one structurally
cannot:

  * **Caps that survive a restart.** An in-process counter resets to zero
    every deploy, so a crash-loop is also a budget-loop.
  * **A ledger.** `db/migrations/0011_ai_usage.sql` records what was
    reserved, what was actually spent, and which retrieved records
    grounded the answer — never the prompt and never the answer text.
    There is no column for either, deliberately (CLAUDE.md: no student
    data to development agents; that table is read by agents).

WHAT THIS MODULE IS NOT
-----------------------
It holds no access rules and no cap values. The caps live in the
`ai_usage_caps` row, the enforcement lives inside `ai_reserve()`, and the
row-level security lives in the migration. This module hashes the
identity, calls the two RPCs and translates a SQLSTATE into a typed
Python error. That is the whole of it, so there is exactly one place the
rule lives.

THE IDENTITY IS NEVER SENT RAW
------------------------------
`identity` is an account uuid or a guest-session token. Only its SHA-256
digest crosses the wire, matching `ai_identity_hash()` in the migration
byte for byte (both are `sha256(utf-8 bytes)`, hex). The raw value is
kept out of this object's `repr` as well — a guest-session token in a log
line is the token, and the database only ever holds its hash.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from supabase import Client

from app.ai.budget import AIBudgetExceededError
from app.db import get_anon_client

#: SQLSTATEs raised by db/migrations/0011_ai_usage.sql. PostgREST passes
#: the code through to the client (confirmed against the local stack,
#: 2026-09-22), so this is a real discriminator and not a message match.
_BUDGET_EXCEEDED_SQLSTATE = "BCAI1"
_SETTLEMENT_SQLSTATE = "BCAI2"
_PROTOCOL_SQLSTATE = "BCAI3"

#: Belt and braces for the one thing that must never be mistaken for
#: something else. If a future PostgREST version ever stopped forwarding
#: the SQLSTATE, a cap would otherwise surface as a generic 500 and the
#: caller would retry into it; the message marker keeps "budget exceeded"
#: recognisable either way. It is checked in ADDITION to the code, never
#: instead of it.
_BUDGET_EXCEEDED_MARKER = "AI budget exceeded"

ACCOUNT = "account"
GUEST = "guest"


class AIUsageError(RuntimeError):
    """The reservation protocol was used incorrectly.

    A malformed call (unknown identity kind, an unhashed identifier, a
    settlement larger than its reservation) — never "you are out of
    budget", which is `AIBudgetExceededError`. Keeping the two apart
    matters: a caller that treats a programming error as a cap silently
    turns a bug into a permanent, invisible AI outage.
    """


def identity_digest(identity: str) -> str:
    """The value stored in `ai_usage.identity_hash`.

    Must stay byte-identical to `ai_identity_hash()` in
    db/migrations/0011_ai_usage.sql — `tests/db/test_ai_usage.py` asserts
    the two agree, against the live stack, rather than trusting this
    comment.
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code is not None else None


def _error_message(exc: Exception) -> str:
    return str(getattr(exc, "message", None) or exc)


def _translate(exc: Exception) -> Exception:
    """Map a PostgREST/Postgres error onto this module's vocabulary."""
    code = _error_code(exc)
    message = _error_message(exc)
    if code == _BUDGET_EXCEEDED_SQLSTATE or _BUDGET_EXCEEDED_MARKER in message:
        return AIBudgetExceededError(f"{message} The provider was not called.")
    if code in {_SETTLEMENT_SQLSTATE, _PROTOCOL_SQLSTATE}:
        return AIUsageError(message)
    return exc


@dataclass
class AIRequestBudgetDB:
    """One identity's view of the shared, database-held request budget.

    Construct one per request (it is a thin handle over an RPC, not a
    counter — there is no per-instance state to share and nothing to keep
    warm). `identity_kind` is `'account'` or `'guest'`; `identity` is the
    account uuid or the guest-session token, which is hashed before it
    goes anywhere.
    """

    identity_kind: str
    #: Raw account id or guest-session token. `repr=False`: this value is
    #: a credential in the guest case, and a dataclass repr is exactly
    #: how one ends up in a log line.
    identity: str = field(repr=False)
    template_id: str = "default"
    #: An already-built Supabase client, if the caller has one for this
    #: request (`app/db/client.py`: never cache or share one). None means
    #: "build a fresh anon client per call", which is what a guest path
    #: does anyway — every access decision here is made by the definer
    #: functions, not by which key was used.
    client: Client | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.identity_kind not in {ACCOUNT, GUEST}:
            raise AIUsageError(
                f"identity_kind must be {ACCOUNT!r} or {GUEST!r}, not {self.identity_kind!r}."
            )
        if not self.identity:
            raise AIUsageError("identity must not be empty — there would be nothing to cap.")

    # -- plumbing ----------------------------------------------------
    def _db(self) -> Client:
        return self.client if self.client is not None else get_anon_client()

    def _rpc(self, name: str, params: dict[str, Any]) -> Any:
        try:
            return self._db().rpc(name, params).execute().data
        except Exception as exc:  # noqa: BLE001 — re-raised, typed, below
            raise _translate(exc) from exc

    @property
    def identity_hash(self) -> str:
        """What the database stores for this identity. Never the identity."""
        return identity_digest(self.identity)

    # -- the AIRequestBudget call shape ------------------------------
    def remaining(self, *, today: date | None = None) -> int:
        """How many calls are still allowed for this identity right now.

        The smallest of the three headrooms (this identity today, the
        whole installation today, the whole installation this month), so
        a caller that sees `n` may genuinely make `n` calls.

        `today` is accepted for call-shape compatibility with
        `AIRequestBudget.remaining` and is deliberately IGNORED: the
        window is the database's own UTC day/month, and letting a caller
        name a different day would make the cap advisory. (It is not an
        error to pass one — a drop-in caller near midnight would
        otherwise start raising in production, which is a worse outcome
        than a parameter that does nothing.)
        """
        del today
        value = self._rpc(
            "ai_budget_remaining",
            {"p_identity_kind": self.identity_kind, "p_identity_hash": self.identity_hash},
        )
        return int(value or 0)

    def reserve(self, *, today: date | None = None) -> None:
        """Reserve ONE provider call, or raise `AIBudgetExceededError`.

        Drop-in for `AIRequestBudget.reserve`: same arguments, same
        exception type, same "nothing was reserved and the provider must
        not be called" meaning when it raises. The reservation's id is
        discarded here — use `reserve_usage()` when you intend to settle
        it afterwards, which is the fuller protocol this table exists
        for.
        """
        del today
        self.reserve_usage(calls=1)

    # -- the two-call protocol ---------------------------------------
    def reserve_usage(self, *, calls: int = 1, template_id: str | None = None) -> str:
        """Reserve `calls` provider calls and return the reservation id.

        Raises `AIBudgetExceededError` — having reserved nothing — when
        any of the three caps would be exceeded. Call this BEFORE the
        provider, and do not call the provider at all if it raises.
        """
        usage_id = self._rpc(
            "ai_reserve",
            {
                "p_identity_kind": self.identity_kind,
                "p_identity_hash": self.identity_hash,
                "p_template_id": template_id or self.template_id,
                "p_calls": calls,
            },
        )
        if not isinstance(usage_id, str) or not usage_id:
            raise AIUsageError(
                "ai_reserve() returned no reservation id — is "
                "db/migrations/0011_ai_usage.sql applied to this database?"
            )
        return usage_id

    def settle(
        self,
        usage_id: str,
        *,
        calls_made: int,
        status: str = "settled",
        selection_ids: Sequence[str] | None = None,
        verification_ids: Sequence[str] | None = None,
    ) -> bool:
        """Record what the reservation actually spent.

        `status` is `'settled'` (the call happened, however it turned
        out) or `'failed'` (it did not). False means the id is unknown or
        was already settled — an ordinary outcome for a retry, not an
        error. Ids only, never text: there is no column for a prompt or
        an answer and there never may be one.
        """
        return bool(
            self._rpc(
                "ai_settle",
                {
                    "p_usage_id": usage_id,
                    "p_calls_made": calls_made,
                    "p_status": status,
                    "p_selection_ids": list(selection_ids) if selection_ids is not None else None,
                    "p_verification_ids": (
                        list(verification_ids) if verification_ids is not None else None
                    ),
                },
            )
        )

    # -- constructors that name the identity kind for you ------------
    @classmethod
    def for_account(
        cls, account_id: str, *, template_id: str = "default", client: Any | None = None
    ) -> AIRequestBudgetDB:
        """For a signed-in student. `account_id` is their Supabase Auth
        user id — the same value `auth.uid()` returns, which is what the
        `ai_usage_select_own` policy hashes to decide whose rows are
        whose."""
        return cls(
            identity_kind=ACCOUNT, identity=account_id, template_id=template_id, client=client
        )

    @classmethod
    def for_guest(
        cls, session_token: str, *, template_id: str = "default", client: Any | None = None
    ) -> AIRequestBudgetDB:
        """For a guest, keyed on the same opaque session token
        `app/web/guest_session.py` puts in the httponly cookie. A guest
        can never READ any `ai_usage` row — there is no durable identity
        to check ownership against — so this is accounting only, which is
        all a cap needs."""
        return cls(
            identity_kind=GUEST, identity=session_token, template_id=template_id, client=client
        )
