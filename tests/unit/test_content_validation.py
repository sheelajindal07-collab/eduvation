"""Unit tests for CONTENT-6 session 1's four automated content checks
(scripts/content/validation.py).
"""

from __future__ import annotations

from pathlib import Path

from scripts.content.validation import (
    ClaimRow,
    check_aggregator_domain,
    check_incomplete_eligibility_set,
    check_missing_checked_by,
    check_missing_verbatim_quote,
    load_rows,
    load_source_urls,
    validate_csv,
    validate_rows,
)

ALLOWED = frozenset({"nta.ac.in"})
SOURCES = {"jee-main-notice": "https://jeemain.nta.ac.in/notice"}


def _row(row_number: int = 1, **overrides: str) -> ClaimRow:
    defaults: dict[str, str] = {
        "entity_type": "pathway",
        "entity_key": "jee-main",
        "field": "minimum_age",
        "value": "17",
        "unit": "",
        "jurisdiction": "IN",
        "cycle": "2026-27",
        "tier": "1",
        "source_key": "jee-main-notice",
        "section_ref": "clause 3.1",
        "quote": "Candidates must be at least 17 years of age.",
        "checked_by": "editor1",
        "checked_on": "2026-09-21",
    }
    defaults.update(overrides)
    raw = dict(defaults)
    return ClaimRow(row_number=row_number, raw=raw, **defaults)


# ---------------------------------------------------------------------
# Check 1: missing checked_by
# ---------------------------------------------------------------------


def test_missing_checked_by_is_flagged() -> None:
    rows = [_row(checked_by="")]
    violations = check_missing_checked_by(rows)
    assert len(violations) == 1
    assert violations[0].reason == "missing_checked_by"


def test_present_checked_by_is_not_flagged() -> None:
    rows = [_row(checked_by="editor1")]
    assert check_missing_checked_by(rows) == []


def test_whitespace_only_checked_by_is_flagged() -> None:
    rows = [_row(checked_by="   ")]
    violations = check_missing_checked_by(rows)
    assert len(violations) == 1


# ---------------------------------------------------------------------
# Check 2: missing verbatim quote
# ---------------------------------------------------------------------


def test_missing_quote_is_flagged() -> None:
    rows = [_row(quote="")]
    violations = check_missing_verbatim_quote(rows)
    assert len(violations) == 1
    assert violations[0].reason == "missing_verbatim_quote"


def test_present_quote_is_not_flagged() -> None:
    rows = [_row(quote="Candidates must be at least 17 years of age.")]
    assert check_missing_verbatim_quote(rows) == []


# ---------------------------------------------------------------------
# Check 3: aggregator-domain source
# ---------------------------------------------------------------------


def test_allowlisted_source_is_not_flagged() -> None:
    rows = [_row(source_key="jee-main-notice")]
    violations = check_aggregator_domain(rows, SOURCES, ALLOWED)
    assert violations == []


def test_aggregator_source_is_flagged() -> None:
    sources = {"wiki": "https://en.wikipedia.org/wiki/JEE_Main"}
    rows = [_row(source_key="wiki")]
    violations = check_aggregator_domain(rows, sources, ALLOWED)
    assert len(violations) == 1
    assert violations[0].reason == "aggregator_domain"


def test_unlisted_domain_source_is_flagged() -> None:
    sources = {"random": "https://example.com/page"}
    rows = [_row(source_key="random")]
    violations = check_aggregator_domain(rows, sources, ALLOWED)
    assert len(violations) == 1
    assert violations[0].reason == "domain_not_allowlisted"


def test_javascript_scheme_source_is_flagged() -> None:
    sources = {"bad": "javascript:alert(1)"}
    rows = [_row(source_key="bad")]
    violations = check_aggregator_domain(rows, sources, ALLOWED)
    assert len(violations) == 1
    assert violations[0].reason == "invalid_scheme"


def test_missing_source_key_is_flagged() -> None:
    rows = [_row(source_key="")]
    violations = check_aggregator_domain(rows, SOURCES, ALLOWED)
    assert len(violations) == 1
    assert violations[0].reason == "missing_source_key"


def test_unknown_source_key_is_flagged() -> None:
    rows = [_row(source_key="does-not-exist")]
    violations = check_aggregator_domain(rows, SOURCES, ALLOWED)
    assert len(violations) == 1
    assert violations[0].reason == "unknown_source_key"


# ---------------------------------------------------------------------
# Check 4: incomplete eligibility set
# ---------------------------------------------------------------------


def test_entity_with_no_required_fields_declared_is_not_flagged() -> None:
    rows = [_row(field="minimum_age", value="17")]
    assert check_incomplete_eligibility_set(rows) == []


def test_complete_eligibility_set_is_not_flagged() -> None:
    rows = [
        _make_row_with_required(1, field="minimum_age", value="17",
                                 required_fields="minimum_age,marks_percentage_min"),
        _make_row_with_required(2, field="marks_percentage_min", value="75"),
    ]
    assert check_incomplete_eligibility_set(rows) == []


def test_incomplete_eligibility_set_is_flagged() -> None:
    rows = [
        _make_row_with_required(1, field="minimum_age", value="17",
                                 required_fields="minimum_age,marks_percentage_min"),
        # marks_percentage_min never supplied for this entity
    ]
    violations = check_incomplete_eligibility_set(rows)
    assert len(violations) == 1
    assert violations[0].reason == "incomplete_eligibility_set"
    assert violations[0].row_number is None
    assert "marks_percentage_min" in violations[0].detail


def test_eligibility_field_present_but_blank_value_still_counts_as_missing() -> None:
    rows = [
        _make_row_with_required(1, field="minimum_age", value="",
                                 required_fields="minimum_age"),
    ]
    violations = check_incomplete_eligibility_set(rows)
    assert len(violations) == 1


