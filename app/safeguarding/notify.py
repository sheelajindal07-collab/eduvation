"""CONSENT-8 — the off-request-path safeguarding notification.

`notify_safeguarding_flag(flag_id)` is the ONLY thing this module does: a
single outbound HTTP POST to `Settings.n8n_webhook_url` (CLAUDE.md: "n8n off
the request path (reviewer notices, review-due reminders only)" — this is
exactly that channel, not a new one) carrying nothing but the flag's own
opaque id.

## Payload shape — closed, not a dict a caller can grow
The payload is exactly `{"flag_id": <str>}`. No free text, no email, no user
id in any human-readable form (the task's own wording) — deliberately not
`student_id` either, even though `safeguarding_flags.student_id` is itself
only ever an opaque uuid (never an email/name — see
`db/migrations/0013_safeguarding_schema.sql`'s own table comment): the
receiving n8n workflow does not need to know WHO a flag concerns to alert a
human that ONE exists, and every extra field here is one more thing a future
change to this function could accidentally widen. Whoever eventually reads
this payload back is expected to look the flag id up in
`GET /reviewer/support` (a signed-in safeguarding-staff session), which is
the one place this app enforces `is_safeguarding_staff()` before showing
anything about it — never carry the answer to that question in the webhook
call itself.

## No configured URL -> no-op, not an error
`docs/CONSENT.md`/this task's own text: "the documented fallback is a daily
manual check of this same page." `Settings.n8n_webhook_url` defaults to
`None` (reserved, unread by any code before this task — see
`docs/plan/inventory-3-platform-launch.md`'s own note on it) in every
environment this pilot runs in today, so this function returns `False`
(nothing sent) rather than raising — the caller is never forced to treat
"nobody has configured n8n yet" as a failure.

## Never raises, even once a URL IS configured
Deliberately the opposite contract from `app.notifications.sender.
EmailSender.send` (which raises on a transport failure — the guardian-
consent gate genuinely needs to know "did this reach an inbox"). A missed
safeguarding webhook call must never surface as a 500 on whatever page
happens to trigger it, and this task's own fallback ("a daily manual check
of this same page") only works if a failed call is silent and logged, not
propagated. `logger.warning` below logs the flag id only (an opaque uuid,
the same thing already visible to anyone who can load `/reviewer/support`)
— never the category, never a student id, matching `app/web/reviewer/
queue.py`'s own "opaque identifiers only" logging convention.

## No call site wired yet — and that is disclosed, not hidden
Nothing in this codebase creates a `safeguarding_flags` row yet (the
distress-keyword detection that would is Phase 2 — see
`db/migrations/0013_safeguarding_schema.sql`'s own header). This task
builds the notification MECHANISM only; the future code that inserts a
flag is what should call `notify_safeguarding_flag(flag_id)` once it exists,
the same way `db/migrations/0013_safeguarding_schema.sql`'s own comment
says the write path for the table itself is Phase 2's to add.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0


def notify_safeguarding_flag(flag_id: str) -> bool:
    """POST `{"flag_id": flag_id}` to `Settings.n8n_webhook_url`.

    Returns `True` only if the request was actually sent (not necessarily
    accepted with a 2xx — this function does not inspect the response body,
    since a webhook receiver's own retry/ack semantics are n8n's concern,
    not this app's); `False` for both "no URL configured" and "the request
    itself failed" — deliberately the same return value for both, since
    every caller's fallback is identical either way (see this module's own
    docstring): "the documented fallback is a daily manual check of this
    same page."
    """
    settings = get_settings()
    webhook_url = settings.n8n_webhook_url
    if not webhook_url:
        return False

    payload = {"flag_id": flag_id}
    try:
        httpx.post(webhook_url, json=payload, timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — a failed notification must never raise
        logger.warning(
            "Safeguarding notification webhook call failed for flag_id=%s",
            flag_id,
            exc_info=True,
        )
        return False
    return True
