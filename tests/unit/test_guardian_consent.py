"""Unit tests for app/api/guardian_consent.py's pure logic (age
arithmetic) and app/notifications/'s pluggable EmailSender — no network
call, no live database, mirroring tests/unit/test_ai_adapter.py's own
gated-construction tests for GeminiProvider exactly, for the same reason
(app/notifications/smtp_sender.py's SmtpEmailSender mirrors
app/ai/gemini_provider.py's GeminiProvider on purpose).

Live, database-backed behaviour (the actual gate, RLS, the confirm
endpoint) is in tests/db/test_guardian_consent.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest
from supabase import Client

from app.api.guardian_consent import (
    MINOR_AGE_THRESHOLD_YEARS,
    compute_age,
    create_guardian_consent_request,
    is_minor,
)
from app.core.config import Settings
from app.notifications.logging_sender import LoggingEmailSender
from app.notifications.sender import EmailSender
from app.notifications.smtp_sender import SmtpEmailSender, SmtpNotConfiguredError

# ---------------------------------------------------------------------
# compute_age / is_minor — ordinary arithmetic, boundary-checked.
# ---------------------------------------------------------------------


def test_compute_age_before_birthday_this_year() -> None:
    assert compute_age(date(2010, 6, 15), as_of=date(2026, 6, 14)) == 15


def test_compute_age_on_birthday_counts_the_new_year() -> None:
    assert compute_age(date(2010, 6, 15), as_of=date(2026, 6, 15)) == 16


def test_compute_age_after_birthday_this_year() -> None:
    assert compute_age(date(2010, 6, 15), as_of=date(2026, 6, 16)) == 16


def test_is_minor_true_just_under_threshold() -> None:
    dob = date(2008, 9, 21)
    as_of = date(2026, 9, 20)  # one day before turning 18
    assert compute_age(dob, as_of=as_of) == 17
    assert is_minor(dob, as_of=as_of) is True


def test_is_minor_false_exactly_at_threshold() -> None:
    dob = date(2008, 9, 21)
    as_of = date(2026, 9, 21)  # 18th birthday
    assert compute_age(dob, as_of=as_of) == MINOR_AGE_THRESHOLD_YEARS
    assert is_minor(dob, as_of=as_of) is False


def test_is_minor_false_well_over_threshold() -> None:
    assert is_minor(date(1990, 1, 1), as_of=date(2026, 9, 21)) is False


# ---------------------------------------------------------------------
# LoggingEmailSender — the sender that actually runs today. Never a
# network call; records what it "sent" for a caller to assert on.
# ---------------------------------------------------------------------


def test_logging_email_sender_records_the_call_and_sends_nothing_real() -> None:
    sender = LoggingEmailSender()
    sender.send(to="guardian@example.com", subject="Confirm", body="Click here: ...")
    assert sender.sent == [
        {"to": "guardian@example.com", "subject": "Confirm", "body": "Click here: ..."}
    ]


def test_logging_email_sender_satisfies_the_email_sender_protocol() -> None:
    assert isinstance(LoggingEmailSender(), EmailSender)


# ---------------------------------------------------------------------
# create_guardian_consent_request — the RPC-call shape
# (db/migrations/0005_guardian_consent_request_rpc.sql). Mocks
# `client.rpc(...).execute()` only, never a live database — the live,
# RLS-backed version of this same function is exercised in
# tests/db/test_guardian_consent.py's TestCreateGuardianConsentRequest.
#
# Why this RPC exists at all, in one line (full reasoning in the
# migration and in create_guardian_consent_request's own docstring):
# supabase-py's `.table(...).insert(...).execute()` used to ask
# PostgREST to RETURNING the inserted row, which Postgres RLS gates on
# guardian_consents' (nonexistent, by design) SELECT policy — so the
# insert failed outright. The fix reads the token back inside a
# SECURITY DEFINER function instead, which is what `client.rpc(...)`
# below stands in for.
# ---------------------------------------------------------------------


class _FakeRpcExecute:
    """Stands in for the `.execute()` call at the end of
    `client.rpc(name, params).execute()` — just enough of postgrest's
    return shape (a `.data` attribute) for
    create_guardian_consent_request, which reads nothing else off it."""

    def __init__(self, data: str | None) -> None:
        self.data = data

    def execute(self) -> _FakeRpcExecute:
        return self


class _FakeSupabaseClient:
    """A minimal stand-in for `supabase.Client` — the only method
    create_guardian_consent_request calls on `client` is `.rpc(...)`, so
    that's the only one faked here. Records every call so a test can
    assert on exactly what was sent, the same "assert on what was
    actually sent" style this file already uses for LoggingEmailSender."""

    def __init__(self, *, token: str | None) -> None:
        self._token = token
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, fn_name: str, params: dict[str, Any]) -> _FakeRpcExecute:
        self.rpc_calls.append((fn_name, dict(params)))
        return _FakeRpcExecute(self._token)