def _make_row_with_required(row_number: int, *, field: str, value: str,
                             required_fields: str = "", entity_key: str = "jee-main") -> ClaimRow:
    row = _row(row_number=row_number, field=field, value=value, entity_key=entity_key)
    raw = dict(row.raw)
    raw["required_fields"] = required_fields
    return ClaimRow(
        row_number=row.row_number,
        entity_type=row.entity_type,
        entity_key=row.entity_key,
        field=row.field,
        value=row.value,
        unit=row.unit,
        jurisdiction=row.jurisdiction,
        cycle=row.cycle,
        tier=row.tier,
        source_key=row.source_key,
        section_ref=row.section_ref,
        quote=row.quote,
        checked_by=row.checked_by,
        checked_on=row.checked_on,
        raw=raw,
    )


# ---------------------------------------------------------------------
# CSV loading and end-to-end validate_rows / validate_csv
# ---------------------------------------------------------------------


def test_load_rows_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_rows(tmp_path / "missing.csv") == []


def test_load_rows_reads_extra_columns_into_raw(tmp_path: Path) -> None:
    csv_path = tmp_path / "claims.csv"
    csv_path.write_text(
        "entity_type,entity_key,field,value,unit,jurisdiction,cycle,tier,"
        "source_key,section_ref,quote,checked_by,checked_on,required_fields\n"
        "pathway,jee-main,minimum_age,17,,IN,2026-27,1,jee-main-notice,"
        "clause 3.1,\"Candidates must be at least 17 years of age.\","
        "editor1,2026-09-21,minimum_age\n",
        encoding="utf-8",
    )

    rows = load_rows(csv_path)

    assert len(rows) == 1
    assert rows[0].entity_key == "jee-main"
    assert rows[0].required_fields == frozenset({"minimum_age"})


def test_load_source_urls_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_source_urls(tmp_path / "missing.csv") == {}


def test_load_source_urls_reads_source_key_to_url(tmp_path: Path) -> None:
    csv_path = tmp_path / "sources_register.csv"
    csv_path.write_text(
        "source_key,authority,url,source_type,document_title,publication_date,"
        "cycle,retrieved_date,sha256\n"
        "jee-main-notice,NTA,https://jeemain.nta.ac.in/notice,official,"
        "JEE Main 2027 notice,2026-11-01,2027,2026-09-21,\n",
        encoding="utf-8",
    )

    mapping = load_source_urls(csv_path)

    assert mapping == {"jee-main-notice": "https://jeemain.nta.ac.in/notice"}


def test_validate_rows_combines_all_four_checks() -> None:
    good = _make_row_with_required(
        1, field="minimum_age", value="17", required_fields="minimum_age",
        entity_key="jee-main",
    )
    missing_checked_by = _row(row_number=2, checked_by="", entity_key="cds")
    missing_quote = _row(row_number=3, quote="", entity_key="cds")
    bad_source = _row(row_number=4, source_key="wiki", entity_key="cds")

    sources = {**SOURCES, "wiki": "https://en.wikipedia.org/wiki/CDS"}
    violations = validate_rows(
        [good, missing_checked_by, missing_quote, bad_source],
        source_urls=sources,
        allowed_domains=ALLOWED,
    )

    reasons = {v.reason for v in violations}
    assert "missing_checked_by" in reasons
    assert "missing_verbatim_quote" in reasons
    assert "aggregator_domain" in reasons
    assert not any(v.entity_key == "jee-main" for v in violations)


def test_validate_csv_missing_claims_file_returns_empty(tmp_path: Path) -> None:
    violations = validate_csv(
        tmp_path / "missing.csv",
        sources_register_path=tmp_path / "missing_sources.csv",
        allowed_domains_path=tmp_path / "missing_domains.txt",
    )
    assert violations == []


def test_validate_csv_end_to_end(tmp_path: Path) -> None:
    claims_path = tmp_path / "trial_subset.csv"
    claims_path.write_text(
        "entity_type,entity_key,field,value,unit,jurisdiction,cycle,tier,"
        "source_key,section_ref,quote,checked_by,checked_on,required_fields\n"
        "pathway,jee-main,minimum_age,17,,IN,2026-27,1,jee-main-notice,"
        "clause 3.1,\"Candidates must be at least 17.\",editor1,2026-09-21,\n"
        "pathway,cds,minimum_age,19,,IN,2026-27,1,wiki-source,clause 1,,,\n",
        encoding="utf-8",
    )
    register_path = tmp_path / "sources_register.csv"
    register_path.write_text(
        "source_key,authority,url,source_type,document_title,publication_date,"
        "cycle,retrieved_date,sha256\n"
        "jee-main-notice,NTA,https://jeemain.nta.ac.in/notice,official,,,,,\n"
        "wiki-source,Wikipedia,https://en.wikipedia.org/wiki/CDS,aggregator,,,,,\n",
        encoding="utf-8",
    )
    domains_path = tmp_path / "allowed_domains.txt"
    domains_path.write_text("nta.ac.in\n", encoding="utf-8")

    violations = validate_csv(
        claims_path,
        sources_register_path=register_path,
        allowed_domains_path=domains_path,
    )

    reasons_by_entity: dict[str, set[str]] = {}
    for v in violations:
        reasons_by_entity.setdefault(v.entity_key, set()).add(v.reason)

    assert "jee-main" not in reasons_by_entity
    assert reasons_by_entity["cds"] == {
        "missing_checked_by",
        "missing_verbatim_quote",
        "aggregator_domain",
    }


def test_project_default_files_do_not_crash_validate_csv() -> None:
    """The real (currently empty/template) content/ files must at least
    load without error -- this is what `make content-check` runs."""
    violations = validate_csv()
    assert isinstance(violations, list)
