"""Unit tests for app.ai.alerts (AI-13, BCI-023).

No network, no live stack anywhere in this file: `CapSnapshot`/
`CapThresholdEvent` are built by hand and `AlertStateStore` always points
at a pytest `tmp_path` file, never the OS-temp default `app/ai/alerts.py`
itself falls back to — so two test runs (or a leftover file from a
previous manual run) can never bleed into these assertions.
`app.ai.alerts.fetch_fresh`/`check_and_notify` (the DB-touching half)
are exercised against the live stack instead, in
tests/db/test_ai_spend_report.py, per this card's own "Tests" section.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.ai.alerts import (
    DAILY_CAP,
    MONTHLY_CAP,
    THRESHOLDS,
    AlertStateStore,
    AlertsUnavailableError,
    CapSnapshot,
    CapThresholdEvent,
    check_thresholds,
    snapshots_from_caps_row,
)
from app.notifications.logging_sender import LoggingEmailSender

RECIPIENT = "owner@example.invalid"

#: A raw account id, a guest-session token's SHA-256 digest, or a
#: selection/verification id (`ai_usage.selection_ids`/
#: `.verification_ids`, both `uuid[]`) would each look like one of these
#: two shapes if it ever leaked into an alert's subject/body — neither
#: shape is otherwise produced by anything `app/ai/alerts.py` builds.
_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)


def _store(tmp_path: Path) -> AlertStateStore:
    return AlertStateStore(tmp_path / "state.json")


class TestCapSnapshotFraction:
    def test_fraction_is_used_over_limit(self) -> None:
        snap = CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=25, limit=50)
        assert snap.fraction == 0.5

    def test_fraction_is_zero_for_a_non_positive_limit(self) -> None:
        """Belt-and-braces: `ai_usage_caps`' own CHECK constraints
        already forbid a non-positive cap, so this path is not expected
        to run against real data, but it must not raise if it ever does."""
        snap = CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=5, limit=0)
        assert snap.fraction == 0.0


class TestSixThresholdCapCombinationsFireExactlyOncePerPeriod:
    """The card's own accounting: 2 caps (daily, monthly) x 3 thresholds
    (50%, 80%, 100%) = 6 combinations, each fired exactly once for a
    given period and never re-sent on a later check of that same period.
    """

    def test_all_six_fire_on_the_first_check_at_100_percent(self, tmp_path: Path) -> None:
        caps = [
            CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=50, limit=50),
            CapSnapshot(name=MONTHLY_CAP, period_key="2026-09", used=500, limit=500),
        ]
        sender = LoggingEmailSender()
        fired = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=_store(tmp_path))

        combos = {(event.cap_name, event.threshold) for event in fired}
        expected = {
            (cap, threshold) for cap in (DAILY_CAP, MONTHLY_CAP) for threshold in THRESHOLDS
        }
        assert combos == expected
        assert len(fired) == 6
        assert len(sender.sent) == 6

    def test_thresholds_fire_in_ascending_order_per_cap(self, tmp_path: Path) -> None:
        caps = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=100, limit=100)]
        sender = LoggingEmailSender()
        fired = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=_store(tmp_path))
        assert [event.threshold for event in fired] == [0.5, 0.8, 1.0]

    def test_a_second_check_of_the_same_period_sends_nothing_new(self, tmp_path: Path) -> None:
        caps = [
            CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=50, limit=50),
            CapSnapshot(name=MONTHLY_CAP, period_key="2026-09", used=500, limit=500),
        ]
        sender = LoggingEmailSender()
        store = _store(tmp_path)

        first = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=store)
        second = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=store)

        assert len(first) == 6
        assert second == []
        assert len(sender.sent) == 6, "the second check must not have sent anything more"

    def test_a_new_period_key_fires_again_independently(self, tmp_path: Path) -> None:
        """A new UTC day resets the DAILY cap's own notices without
        being affected by (or affecting) the monthly cap's state."""
        store = _store(tmp_path)
        sender = LoggingEmailSender()

        day_one = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=50, limit=50)]
        check_thresholds(day_one, recipient=RECIPIENT, sender=sender, state=store)

        day_two = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-23", used=50, limit=50)]
        fired = check_thresholds(day_two, recipient=RECIPIENT, sender=sender, state=store)

        assert len(fired) == 3
        assert all(event.period_key == "2026-09-23" for event in fired)

    def test_crossing_two_thresholds_at_once_fires_both_not_just_the_higher(
        self, tmp_path: Path
    ) -> None:
        """A cap discovered already at 85% on its very first check this
        period must still get its 50% AND its 80% notice, once each —
        not just the highest threshold reached."""
        caps = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=85, limit=100)]
        sender = LoggingEmailSender()
        fired = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=_store(tmp_path))
        assert {event.threshold for event in fired} == {0.5, 0.8}

    def test_below_every_threshold_fires_nothing(self, tmp_path: Path) -> None:
        caps = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=10, limit=100)]
        sender = LoggingEmailSender()
        fired = check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=_store(tmp_path))
        assert fired == []
        assert sender.sent == []


