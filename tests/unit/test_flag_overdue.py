"""CONSENT-8 — pure/unit-level coverage that needs no database:

1. `app.web.support_pages.is_flag_overdue` — the 24-hour overdue highlight
   (the task's own acceptance wording: "unit-tested with a flag
   deliberately timestamped >24h old and one deliberately timestamped
   recent").
2. `app.safeguarding.notify.notify_safeguarding_flag` — the webhook is a
   no-op when unconfigured, and its outgoing payload (inspected directly,
   not just the function's signature) carries nothing but the flag id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import Settings
from app.safeguarding import notify as notify_module
from app.web import support_pages


class TestIsFlagOverdue:
    def test_a_flag_more_than_24_hours_old_is_overdue(self) -> None:
        now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
        created_at = now - timedelta(hours=24, minutes=1)
        assert support_pages.is_flag_overdue(created_at, now) is True

    def test_a_flag_exactly_24_hours_old_is_not_yet_overdue(self) -> None:
        """Strictly more than 24h -- exactly on the boundary is not
        overdue yet, matching OVERDUE_AFTER's own `>` comparison."""
        now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
        created_at = now - timedelta(hours=24)
        assert support_pages.is_flag_overdue(created_at, now) is False

    def test_a_recent_flag_is_not_overdue(self) -> None:
        now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
        created_at = now - timedelta(minutes=5)
        assert support_pages.is_flag_overdue(created_at, now) is False

    def test_a_naive_datetime_is_treated_as_utc_not_rejected(self) -> None:
        now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
        naive_created_at = datetime(2026, 9, 20, 12, 0, 0)  # no tzinfo
        assert support_pages.is_flag_overdue(naive_created_at, now) is True

    def test_defaults_to_the_real_current_time_when_now_is_omitted(self) -> None:
        far_past = datetime(2000, 1, 1, tzinfo=UTC)
        assert support_pages.is_flag_overdue(far_past) is True
        just_now = datetime.now(UTC)
        assert support_pages.is_flag_overdue(just_now) is False


class TestNotifySafeguardingFlag:
    def test_no_webhook_url_configured_is_a_silent_no_op(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            notify_module, "get_settings", lambda: Settings(_env_file=None, n8n_webhook_url=None)
        )

        def _fail_if_called(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("httpx.post must never be called with no webhook URL configured")

        monkeypatch.setattr(notify_module.httpx, "post", _fail_if_called)

        result = notify_module.notify_safeguarding_flag("11111111-1111-1111-1111-111111111111")
        assert result is False

    def test_configured_webhook_receives_only_the_flag_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proven by inspecting the actual outgoing call, not the function
        signature (the task's own acceptance wording): the captured
        `json=` payload's keys are checked directly."""
        monkeypatch.setattr(
            notify_module,
            "get_settings",
            lambda: Settings(_env_file=None, n8n_webhook_url="http://localhost:9999/webhook"),
        )

        calls: list[dict[str, Any]] = []

        def _fake_post(url: str, *, json: Any = None, timeout: Any = None) -> None:
            calls.append({"url": url, "json": json, "timeout": timeout})

        monkeypatch.setattr(notify_module.httpx, "post", _fake_post)

        flag_id = "22222222-2222-2222-2222-222222222222"
        result = notify_module.notify_safeguarding_flag(flag_id)

        assert result is True
        assert len(calls) == 1
        assert calls[0]["url"] == "http://localhost:9999/webhook"
        payload = calls[0]["json"]
        assert payload == {"flag_id": flag_id}
        # No free text, no email, no user id in any other form -- the
        # payload's only key is flag_id, full stop.
        assert set(payload.keys()) == {"flag_id"}
        for value in payload.values():
            assert "@" not in str(value)  # no email ever slips in

    def test_a_transport_failure_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            notify_module,
            "get_settings",
            lambda: Settings(_env_file=None, n8n_webhook_url="http://localhost:9999/webhook"),
        )

        def _raise(*args: Any, **kwargs: Any) -> None:
            raise ConnectionError("boom")

        monkeypatch.setattr(notify_module.httpx, "post", _raise)

        result = notify_module.notify_safeguarding_flag("33333333-3333-3333-3333-333333333333")
        assert result is False
