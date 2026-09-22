"""I18N-2 — locale-aware display formatting.

Table-driven, per the task card: 0, a negative, the 99,999 / 1,00,000 /
1,00,00,000 grouping boundaries, `None` -> the "not available" key, a
leap day, an ISO-string input, and both locales throughout.

The one test that is not about display: `TestRoundingMatchesTheArithmetic`
covers I18N-2's own risk note — if this module rounded differently from
the `"{:,.0f}"` formatting that shipped before it, the three cost lines
and the net-to-arrange total on the Compare screen could visibly fail to
add up.
"""

from __future__ import annotations

import ast
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.i18n import translate
from app.i18n.formatting import (
    NOT_AVAILABLE_KEY,
    format_date,
    format_duration_weeks,
    format_inr,
    format_money,
    format_number,
    group_indian,
)
from app.web import templating

RUPEE = "₹"
DEVANAGARI_DIGITS = set("०१२३४५६७८९")


class TestIndianGrouping:
    @pytest.mark.parametrize(
        ("digits", "expected"),
        [
            ("0", "0"),
            ("7", "7"),
            ("99", "99"),
            ("999", "999"),
            ("1000", "1,000"),
            ("99999", "99,999"),
            ("100000", "1,00,000"),
            ("999999", "9,99,999"),
            ("1000000", "10,00,000"),
            ("10000000", "1,00,00,000"),
            ("1000000000", "1,00,00,00,000"),
        ],
    )
    def test_last_three_then_pairs(self, digits: str, expected: str) -> None:
        assert group_indian(digits) == expected


class TestFormatInr:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, f"{RUPEE}0"),
            (7, f"{RUPEE}7"),
            (99999, f"{RUPEE}99,999"),
            (100000, f"{RUPEE}1,00,000"),
            (10000000, f"{RUPEE}1,00,00,000"),
            (-5000, f"-{RUPEE}5,000"),
            (-100000, f"-{RUPEE}1,00,000"),
            (85000.0, f"{RUPEE}85,000"),
            (30000.4, f"{RUPEE}30,000"),
            (Decimal("125000"), f"{RUPEE}1,25,000"),
        ],
    )
    def test_rupees_with_indian_grouping_and_no_decimals(
        self, value: float | Decimal, expected: str
    ) -> None:
        assert format_inr(value) == expected

    def test_none_is_the_not_available_string_never_a_blank(self) -> None:
        assert format_inr(None) == translate(NOT_AVAILABLE_KEY, "en")
        assert format_inr(None, "hi") == translate(NOT_AVAILABLE_KEY, "hi")
        assert format_inr(None).strip()

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, False])
    def test_a_value_that_cannot_be_rendered_faithfully_is_not_available(
        self, value: object
    ) -> None:
        assert format_inr(value) == translate(NOT_AVAILABLE_KEY, "en")  # type: ignore[arg-type]

    def test_the_trailing_point_zero_display_bug_cannot_come_back(self) -> None:
        assert ".0" not in format_inr(30000.0)

    def test_both_locales_use_latin_digits_and_the_rupee_sign(self) -> None:
        for locale in ("en", "hi"):
            rendered = format_inr(100000, locale)
            assert rendered == f"{RUPEE}1,00,000", locale
            assert not (DEVANAGARI_DIGITS & set(rendered))


class TestFormatMoney:
    """RULES-10 / docs/CONTRACTS.md "Money and currency": the one
    formatter, `format_money(amount, currency)` -- `format_inr` is now a
    thin wrapper over its `INR` branch."""

    def test_inr_matches_format_inr_exactly(self) -> None:
        for value in (0, 7, 99999, 100000, 10000000, -5000):
            assert format_money(value, "INR") == format_inr(value)

    def test_inr_is_the_default_currency(self) -> None:
        assert format_money(100000) == format_inr(100000)

    def test_a_non_inr_currency_uses_the_code_and_western_grouping(self) -> None:
        assert format_money(1000, "USD") == "USD 1,000"
        assert format_money(1000000, "USD") == "USD 1,000,000"

    def test_a_negative_non_inr_amount_leads_with_the_sign(self) -> None:
        assert format_money(-5000, "USD") == "-USD 5,000"

    def test_zero_non_inr_amount(self) -> None:
        assert format_money(0, "GBP") == "GBP 0"

    def test_none_is_not_available_regardless_of_currency(self) -> None:
        assert format_money(None, "USD") == translate(NOT_AVAILABLE_KEY, "en")
        assert format_money(None) == translate(NOT_AVAILABLE_KEY, "en")

    def test_no_currency_symbol_literal_outside_format_money(self) -> None:
        """docs/CONTRACTS.md: "no currency symbol literal may exist
        outside it" -- the rupee sign appears in this module exactly
        once, inside `format_money` itself."""
        source = FORMATTING_MODULE_PATH.read_text(encoding="utf-8")
        assert source.count('"₹"') == 1


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMATTING_MODULE_PATH = REPO_ROOT / "app" / "i18n" / "formatting.py"
TEMPLATES_DIR = REPO_ROOT / "app" / "web" / "templates"

