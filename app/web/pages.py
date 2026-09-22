"""Server-rendered HTML pages — the actual clickable journey docs/UI.md
describes (explore -> compare -> requirements -> timeline).

UI-2: this module used to hold every screen's routes directly; it is now
a thin aggregator over one module per screen (`explore_pages.py`,
`compare_pages.py`, `requirements_pages.py`, `timeline_pages.py`), each
in this same package. Shared helpers and the `templates` object live in
`app/web/common.py`. Every route path and behaviour is unchanged — this
is a pure refactor, not a rewrite (see each screen module's own
docstring for the reasoning that used to live here).

`app/main.py` and every test that only hits routes by URL are untouched
by this split; `_db_client_or_none` is re-exported below because
tests/db/test_web_pages.py overrides that exact dependency by importing
it from here (see app/web/common.py's own docstring on why it must stay
one function object, not one per screen module).

A new screen registers with a one-line append below.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.web.common import _db_client_or_none  # noqa: F401 (re-exported for tests/db)
from app.web.compare_pages import router as compare_pages_router
from app.web.detail_pages import router as detail_pages_router
from app.web.explore_pages import router as explore_pages_router
from app.web.requirements_pages import router as requirements_pages_router
from app.web.timeline_pages import router as timeline_pages_router

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface
router.include_router(explore_pages_router)
router.include_router(compare_pages_router)
router.include_router(detail_pages_router)
router.include_router(requirements_pages_router)
router.include_router(timeline_pages_router)
