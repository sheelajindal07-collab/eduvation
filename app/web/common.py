"""Shared helpers for `app/web/*_pages.py` (UI-2's split of the former
monolithic `app/web/pages.py`). Nothing here is a route — every screen
module imports what it needs from here, and `app/web/pages.py` itself
only aggregates the screen routers and re-exports `_db_client_or_none`
(some tests key a FastAPI `dependency_overrides` entry on that exact
function object — see its own docstring below for why it must keep
living at one place, not be redefined per screen module).
"""

from __future__ import annotations

import uuid as uuid_module
from collections.abc import Iterator
from typing import Any

from fastapi import Header
from fastapi.templating import Jinja2Templates
from supabase import Client

from app.api.deps import get_db_client
from app.db import SupabaseNotConfiguredError

templates = Jinja2Templates(directory="app/web/templates")

# docs/UI.md "difficult states": a plain-language, visible status --
# never a generic error -- for the realistic "Weak connection" case.
# Shared by every screen below so a DB outage degrades the same way
# everywhere, rather than inventing a different message per module.
_DB_UNAVAILABLE_MESSAGE = (
    "We're having trouble reaching our data right now. Please try again shortly."
)


def _db_client_or_none(
    authorization: str | None = Header(default=None),
) -> Iterator[Client | None]:
    """Same contract as `app.api.deps.get_db_client`, except a Supabase
    misconfiguration (`SupabaseNotConfiguredError`) degrades to `None`
    instead of propagating out of dependency resolution -- which happens
    BEFORE a route function's body ever runs, so a plain try/except
    inside compare_page/requirements_page can't catch it; the route body
    can only react to what its dependency handed it. `get_db_client`'s
    own generator does the real work (bearer-token resolution, and the
    `finally: client.postgrest.aclose()` cleanup app/api/deps.py's
    docstring explains) -- advanced by hand here rather than
    reimplemented, so there is exactly one place either piece of logic
    lives. app/db/client.py's own docstring: "Callers should catch this
    and degrade gracefully" -- this is that catch, for the pages that
    have a friendly template to fall back to.

    Defined here (not in app/web/pages.py) so every screen module that
    needs it imports the SAME function object -- FastAPI's
    `dependency_overrides` keys on object identity, and
    tests/db/test_web_pages.py overrides this exact dependency via
    `from app.web.pages import _db_client_or_none`, which only works
    because pages.py re-exports this one object rather than each screen
    module defining its own copy.
    """
    gen = get_db_client(authorization)
    try:
        client = next(gen)
    except SupabaseNotConfiguredError:
        yield None
        return
    try:
        yield client
    finally:
        next(gen, None)  # resumes get_db_client() past its own `yield`, running its `finally`


def _looks_like_a_uuid(value: str) -> bool:
    try:
        uuid_module.UUID(value)
    except ValueError:
        return False
    return True


def _int_or_none(raw: str | None) -> int | None:
    """Shared by requirements_page (age) and timeline_calculate (stage/
    parallel-activity durations): not this module's job to validate
    typed input character-by-character -- a missing or unparsable value
    is simply "not provided", never guessed at, silently dropped, or
    (ux-qa-reviewer finding: age used to be a native `int | None` FastAPI
    query param, so a non-numeric value never even reached this
    function -- FastAPI's own request validation rejected it first with
    a raw JSON 422, before a human-clicked-a-page error page could ever
    show) a crash."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _float_or_none(raw: str | None) -> float | None:
    """Same contract as `_int_or_none`, for marks_percentage."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _form_str(form: Any, key: str) -> str:
    """`FormData.get` can return `str | UploadFile | None` in general;
    every field on this form is a plain text/number/checkbox input, so
    anything else (or a missing key) is treated as blank rather than
    guessed at."""
    value = form.get(key)
    return value if isinstance(value, str) else ""
