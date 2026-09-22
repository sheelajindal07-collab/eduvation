#!/usr/bin/env python
"""Read-only, owner-run AI spend report (AI-13, BCI-023).

For a given UTC date range, reports:

  * total provider calls reserved vs. settled (and how many rows are
    still merely `reserved`, `settled` or `failed` — see
    `SpendReport.rows_by_status`);
  * the FALLBACK RATE — the fraction of resolved (settled or failed)
    requests that did NOT end up `app.ai.schemas.AIAnswerStatus.
    answered` (see "DERIVING THE FALLBACK RATE" below — it is inferred,
    the same way the two-pass disagreement rate is, and for the same
    structural reason: `ai_usage` records what was spent, never what the
    answer said);
  * the TWO-PASS DISAGREEMENT RATE (see "DERIVING TWO-PASS DISAGREEMENT"
    below);
  * spend against each of the three `ai_usage_caps` ceilings, via
    `app.ai.alerts.fetch_fresh`/`snapshots_from_caps_row` (shared with
    that module rather than reimplemented here — one source of truth for
    "what counts as used against a cap");
  * requests per identity-hash bucket — a count per already-hashed
    `ai_usage.identity_hash`, NEVER the raw account id or guest-session
    token the hash was built from (see "NO CLAIM OR ANSWER CONTENT, NO
    RAW IDENTITY" below).

Usage:
    python -m scripts.ai_spend_report --start 2026-09-01 --end 2026-09-22
    python -m scripts.ai_spend_report --start 2026-09-01 --end 2026-09-22 \\
        --check-alerts --alert-to owner@example.invalid

Invoked with `-m` (`python -m scripts.ai_spend_report ...`), not
`python scripts/ai_spend_report.py`, from the repo root — same reason as
`scripts/run_ai_eval.py`'s own header: only `-m` puts the repo root on
`sys.path` so `scripts` resolves as a package (this module is also
imported directly, without `-m`, by tests/db/test_ai_spend_report.py,
where pytest's own rootdir insertion covers the same need).

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment — see
`build_service_client()` below for exactly why a service-role key is
unavoidable for this report, not merely convenient.

WHY SERVICE ROLE, NOT A REVIEWER LOGIN
----------------------------------------
This report needs two things no reviewer JWT can ever see:

  1. `ai_usage_caps` itself. `db/migrations/0011_ai_usage.sql` enables
     RLS on it with NO policy at all and explicitly `revoke`s every
     grant from `anon`/`authenticated` — "no API role may see or change
     the caps" is that file's own words. `tests/db/test_ai_usage.py`'s
     `test_nobody_but_the_owner_can_read_or_change_the_caps` proves a
     reviewer gets refused too. There is no lower-privilege way to read
     a cap's numeric value at all.
  2. Every identity's raw `ai_usage` rows, which the per-identity-hash
     bucket counts and the two-pass disagreement rate both need
     (`selection_ids`/`verification_ids` are not in the aggregate
     `ai_usage_daily_totals` view at all — that view's own comment in
     the migration explains why: it carries no identity or per-row
     detail on purpose). `ai_usage_select_own` scopes a signed-in
     account (reviewers included) to their OWN rows only —
     `tests/db/test_ai_usage.py`'s `TestCrossUserAccess` class proves a
     reviewer reading `ai_usage` directly sees nothing.

`ai_usage_daily_totals` (the reviewer-only view this card also names) is
real and reviewer-readable, but a service-role connection — which this
script needs anyway for (1) and (2) — already sees a strict superset of
what that view exposes by reading `ai_usage` directly, so this script
never queries the view separately; `fetch_usage_rows` below reads the
same underlying rows the view is built from. This mirrors
`scripts/seed_synthetic.py`'s own `SUPABASE_SERVICE_ROLE_KEY`
requirement: an owner-run, off-the-request-path script holding the one
credential the application itself never reads (CLAUDE.md: "no secrets in
repo memory — variable names only, values via provider dashboards /
environment").

DERIVING THE FALLBACK RATE
----------------------------
`ai_usage` has no column recording `app.ai.schemas.AIAnswerStatus` at
all — only `status in ('reserved', 'settled', 'failed')`. Three of the
six `AIAnswerStatus` values (`not_available`, `budget_exhausted`,
`unsupported_template`) are decided BEFORE any reservation is even
attempted (schemas.py's own docstring: `not_available` — "the provider is
never called; there is nothing to ground on"; the other two are refused
even earlier), so they never produce an `ai_usage` row to count at all —
a fallback rate computed from this table structurally cannot and does
not claim to cover them. Of the three that DO reserve, `ai_settle`'s own
docstring draws the line this script uses: `status = 'failed'` means the
call did not happen (`ai_unavailable`); `status = 'reserved'` means it
has not resolved to anything yet, so it is excluded from both the
numerator and the denominator (matching how `ai_usage_daily_totals`
keeps `reserved` as its own row rather than folding it into either
outcome); `status = 'settled'` means "the call happened, however it
turned out" — which still leaves `answered` and
`insufficient_information` needing to be told apart. The only per-row
signal left for that is `verification_ids`: `AIAnswerStatus.answered` is
schemas.py's OWN words "the ONLY status that ever carries sentences",
which requires pass two to have actually confirmed at least one
retrieved record survived both passes plus validation — i.e.
`verification_ids` non-empty. A settled row with empty/null
`verification_ids` reflects `insufficient_information`: pass two
confirmed nothing. So: `answered = settled AND verification_ids
non-empty`; every other resolved (settled-or-failed) row counts as
FALLBACK. This is an inference from two fields the ledger happens to
carry, not a stored fact, stated here exactly as loudly as the two-pass
disagreement derivation is stated below.

DERIVING TWO-PASS DISAGREEMENT
---------------------------------
Not directly recorded either — computed the same way tasks/BCI-023.md
specifies: among SETTLED rows whose `selection_ids` is non-empty, the
fraction where `verification_ids` is a STRICT SUBSET of `selection_ids`
(pass two dropped at least one id pass one proposed). `set(a) < set(b)`
in Python means exactly "`a` is a proper subset of `b`", which is the
expression `build_report` uses below — including the case where
`verification_ids` is empty/null (pass two dropped everything pass one
proposed), which is still a strict subset of any non-empty set and
therefore still counts as disagreement.

NO CLAIM OR ANSWER CONTENT, NO RAW IDENTITY
-----------------------------------------------
`fetch_usage_rows` below selects an explicit column list (never
`select("*")`) drawn only from `ai_usage`'s documented shape — a table
that structurally has no prompt/answer/question column at all
(`db/migrations/0011_ai_usage.sql`'s own header, checked by
`tests/db/test_ai_usage.py::TestTheTableHoldsNoStudentData`). The only
per-row identity value that ever appears anywhere in this script's
output is `identity_hash`, which is ALREADY a SHA-256 digest by the time
it reaches this table (`ai_identity_hash()`/`app.ai.budget_db.
identity_digest`) — this script never reverses it, never looks it up
against `auth.users`, and never prints the raw account id or guest
session token those hashes were built from (it never even reads one).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

from supabase import Client, create_client

from app.ai.alerts import CapSnapshot, check_thresholds, fetch_fresh
from app.ai.schemas import AIAnswerStatus
from app.notifications.factory import get_email_sender

#: Only these columns are ever asked for — see module docstring "NO
#: CLAIM OR ANSWER CONTENT, NO RAW IDENTITY".
_USAGE_COLUMNS = (
    "identity_kind, identity_hash, template_id, calls_reserved, "
    "calls_made, status, selection_ids, verification_ids, created_at"
)

_TERMINAL_STATUSES = ("settled", "failed")


class SpendReportUnavailableError(RuntimeError):
    """The environment or the database is not ready for this report —
    raised rather than guessed past (missing service-role credentials,
    or `ai_usage_caps` holding no row)."""


@dataclass(frozen=True)
class UsageRow:
    """One `ai_usage` row, narrowed to the columns this report uses."""

    identity_kind: str
    identity_hash: str
    template_id: str
    calls_reserved: int
    calls_made: int
    status: str
    selection_ids: tuple[str, ...]
    verification_ids: tuple[str, ...]
    created_at: str


def _row_from_raw(raw: Mapping[str, Any]) -> UsageRow:
    return UsageRow(
        identity_kind=str(raw["identity_kind"]),
        identity_hash=str(raw["identity_hash"]),
        template_id=str(raw["template_id"]),
        calls_reserved=int(raw["calls_reserved"]),
        calls_made=int(raw["calls_made"]),
        status=str(raw["status"]),
        selection_ids=tuple(raw.get("selection_ids") or ()),
        verification_ids=tuple(raw.get("verification_ids") or ()),
        created_at=str(raw["created_at"]),
    )


@dataclass(frozen=True)
class SpendReport:
    """Everything this card asks for, for one `[start, end)` UTC-date
    range, plus the caps' current (not range-bound) status."""

    start: date
    end: date  # exclusive
    calls_reserved_total: int
    calls_made_total: int
    rows_total: int
    rows_by_status: dict[str, int]

    #: See module docstring "DERIVING THE FALLBACK RATE".
    resolved_rows: int
    answered_rows: int
    fallback_rows: int
    fallback_rate: float | None  # None when resolved_rows == 0 — no rate to report, not 0%

    #: See module docstring "DERIVING TWO-PASS DISAGREEMENT".
    disagreement_eligible_rows: int
    disagreement_rows: int
    disagreement_rate: float | None

    #: identity_hash (a digest — see module docstring) -> request count.
    requests_by_identity_hash: dict[str, int]

    #: "Right now", not scoped to [start, end) — see app.ai.alerts.
    cap_snapshots: list[CapSnapshot]


