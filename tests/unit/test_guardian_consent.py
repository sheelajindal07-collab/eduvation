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

import pytest

from app.api.guardian_consent import MINOR_AGE_THRESHOLD_YEARS, compute_age, is_minor
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
