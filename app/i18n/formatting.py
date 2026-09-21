"""Locale-aware display formatting (I18N-2).

Pure functions: no HTTP, no request, no global state, no new pip
dependency (I18N-2's own constraint — Babel would bring an ICU-sized
locale database to format four things). `app/web/templating.py`
registers each one as a Jinja filter; every function here is directly
callable and table-testable without Jinja.

## Indian digit grouping

`1,00,000`, not `100,000`. Python's own `{:,}` is Western-only
(thousands, then thousands), so the grouping is done here: the last
three digits, then pairs. This is what a fee receipt, a scholarship
letter and a bank statement in India look like, and the pilot's readers
are Class 8-12 students and their parents.

## Rounding must not diverge from the arithmetic (I18N-2's risk note)

`app/planning/cost.py` computes `net_to_arrange`; `compare.html`
displays it. If this module rounded differently from the `"{:,.0f}"`
formatting that shipped before it, the three cost lines and the total
could visibly fail to add up — the exact thing docs/UI.md's "Three
separate amounts, always" exists to make legible. So `_integer_digits`
below goes through `format(value, ".0f")`, the identical call, and only
then regroups the digits. Same rounding, same edge cases, different
separators.

## Latin digits in both locales

`7`, `12`, `2026` — never `७`, `१२`, `२०२६`. Every form, exam paper,
fee receipt and admit card an Indian student handles uses Latin digits,
including Hindi-medium ones; Devanagari numerals would make a Hindi page
*harder* to read, not more familiar. A unit test asserts no Devanagari
numeral ever reaches `hi.json` either.

## Nothing here invents a value

Every function takes `None` (and anything it cannot faithfully render —
a NaN, an unparsable date) to the catalogue's "Not available" string.
Never a blank, never a zero standing in for "unknown", never a raw
`None` leaking into the page.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from app.i18n import DEFAULT_LOCALE, translate

RUPEE_SIGN: Final = "₹"

NOT_AVAILABLE_KEY: Final = "global.trust_badge.not_available"
"""Deliberately the SAME key the trust badge uses, not a second key with
the same text. docs/COPY.md section 2: "do not give the same string two
different keys". A missing number and a missing fact read identically to
a student, so they share one string and one future translation."""

_MONTH_KEYS: Final[tuple[str, ...]] = (
    "global.month.jan",
    "global.month.feb",
    "global.month.mar",
    "global.month.apr",
    "global.month.may",
    "global.month.jun",
    "global.month.jul",
    "global.month.aug",
    "global.month.sep",
    "global.month.oct",
    "global.month.nov",
    "global.month.dec",
)
"""Month names live in the catalogue, not in this file, so the Hindi
reviewer (I18N-11) can correct them like any other string. The key ids
stay English abbreviations — they are identifiers, not display text."""

_WEEKS_IN_A_YEAR: Final = 52
_WEEKS_IN_A_MONTH: Final = 52 / 12  # 4.333...
_MINIMUM_WEEKS_FOR_AN_APPROXIMATION: Final = 4
"""Below four weeks the rounding overstates: three weeks is 0.7 of a
month and would read as "about 1 month", a 45% exaggeration of how long
something takes. Under this threshold only the weeks are shown."""

Number = int | float | Decimal


def _is_real_number(value: object) -> bool:
    """`bool` is an `int` subclass in Python: `format_inr(True)` would
    otherwise render as one rupee. A NaN or an infinity formats as the
    literal text "nan"/"inf", which must never reach a page either."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return not (isinstance(value, Decimal) and not value.is_finite())


def group_indian(digits: str) -> str:
    """`"100000"` -> `"1,00,000"`. Last three digits, then pairs.

    Takes and returns digits only — sign and currency are the caller's
    business, so this stays trivially testable.
    """
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join([*pairs, tail])


def _rounded_digits(value: Number) -> tuple[str, str]:
    """`(sign, ungrouped digits)` using the same rounding as the
    `"{:,.0f}"` formatting this replaces — see the module docstring.
    Shared by `_integer_digits` (Indian grouping, below) and
    `format_money`'s non-INR fallback (Western grouping), so both stay
    on the identical rounding rule."""
    try:
        rendered = format(value, ".0f")
    except (ValueError, TypeError, InvalidOperation):  # pragma: no cover - guarded above
        return "", ""
    sign = "-" if rendered.startswith("-") else ""
    digits = rendered.lstrip("-")
    if sign and set(digits) == {"0"}:
        # format(-0.4, ".0f") is "-0": a rounded-away negative, shown as
        # plain "0" rather than a "-0" nobody means.
        sign = ""
    return sign, digits


def _integer_digits(value: Number) -> tuple[str, str]:
    """`(sign, Indian-grouped digits)`."""
    sign, digits = _rounded_digits(value)
    return sign, group_indian(digits)


def format_number(value: Number | None, locale: str = DEFAULT_LOCALE) -> str:
    """A whole number with Indian grouping, no currency sign."""
    if value is None or not _is_real_number(value):
        return translate(NOT_AVAILABLE_KEY, locale)
    sign, digits = _integer_digits(value)
    return f"{sign}{digits}"


