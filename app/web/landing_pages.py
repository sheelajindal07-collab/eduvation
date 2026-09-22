"""GET / — docs/PRODUCT.md's front door and this task's own "Find your
next step" landing screen (UI-3).

Replaces the bare `RedirectResponse(url="/explore")` that used to live in
`app/web/explore_pages.py`: a guest arriving with nothing decided yet now
sees three plain starting choices before anything else, never an account
wall (CLAUDE.md/docs/UI.md "Guest sessions": account creation only when
the student wants to save or sync).

The three choices:

  1. "I have a career in mind"    -- straight into Explore's career list,
                                     one link per already-published career
                                     name (`/explore#career-{id}`), using
                                     the per-career anchor
                                     `app/web/templates/explore.html` now
                                     carries. A DB outage/empty catalogue
                                     degrades to one plain link to
                                     `/explore` rather than an empty box
                                     (docs/UI.md "difficult states": a
                                     missing section says so, it does not
                                     silently disappear).
  2. "I'm not sure yet"           -- the new `/start` quick-start flow
                                     (this task, `app/web/start_pages.py`).
  3. "Just show me everything"    -- a plain link into `/explore` with no
                                     scroll target, for a guest who wants
                                     to browse without committing to
                                     either of the above.

Stateless and DB-optional like `app/web/explore_pages.py`'s own screen --
`_db_client_or_none` degrades to `None` rather than a 500, and the
template shows the plain "not published yet" treatment for the first
choice's list in that case (never a silent, empty section).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from supabase import Client

from app.web.common import _db_client_or_none
from app.web.templating import templates

router = APIRouter(include_in_schema=False)  # HTML pages, not the JSON API surface


@router.get("/")
def landing_page(request: Request, db: Client | None = Depends(_db_client_or_none)) -> Any:
    careers: list[dict[str, Any]] = []
    if db is not None:
        careers_result = db.table("careers").select("id, name").execute()
        careers = cast("list[dict[str, Any]]", careers_result.data)
    return templates.TemplateResponse(request, "landing.html", {"careers": careers})
