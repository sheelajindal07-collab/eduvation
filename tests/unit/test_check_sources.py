"""Unit tests for CONTENT-4's allow-list checker
(scripts/content/check_sources.py).

Covers the acceptance line verbatim: "Unit tests fail javascript:,
data:, Wikipedia or Careers360, and unlisted-domain rows."
"""

from __future__ import annotations

from pathlib import Path

from scripts.content.check_sources import (
    check_register,
    check_url,
    load_allowed_domains,
)

ALLOWED = frozenset({"nta.ac.in", "cbse.gov.in"})


def test_javascript_scheme_is_rejected() -> None:
    result = check_url("javascript:alert(1)", ALLOWED)
    assert result.ok is False
    assert result.reason == "invalid_scheme"


def test_data_scheme_is_rejected() -> None:
    result = check_url("data:text/html,<script>1</script>", ALLOWED)
    assert result.ok is False
    assert result.reason == "invalid_scheme"


def test_wikipedia_is_rejected_as_aggregator() -> None:
    result = check_url("https://en.wikipedia.org/wiki/JEE_Main", ALLOWED)
    assert result.ok is False
    assert result.reason == "aggregator_domain"
    # `domain` echoes the actual host from the URL (not the collapsed
    # allow-list/block-list entry it matched against), so an editor can
    # see exactly what was checked.
    assert result.domain == "en.wikipedia.org"


def test_careers360_is_rejected_as_aggregator() -> None:
    result = check_url("https://www.careers360.com/exams/jee-main", ALLOWED)
    assert result.ok is False
    assert result.reason == "aggregator_domain"


def test_unlisted_domain_is_rejected() -> None:
    result = check_url("https://example.com/some-page", ALLOWED)
    assert result.ok is False
    assert result.reason == "domain_not_allowlisted"
    assert result.domain == "example.com"


def test_allowlisted_https_domain_is_accepted() -> None:
    result = check_url("https://jeemain.nta.ac.in/notice", ALLOWED)
    assert result.ok is True
    assert result.reason == "ok"
    # subdomain of an allow-listed domain matches
    assert result.domain == "jeemain.nta.ac.in"


def test_www_prefix_does_not_bypass_the_allowlist() -> None:
    result = check_url("https://www.cbse.gov.in/notice", ALLOWED)
    assert result.ok is True


def test_ftp_scheme_is_rejected() -> None:
    result = check_url("ftp://nta.ac.in/file.pdf", ALLOWED)
    assert result.ok is False
    assert result.reason == "invalid_scheme"


def test_empty_url_is_rejected() -> None:
    result = check_url("", ALLOWED)
    assert result.ok is False
    assert result.reason == "unparseable_url"


def test_aggregator_check_wins_even_if_domain_is_also_allowlisted() -> None:
    """The aggregator block-list must win over an accidental allow-list
    entry -- an editor mistake should never silently let a known
    secondary source back in."""
    allowed_with_mistake = ALLOWED | {"careers360.com"}
    result = check_url("https://www.careers360.com/exams/jee-main", allowed_with_mistake)
    assert result.ok is False
    assert result.reason == "aggregator_domain"


def test_load_allowed_domains_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    allow_file = tmp_path / "allowed_domains.txt"
    allow_file.write_text(
        "# comment\n\nnta.ac.in\nWWW.CBSE.GOV.IN\n  \n# another comment\n",
        encoding="utf-8",
    )

    domains = load_allowed_domains(allow_file)

    assert domains == frozenset({"nta.ac.in", "cbse.gov.in"})


def test_load_allowed_domains_missing_file_fails_closed(tmp_path: Path) -> None:
    domains = load_allowed_domains(tmp_path / "does_not_exist.txt")
    assert domains == frozenset()


def test_check_register_flags_every_bad_row(tmp_path: Path) -> None:
    register = tmp_path / "sources_register.csv"
    register.write_text(
        "source_key,authority,url,source_type,document_title,publication_date,"
        "cycle,retrieved_date,sha256\n"
        "jee-main-notice,NTA,https://jeemain.nta.ac.in/notice,official,"
        "JEE Main 2027 notice,2026-11-01,2027,2026-09-21,\n"
        "wiki-bad,Wikipedia,https://en.wikipedia.org/wiki/JEE_Main,aggregator,"
        "JEE Main article,,,2026-09-21,\n"
        "js-bad,n/a,javascript:alert(1),unknown,,,,,\n"
        "unlisted-bad,Random,https://example.com/jee,unknown,,,,,\n",
        encoding="utf-8",
    )

    results = check_register(register, ALLOWED)

    assert len(results) == 4
    by_key = {r.source_key: r.check for r in results}
    assert by_key["jee-main-notice"].ok is True
    assert by_key["wiki-bad"].reason == "aggregator_domain"
    assert by_key["js-bad"].reason == "invalid_scheme"
    assert by_key["unlisted-bad"].reason == "domain_not_allowlisted"


def test_check_register_missing_file_returns_empty(tmp_path: Path) -> None:
    results = check_register(tmp_path / "missing.csv", ALLOWED)
    assert results == []


def test_project_allowed_domains_file_parses_without_error() -> None:
    """The real content/allowed_domains.txt (a proposed, not-yet-signed-
    off starting list) must at least be parseable and non-crashing."""
    domains = load_allowed_domains()
    assert isinstance(domains, frozenset)