def format_money(
    amount: Number | None, currency: str = "INR", locale: str = DEFAULT_LOCALE
) -> str:
    """The one formatter for a money amount (RULES-10 / docs/CONTRACTS.md
    "Money and currency": "One formatter, format_money(amount, currency)
    — no currency symbol literal may exist outside it").

    `INR` (the default — Lite is an India-first pilot) keeps the exact
    pre-existing rendering: Indian digit grouping, the `₹` sign, no
    decimals — the same string `format_inr` has always produced, now
    delegated from it rather than duplicated (see below), so no
    student-visible output changes for the common case.

    Any other ISO 4217 code has no Indian-grouping convention and no
    symbol table in this pilot (a `₹`-style glyph per currency is not
    something Lite maintains), so it falls back to the plain currency
    CODE plus Western thousands grouping — e.g. `"USD 1,000"` — which is
    unambiguous even though it is not how a US invoice would typically
    render the same amount. This fallback is a deliberate, documented
    judgement call (RULES-10), not a designed international format;
    SCOPE-4 owns whatever the Compare screen actually needs once a
    non-INR pathway is real content, not a test fixture.

    `None` or an unreal value (`NaN`, `inf`, a `bool`) renders "Not
    available", the same convention every formatter in this module
    follows — never a blank, never a zero standing in for "unknown".
    """
    if amount is None or not _is_real_number(amount):
        return translate(NOT_AVAILABLE_KEY, locale)
    if currency == "INR":
        sign, digits = _integer_digits(amount)
        return f"{sign}{RUPEE_SIGN}{digits}"
    sign, digits = _rounded_digits(amount)
    grouped = f"{int(digits):,}" if digits else digits
    return f"{sign}{currency} {grouped}"


def format_inr(value: Number | None, locale: str = DEFAULT_LOCALE) -> str:
    """Rupees: `₹1,00,000`. No decimals — every money figure in this
    pilot is a whole-rupee fee, charge or estimate, and a trailing `.0`
    reads as a display bug (ux-qa-reviewer finding, 2026-09-19).

    A negative total (confirmed assistance exceeding the charges) prints
    as `-₹5,000`, with the minus leading the whole amount rather than
    sitting between the sign and the digits.

    A thin wrapper over `format_money`'s `INR` branch (RULES-10 /
    docs/CONTRACTS.md: "One formatter") — kept as its own name because
    every existing caller (the `inr` Jinja filter, this module's own
    tests) already spells it this way, and INR is the only currency
    Lite has ever actually displayed.
    """
    return format_money(value, "INR", locale)


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def format_date(value: date | datetime | str | None, locale: str = DEFAULT_LOCALE) -> str:
    """`2026-09-21` -> `21 Sep 2026` / `21 सितंबर 2026`.

    Accepts a `date`, a `datetime`, or the ISO string Postgres/Supabase
    actually returns (`"2026-09-21"`, or a full timestamp). Day-month-
    year order in both locales — the order every Indian form uses, and
    the one that cannot be misread as month-first.

    An unparsable value is "Not available" rather than raw text: a
    verification date that will not parse is corrupt data, and a corrupt
    date shown next to a trust badge would be worse than an honest gap.
    """
    resolved = _coerce_date(value)
    if resolved is None:
        return translate(NOT_AVAILABLE_KEY, locale)
    month = translate(_MONTH_KEYS[resolved.month - 1], locale)
    return f"{resolved.day} {month} {resolved.year}"


def _approximate_parts(weeks: int) -> tuple[int, int]:
    """Whole years, then whole months of the remainder. 52 weeks is a
    year and 13 weeks is three months — deliberately the rough arithmetic
    a student would do in their head, because the output says "about"."""
    years, remaining_weeks = divmod(weeks, _WEEKS_IN_A_YEAR)
    months = int(round(remaining_weeks / _WEEKS_IN_A_MONTH))
    if months >= 12:
        years += 1
        months = 0
    return years, months


def format_duration_weeks(weeks: Number | None, locale: str = DEFAULT_LOCALE) -> str:
    """`78` -> `78 weeks (about 1 year 6 months)`.

    Weeks stay the headline number, because weeks are what
    `app/rules/timeline.py` actually computes and what a student edits.
    The years/months reading is an approximation and always says so —
    docs/UI.md and CLAUDE.md both rule out anything that reads as a
    promise about how long a route takes. Wording comes from the
    catalogue (`global.duration.*`), so Hindi is a translation rather
    than a second implementation.

    Under a month, only the weeks are shown: "4 weeks (about 1 month)"
    helps; "2 weeks (about 0 months)" does not. A negative count is a
    bug upstream, not a duration, so it is "Not available" rather than a
    nonsense phrase.
    """
    if weeks is None or not _is_real_number(weeks):
        return translate(NOT_AVAILABLE_KEY, locale)
    whole_weeks = int(round(float(weeks)))
    if whole_weeks < 0:
        return translate(NOT_AVAILABLE_KEY, locale)

    weeks_text = (
        translate("global.duration.week_one", locale)
        if whole_weeks == 1
        else translate("global.duration.weeks", locale, weeks=format_number(whole_weeks, locale))
    )

    if whole_weeks < _MINIMUM_WEEKS_FOR_AN_APPROXIMATION:
        return weeks_text

    years, months = _approximate_parts(whole_weeks)
    if not years and not months:
        return weeks_text

    years_text = (
        translate("global.duration.year_one", locale)
        if years == 1
        else translate("global.duration.years", locale, years=format_number(years, locale))
    )
    months_text = (
        translate("global.duration.month_one", locale)
        if months == 1
        else translate("global.duration.months", locale, months=format_number(months, locale))
    )

    if years and months:
        approximate = translate(
            "global.duration.years_and_months", locale, years=years_text, months=months_text
        )
    elif years:
        approximate = years_text
    else:
        approximate = months_text

    return translate(
        "global.duration.weeks_with_approximation",
        locale,
        weeks=weeks_text,
        approximate=approximate,
    )