class TestNoClaimOrAnswerContentAndNoRawIdentityInAnAlert:
    def test_cap_snapshot_and_event_carry_only_numbers_and_period_labels(self) -> None:
        """Structural guarantee, not a filter: neither dataclass has a
        field that COULD hold a claim, an AI answer or an identity —
        mirrors db/migrations/0011_ai_usage.sql's own "the table has no
        such column" guarantee for `ai_usage` itself."""
        assert set(CapSnapshot.__dataclass_fields__) == {"name", "period_key", "used", "limit"}
        assert set(CapThresholdEvent.__dataclass_fields__) == {
            "cap_name",
            "period_key",
            "threshold",
            "used",
            "limit",
        }

    def test_the_email_actually_sent_carries_only_the_cap_numbers(self, tmp_path: Path) -> None:
        # used == exactly half of limit: crosses ONLY the 50% threshold,
        # so exactly one email is sent, keeping this test's own
        # assertions about "the" email unambiguous.
        caps = [CapSnapshot(name=DAILY_CAP, period_key="2026-09-22", used=25, limit=50)]
        sender = LoggingEmailSender()
        check_thresholds(caps, recipient=RECIPIENT, sender=sender, state=_store(tmp_path))

        assert len(sender.sent) == 1
        sent = sender.sent[0]
        assert sent["to"] == RECIPIENT
        assert "daily" in sent["subject"]
        assert "25" in sent["body"] and "50" in sent["body"]
        # The real guarantee is structural (the dataclass test above,
        # which shows CapSnapshot/CapThresholdEvent hold nothing but
        # numbers and period labels to begin with) — this is the
        # behavioural proof that nothing hash- or id-shaped rode along
        # in the rendered subject/body either.
        assert not _HEX64.search(sent["subject"] + sent["body"]), (
            "a 64-hex-char token would be an identity_hash digest leaking through"
        )
        assert not _UUID.search(sent["subject"] + sent["body"]), (
            "a UUID would be a selection_ids/verification_ids entry leaking through"
        )


class TestAlertStateStorePersistsBetweenInstances:
    """Simulates the real usage pattern this card describes: "a script
    run every few minutes" — i.e. a FRESH process, and therefore a fresh
    `AlertStateStore` instance, every time. Only a marker that survives
    across separate instances over the same path can suppress a repeat."""

    def test_a_new_store_instance_over_the_same_file_remembers_what_fired(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        AlertStateStore(path).mark_fired("2026-09-22", DAILY_CAP, 0.5)
        assert AlertStateStore(path).has_fired("2026-09-22", DAILY_CAP, 0.5) is True

    def test_an_unfired_threshold_is_false(self, tmp_path: Path) -> None:
        assert _store(tmp_path).has_fired("2026-09-22", DAILY_CAP, 0.5) is False

    def test_a_missing_state_file_is_treated_as_empty_not_an_error(self, tmp_path: Path) -> None:
        store = AlertStateStore(tmp_path / "does-not-exist.json")
        assert store.has_fired("2026-09-22", DAILY_CAP, 0.5) is False

    def test_a_corrupt_state_file_is_treated_as_empty_not_a_crash(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = AlertStateStore(path)
        assert store.has_fired("2026-09-22", DAILY_CAP, 0.5) is False

    def test_marking_the_same_threshold_twice_is_idempotent(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.mark_fired("2026-09-22", DAILY_CAP, 0.5)
        store.mark_fired("2026-09-22", DAILY_CAP, 0.5)
        assert store.has_fired("2026-09-22", DAILY_CAP, 0.5) is True


class TestSnapshotsFromCapsRow:
    def test_builds_daily_and_monthly_snapshots_with_the_right_period_keys(self) -> None:
        caps_row = {
            "per_identity_daily_calls": 5,
            "global_daily_calls": 50,
            "global_monthly_calls": 500,
        }
        snapshots = snapshots_from_caps_row(
            caps_row,
            usage_today_global=10,
            usage_month_global=100,
            today=date(2026, 9, 22),
        )
        by_name = {snap.name: snap for snap in snapshots}
        assert by_name[DAILY_CAP].period_key == "2026-09-22"
        assert by_name[DAILY_CAP].used == 10
        assert by_name[DAILY_CAP].limit == 50
        assert by_name[MONTHLY_CAP].period_key == "2026-09"
        assert by_name[MONTHLY_CAP].used == 100
        assert by_name[MONTHLY_CAP].limit == 500

    def test_never_builds_a_per_identity_snapshot(self) -> None:
        """See app/ai/alerts.py's own "WHICH CAPS, AND WHY" — the
        per-identity cap is deliberately never alerted on."""
        caps_row = {
            "per_identity_daily_calls": 5,
            "global_daily_calls": 50,
            "global_monthly_calls": 500,
        }
        snapshots = snapshots_from_caps_row(
            caps_row, usage_today_global=1, usage_month_global=1, today=date(2026, 9, 22)
        )
        assert {snap.name for snap in snapshots} == {DAILY_CAP, MONTHLY_CAP}


def test_alerts_unavailable_error_is_a_runtime_error() -> None:
    assert issubclass(AlertsUnavailableError, RuntimeError)
