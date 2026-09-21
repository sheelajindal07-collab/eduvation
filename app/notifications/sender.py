"""EmailSender protocol — mirrors app/ai/adapter.py's AIProvider Protocol
exactly (see that module's docstring for the full reasoning; the short
version: an implementation is trusted with nothing more than "send this
already-built message", never with deciding what a message should say).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailSender(Protocol):
    """A plain-text transactional email sender, behind the adapter.

    Implementations (see `logging_sender.py` for the one this app
    actually uses today, `smtp_sender.py` for the gated real one) should
    raise on a genuine transport/API failure rather than swallowing it —
    same "fail loudly, don't silently degrade" contract as
    `app.ai.adapter.AIProvider.generate`. A caller that needs "this email
    never reaching an inbox must never look like it reached one" (the
    guardian-consent gate does) depends on that.
    """

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send one plain-text email. `body` is already-built, final text
        (see `app/notifications/guardian_consent_email.py`) — this method
        does no templating or content decisions of its own, same
        separation-of-concerns `AIProvider.generate` keeps from
        `app/ai/grounding.py`'s prompt construction."""
        ...