CURRENCY_SYMBOL_RE = re.compile("₹|&#0*8377;?|&#x0*20b9;?", re.IGNORECASE)
"""The rupee sign, in every spelling that reaches a reader: the character
itself and the two HTML numeric entities (`&#8377;`, `&#x20B9;`)."""

JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _docstring_constant_ids(tree: ast.Module) -> set[int]:
    """The `id()` of every string constant that is a docstring, so prose
    ABOUT the rupee sign ("never write ₹ here") is not mistaken for a
    rupee sign being rendered. `#` comments never reach the AST at all."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


class TestTheRupeeSignExistsInExactlyOnePlace:
    """SCOPE-4 / docs/CONTRACTS.md "Money and currency": "One formatter,
    `format_money(amount, currency)` -- no currency symbol literal may
    exist outside it."

    This is the guard, not a one-off grep: `compare.html` and
    `_trust_badge.html` both used to print `&#8377;` in front of whatever
    number they were handed, so a fee published in pounds was shown to a
    student as rupees. A reviewer cannot be expected to remember that
    rule for every future template -- this test remembers it."""

    def test_no_template_renders_a_rupee_sign_of_its_own(self) -> None:
        templates = sorted(TEMPLATES_DIR.rglob("*.html"))
        assert templates, f"No templates found under {TEMPLATES_DIR}"
        violations: list[str] = []
        for path in templates:
            text = path.read_text(encoding="utf-8")
            # Developer commentary about the rule is not a violation of it
            # (same convention as tests/unit/test_copy_rules.py).
            rendered = HTML_COMMENT_RE.sub(" ", JINJA_COMMENT_RE.sub(" ", text))
            for match in CURRENCY_SYMBOL_RE.finditer(rendered):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}")
        assert not violations, (
            "A template writes a currency symbol itself instead of using the "
            "`money` filter -- a foreign amount would render as rupees:\n"
            + "\n".join(violations)
        )

    def test_no_python_string_literal_outside_the_formatter_holds_a_rupee_sign(self) -> None:
        violations: list[str] = []
        for path in sorted((REPO_ROOT / "app").rglob("*.py")):
            if path == FORMATTING_MODULE_PATH:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstring_constant_ids(tree)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstrings
                    and CURRENCY_SYMBOL_RE.search(node.value)
                ):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        assert not violations, (
            "A currency symbol literal exists outside app/i18n/formatting.py "
            "(docs/CONTRACTS.md: one formatter only):\n" + "\n".join(violations)
        )

    def test_the_guard_catches_a_seeded_entity(self) -> None:
        """Positive control: the patterns really do match what a template
        author would most plausibly type."""
        for spelling in ("&#8377;1,000", "&#x20B9;1,000", "₹1,000", "&#8377"):
            assert CURRENCY_SYMBOL_RE.search(spelling), spelling


class TestFormatNumber:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, "0"), (-1, "-1"), (99999, "99,999"), (100000, "1,00,000"), (10000000, "1,00,00,000")],
    )
    def test_grouping_without_a_currency_sign(self, value: int, expected: str) -> None:
        assert format_number(value) == expected
        assert RUPEE not in format_number(value)

    def test_none_is_not_available(self) -> None:
        assert format_number(None, "hi") == translate(NOT_AVAILABLE_KEY, "hi")

    def test_a_rounded_away_negative_does_not_print_as_minus_zero(self) -> None:
        assert format_number(-0.4) == "0"


class TestRoundingMatchesTheArithmetic:
    """I18N-2's risk note: "Display rounding must not diverge from the
    net_to_arrange arithmetic." Same rounding as the `"{:,.0f}"` calls
    this replaces — only the separators differ."""

    @pytest.mark.parametrize(
        "value",
        [0, 0.5, 1.5, 2.5, -0.5, -1.5, 99999.5, 100000.49, 100000.5, 12345678.9, -12345.5],
    )
    def test_same_digits_as_the_shipped_format_call(self, value: float) -> None:
        shipped = f"{value:,.0f}".replace(",", "")
        ours = format_number(value).replace(",", "")
        assert ours == shipped or (shipped == "-0" and ours == "0")

    def test_the_three_cost_lines_still_add_up_on_screen(self) -> None:
        """A worked example of the failure this guards against."""
        verified, estimated, assistance = 85000.5, 30000.5, 15000.0
        net = verified + estimated - assistance
        assert format_inr(net) == f"{RUPEE}1,00,001"
        assert format_inr(verified) == f"{RUPEE}85,000"
        assert format_inr(estimated) == f"{RUPEE}30,000"


class TestFormatDate:
    @pytest.mark.parametrize(
        ("value", "expected_en", "expected_hi"),
        [
            (date(2026, 9, 21), "21 Sep 2026", "21 सितंबर 2026"),
            ("2026-09-21", "21 Sep 2026", "21 सितंबर 2026"),
            (datetime(2026, 9, 21, 14, 30), "21 Sep 2026", "21 सितंबर 2026"),
            ("2024-02-29", "29 Feb 2024", "29 फ़रवरी 2024"),
            (date(2024, 2, 29), "29 Feb 2024", "29 फ़रवरी 2024"),
            ("2026-01-01", "1 Jan 2026", "1 जनवरी 2026"),
            ("2026-12-31", "31 Dec 2026", "31 दिसंबर 2026"),
        ],
    )
    def test_day_month_year_in_both_locales(
        self, value: date | datetime | str, expected_en: str, expected_hi: str
    ) -> None:
        assert format_date(value, "en") == expected_en
        assert format_date(value, "hi") == expected_hi

    def test_a_full_iso_timestamp_from_the_database_parses(self) -> None:
        assert format_date("2026-09-21T09:15:00+00:00") == "21 Sep 2026"
        assert format_date("2026-09-21T09:15:00Z") == "21 Sep 2026"

    @pytest.mark.parametrize("value", [None, "", "   ", "not a date", "2026-13-45", "21/09/2026"])
    def test_an_unparsable_value_is_not_available_never_raw_text(self, value: str | None) -> None:
        assert format_date(value) == translate(NOT_AVAILABLE_KEY, "en")

    def test_hindi_dates_use_latin_digits(self) -> None:
        rendered = format_date("2026-09-21", "hi")
        assert not (DEVANAGARI_DIGITS & set(rendered))
        assert "21" in rendered and "2026" in rendered


class TestFormatDurationWeeks:
    @pytest.mark.parametrize(
        ("weeks", "expected"),
        [
            (0, "0 weeks"),
            (1, "1 week"),
            (3, "3 weeks"),
            (4, "4 weeks (about 1 month)"),
            (13, "13 weeks (about 3 months)"),
            (52, "52 weeks (about 1 year)"),
            (78, "78 weeks (about 1 year 6 months)"),
            (104, "104 weeks (about 2 years)"),
            (150, "150 weeks (about 2 years 11 months)"),
            (260, "260 weeks (about 5 years)"),
        ],
    )
    def test_weeks_stay_the_headline_with_an_approximate_reading(
        self, weeks: int, expected: str
    ) -> None:
        assert format_duration_weeks(weeks) == expected

    def test_the_approximation_always_says_about(self) -> None:
        assert "about" in format_duration_weeks(78)
        assert "लगभग" in format_duration_weeks(78, "hi")

    def test_under_a_month_shows_no_about_zero_months(self) -> None:
        assert format_duration_weeks(2) == "2 weeks"
        assert "about" not in format_duration_weeks(2)

    def test_a_near_year_boundary_rounds_up_to_whole_years(self) -> None:
        """51 weeks reads as "about 12 months", which must become a
        year rather than "0 years 12 months"."""
        assert format_duration_weeks(51) == "51 weeks (about 1 year)"

    @pytest.mark.parametrize(
        ("weeks", "expected"),
        [
            (1, "1 सप्ताह"),
            (3, "3 सप्ताह"),
            (52, "52 सप्ताह (लगभग 1 वर्ष)"),
            (78, "78 सप्ताह (लगभग 1 वर्ष 6 महीने)"),
            (4, "4 सप्ताह (लगभग 1 महीना)"),
        ],
    )
    def test_hindi_wording_comes_from_the_catalogue(self, weeks: int, expected: str) -> None:
        assert format_duration_weeks(weeks, "hi") == expected

    @pytest.mark.parametrize("weeks", [None, -1, -52, float("nan")])
    def test_none_and_a_negative_duration_are_not_available(self, weeks: float | None) -> None:
        assert format_duration_weeks(weeks) == translate(NOT_AVAILABLE_KEY, "en")

    def test_a_large_count_is_grouped(self) -> None:
        assert format_duration_weeks(1040).startswith("1,040 weeks")

    def test_hindi_durations_use_latin_digits(self) -> None:
        assert not (DEVANAGARI_DIGITS & set(format_duration_weeks(78, "hi")))


class TestWeeksToApproximateYearsMonthsRoundingRule:
    """RULES-9: `format_duration_weeks` IS the "weeks -> 'about N years M
    months'" helper the timeline flows need — checked against this
    module before writing a second one that would do almost the same
    thing (see app/planning/timeline_assembly.py's own module docstring
    for the same "don't duplicate an existing helper" reasoning applied
    to `field_value_for`). Nothing new to add here; what was missing was
    a single place documenting and pinning the exact rounding rule at
    every year/month boundary the acceptance criteria name, together,
    in one table — four of the five (0, 51, 52, 260) were already
    scattered across individual tests above; 53 is the one genuinely new
    case.

    The rule, from `_approximate_parts` above:
      1. `years, remaining = divmod(whole_weeks, 52)` — 52 weeks makes a
         year (durations in this codebase are always a whole number of
         weeks, docs/CONTRACTS.md, so there is no leap-year/365.25-day
         correction to make).
      2. `months = round(remaining / (52 / 12))` — the remainder in
         twelfths-of-a-year months, rounded to the nearest whole month.
      3. A remainder that rounds UP to 12 months carries into one more
         year rather than ever displaying "0 years 12 months".
    """

    @pytest.mark.parametrize(
        ("weeks", "expected"),
        [
            (0, "0 weeks"),
            # 51/52 = 0 years remainder 51; 51/4.333.. = 11.77 rounds UP
            # to 12 months, which carries into 1 year, 0 months.
            (51, "51 weeks (about 1 year)"),
            # Exactly one year, no remainder at all.
            (52, "52 weeks (about 1 year)"),
            # 53/52 = 1 year remainder 1 week; 1/4.333.. = 0.23 rounds
            # DOWN to 0 months -- still "about 1 year", not "1 year 1
            # month" and not carried into a 2nd year.
            (53, "53 weeks (about 1 year)"),
            # 260/52 = exactly 5 years, no remainder.
            (260, "260 weeks (about 5 years)"),
        ],
    )
    def test_five_documented_year_month_boundary_weeks(
        self, weeks: int, expected: str
    ) -> None:
        assert format_duration_weeks(weeks) == expected


class TestNoNewDependency:
    def test_formatting_imports_only_the_standard_library_and_app_i18n(self) -> None:
        source = (
            __import__("pathlib")
            .Path(__import__("app.i18n.formatting", fromlist=["x"]).__file__)
            .read_text(encoding="utf-8")
        )
        for line in source.splitlines():
            if line.startswith(("import ", "from ")):
                module = line.split()[1].split(".")[0]
                assert module in {"__future__", "math", "datetime", "decimal", "typing", "app"}, (
                    f"I18N-2 adds no dependency; this imports {module}"
                )


class TestRegisteredAsJinjaFilters:
    def _render(self, source: str, **context: object) -> str:
        return templating.templates.env.from_string(source).render(**context)

    def test_every_filter_is_on_the_one_shared_environment(self) -> None:
        for name in ("inr", "money", "number", "date", "duration_weeks"):
            assert name in templating.templates.env.filters, name

    def test_filters_follow_the_pages_locale(self) -> None:
        assert self._render("{{ 100000 | inr }}", lang="en") == f"{RUPEE}1,00,000"
        assert self._render("{{ '2026-09-21' | date }}", lang="hi") == "21 सितंबर 2026"
        hindi_duration = self._render("{{ 78 | duration_weeks }}", lang="hi")
        assert hindi_duration == "78 सप्ताह (लगभग 1 वर्ष 6 महीने)"

    def test_an_explicit_locale_argument_wins(self) -> None:
        assert self._render("{{ '2026-09-21' | date('hi') }}", lang="en") == "21 सितंबर 2026"

    def test_an_unsupported_explicit_locale_falls_back_to_english(self) -> None:
        assert self._render("{{ '2026-09-21' | date('fr') }}") == "21 Sep 2026"

    def test_a_none_value_renders_the_not_available_string_not_the_word_none(self) -> None:
        rendered = self._render("{{ nothing | inr }}", nothing=None)
        assert rendered == "Not available"
        assert "None" not in rendered

    def test_an_undefined_variable_does_not_crash_the_page(self) -> None:
        assert self._render("{{ never_set | inr }}") == "Not available"


class TestTheMoneyFilter:
    """SCOPE-4: `{{ amount | money(currency) }}` is how a template shows
    money now -- amount and currency together, through the one
    formatter."""

    def _render(self, source: str, **context: object) -> str:
        return templating.templates.env.from_string(source).render(**context)

    def test_inr_renders_exactly_as_the_inr_filter_always_did(self) -> None:
        assert self._render("{{ 125000 | money('INR') }}") == f"{RUPEE}1,25,000"
        assert self._render("{{ 125000 | money('INR') }}") == self._render("{{ 125000 | inr }}")

    def test_a_foreign_currency_never_renders_a_rupee_sign(self) -> None:
        rendered = self._render("{{ 9500 | money('GBP') }}")
        assert rendered == "GBP 9,500"
        assert RUPEE not in rendered

    def test_a_missing_currency_is_not_available_never_assumed_rupees(self) -> None:
        """The core safety property of this filter: no currency, no
        number. Assuming INR here is the display bug SCOPE-4 exists to
        prevent (docs/CONTRACTS.md: "a money claim with a null currency
        renders not_available")."""
        for template in (
            "{{ 9500 | money(none) }}",
            "{{ 9500 | money('') }}",
            "{{ 9500 | money('   ') }}",
            "{{ 9500 | money(never_set) }}",
            "{{ 9500 | money }}",
        ):
            rendered = self._render(template)
            assert rendered == "Not available", template
            assert RUPEE not in rendered, template

    def test_a_missing_amount_is_not_available_not_a_bare_currency_code(self) -> None:
        assert self._render("{{ nothing | money('GBP') }}", nothing=None) == "Not available"

    def test_it_follows_the_pages_locale(self) -> None:
        assert self._render("{{ nothing | money('INR') }}", nothing=None, lang="hi") == translate(
            NOT_AVAILABLE_KEY, "hi"
        )
        assert self._render("{{ 100000 | money('INR') }}", lang="hi") == f"{RUPEE}1,00,000"

    def test_an_explicit_locale_argument_wins(self) -> None:
        rendered = self._render("{{ nothing | money('INR', 'hi') }}", nothing=None, lang="en")
        assert rendered == translate(NOT_AVAILABLE_KEY, "hi")

    def test_a_lowercase_or_padded_code_is_not_mistaken_for_inr(self) -> None:
        """`format_money` matches `"INR"` exactly; anything else takes the
        code-and-Western-grouping branch. Padding is stripped so a stray
        space in a claim's currency column does not turn ₹ into "INR "."""
        assert self._render("{{ 1000 | money(' INR ') }}") == f"{RUPEE}1,000"
        assert self._render("{{ 1000 | money('inr') }}") == "inr 1,000"
