"""LoggingEmailSender — the ONLY EmailSender that actually runs anywhere
in this app today (dev, tests, and — until the owner provisions a real
provider — a real deployment too). Logs at INFO level exactly what would
have been sent (`to`, `subject`, the rendered body, which for the
guardian-consent flow includes the full confirmation link with its
token) and does nothing else: no network call, no real inbox is ever
reached.

## This is a deliberate, loud limitation, not a bug
No SMTP/SendGrid/SES/Mailgun/Resend account is configured anywhere in
this codebase, and this task was explicitly scoped NOT to sign up for or
wire one — provisioning a real provider is an owner action (CLAUDE.md:
"no secrets in repo memory — variable names only, values via provider
dashboards / environment"), the exact same shape as
`app/ai/gemini_provider.py` needing a real `GEMINI_API_KEY` before it can
make a real call. See `app/notifications/smtp_sender.py` for the gated,
real (but unconfigured) alternative, and `Settings.email_configured`
(`app/core/config.py`) for how the app decides which one is actually
used at runtime (`app/notifications/factory.py`).

## Practical consequence — read this before treating the gate as done
`app/api/guardian_consent.py`'s account-status bookkeeping is genuinely
real: an under-18 account genuinely stays `pending_guardian_consent`
until `confirm_guardian_consent()` is called with a valid token, and
that part is enforced at the database (`db/migrations/0004_guardian_
consent.sql`), not just by this sender's own good behaviour. But with
`LoggingEmailSender` as the active sender, **no guardian ever actually
receives the link to click** — the token only ever reaches this
process's own log output. STATUS.md names the exact owner action needed
(provision a real provider, set the matching `.env` values) before this
gate provides real child-safety protection rather than correct-but-
inert database bookkeeping nobody downstream can act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LoggingEmailSender:
    """Deterministic `EmailSender` implementation. `sent` records every
    call (`to`/`subject`/`body`) so a test can assert what WOULD have
    been sent, without ever actually sending it — same `calls`-recording
    idiom as `app/ai/mock_provider.py`'s `MockAIProvider.calls`."""

    sent: list[dict[str, str]] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info(
            "EMAIL NOT SENT — no real provider is configured "
            "(app/notifications/logging_sender.py). Would send:\n"
            "  to: %s\n  subject: %s\n  body:\n%s",
            to,
            subject,
            body,
        )
        self.sent.append({"to": to, "subject": subject, "body": body})
