"""app/safeguarding/ — CONSENT-8: staff-only safeguarding support.

Currently holds `notify.py` only (the off-request-path webhook call). The
queue page itself (`GET /reviewer/support`) lives in `app/web/support_pages.py`,
not here — this package is for safeguarding-domain logic that isn't a route,
mirroring `app/planning/`'s separation from `app/web/`.
"""

from __future__ import annotations