def build_report(
    rows: Sequence[UsageRow],
    *,
    start: date,
    end: date,
    cap_snapshots: Sequence[CapSnapshot] = (),
) -> SpendReport:
    """Pure: every number comes only from `rows` and `cap_snapshots`, no
    network call — exercised directly by tests without a live stack.
    `tests/db/test_ai_spend_report.py` additionally exercises the real
    query path (`fetch_usage_rows`) that produces `rows` in practice."""
    calls_reserved_total = sum(r.calls_reserved for r in rows)
    calls_made_total = sum(r.calls_made for r in rows)
    rows_by_status = dict(Counter(r.status for r in rows))

    resolved = [r for r in rows if r.status in _TERMINAL_STATUSES]
    answered_rows = sum(
        1 for r in resolved if r.status == "settled" and len(r.verification_ids) > 0
    )
    fallback_rows = len(resolved) - answered_rows
    fallback_rate = (fallback_rows / len(resolved)) if resolved else None

    eligible = [r for r in rows if r.status == "settled" and len(r.selection_ids) > 0]
    disagreement_rows = sum(
        1 for r in eligible if set(r.verification_ids) < set(r.selection_ids)
    )
    disagreement_rate = (disagreement_rows / len(eligible)) if eligible else None

    requests_by_identity_hash: dict[str, int] = {}
    for r in rows:
        requests_by_identity_hash[r.identity_hash] = (
            requests_by_identity_hash.get(r.identity_hash, 0) + 1
        )

    return SpendReport(
        start=start,
        end=end,
        calls_reserved_total=calls_reserved_total,
        calls_made_total=calls_made_total,
        rows_total=len(rows),
        rows_by_status=rows_by_status,
        resolved_rows=len(resolved),
        answered_rows=answered_rows,
        fallback_rows=fallback_rows,
        fallback_rate=fallback_rate,
        disagreement_eligible_rows=len(eligible),
        disagreement_rows=disagreement_rows,
        disagreement_rate=disagreement_rate,
        requests_by_identity_hash=requests_by_identity_hash,
        cap_snapshots=list(cap_snapshots),
    )


