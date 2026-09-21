"""I18N-1 — the i18n mechanism: locale resolution, the catalogue
contract, the per-key fallback chain, and the single shared Jinja
environment.

No template text is asserted here (I18N-3 does the extraction); this
covers the mechanism those later tasks are built on, including the two
properties that would otherwise fail silently in production: a `lang`
value reaching a file path, and a macro rendering English inside a
Hindi page because it was imported without context.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.requests import Request

from app import i18n
from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, resolve_locale, translate
from app.web import (
    common,
    compare_pages,
    consent_pages,
    explore_pages,
    requirements_pages,
    reviewer_pages,
    templating,
    timeline_pages,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "app" / "i18n"


def _fake_request(cookies: dict[str, str] | None = None) -> Request:
    """A minimal ASGI scope — enough for `request.cookies`, with no
    server, no app and no event loop involved."""
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


class TestResolverPrecedenceAndAllowlist:
    def test_absent_cookie_resolves_to_english(self) -> None:
        assert templating.locale_for_request(_fake_request()) == "en"

    def test_the_lang_cookie_selects_the_locale(self) -> None:
        assert templating.locale_for_request(_fake_request({"lang": "hi"})) == "hi"

    def test_another_cookie_never_selects_a_locale(self) -> None:
        request = _fake_request({"bcion_reviewer_session": "hi", "preferred_language": "hi"})
        assert templating.locale_for_request(request) == "en"

    @pytest.mark.parametrize("raw", ["", "  ", "fr", "en-GB", "gu", "HINDI", "hi,en", "0", "null"])
    def test_a_value_off_the_allowlist_falls_back_to_english(self, raw: str) -> None:
        assert resolve_locale(raw) == DEFAULT_LOCALE

    @pytest.mark.parametrize("raw", ["HI", " hi ", "Hi", "EN"])
    def test_case_and_surrounding_whitespace_are_tolerated(self, raw: str) -> None:
        assert resolve_locale(raw) in SUPPORTED_LOCALES

    def test_none_resolves_to_english(self) -> None:
        assert resolve_locale(None) == DEFAULT_LOCALE

    def test_only_two_locales_are_supported(self) -> None:
        assert SUPPORTED_LOCALES == ("en", "hi")


class TestTheLangValueNeverReachesAFilePath:
    """I18N-1's own risk note. Every one of these is a real cookie value
    a client can send; none may be turned into a path, and none may
    raise — they all become plain English."""

    @pytest.mark.parametrize(
        "raw",
        [
            "../../etc/passwd",
            "../en",
            "en/../../../../etc/passwd",
            "/etc/passwd",
            "C:\\Windows\\win.ini",
            "en\x00.json",
            "en.json",
            "hi.json",
            "..%2f..%2fen",
            "\\\\server\\share\\en",
        ],
    )
    def test_a_traversal_shaped_cookie_value_is_just_english(self, raw: str) -> None:
        assert resolve_locale(raw) == DEFAULT_LOCALE
        # And it still translates, from the English catalogue:
        assert translate("global.trust_badge.estimate", resolve_locale(raw)) == "Estimate"

    def test_catalogue_filenames_are_constants_not_built_from_the_locale(self) -> None:
        assert i18n._CATALOGUE_FILENAMES == {"en": "en.json", "hi": "hi.json"}

    def test_an_unsupported_locale_is_never_looked_up_as_a_catalogue(self) -> None:
        assert set(i18n._CATALOGUES) == set(SUPPORTED_LOCALES)


class TestCatalogueContract:
    def test_both_catalogues_are_flat_key_to_string_maps(self) -> None:
        for locale in SUPPORTED_LOCALES:
            for key, value in i18n.catalogue(locale).items():
                assert isinstance(key, str)
                assert isinstance(value, str), f"{locale}: {key} is not a string"

    def test_en_and_hi_have_exactly_the_same_keys(self) -> None:
        missing_in_hi = i18n.catalogue_keys("en") - i18n.catalogue_keys("hi")
        extra_in_hi = i18n.catalogue_keys("hi") - i18n.catalogue_keys("en")
        assert not missing_in_hi, f"hi.json is missing: {sorted(missing_in_hi)}"
        assert not extra_in_hi, f"hi.json has keys en.json does not: {sorted(extra_in_hi)}"

    def test_every_screen_key_has_three_dot_separated_segments(self) -> None:
        """docs/COPY.md section 2: `screen.component.purpose`. `_meta.*`
        provenance keys are the documented exception."""
        for key in i18n.catalogue_keys("en"):
            if key.startswith("_meta."):
                continue
            assert len(key.split(".")) == 3, f"{key} is not screen.component.purpose"
            assert key == key.lower(), f"{key} is not lower snake_case"

    def test_no_catalogue_string_is_blank(self) -> None:
        for locale in SUPPORTED_LOCALES:
            for key, value in i18n.catalogue(locale).items():
                if key.startswith("_meta."):
                    continue
                assert value.strip(), f"{locale}: {key} is blank"

    def test_the_hindi_catalogue_is_marked_unreviewed_until_a_human_reviews_it(self) -> None:
        """CLAUDE.md: a development agent's draft is never presented as
        reviewed work. I18N-11 flips this, with a name and a date."""
        hi = i18n.catalogue("hi")
        assert hi["_meta.review_status"] == "unreviewed"
        assert hi["_meta.reviewed_by"] == ""

    def test_hindi_uses_latin_digits_not_devanagari_numerals(self) -> None:
        """I18N-2's rule, asserted against the catalogue too: a student
        reading a Hindi page still sees 7, 12, 2026 — the same digits
        every form, exam paper and fee receipt in India uses."""
        devanagari_digits = set("०१२३४५६७८९")
        for key, value in i18n.catalogue("hi").items():
            assert not (devanagari_digits & set(value)), f"hi: {key} uses Devanagari numerals"

    def test_placeholders_match_between_locales(self) -> None:
        """A translation that drops or renames `{date}` would render a
        literal brace to a student."""
        for key in i18n.catalogue_keys("en"):
            en_names = set(i18n._PLACEHOLDER_RE.findall(i18n.catalogue("en")[key]))
            hi_names = set(i18n._PLACEHOLDER_RE.findall(i18n.catalogue("hi")[key]))
            assert en_names == hi_names, f"{key}: placeholders differ ({en_names} vs {hi_names})"

    def test_a_duplicated_key_is_rejected_rather_than_silently_dropped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "dupe.json").write_text('{"a.b.c": "one", "a.b.c": "two"}', encoding="utf-8")
        monkeypatch.setattr(i18n, "_CATALOGUE_DIRECTORY", tmp_path)
        with pytest.raises(ValueError, match="duplicate key"):
            i18n._load_catalogue("dupe.json")

    def test_a_nested_catalogue_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "nested.json").write_text('{"a": {"b": "c"}}', encoding="utf-8")
        monkeypatch.setattr(i18n, "_CATALOGUE_DIRECTORY", tmp_path)
        with pytest.raises(ValueError, match="not a string"):
            i18n._load_catalogue("nested.json")


class TestTheCatalogueMatchesDocsCopyMd:
    """docs/COPY.md is the source of truth for these strings (DESIGN-2).
    A reworded catalogue entry is a silent copy change; this catches it."""

    @pytest.mark.parametrize(
        ("key", "english"),
        [
            (
                "global.trust_badge.checked_against_official_source",
                "Checked against official source",
            ),
            ("global.trust_badge.not_available", "Not available"),
            ("global.eligibility_badge.meets_criterion", "Meets this requirement"),
            ("global.eligibility_badge.insufficient_information_criterion", "Not yet known"),
            (
                "global.difficult_state.ai_unavailable",
                "You can still compare routes and use the calculators.",
            ),
            ("global.guest_session.notice", "Not saved to an account."),
            (
                "compare.closing_prompt.text",
                "Which option would you like to investigate further?",
            ),
        ],
    )
    def test_shipped_strings_are_verbatim(self, key: str, english: str) -> None:
        assert translate(key, "en") == english

    def test_every_fixed_key_in_copy_md_exists_in_the_catalogue(self) -> None:
        """Parses the `| key | English |` tables out of docs/COPY.md
        section 3 rather than hard-coding a second list of keys."""
        copy_md = (REPO_ROOT / "docs" / "COPY.md").read_text(encoding="utf-8")
        keys = {
            line.split("|")[1].strip().strip("`")
            for line in copy_md.splitlines()
            if line.startswith("| `") and "." in line.split("|")[1]
        }
        assert len(keys) >= 20, "docs/COPY.md's key tables no longer parse"
        missing = keys - i18n.catalogue_keys("en")
        assert not missing, f"docs/COPY.md fixes these keys; en.json lacks them: {sorted(missing)}"


class TestFallbackChain:
    def test_a_key_missing_from_hindi_falls_back_to_english_not_a_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(i18n._CATALOGUES, "hi", {"kept.in.hindi": "हिंदी"})
        assert translate("kept.in.hindi", "hi") == "हिंदी"
        assert translate("global.trust_badge.estimate", "hi") == "Estimate"

    def test_the_fallback_is_per_key_not_per_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            i18n._CATALOGUES,
            "hi",
            {"global.trust_badge.estimate": "अनुमान"},
        )
        assert translate("global.trust_badge.estimate", "hi") == "अनुमान"
        assert translate("global.trust_badge.not_available", "hi") == "Not available"

    def test_a_key_missing_everywhere_renders_as_the_key_never_a_blank(self) -> None:
        assert translate("explore.nothing.here", "en") == "explore.nothing.here"
        assert translate("explore.nothing.here", "hi") == "explore.nothing.here"

    def test_an_unsupported_locale_reads_the_english_catalogue(self) -> None:
        assert translate("global.trust_badge.estimate", "fr") == "Estimate"


class TestPlaceholderSubstitution:
    def test_named_placeholders_are_substituted(self) -> None:
        rendered = translate(
            "global.difficult_state.information_changed",
            "en",
            field="Course fee",
            date="21 Sep 2026",
        )
        assert rendered == (
            "Course fee changed on 21 Sep 2026. "
            "Check whether it affects a plan you saved."
        )

    def test_a_forgotten_variable_leaves_the_placeholder_rather_than_raising(self) -> None:
        rendered = translate("global.difficult_state.information_changed", "en", field="Fee")
        assert "{date}" in rendered
        assert "Fee changed on" in rendered

    def test_an_unknown_variable_is_ignored(self) -> None:
        assert translate("global.trust_badge.estimate", "en", unrelated="x") == "Estimate"

    def test_a_variable_named_key_or_locale_does_not_collide_with_the_signature(self) -> None:
        assert i18n.substitute("{key}/{locale}", {"key": "a", "locale": "b"}) == "a/b"

    def test_a_stray_brace_is_left_alone_rather_than_raising(self) -> None:
        assert i18n.substitute("100% {of} {x", {"of": "of"}) == "100% of {x"

    def test_substitution_returns_a_plain_str_so_jinja_still_escapes_it(self) -> None:
        rendered = translate(
            "global.difficult_state.information_changed", "en", field="<b>x</b>", date="today"
        )
        assert type(rendered) is str
        assert "<b>x</b>" in rendered  # escaped by Jinja at render time, not here


class TestOneSharedJinjaEnvironment:
    """I18N-1's acceptance: "both routers share one environment"."""

    def test_every_router_module_uses_the_same_templates_object(self) -> None:
        for module in (
            common,
            explore_pages,
            compare_pages,
            requirements_pages,
            timeline_pages,
            reviewer_pages,
        ):
            assert module.templates is templating.templates, module.__name__

    def test_there_is_exactly_one_jinja_environment(self) -> None:
        environments = {
            id(module.templates.env)
            for module in (common, explore_pages, reviewer_pages, timeline_pages, consent_pages)
        }
        assert len(environments) == 1

    def test_no_web_module_constructs_its_own_jinja2templates(self) -> None:
        """A grep-style guard: the next screen module that copy-pastes
        `Jinja2Templates(...)` re-creates the split this task closed.

        `consent_pages.py` used to be a real, disclosed exception (it
        built its own instance) -- fixed to import the shared one like
        every other module; no exemption needed any more."""
        offenders = [
            path.name
            for path in (REPO_ROOT / "app" / "web").glob("*.py")
            if path.name != "templating.py"
            and "Jinja2Templates(" in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"these build a second Jinja environment: {offenders}"

    def test_the_t_global_is_registered_on_that_one_environment(self) -> None:
        assert "t" in templating.templates.env.globals

    def test_autoescaping_is_on_for_html_templates(self) -> None:
        autoescape = templating.templates.env.autoescape
        resolved = autoescape("base.html") if callable(autoescape) else autoescape
        assert resolved is True


class TestTInsideTemplates:
    def _render(self, source: str, **context: object) -> str:
        return templating.templates.env.from_string(source).render(**context)

    def test_t_uses_the_lang_in_the_render_context(self) -> None:
        assert self._render("{{ t('global.trust_badge.estimate') }}", lang="hi") == "अनुमान"
        assert self._render("{{ t('global.trust_badge.estimate') }}", lang="en") == "Estimate"

    def test_t_falls_back_to_the_requests_cookie_when_lang_is_absent(self) -> None:
        rendered = self._render(
            "{{ t('global.trust_badge.estimate') }}", request=_fake_request({"lang": "hi"})
        )
        assert rendered == "अनुमान"

    def test_t_with_no_context_at_all_renders_english_never_an_error(self) -> None:
        assert self._render("{{ t('global.trust_badge.estimate') }}") == "Estimate"

    def test_a_translation_is_autoescaped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(i18n._CATALOGUES, "en", {"x.y.z": "<script>alert(1)</script>"})
        assert "&lt;script&gt;" in self._render("{{ t('x.y.z') }}")

    def test_a_substituted_value_is_autoescaped(self) -> None:
        rendered = self._render(
            "{{ t('global.difficult_state.eligibility_uncertain', requirement=r) }}",
            r="<img src=x>",
        )
        assert "<img src=x>" not in rendered
        assert "&lt;img" in rendered

    def test_a_macro_imported_without_context_still_gets_the_page_locale(self) -> None:
        """The ContextVar path (see app/web/templating.py's docstring).
        Without it a shared macro renders English inside a Hindi page."""
        templating._current_locale.set("hi")
        try:
            assert self._render("{{ t('global.trust_badge.estimate') }}") == "अनुमान"
        finally:
            templating._current_locale.set("en")


class TestCatalogueFilesOnDisk:
    def test_both_files_are_utf8_json_objects(self) -> None:
        for filename in ("en.json", "hi.json"):
            parsed = json.loads((I18N_DIR / filename).read_text(encoding="utf-8"))
            assert isinstance(parsed, dict)

    def test_the_catalogue_directory_holds_no_unexpected_locale_file(self) -> None:
        on_disk = {path.name for path in I18N_DIR.glob("*.json")}
        assert on_disk == {"en.json", "hi.json"}
