"""Pluggable email-sending adapter — built for the guardian-consent gate
(app/api/guardian_consent.py) but generic enough for any future
transactional email BCION Lite needs.

Mirrors `app/ai/`'s adapter+mock/real-provider split exactly, on the
owner's own instruction for this task:
- `sender.py` — the `EmailSender` Protocol, mirroring `app/ai/adapter.py`'s
  `AIProvider` Protocol.
- `logging_sender.py` — `LoggingEmailSender`, the always-safe default,
  mirroring `app/ai/mock_provider.py`'s role (deterministic, no network
  call) but — unlike the AI mock, which is test-only — this one is what
  actually RUNS in every environment today, dev and (if deployed as-is)
  production alike, because no real provider is configured anywhere.
- `smtp_sender.py` — `SmtpEmailSender`, a real, working implementation
  (stdlib `smtplib`, no new dependency) gated behind construction-time
  configuration exactly the way `app/ai/gemini_provider.py` is gated
  behind `GEMINI_API_KEY` — raises immediately if unconfigured, rather
  than constructing successfully and failing (or silently no-op'ing) the
  first time `.send()` is called.
- `factory.py` — `get_email_sender()`, the one place that decides which
  of the two above actually runs, from `Settings.email_configured`.

**No email-sending capability existed anywhere in this codebase before
this task, and none is configured now.** `LoggingEmailSender` — see that
module's docstring — is what every guardian-consent email actually goes
through today: it logs what would have been sent, at INFO level, and does
nothing else. A guardian's real inbox is never reached until the owner
provisions a real provider (an SMTP relay, or a transactional email API
adapted the same way) and sets the matching `.env` values — see
`STATUS.md` for exactly what is and is not wired, spelled out loudly on
purpose: a consent gate whose email silently never sends would be worse
than no gate at all, because it would look like it works.
"""
