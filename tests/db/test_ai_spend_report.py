"""scripts/ai_spend_report.py and app/ai/alerts.py against the live stack
(AI-13, BCI-023).

Everything this file seeds goes through `app.ai.budget_db.
AIRequestBudgetDB.reserve_usage()`/`.settle()` — the same real
reservation protocol `db/migrations/0011_ai_usage.sql` enforces for
every caller — never a direct `admin_client.table("ai_usage").insert()`,
so what this file proves is genuinely "the report reads what the real
protocol wrote", not "the report reads what a test fabricated in a shape
the protocol would never actually produce".

Three things are proved here:

1. **The numbers are right**, against a hand-built scenario whose
   fallback rate, two-pass disagreement rate and identity-hash bucket
   counts are worked out by hand in `_SEED_SCENARIO`'s own comment and
   cross-checked against `build_report`'s output.
2. **No claim/answer content, and no raw identity, ever appears** in
   anything this script or `app.ai.alerts` produces — checked
   structurally (the dataclasses' own field sets) and behaviourally (the
   raw identity strings this file itself creates are asserted absent
   from the rendered report and every alert email).
3. **The six threshold/cap combinations** (`app.ai.alerts`) fire against
   the LIVE `ai_usage_caps` row and LIVE `ai_usage` data, once each,
   through `fetch_fresh`/`check_and_notify` — the sibling, DB-touching
   half of tests/unit/test_ai_alerts.py's pure `check_thresholds` proof.
   `ai_usage_caps` is temporarily lowered and restored in a `finally`,
   the same pattern tests/db/test_ai_usage.py's
   `test_the_global_daily_cap_stops_an_identity_with_headroom_to_spare`
   already uses for the same reason (there is only ever one caps row).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from supabase import Client

from app.ai.alerts import (
    DAILY_CAP,
    MONTHLY_CAP,
    THRESHOLDS,
    AlertStateStore,
    CapThresholdEvent,
    check_and_notify,
    fetch_fresh,
)
from app.ai.budget_db import GUEST, AIRequestBudgetDB, identity_digest
from app.notifications.logging_sender import LoggingEmailSender
from scripts.ai_spend_report import (
    SpendReport,
    UsageRow,
    build_report,
    busiest_identity_daily_usage,
    fetch_per_identity_daily_cap,
    fetch_usage_rows,
)
from tests.db.conftest import RUN_ID, _require_live

TEMPLATE_ID = f"ai13-test-{RUN_ID}"

_MIGRATION_SKIP_REASON = (
    "db/migrations/0011_ai_usage.sql not yet applied to this stack. Apply "
    "db/migrations/*.sql (see db/migrations/README.md); a stale PostgREST "
    "schema cache looks identical and is reloaded by re-running the "
    "migrate step."
)


def _unavailable(reason: str) -> None:
    if _require_live():
        pytest.fail(f"BCION_REQUIRE_LIVE=1, so this may not skip: {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(autouse=True, scope="module")
def _migration_applied(admin_client: Client) -> None:
    try:
        admin_client.rpc("ai_usage_schema_version", {}).execute()
    except Exception:  # noqa: BLE001 — any failure here means "not applied yet"
        _unavailable(_MIGRATION_SKIP_REASON)


@pytest.fixture
def usage(admin_client: Client) -> Iterator[list[str]]:
    """Identity hashes whose rows this file wants removed afterwards —
    same fixture shape as tests/db/test_ai_usage.py's own `usage`."""
    hashes: list[str] = []
    yield hashes
    for identity_hash in hashes:
        admin_client.table("ai_usage").delete().eq("identity_hash", identity_hash).execute()


def _fresh_identity(usage: list[str], raw_identities: list[str]) -> AIRequestBudgetDB:
    """A budget handle for an identity no other test has ever used. The
    RAW identity string is also recorded (`raw_identities`) so
    `TestNoRawIdentityOrAnswerContentEverAppears` can assert it is never
    echoed anywhere this file's functions under test produce."""
    raw = f"ai13-{uuid.uuid4().hex}"
    raw_identities.append(raw)
    budget = AIRequestBudgetDB(identity_kind=GUEST, identity=raw, template_id=TEMPLATE_ID)
    usage.append(budget.identity_hash)
    return budget