def test_create_guardian_consent_request_calls_the_rpc_and_never_sends_a_student_id() -> None:
    """The core shape of the fix: exactly one call to the
    `create_guardian_consent_request` RPC, with only the two documented
    params — and, just as importantly, proves the spoofing-is-
    structurally-impossible claim at the Python layer: there is no
    `student_id` key in the params this function ever constructs (the
    RPC determines the caller from `auth.uid()` server-side; a
    `student_id` parameter doesn't exist for anyone to even attempt to
    spoof with)."""
    fake_client = _FakeSupabaseClient(token="freshly-generated-token-value")
    sender = LoggingEmailSender()

    create_guardian_consent_request(
        cast(Client, fake_client),
        student_id="some-other-students-uuid-must-never-reach-the-rpc",
        date_of_birth=date(2015, 3, 4),
        guardian_email="guardian@example.com",
        sender=sender,
    )

    assert len(fake_client.rpc_calls) == 1
    fn_name, params = fake_client.rpc_calls[0]
    assert fn_name == "create_guardian_consent_request"
    assert params == {
        "p_date_of_birth": "2015-03-04",
        "p_guardian_email": "guardian@example.com",
    }
    assert "student_id" not in params
    assert "p_student_id" not in params

    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == "guardian@example.com"
    assert "freshly-generated-token-value" in sender.sent[0]["body"]


def test_create_guardian_consent_request_sends_no_email_when_rpc_reports_already_pending() -> None:
    """The RPC returns NULL (not an error) when a pending request already
    existed — idempotent-skip, no second email, matching the previous
    caught-unique-violation behaviour this RPC call replaced."""
    fake_client = _FakeSupabaseClient(token=None)
    sender = LoggingEmailSender()

    create_guardian_consent_request(
        cast(Client, fake_client),
        student_id="student-uuid",
        date_of_birth=date(2015, 3, 4),
        guardian_email="guardian@example.com",
        sender=sender,
    )

    assert len(fake_client.rpc_calls) == 1  # the RPC was still called
    assert sender.sent == []  # but no email — nothing new was created


# ---------------------------------------------------------------------
# SmtpEmailSender — never constructed anywhere in this app's own request
# path or test suite except here, exactly like GeminiProvider
# (tests/unit/test_ai_adapter.py's own equivalent tests).
# ---------------------------------------------------------------------


def test_smtp_email_sender_is_not_constructible_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.notifications.smtp_sender as smtp_sender_module

    monkeypatch.setattr(smtp_sender_module, "get_settings", lambda: Settings(_env_file=None))

    with pytest.raises(SmtpNotConfiguredError):
        SmtpEmailSender()


def test_smtp_email_sender_constructs_once_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flip side of the gate above: configured credentials let the
    object actually construct (still makes no network call — building
    the object does not itself connect to an SMTP server)."""
    import app.notifications.smtp_sender as smtp_sender_module

    monkeypatch.setattr(
        smtp_sender_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            smtp_host="smtp.example.invalid",
            smtp_username="test-only-not-real",
            smtp_password="test-only-not-real",
        ),
    )

    sender = SmtpEmailSender()
    assert isinstance(sender, EmailSender)


def test_settings_email_configured_is_false_by_default() -> None:
    assert Settings(_env_file=None).email_configured is False


def test_settings_email_configured_is_true_once_all_three_are_set() -> None:
    settings = Settings(
        _env_file=None,
        smtp_host="smtp.example.invalid",
        smtp_username="u",
        smtp_password="p",
    )
    assert settings.email_configured is True