def build_service_client(url: str | None = None, key: str | None = None) -> Client:
    """A plain, unshared Supabase client authenticated as the SERVICE
    ROLE. Deliberately NOT built through `app.db.client`'s anon/user-
    scoped factories — see module docstring "WHY SERVICE ROLE, NOT A
    REVIEWER LOGIN" for exactly what those cannot see. Reads
    `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` straight from the process
    environment, the same two names `scripts/seed_synthetic.py` and
    `tests/db/conftest.py`'s `admin_client` already use — never from
    `app.core.config.Settings`, which deliberately never carries this
    key at all."""
    resolved_url = (url or os.environ.get("SUPABASE_URL", "")).strip()
    resolved_key = (key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    if not resolved_url or not resolved_key:
        raise SpendReportUnavailableError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set in the "
            "environment for this owner-run report. Never put the service-role key "
            "in the application's own .env (app/core/config.py never reads it)."
        )
    return create_client(resolved_url, resolved_key)


def fetch_usage_rows(client: Client, *, start: date, end: date) -> list[UsageRow]:
    """Every `ai_usage` row created in `[start, end)` — UTC calendar
    dates, `end` EXCLUSIVE. See module docstring "NO CLAIM OR ANSWER
    CONTENT, NO RAW IDENTITY" for why the column list is explicit."""
    start_iso = f"{start.isoformat()}T00:00:00+00:00"
    end_iso = f"{end.isoformat()}T00:00:00+00:00"
    raw = cast(
        "list[dict[str, Any]]",
        client.table("ai_usage")
        .select(_USAGE_COLUMNS)
        .gte("created_at", start_iso)
        .lt("created_at", end_iso)
        .execute()
        .data,
    )
    return [_row_from_raw(row) for row in raw]