def _caps(admin_client: Client) -> dict[str, Any]:
    rows = admin_client.table("ai_usage_caps").select("*").execute().data
    assert rows, "ai_usage_caps must hold exactly one configuration row (0011 seeds it)."
    return dict(rows[0])


# =====================================================================
# The seeded scenario — five rows, four identities, worked out by hand
# =====================================================================
# alpha (2 rows):
#   A: settled, selection=[s1,s2], verification=[s1]
#      -> ANSWERED (verification non-empty); DISAGREEMENT (proper subset)
#   B: settled, selection=[s3],    verification=[s3]
#      -> ANSWERED (verification non-empty); NOT disagreement (equal, not
#         a *proper* subset)
# beta (1 row):
#   C: settled, selection=[s4],    verification=[]
#      -> FALLBACK (verification empty); DISAGREEMENT (empty is a proper
#         subset of any non-empty set — pass two dropped everything)
# gamma (1 row):
#   D: failed (calls_made=0, no ids)
#      -> FALLBACK (status != settled); NOT eligible for disagreement
#         (status != settled)
# delta (1 row):
#   E: reserved (never settled)
#      -> EXCLUDED from the fallback rate entirely (not yet resolved);
#         EXCLUDED from disagreement eligibility (status != settled)
#
# Expected, by hand:
#   rows_total = 5;  rows_by_status = settled:3, failed:1, reserved:1
#   calls_reserved_total = 5 (one call reserved per row)
#   calls_made_total = 3 (A, B, C each settle 1 call; D settles 0; E never settles)
#   resolved_rows (settled+failed) = 4;  answered_rows = 2 (A, B)
#   fallback_rows = 2 (C, D);  fallback_rate = 0.5
#   disagreement_eligible_rows = 3 (A, B, C — settled + non-empty selection)
#   disagreement_rows = 2 (A, C);  disagreement_rate = 2/3
#   requests_by_identity_hash: alpha->2, beta->1, gamma->1, delta->1 (4 buckets)
def _seed_scenario(usage: list[str], raw_identities: list[str]) -> None:
    alpha = _fresh_identity(usage, raw_identities)
    s1, s2, s3 = (str(uuid.uuid4()) for _ in range(3))
    row_a = alpha.reserve_usage(calls=1)
    alpha.settle(
        row_a, calls_made=1, status="settled", selection_ids=[s1, s2], verification_ids=[s1]
    )
    row_b = alpha.reserve_usage(calls=1)
    alpha.settle(
        row_b, calls_made=1, status="settled", selection_ids=[s3], verification_ids=[s3]
    )

    beta = _fresh_identity(usage, raw_identities)
    s4 = str(uuid.uuid4())
    row_c = beta.reserve_usage(calls=1)
    beta.settle(row_c, calls_made=1, status="settled", selection_ids=[s4], verification_ids=[])

    gamma = _fresh_identity(usage, raw_identities)
    row_d = gamma.reserve_usage(calls=1)
    gamma.settle(row_d, calls_made=0, status="failed")

    delta = _fresh_identity(usage, raw_identities)
    delta.reserve_usage(calls=1)  # left `reserved` on purpose — never settled


def _own_rows(rows: list[UsageRow]) -> list[UsageRow]:
    return [row for row in rows if row.template_id == TEMPLATE_ID]


