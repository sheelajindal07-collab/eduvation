"""Real `EmailSender` implementation, over plain SMTP (stdlib `smtplib` —
no new dependency; any real provider this pilot might pick — SendGrid,
SES, Mailgun, Resend, a plain Gmail/Workspace relay — exposes an SMTP
endpoint, so this one implementation covers all of them without
presupposing which the owner eventually chooses).

**Never constructed by anything in this codebase's own request path or
test suite today** — mirrors `app/ai/gemini_provider.py`'s own docstring
claim about `GeminiProvider` exactly, for the identical reason:
`app/notifications/factory.py`'s `get_email_sender()` only returns one of
these once `Settings.email_configured` is true, and nothing sets the
required `SMTP_*` environment variables anywhere in this repo or CI.
Constructing one makes no network call by itself; only `.send()` does.

Gated construction (mirrors `app/db/client.py`'s
`SupabaseNotConfiguredError` / `app/ai/gemini_provider.py`'s
`GeminiNotConfiguredError` — "fail clearly, don't silently degrade"):
`SmtpEmailSender()` raises `SmtpNotConfiguredError` immediately unless
`Settings.smtp_host`/`smtp_username`/`smtp_password` are all actually
set, rather than constructing successfully and only failing (or worse,
silently no-op'ing) the first time `.send()` is called.

**This task was explicitly scoped NOT to sign up for or configure a real
email provider account** — that is an owner action (provision an SMTP
relay, put the credentials in the owner's own `.env`, never in chat or
this repo). This class exists so that action is the ONLY thing standing
between "database bookkeeping only" and "guardian emails actually
deliver" — see `app/notifications/logging_sender.py`'s docstring and
STATUS.md for what runs instead until then.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from app.core.config import get_settings


class SmtpNotConfiguredError(RuntimeError):
    """Raised by `SmtpEmailSender()` when SMTP_HOST/SMTP_USERNAME/
    SMTP_PASSWORD are not all set. Mirrors `GeminiNotConfiguredError` —
    a missing credential is a clear, immediate construction-time
    failure, never a sender that silently no-ops."""


class SmtpEmailSender:
    """`EmailSender` backed by a real SMTP relay. See module docstring."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.email_configured:
            raise SmtpNotConfiguredError(
                "SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD are not all set. "
                "Provision a real SMTP relay (any transactional email "
                "provider's SMTP endpoint works) via its own dashboard, then "
                "put the credentials in your own .env (CLAUDE.md: no secrets "
                "in repo memory, values via provider dashboards / environment "
                "only)."
            )
        assert settings.smtp_host is not None
        assert settings.smtp_username is not None
        assert settings.smtp_password is not None
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._from_address = settings.smtp_from_address or settings.smtp_username

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = MIMEText(body, "plain")
        message["Subject"] = subject
        message["From"] = self._from_address
        message["To"] = to

        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(self._username, self._password)
            smtp.sendmail(self._from_address, [to], message.as_string())