def _format_rate(rate: float | None) -> str:
    return "n/a (no resolved rows)" if rate is None else f"{rate:.1%}"


def _print_report(report: SpendReport) -> None:
    print(f"AI spend report: {report.start.isoformat()} to {report.end.isoformat()} (UTC, exclusive end)")  # noqa: E501, T201
    print(f"  rows: {report.rows_total}  (by status: {report.rows_by_status})")  # noqa: T201
    print(f"  calls reserved: {report.calls_reserved_total}   calls made (settled): {report.calls_made_total}")  # noqa: E501, T201
    print(  # noqa: T201
        f"  fallback rate (not {AIAnswerStatus.answered.value!r}): "
        f"{_format_rate(report.fallback_rate)}  "
        f"({report.fallback_rows}/{report.resolved_rows} resolved rows)"
    )
    print(  # noqa: T201
        f"  two-pass disagreement rate: {_format_rate(report.disagreement_rate)}  "
        f"({report.disagreement_rows}/{report.disagreement_eligible_rows} eligible rows)"
    )
    print(f"  distinct identity-hash buckets: {len(report.requests_by_identity_hash)}")  # noqa: T201
    for cap in report.cap_snapshots:
        print(  # noqa: T201
            f"  cap[{cap.name}] {cap.period_key}: {cap.used}/{cap.limit} "
            f"({cap.fraction:.1%})"
        )


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only AI spend report (AI-13). Never writes anything."
    )
    parser.add_argument(
        "--start", type=_parse_date, required=True, help="UTC date, YYYY-MM-DD, inclusive"
    )
    parser.add_argument(
        "--end", type=_parse_date, required=True, help="UTC date, YYYY-MM-DD, exclusive"
    )
    parser.add_argument(
        "--check-alerts",
        action="store_true",
        help="also run the threshold-alert check (app.ai.alerts) and send any due notices",
    )
    parser.add_argument(
        "--alert-to", default=None, help="recipient email, required with --check-alerts"
    )
    args = parser.parse_args(argv)

    if args.check_alerts and not args.alert_to:
        parser.error("--check-alerts needs --alert-to")

    client = build_service_client()
    rows = fetch_usage_rows(client, start=args.start, end=args.end)
    caps = fetch_fresh(client)
    report = build_report(rows, start=args.start, end=args.end, cap_snapshots=caps)
    _print_report(report)

    if args.check_alerts:
        fired = check_thresholds(caps, recipient=args.alert_to, sender=get_email_sender())
        if fired:
            print("alerts sent:")  # noqa: T201
            for event in fired:
                pct = round(event.threshold * 100)
                print(  # noqa: T201
                    f"  {event.cap_name} cap crossed {pct}% for {event.period_key} "
                    f"({event.used}/{event.limit})"
                )
        else:
            print("alerts: nothing newly due")  # noqa: T201

    return 0


if __name__ == "__main__":
    sys.exit(main())