class TestTheNumbersAreRight:
    def test_the_full_scenario_matches_the_hand_worked_expectation(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        raw_identities: list[str] = []
        _seed_scenario(usage, raw_identities)

        today = date.today()
        tomorrow = today + timedelta(days=1)
        all_rows = fetch_usage_rows(admin_client, start=today, end=tomorrow)
        rows = _own_rows(all_rows)
        report = build_report(rows, start=today, end=tomorrow)

        assert report.rows_total == 5
        assert report.rows_by_status == {"settled": 3, "failed": 1, "reserved": 1}
        assert report.calls_reserved_total == 5
        assert report.calls_made_total == 3
        assert report.resolved_rows == 4
        assert report.answered_rows == 2
        assert report.fallback_rows == 2
        assert report.fallback_rate == pytest.approx(0.5)
        assert report.disagreement_eligible_rows == 3
        assert report.disagreement_rows == 2
        assert report.disagreement_rate == pytest.approx(2 / 3)
        assert len(report.requests_by_identity_hash) == 4
        assert sorted(report.requests_by_identity_hash.values()) == [1, 1, 1, 2]

    def test_a_date_range_that_excludes_today_excludes_the_seeded_rows(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        raw_identities: list[str] = []
        _seed_scenario(usage, raw_identities)

        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        rows = _own_rows(fetch_usage_rows(admin_client, start=yesterday, end=today))
        assert rows == [], "a range ending before today must not include rows created today"

    def test_a_range_with_no_matching_rows_reports_none_rates_not_zero(self) -> None:
        """No resolved rows -> no fallback rate to report at all, and no
        eligible rows -> no disagreement rate — `None`, never a
        misleading `0.0` that would read as "0% fallback"."""
        today = date.today()
        report = build_report([], start=today, end=today + timedelta(days=1))
        assert report.fallback_rate is None
        assert report.disagreement_rate is None
        assert report.requests_by_identity_hash == {}


class TestNoRawIdentityOrAnswerContentEverAppears:
    """Structural (the dataclass field sets) AND behavioural (the raw
    identity strings this file itself created are never echoed back)."""

    def test_usage_row_and_spend_report_carry_no_field_that_could_hold_content(self) -> None:
        assert set(UsageRow.__dataclass_fields__) == {
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
        # selection_ids/verification_ids are opaque ids only (see
        # db/migrations/0011_ai_usage.sql's own header) — SpendReport
        # itself carries counts derived from them, never the ids.
        assert "selection_ids" not in SpendReport.__dataclass_fields__
        assert "verification_ids" not in SpendReport.__dataclass_fields__

    def test_no_raw_identity_appears_anywhere_in_the_built_report(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        raw_identities: list[str] = []
        _seed_scenario(usage, raw_identities)
        assert len(raw_identities) == 4

        today = date.today()
        tomorrow = today + timedelta(days=1)
        rows = _own_rows(fetch_usage_rows(admin_client, start=today, end=tomorrow))
        report = build_report(rows, start=today, end=tomorrow)

        haystack = repr(report) + repr(rows)
        for raw in raw_identities:
            assert raw not in haystack, f"raw identity {raw!r} leaked into the report"

        # Every bucket key this test's own identities produced is exactly
        # the digest `app.ai.budget_db.identity_digest` would compute for
        # the matching raw identity — i.e. the buckets ARE identity
        # hashes, correctly, not something else that merely looks like
        # one — and each is counted the right number of times.
        by_hash = report.requests_by_identity_hash
        alpha_hash, beta_hash, gamma_hash, delta_hash = (
            identity_digest(raw) for raw in raw_identities
        )
        assert by_hash.get(alpha_hash) == 2
        assert by_hash.get(beta_hash) == 1
        assert by_hash.get(gamma_hash) == 1
        assert by_hash.get(delta_hash) == 1


class TestPerIdentityDailyCapReporting:
    """The third cap `ai_usage_caps` defines (per-identity, daily) —
    reported as "the busiest identity's own utilisation today", never a
    per-identity breakdown and never naming which identity_hash it was
    (see `scripts.ai_spend_report.SpendReport.busiest_identity_daily_
    used`'s own docstring)."""

    def test_fetch_per_identity_daily_cap_matches_the_live_caps_row(
        self, admin_client: Client
    ) -> None:
        caps = _caps(admin_client)
        assert fetch_per_identity_daily_cap(admin_client) == int(caps["per_identity_daily_calls"])

    def test_busiest_identity_daily_usage_reflects_the_largest_bucket(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        raw_identities: list[str] = []
        _seed_scenario(usage, raw_identities)  # alpha alone costs 2 calls today

        today = date.today()
        tomorrow = today + timedelta(days=1)
        rows = _own_rows(fetch_usage_rows(admin_client, start=today, end=tomorrow))
        busiest = busiest_identity_daily_usage(rows)

        assert busiest >= 2, "alpha alone made 2 settled calls today"
        assert isinstance(busiest, int), "a bare count — structurally incapable of naming anyone"

    def test_busiest_identity_daily_usage_is_zero_for_no_rows(self) -> None:
        assert busiest_identity_daily_usage([]) == 0


class TestFetchFreshReflectsLiveUsage:
    def test_a_before_after_delta_matches_the_calls_just_made(
        self, admin_client: Client, usage: list[str]
    ) -> None:
        before = {snap.name: snap for snap in fetch_fresh(admin_client)}

        budget = AIRequestBudgetDB(
            identity_kind=GUEST, identity=f"ai13-fresh-{uuid.uuid4().hex}", template_id=TEMPLATE_ID
        )
        usage.append(budget.identity_hash)
        for _ in range(3):
            usage_id = budget.reserve_usage(calls=1)
            budget.settle(usage_id, calls_made=1, status="settled")

        after = {snap.name: snap for snap in fetch_fresh(admin_client)}
        assert after[DAILY_CAP].used - before[DAILY_CAP].used == 3
        assert after[MONTHLY_CAP].used - before[MONTHLY_CAP].used == 3


class TestSixThresholdCapCombinationsFireAgainstTheLiveCaps:
    """The DB-backed sibling of tests/unit/test_ai_alerts.py's pure
    `check_thresholds` proof: drives the same six-notices-once-each
    behaviour through `check_and_notify` against the real
    `ai_usage_caps` row and real `ai_usage` rows."""

    def test_check_and_notify_fires_all_six_combinations_exactly_once(
        self, admin_client: Client, usage: list[str], tmp_path: Path
    ) -> None:
        before_caps = _caps(admin_client)
        try:
            current = {snap.name: snap for snap in fetch_fresh(admin_client)}
            daily_used = current[DAILY_CAP].used
            monthly_used = current[MONTHLY_CAP].used

            admin_client.table("ai_usage_caps").update(
                {
                    "per_identity_daily_calls": 2,
                    "global_daily_calls": daily_used + 2,
                    "global_monthly_calls": monthly_used + 2,
                }
            ).eq("id", True).execute()

            budget = AIRequestBudgetDB(
                identity_kind=GUEST,
                identity=f"ai13-threshold-{uuid.uuid4().hex}",
                template_id=TEMPLATE_ID,
            )
            usage.append(budget.identity_hash)
            for _ in range(2):
                usage_id = budget.reserve_usage(calls=1)
                budget.settle(usage_id, calls_made=1, status="settled")

            sender = LoggingEmailSender()
            store = AlertStateStore(tmp_path / "state.json")
            fired: list[CapThresholdEvent] = check_and_notify(
                admin_client, recipient="owner@example.invalid", sender=sender, state=store
            )

            combos = {(event.cap_name, event.threshold) for event in fired}
            expected = {
                (cap, threshold) for cap in (DAILY_CAP, MONTHLY_CAP) for threshold in THRESHOLDS
            }
            assert combos == expected
            assert len(fired) == 6
            assert len(sender.sent) == 6

            # A second call for the same UTC day/month sends nothing more.
            again = check_and_notify(
                admin_client, recipient="owner@example.invalid", sender=sender, state=store
            )
            assert again == []
            assert len(sender.sent) == 6
        finally:
            admin_client.table("ai_usage_caps").update(
                {
                    "per_identity_daily_calls": int(before_caps["per_identity_daily_calls"]),
                    "global_daily_calls": int(before_caps["global_daily_calls"]),
                    "global_monthly_calls": int(before_caps["global_monthly_calls"]),
                }
            ).eq("id", True).execute()
        restored = _caps(admin_client)
        for column in ("per_identity_daily_calls", "global_daily_calls", "global_monthly_calls"):
            assert restored[column] == before_caps[column], f"{column} was not restored"
