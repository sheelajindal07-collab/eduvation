"""Spend-cap threshold alerts (AI-13, BCI-023).

docs/SECURITY.md's spend controls ("atomic per-request spend reservation;
global + per-account spend caps; graceful fallback ... at the cap") give
the pilot a hard circuit breaker (`db/migrations/0011_ai_usage.sql`'s
`ai_reserve`). What that circuit breaker does NOT do is tell anyone it
tripped — a cap silently refusing calls looks, from the owner's side,
identical to "nobody asked Ask BCION anything today" until a person goes
looking. This module is the "somebody finds out" half: it watches the two
INSTALLATION-WIDE caps (`ai_usage_caps.global_daily_calls` and
`.global_monthly_calls` — never the per-identity cap, see "WHICH CAPS,
AND WHY" below) and sends one email the first time each crosses 50%, 80%
or 100% of its ceiling, through the same `app.notifications.factory.
get_email_sender()` / `EmailSender` protocol the guardian-consent flow
already uses. Never n8n (docs/DECISIONS.md, settled: n8n is not deployed
for this pilot) and never a new notification channel.

WHICH CAPS, AND WHY
--------------------
`ai_usage_caps` defines three ceilings: per-identity daily, global daily,
global monthly. This module alerts on only the latter two. The
per-identity cap being reached is an expected, self-healing, PER-STUDENT
event — `app.ai.schemas.AIAnswerStatus.budget_exhausted`'s own docstring
says so explicitly ("expected, self-healing and an operator signal, not
an incident") — and one student's cap tells the owner nothing about
whether the INSTALLATION is about to stop answering anyone. The global
caps are the ones whose exhaustion is an operator-facing incident (no
student gets an AI answer until the next UTC day/month), which is what
"the daily cap" / "the monthly cap" mean throughout this module and in
its card (tasks/BCI-023.md's "AI-13" section names exactly these two,
three thresholds each — six threshold/cap combinations total).

TWO WAYS TO GET THE NUMBERS IN
-------------------------------
`check_thresholds()` is a pure function: give it `CapSnapshot`s (just a
name, a period key, a used count and a limit) and it decides what to
send and sends it — no network call, so it is exercised with zero
database access in tests/unit/test_ai_alerts.py. `fetch_fresh()` is the
"(or queried fresh)" half the card also asks for: it reads the live
`ai_usage_caps` row and today's/this month's actual global usage and
builds the two `CapSnapshot`s for you. `check_and_notify()` chains the
two for the common case. `scripts/ai_spend_report.py` (the sibling half
of this card) calls into this module rather than duplicating either the
cap-fetching query or the alerting logic.

`fetch_fresh()` needs a SERVICE-ROLE Supabase client, not an ordinary
anon/reviewer-scoped one: `ai_usage_caps` has RLS enabled with no policy
at all and its grants to `anon`/`authenticated` are explicitly revoked
(db/migrations/0011_ai_usage.sql) — no signed-in role, reviewer included,
may read it. This is the same "owner holds the one key an ordinary
request never sees" shape as `scripts/seed_synthetic.py`'s
`SUPABASE_SERVICE_ROLE_KEY` requirement. This module never imports or
constructs that client itself (a script owns environment/credential
plumbing, not a library module); callers hand `fetch_fresh`/
`check_and_notify` an already-built `Client`.

"ONCE PER THRESHOLD" — THE STATE-TRACKING CHOICE
--------------------------------------------------
`AlertStateStore` is a small JSON file on local disk, not an in-memory
set. The reason is what actually invokes this: "a script run every few
minutes" (the card's own words) — this pilot has no persistent scheduler
process (CLAUDE.md: "Postgres jobs table + one worker process, no
Redis/broker"; n8n is off the request path and not deployed for this
pilot), so each run is a FRESH `python -m scripts.ai_spend_report`
process. An in-memory marker is reinitialised to empty at the start of
every one of those processes and would therefore never actually suppress
a repeat — it would resend all six threshold notices, in full, on every
single invocation. A file that persists between invocations is the least
machinery that fixes that at this pilot's 10-100-user scale: no new
migration (this card's own "Reserved migration number: n/a"), no new
table, no broker, just a JSON object read-modify-written by one
single-worker process. It is keyed by `(cap name, period key)` where
`period_key` is the UTC calendar day (daily cap) or UTC calendar month
(monthly cap) currently in force, so a new day/month naturally needs a
fresh set of notices without anything having to explicitly clear the
file. The default location is the OS temp directory, not inside the
repo, specifically so a default run can never leave a stray untracked
file for `git status` to notice; `AI_SPEND_ALERT_STATE_FILE` (or passing
a path directly to `AlertStateStore`) points it somewhere durable for a
real deployment.

NO CLAIM OR ANSWER CONTENT, NO RAW IDENTITY — STRUCTURAL, NOT A FILTER
------------------------------------------------------------------------
`CapSnapshot` and `CapThresholdEvent` carry exactly four numbers/strings
each (a cap name, a period key, a used count, a limit) and nothing else
— there is no field here that COULD hold a claim, an AI answer or an
identity hash, the same "the table has no such column" guarantee
`db/migrations/0011_ai_usage.sql` gives `ai_usage` itself. The email
bodies this module builds (`_body` below) are built exclusively from
those same four fields.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from supabase import Client

from app.notifications.factory import get_email_sender
from app.notifications.sender import EmailSender

#: Fired once each, ascending, whenever a cap's used/limit fraction
#: reaches or passes one of these — 50%, 80%, 100%. 1.0 still fires a
#: notice even though `ai_reserve` has, by then, already started
#: refusing further reservations: the cap's own refusal is silent to
#: everyone but the caller it refused, and the point of this module is
#: that the OWNER finds out too.
THRESHOLDS: tuple[float, ...] = (0.5, 0.8, 1.0)

#: The two caps this module ever alerts on — see module docstring
#: "WHICH CAPS, AND WHY".
DAILY_CAP = "daily"
MONTHLY_CAP = "monthly"


class AlertsUnavailableError(RuntimeError):
    """`fetch_fresh()` could not find what it needs (no `ai_usage_caps`
    row — i.e. db/migrations/0011_ai_usage.sql is not applied to whatever
    database `client` is pointed at). Never silently reports "no spend"
    in that case; a missing configuration row is a setup problem, not a
    quiet 0%."""


@dataclass(frozen=True)
class CapSnapshot:
    """What `check_thresholds` needs to know about ONE cap, right now.

    Deliberately minimal and DB-agnostic — this is the "given a spend
    report" half of the card: build one of these however you like (by
    hand in a test, from `scripts.ai_spend_report`'s own report, or via
    `fetch_fresh` below) and `check_thresholds` does not care which.
    """

    #: `DAILY_CAP` or `MONTHLY_CAP` — used for the email copy and as half
    #: of the "already fired" state key.
    name: str
    #: The UTC calendar day (`"2026-09-22"`) or month (`"2026-09"`) this
    #: snapshot's `used` figure was computed for — the other half of the
    #: state key, and what makes a new day/month need fresh notices.
    period_key: str
    used: int
    limit: int

    @property
    def fraction(self) -> float:
        """`used / limit`, or 0.0 for a non-positive limit (never a
        ZeroDivisionError over a misconfigured cap row — `ai_usage_caps`'
        own CHECK constraints already forbid a non-positive cap, so this
        is belt-and-braces, not a path expected to run)."""
        if self.limit <= 0:
            return 0.0
        return self.used / self.limit


@dataclass(frozen=True)
class CapThresholdEvent:
    """One notice that was actually sent — returned by
    `check_thresholds`/`check_and_notify` so a caller (a script's own
    stdout, a test) can report exactly what fired without re-deriving it
    from the snapshots."""

    cap_name: str
    period_key: str
    threshold: float
    used: int
    limit: int


def _default_state_path() -> Path:
    override = os.environ.get("AI_SPEND_ALERT_STATE_FILE", "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "bcion_ai_spend_alert_state.json"


def _threshold_token(threshold: float) -> str:
    """`0.5` -> `"50"`. A plain integer-percent string, so the state
    file is human-readable and stays stable under float rounding."""
    return str(round(threshold * 100))


class AlertStateStore:
    """Tracks which `(cap name, period key, threshold)` combinations have
    already fired a notice. See module docstring "ONCE PER THRESHOLD" for
    why this is a file and not an in-memory set."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_state_path()

    def _read(self) -> dict[str, list[str]]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            data: Any = json.loads(raw)
        except ValueError:
            # A corrupt/partial file must never crash the whole check —
            # worst case is one duplicate notice, which is still better
            # than the alert silently stopping forever.
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): [str(v) for v in values]
            for key, values in data.items()
            if isinstance(values, list)
        }

    @staticmethod
    def _key(period_key: str, cap_name: str) -> str:
        return f"{cap_name}:{period_key}"

    def has_fired(self, period_key: str, cap_name: str, threshold: float) -> bool:
        fired = self._read().get(self._key(period_key, cap_name), [])
        return _threshold_token(threshold) in fired

    def mark_fired(self, period_key: str, cap_name: str, threshold: float) -> None:
        data = self._read()
        key = self._key(period_key, cap_name)
        fired = data.get(key, [])
        token = _threshold_token(threshold)
        if token not in fired:
            fired.append(token)
        data[key] = fired
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _subject(event: CapThresholdEvent) -> str:
    pct = round(event.threshold * 100)
    return f"BCION Lite AI spend: {event.cap_name} cap at {pct}% ({event.period_key})"


