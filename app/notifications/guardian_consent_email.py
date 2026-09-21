"""Builds the guardian-consent confirmation email's content. Kept
separate from both the sending mechanism (`sender.py` and friends) and
the account/token bookkeeping (`app/api/guardian_consent.py`) — same
separation `app/ai/grounding.py`'s prompt construction keeps from
`app/ai/adapter.py`'s provider call.
"""

from __future__ import annotations


def build_guardian_consent_email(*, confirm_url: str, expiry_hours: int) -> tuple[str, str]:
    """Returns `(subject, body)`, plain text, zero HTML (matches this
    app's zero-JS/plain-page convention elsewhere — no tracking pixels,
    no rendering surface for an XSS-style concern to even exist in)."""
    subject = "Confirm your child's BCION Lite account"
    body = (
        "Hello,\n\n"
        "A BCION Lite account (a career-guidance pilot for Indian "
        "students, Class 8-12) was just created using this email address "
        "as the guardian contact for a student under 18. BCION Lite is a "
        "technical pilot, not the national platform.\n\n"
        "If you are this student's parent or guardian and consent to this "
        "account, open the link below to confirm. The account cannot be "
        "used until you do:\n\n"
        f"{confirm_url}\n\n"
        f"This link expires in {expiry_hours} hours and can only be used "
        "once. If you did not expect this email, you do not need to do "
        "anything — the account stays inactive and no data about the "
        "student is shared with you or anyone else by this email alone.\n\n"
        "— BCION Lite"
    )
    return subject, body
