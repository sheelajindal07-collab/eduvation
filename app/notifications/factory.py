"""The one place that decides which `EmailSender` actually runs.

Mirrors the shape `app/ai/`'s AI provider would use if anything in this
app wired it up yet (nothing does — M5 groundwork only, see
`app/ai/gemini_provider.py`'s own docstring). This module IS wired up:
`app/api/guardian_consent.py`'s sign-up/sign-in gate calls
`get_email_sender()` to obtain the sender it sends the guardian
confirmation email through.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.notifications.logging_sender import LoggingEmailSender
from app.notifications.sender import EmailSender
from app.notifications.smtp_sender import SmtpEmailSender


def get_email_sender() -> EmailSender:
    """`SmtpEmailSender` once a real provider is configured
    (`Settings.email_configured`); `LoggingEmailSender` otherwise — which
    is every environment today, see that module's docstring for what
    that actually means in practice.

    Not process-wide cached on purpose (mirrors `app/ai/budget.
    default_budget`'s own note): `LoggingEmailSender` accumulates `sent`
    per instance, and a caller (a test, in particular) that wants to
    assert on what was sent should construct its own instance and pass
    it directly to `app/api/guardian_consent.py`'s functions rather than
    rely on a shared instance here.
    """
    settings = get_settings()
    if settings.email_configured:
        return SmtpEmailSender()
    return LoggingEmailSender()