def _body(event: CapThresholdEvent) -> str:
    pct = round(event.threshold * 100)
    return (
        f"The {event.cap_name} AI provider-call cap has reached {pct}% of its limit "
        f"for {event.period_key}.\n\n"
        f"Used: {event.used} of {event.limit} calls.\n\n"
        "This is an automated spend notice (app/ai/alerts.py, AI-13). It carries no "
        "student question or AI answer content and no per-student identity — see "
        "db/migrations/0011_ai_usage.sql for what this figure is built from and "
        "scripts/ai_spend_report.py for the fuller report."
    )


def check_thresholds(
    caps: Sequence[CapSnapshot],
    *,
    recipient: str,
    sender: EmailSender,
    state: AlertStateStore | None = None,
) -> list[CapThresholdEvent]:
    """The whole decision, given the numbers: for each `CapSnapshot`,
    walk the three thresholds ascending and send one email for every
    threshold this snapshot's fraction has reached AND that has not
    already fired for this `(cap, period)` — so a cap discovered already
    past 80% on its very first check this period still gets both its 50%
    and 80% notices, once each, not just the highest one.

    Returns the events actually sent, in the order sent (empty when
    nothing new crossed a threshold this call).
    """
    store = state if state is not None else AlertStateStore()
    fired: list[CapThresholdEvent] = []
    for snapshot in caps:
        for threshold in THRESHOLDS:
            if snapshot.fraction < threshold:
                continue
            if store.has_fired(snapshot.period_key, snapshot.name, threshold):
                continue
            event = CapThresholdEvent(
                cap_name=snapshot.name,
                period_key=snapshot.period_key,
                threshold=threshold,
                used=snapshot.used,
                limit=snapshot.limit,
            )
            sender.send(to=recipient, subject=_subject(event), body=_body(event))
            store.mark_fired(snapshot.period_key, snapshot.name, threshold)
            fired.append(event)
    return fired


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _cost(rows: Sequence[Mapping[str, Any]]) -> int:
    """A reservation costs what it reserved until it settles, then what
    it actually made — the exact expression `ai_reserve`/
    `ai_budget_remaining` use in db/migrations/0011_ai_usage.sql, kept in
    lockstep with them on purpose: this module's "used" figure must mean
    the same thing the cap itself enforces, not a plausible-looking
    approximation of it."""
    total = 0
    for row in rows:
        if str(row.get("status")) == "reserved":
            total += int(row.get("calls_reserved") or 0)
        else:
            total += int(row.get("calls_made") or 0)
    return total


