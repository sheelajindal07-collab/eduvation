"""GET /consent/confirm?token=... — the plain, zero-JS page a guardian
lands on after clicking the link in the guardian-consent email
(app/notifications/guardian_consent_email.py). Mirrors app/web/pages.py's
convention (Jinja2Templates, `include_in_schema=False` — this is a page a
human clicks into, not part of the JSON API surface).

All the real logic — token match, expiry, single-use, flipping both
`guardian_consents.status` and `student_accounts.account_status`
atomically — lives in `confirm_guardian_consent()`, a database function
(see db/migrations/0004_guardian_consent.sql's own docstring for why).
This route does nothing but call it and render one of exactly two
generic outcomes; it holds no business logic of its own to keep in sync
with the database's.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.db import get_anon_client
from app.web.templating import templates

router = APIRouter(prefix="/consent", tags=["guardian-consent"], include_in_schema=False)


@router.get("/confirm")
def consent_confirm(request: Request, token: str | None = Query(default=None)) -> Any:
    """No `db: Client = Depends(get_db_client)` here on purpose: this
    call is never scoped to a signed-in user's own token (a guardian has
    no BCION Lite session at all) and must not accidentally pick one up
    from an `Authorization` header a guardian's browser would never send
    anyway — `get_anon_client()` directly, matching how
    `confirm_guardian_consent()` is deliberately grant-ed to `anon`
    (see the migration).

    A missing/blank token degrades to the same generic "not valid"
    outcome as a wrong one, rather than a distinguishable error — same
    non-enumeration reasoning as the token itself (task requirement #5),
    and it means a malformed/absent token can never reach the database
    call at all, only ever this template."""
    confirmed = False
    if token:
        client = get_anon_client()
        try:
            result = client.rpc("confirm_guardian_consent", {"p_token": token}).execute()
            confirmed = bool(result.data)
        except Exception:
            # Never a raw 500 for a guardian who clicked a link from
            # their inbox (task requirement: "a malformed/nonexistent
            # token degrades gracefully") -- any failure here (including
            # the migration not being applied yet) renders the same
            # generic "not valid" page a wrong/expired/already-used
            # token would.
            confirmed = False
        finally:
            client.postgrest.aclose()

    return templates.TemplateResponse(
        request, "consent_confirm.html", {"confirmed": confirmed}
    )
