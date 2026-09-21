"""The i18n mechanism (I18N-1): locale resolution and the string catalogue.

This package is deliberately tiny and dependency-free — no Babel, no
gettext, no new pip dependency (I18N-1/I18N-2's own constraint). It is
the *mechanism* only: no template text is changed here (that is I18N-3's
job), and nothing in this package knows about HTTP. `app/web/templating.py`
is the only module that bridges a request to these functions.

## The key contract (docs/COPY.md section 2, unchanged here)

Flat, dot-separated, three segments: `screen.component.purpose`. Flat on
purpose — a future translation spreadsheet only needs `key,en,hi`
columns, never this project's own nesting scheme. `_load_catalogue`
below *enforces* the flatness (a nested JSON object raises at import
time) rather than leaving it as a docs-only convention.

Keys beginning with `_meta.` carry catalogue provenance rather than
screen text: which locale the file is, whether a human has reviewed it,
and when. They are ordinary flat keys so a translator tool never needs a
second file format; nothing renders them.

## Fallbacks — never a blank

- An unknown/absent locale resolves to English (`resolve_locale`), and
  the allow-list is closed: only `en` and `hi` are ever accepted.
- A key missing from a non-English catalogue falls back to English
  *per key*, not per file — a half-translated `hi.json` shows Hindi where
  it has Hindi and English everywhere else, never an empty string.
- A key missing from English too renders as the key itself. That is
  ugly on purpose: visible and greppable beats a silent blank, and
  I18N-3's string-lint is what stops one reaching a real screen.

## Placeholders

`{name}` only (docs/COPY.md: "plain `{name}` interpolation, no other
templating syntax"). Substitution is a regex pass, NOT `str.format`:
`str.format` raises `KeyError` on a variable a caller forgot and
`ValueError`/`IndexError` on a stray brace in a translation, and a
missing UI variable must never be able to crash a page. An unknown
placeholder is left standing (again: visible, greppable) and a stray
brace is just a brace.

The returned value is always a plain `str`, never `Markup` — so Jinja
autoescaping applies to the translation *and* to every substituted
value. A translation can therefore never inject markup.

## Security (I18N-1's own risk note)

`lang` arrives from a cookie, i.e. from the client. It is never used to
build a path: the catalogue filenames below are constants, loaded once
at import, and `resolve_locale` maps anything not on the allow-list to
`en`. There is no code path where a cookie value reaches the filesystem.
The cookie itself carries no personal data — it is one of two fixed
tokens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

DEFAULT_LOCALE: Final = "en"
"""English is both the default and the fallback catalogue."""

SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("en", "hi")
"""The closed allow-list. Adding a locale means adding its file to
`_CATALOGUE_FILENAMES` below and a line here — nothing else (I18N-14's
deferred `gu.json` is exactly that one change)."""

LOCALE_COOKIE_NAME: Final = "lang"
"""The only locale input this app reads. No `Accept-Language` sniffing:
I18N-1 fixes the resolver order as `lang` cookie -> `en`, so what a
student sees is what they last chose, not what a borrowed/shared phone's
OS happens to be set to."""

_CATALOGUE_FILENAMES: Final[dict[str, str]] = {"en": "en.json", "hi": "hi.json"}
"""locale -> filename, as literal constants. Never `f"{locale}.json"`:
see the security note in this module's docstring."""

_PLACEHOLDER_RE: Final = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

_CATALOGUE_DIRECTORY: Final = Path(__file__).resolve().parent


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """`json.loads` silently keeps the LAST of two identical keys, which
    would make docs/COPY.md's "Do not reuse a key for two different
    strings" unenforceable — one of the pair just disappears with no
    diff anyone would notice. Raises instead."""
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _load_catalogue(filename: str) -> dict[str, str]:
    """Read one catalogue file, enforcing the flat `key -> string` shape.

    A nested object, a non-string value or a duplicated key raises here,
    at import time, rather than surfacing as a mangled or silently
    dropped string on a student's screen.
    """
    path = _CATALOGUE_DIRECTORY / filename
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ValueError as exc:
        raise ValueError(f"{filename}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{filename}: a catalogue must be a flat JSON object.")
    catalogue: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise ValueError(
                f"{filename}: key {key!r} is not a string. Catalogues are flat "
                "`screen.component.purpose` -> string maps (docs/COPY.md section 2); "
                "nested objects are not supported."
            )
        catalogue[key] = value
    return catalogue


_CATALOGUES: Final[dict[str, dict[str, str]]] = {
    locale: _load_catalogue(filename) for locale, filename in _CATALOGUE_FILENAMES.items()
}


def resolve_locale(raw: str | None) -> str:
    """Client-supplied value -> a locale this app actually has.

    Anything not on `SUPPORTED_LOCALES` — absent, empty, a typo, another
    language, a path fragment, a control character — becomes
    `DEFAULT_LOCALE`. Surrounding whitespace and case are tolerated
    (a hand-typed cookie value of `HI ` is still Hindi); nothing else is.
    """
    if raw is None:
        return DEFAULT_LOCALE
    candidate = raw.strip().lower()
    if candidate in SUPPORTED_LOCALES:
        return candidate
    return DEFAULT_LOCALE


def catalogue(locale: str) -> dict[str, str]:
    """A copy of one catalogue, for tests and for the parity check. The
    copy keeps a caller from mutating the process-wide catalogue."""
    return dict(_CATALOGUES[resolve_locale(locale)])


def catalogue_keys(locale: str) -> frozenset[str]:
    return frozenset(_CATALOGUES[resolve_locale(locale)])


def lookup(key: str, locale: str = DEFAULT_LOCALE) -> str:
    """The raw (un-substituted) string for `key`, with the per-key
    fallback chain: requested locale -> English -> the key itself."""
    resolved = resolve_locale(locale)
    value = _CATALOGUES[resolved].get(key)
    if value is None and resolved != DEFAULT_LOCALE:
        value = _CATALOGUES[DEFAULT_LOCALE].get(key)
    if value is None:
        return key
    return value


def substitute(text: str, variables: dict[str, object]) -> str:
    """`{name}` substitution that cannot raise — see this module's
    docstring on why `str.format` is not used."""
    if not variables:
        return text

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return str(variables[name])
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, text)


def translate(key: str, locale: str = DEFAULT_LOCALE, /, **variables: object) -> str:
    """The one function every caller uses. `key` and `locale` are
    positional-only so a catalogue string is free to have a `{key}` or
    `{locale}` placeholder without colliding with this signature."""
    return substitute(lookup(key, locale), variables)