def snapshots_from_caps_row(
    caps_row: Mapping[str, Any],
    *,
    usage_today_global: int,
    usage_month_global: int,
    today: date,
) -> list[CapSnapshot]:
    """Pure helper: turns an already-fetched `ai_usage_caps` row plus
    two already-computed global usage counts into the two `CapSnapshot`s
    `check_thresholds` needs. Exported so `scripts/ai_spend_report.py`
    can build the same snapshots from data it fetched itself, without
    this module importing that script (app/ never depends on scripts/)."""
    return [
        CapSnapshot(
            name=DAILY_CAP,
            period_key=today.isoformat(),
            used=usage_today_global,
            limit=int(caps_row["global_daily_calls"]),
        ),
        CapSnapshot(
            name=MONTHLY_CAP,
            period_key=today.strftime("%Y-%m"),
            used=usage_month_global,
            limit=int(caps_row["global_monthly_calls"]),
        ),
    ]


def fetch_fresh(client: Client, *, today: date | None = None) -> list[CapSnapshot]:
    """The "(or queried fresh)" path: reads the live `ai_usage_caps` row
    and this UTC day's / this UTC month's actual global usage, and
    returns the two `CapSnapshot`s for `check_thresholds`.

    `client` MUST be a service-role client — see module docstring "TWO
    WAYS TO GET THE NUMBERS IN". Two queries (day window, month window):
    the filtering happens in Postgres via `.gte("created_at", ...)`
    rather than by comparing ISO-timestamp strings in Python, which
    would be one string-format assumption away from a silent off-by-a-
    few-hours bug.
    """
    caps_rows = cast(
        "list[dict[str, Any]]", client.table("ai_usage_caps").select("*").execute().data
    )
    if not caps_rows:
        raise AlertsUnavailableError(
            "ai_usage_caps holds no configuration row — is "
            "db/migrations/0011_ai_usage.sql applied to this database?"
        )
    caps_row = caps_rows[0]

    now = today if today is not None else _utc_today()
    month_start_iso = f"{now.replace(day=1).isoformat()}T00:00:00+00:00"
    day_start_iso = f"{now.isoformat()}T00:00:00+00:00"

    columns = "status, calls_reserved, calls_made"
    month_rows = cast(
        "list[dict[str, Any]]",
        client.table("ai_usage").select(columns).gte("created_at", month_start_iso).execute().data,
    )
    day_rows = cast(
        "list[dict[str, Any]]",
        client.table("ai_usage").select(columns).gte("created_at", day_start_iso).execute().data,
    )

    return snapshots_from_caps_row(
        caps_row,
        usage_today_global=_cost(day_rows),
        usage_month_global=_cost(month_rows),
        today=now,
    )


def check_and_notify(
    client: Client,
    *,
    recipient: str,
    sender: EmailSender | None = None,
    state: AlertStateStore | None = None,
    today: date | None = None,
) -> list[CapThresholdEvent]:
    """The one-call "queried fresh" entry point: `fetch_fresh` then
    `check_thresholds`. `sender` defaults to `app.notifications.factory.
    get_email_sender()`, built fresh here rather than cached — mirrors
    that factory's own docstring (a caller that wants to assert on what
    was sent should build and pass its own `LoggingEmailSender`
    instance instead of relying on a shared one)."""
    caps = fetch_fresh(client, today=today)
    active_sender = sender if sender is not None else get_email_sender()
    return check_thresholds(caps, recipient=recipient, sender=active_sender, state=state)
