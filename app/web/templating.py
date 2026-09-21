"""The single Jinja environment for every HTML page in this app (I18N-1).

Before this module there were separate `Jinja2Templates(...)` instances —
one in `app/web/common.py` (shared by the four student screen modules
after UI-2's split) and one in `app/web/reviewer_pages.py` — which meant
two independent Jinja `Environment`s. Two environments means anything
registered on one (a global, a filter, a policy) silently does not exist
on the other: a `t()` call that works on `/compare/view` would raise
`UndefinedError` on `/reviewer/queue`, and nobody would find out until a
reviewer loaded the page. Every router now imports `templates` from
here, so there is exactly one environment and exactly one place a global
or filter is registered.

`app/web/common.py` re-exports this same object, so an older
`from app.web.common import templates` keeps working and keeps pointing
at the SAME instance — there is no second environment anywhere.

## How a request's locale reaches a template

`context_processors` runs on every `TemplateResponse`, immediately
before Jinja renders, so no route function has to pass anything: it
resolves the `lang` cookie once and puts `lang` into the template
context. No route signature changes; no route needs to know i18n exists.

`t()` is registered as a Jinja *global* and resolves the locale in this
order:

1. `lang` from the render context (the normal path — put there by the
   context processor below);
2. the request's own cookie, if a caller built a context by hand;
3. `_current_locale`, a `ContextVar` set by the same context processor.

Step 3 is not redundant. A macro imported with a plain
`{% from "_components.html" import career_card %}` renders in a *fresh*
Jinja context that carries the environment's globals but NOT the calling
template's variables — so `lang` and `request` are both absent inside
it. Without the ContextVar, every string inside every shared macro would
silently fall back to English while the page around it rendered in
Hindi. Rendering happens synchronously inside
`Jinja2Templates.TemplateResponse` (Starlette's `_TemplateResponse`
renders in its own `__init__`), on the same thread that just ran the
context processor, so the ContextVar always holds the value for *this*
render.

The alternative — requiring `{% from ... with context %}` at every
import site — was rejected: forgetting it fails silently (English text
inside a Hindi page), and it would be a rule every future task has to
remember rather than something the mechanism guarantees.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

import jinja2
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.config import get_settings
from app.i18n import DEFAULT_LOCALE, LOCALE_COOKIE_NAME, resolve_locale, translate
from app.i18n.formatting import format_date, format_duration_weeks, format_inr, format_number

TEMPLATE_DIRECTORY = "app/web/templates"
"""Unchanged from the instances this module replaces: relative to the
process's working directory, which is the repo root for `make dev`,
pytest and the container alike."""

_current_locale: ContextVar[str] = ContextVar("bcion_current_locale", default=DEFAULT_LOCALE)
"""Fallback channel for macros imported without context — see this
module's docstring. Always re-set by `_locale_context` before a render,
so it can never carry a previous request's locale into this one."""


def locale_for_request(request: Request) -> str:
    """The resolver, in one place: the `lang` cookie, allow-listed to
    `en`/`hi`, defaulting to English. No `Accept-Language` sniffing —
    see `app/i18n/__init__.py`'s note on `LOCALE_COOKIE_NAME`."""
    return resolve_locale(request.cookies.get(LOCALE_COOKIE_NAME))


def _locale_context(request: Request) -> dict[str, Any]:
    """Starlette context processor: one resolution per response, shared
    by `{{ lang }}` (I18N-3 sets `<html lang="...">` from it) and by
    every `t()`/filter call in that render.

    `ai_enabled` rides along (DESIGN-18) so a template can hide an AI
    entry point without every route having to remember to pass the
    flag. It is `app/core/config.py`'s `AI_ENABLED`, which is
    fail-closed: a missing var, an empty string or a typo all parse as
    off. Read here rather than captured at import so flipping the
    kill switch does not need a redeploy of this module's state.
    """
    lang = locale_for_request(request)
    _current_locale.set(lang)
    return {"lang": lang, "ai_enabled": get_settings().ai_enabled}


def locale_from_context(context: jinja2.runtime.Context) -> str:
    """The three-step lookup described in this module's docstring."""
    lang = context.get("lang")
    if isinstance(lang, str):
        return resolve_locale(lang)
    request = context.get("request")
    if isinstance(request, Request):
        return locale_for_request(request)
    return resolve_locale(_current_locale.get())


@jinja2.pass_context
def _t(context: jinja2.runtime.Context, key: str, /, **variables: object) -> str:
    """`t("screen.component.purpose", name=value)` inside any template.

    `context` and `key` are positional-only so a catalogue string may
    use a `{key}` or `{context}` placeholder without colliding with this
    signature. Returns a plain `str`, never `Markup`: Jinja autoescapes
    both the translation and every substituted value, so no catalogue
    entry and no interpolated value can inject markup.
    """
    return translate(key, locale_from_context(context), **variables)


def _locale_aware_filter(
    function: Callable[..., str],
) -> Callable[[jinja2.runtime.Context, Any], str]:
    """Wrap one pure `app/i18n/formatting.py` function as a Jinja filter
    that supplies the current locale.

    The formatting functions stay pure and locale-explicit (I18N-2:
    "pure functions ... registered as Jinja filters"), so they are
    table-testable without Jinja; only this wrapper knows about a
    request. An optional explicit locale still wins —
    `{{ d | date("hi") }}` — which is what the components gallery uses
    to show both locales on one page.
    """

    @jinja2.pass_context
    def filter_(context: jinja2.runtime.Context, value: Any, locale: str | None = None) -> str:
        return function(value, resolve_locale(locale) if locale else locale_from_context(context))

    return filter_


templates = Jinja2Templates(directory=TEMPLATE_DIRECTORY, context_processors=[_locale_context])
"""THE templates object. Import this, never construct another."""

templates.env.globals["t"] = _t

# I18N-2 — display formatting. Registered here, on the one shared
# environment, so `{{ fee | inr }}` means the same thing on a student
# screen and in the reviewer console.
templates.env.filters["inr"] = _locale_aware_filter(format_inr)
templates.env.filters["number"] = _locale_aware_filter(format_number)
templates.env.filters["date"] = _locale_aware_filter(format_date)
templates.env.filters["duration_weeks"] = _locale_aware_filter(format_duration_weeks)
