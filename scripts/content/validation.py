"""CONTENT-6 (session 1) -- the four automated content-import checks.

Ordinary, deterministic code (CLAUDE.md: "ordinary code for facts, rules
and arithmetic" -- no model call, ever). This module is the validation
half of CONTENT-6's importer; ``scripts/content/import_claims.py`` (a
later session) is expected to call :func:`validate_rows` before writing
anything, and to refuse to import any row this module flags.

**No DB writes, no network call, no AI provider.** This validates a
structured claims-import CSV (and the sources register CSV it points
at) purely in memory. It never publishes, approves or claims anything --
a row passing every check here is only "structurally fit to enter
review", never "verified" or "published" (CLAUDE.md non-negotiables;
those states are a human, server-enforced maker-checker workflow this
module has no part in).

The four checks, matching the plan's own CONTENT-6 acceptance criteria
(``docs/plan/inventory-2-trust-content.md``) and explained for editors in
``docs/CONTENT-EDITOR-HANDBOOK.md`` section 13:

1. ``missing_checked_by`` -- the ``checked_by`` cell is blank.
2. ``missing_verbatim_quote`` -- the ``quote`` cell is blank.
3. ``aggregator_domain`` -- the row's ``source_key`` resolves (via the
   sources register) to a URL that is not http(s), not allow-listed, or
   is a known secondary aggregator -- delegated entirely to
   ``scripts/content/check_sources.py`` (CONTENT-4), never
   re-implemented here.
4. ``incomplete_eligibility_set`` -- an entity that declares a required
   field set (see below) is missing one or more of those fields among
   its own rows.

Row schema (CSV columns), matching CONTENT-2's frozen column list
(``docs/plan/inventory-2-trust-content.md`` CONTENT-2 "What") and the
``content_hash`` field list frozen in ``docs/CONTRACTS.md``'s
"Publishing evidence in Phase 1" section:

    entity_type, entity_key, field, value, unit, jurisdiction, cycle,
    tier, source_key, section_ref, quote, checked_by, checked_on,
    required_fields

``entity_key`` is the entity's natural key (e.g. an exam or pathway
slug). ``required_fields`` is optional and CSV-internal to this
validator (not yet part of any frozen contract file -- CONTENT-2's own
``docs/CONTENT-IMPORT.md`` / ``content/templates/*.csv`` do not exist on
disk yet): a comma-separated list of ``field`` values that must all be
present, with a non-blank ``value``, among a given entity's rows for
that entity's eligibility set to count as complete. Declaring the
required set from data (rather than a hard-coded per-exam table in this
script) keeps the actual, real per-pathway eligibility requirement --
which is a content decision, not something this script should invent --
in the hands of whoever curates the CSV (CONTENT-5), while still letting
this check be fully deterministic and unit-tested. A row's own
``required_fields`` cell may be left blank; only one row per entity needs
to carry it (repeating it on every row for that entity is fine too, and
is checked for consistency).

Usage (run as a module, not as a bare script, because it imports its
sibling ``check_sources`` module by package path -- see
``mk/content.mk``'s ``content-check`` target)::

    python -m scripts.content.validation
    python -m scripts.content.validation --claims path/to/claims.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from scripts.content.check_sources import (
    AGGREGATOR_DOMAINS,
    DEFAULT_ALLOWED_DOMAINS_PATH,
    DEFAULT_REGISTER_PATH,
    check_url,
    load_allowed_domains,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLAIMS_PATH = REPO_ROOT / "content" / "curation" / "trial_subset.csv"

REQUIRED_ROW_COLUMNS = (
    "entity_type",
    "entity_key",
    "field",
    "value",
    "unit",
    "jurisdiction",
    "cycle",
    "tier",
    "source_key",
    "section_ref",
    "quote",
    "checked_by",
    "checked_on",
)


@dataclass(frozen=True)
class ClaimRow:
    """One row of a claims-import CSV, as a plain typed record. Extra
    CSV columns beyond :data:`REQUIRED_ROW_COLUMNS` (e.g.
    ``required_fields``) are kept in ``raw`` rather than added as new
    dataclass fields, so this stays in step with whichever exact column
    set CONTENT-2 eventually freezes."""

    row_number: int  # 1-based, header excluded
    entity_type: str
    entity_key: str
    field: str
    value: str
    unit: str
    jurisdiction: str
    cycle: str
    tier: str
    source_key: str
    section_ref: str
    quote: str
    checked_by: str
    checked_on: str
    raw: dict[str, str]

    @property
    def required_fields(self) -> frozenset[str]:
        cell = (self.raw.get("required_fields") or "").strip()
        if not cell:
            return frozenset()
        return frozenset(part.strip() for part in cell.split(",") if part.strip())


@dataclass(frozen=True)
class Violation:
    """One thing wrong with one row (or one entity's row group)."""

    row_number: int | None  # None when the violation spans a whole entity group
    entity_key: str
    reason: str
    detail: str


def _clean(value: str | None) -> str:
    return (value or "").strip()


def load_rows(path: Path) -> list[ClaimRow]:
    """Read a claims-import CSV into :class:`ClaimRow` records. A
    missing file returns an empty list (fails closed -- nothing to
    import rather than an error that could be mistaken for "all rows
    passed")."""
    if not path.exists():
        return []

    rows: list[ClaimRow] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, raw in enumerate(reader, start=1):
            rows.append(
                ClaimRow(
                    row_number=row_number,
                    entity_type=_clean(raw.get("entity_type")),
                    entity_key=_clean(raw.get("entity_key")),
                    field=_clean(raw.get("field")),
                    value=_clean(raw.get("value")),
                    unit=_clean(raw.get("unit")),
                    jurisdiction=_clean(raw.get("jurisdiction")),
                    cycle=_clean(raw.get("cycle")),
                    tier=_clean(raw.get("tier")),
                    source_key=_clean(raw.get("source_key")),
                    section_ref=_clean(raw.get("section_ref")),
                    quote=_clean(raw.get("quote")),
                    checked_by=_clean(raw.get("checked_by")),
                    checked_on=_clean(raw.get("checked_on")),
                    raw=dict(raw),
                )
            )
    return rows


def load_source_urls(path: Path = DEFAULT_REGISTER_PATH) -> dict[str, str]:
    """Read ``source_key -> url`` out of a sources_register.csv (the
    same file CONTENT-4's ``check_sources.py`` reads). A missing file or
    a missing/blank cell is simply absent from the returned mapping."""
    if not path.exists():
        return {}
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_key = _clean(row.get("source_key"))
            url = _clean(row.get("url"))
            if source_key and url:
                mapping[source_key] = url
    return mapping


# ---------------------------------------------------------------------
# The four checks. Each takes the full row list (plus whatever extra
# context it needs) and returns every violation it finds -- never raises
# on a bad row, since one bad row must not stop the rest from being
# checked and reported in the same pass.
# ---------------------------------------------------------------------


def check_missing_checked_by(rows: list[ClaimRow]) -> list[Violation]:
    return [
        Violation(
            row_number=row.row_number,
            entity_key=row.entity_key,
            reason="missing_checked_by",
            detail="checked_by is blank -- an unattributed row can never be a claim.",
        )
        for row in rows
        if not row.checked_by.strip()
    ]


def check_missing_verbatim_quote(rows: list[ClaimRow]) -> list[Violation]:
    return [
        Violation(
            row_number=row.row_number,
            entity_key=row.entity_key,
            reason="missing_verbatim_quote",
            detail="quote is blank -- every claim needs the exact source wording.",
        )
        for row in rows
        if not row.quote.strip()
    ]


def check_aggregator_domain(
    rows: list[ClaimRow],
    source_urls: dict[str, str],
    allowed_domains: frozenset[str],
    *,
    aggregator_domains: frozenset[str] = AGGREGATOR_DOMAINS,
) -> list[Violation]:
    """Resolve each row's ``source_key`` to a URL via the sources
    register and delegate the actual scheme/allow-list/aggregator
    decision to ``scripts/content/check_sources.check_url`` -- this
    function never re-implements that logic."""
    violations: list[Violation] = []
    for row in rows:
        if not row.source_key:
            violations.append(
                Violation(
                    row_number=row.row_number,
                    entity_key=row.entity_key,
                    reason="missing_source_key",
                    detail="source_key is blank -- cannot resolve a source to check.",
                )
            )
            continue

        url = source_urls.get(row.source_key)
        if url is None:
            violations.append(
                Violation(
                    row_number=row.row_number,
                    entity_key=row.entity_key,
                    reason="unknown_source_key",
                    detail=(
                        f"source_key {row.source_key!r} is not in the sources register."
                    ),
                )
            )
            continue

        result = check_url(url, allowed_domains, aggregator_domains=aggregator_domains)
        if not result.ok:
            violations.append(
                Violation(
                    row_number=row.row_number,
                    entity_key=row.entity_key,
                    reason=result.reason,
                    detail=f"source_key {row.source_key!r} -> {url!r}: {result.reason}",
                )
            )
    return violations


def check_incomplete_eligibility_set(rows: list[ClaimRow]) -> list[Violation]:
    """Group rows by ``entity_key`` and, for any entity that declares a
    non-empty ``required_fields`` set on at least one of its rows,
    confirm every one of those fields has a row with a non-blank
    ``value`` for that entity. Per CONTENT-5's acceptance criterion and
    docs/CONTENT-EDITOR-HANDBOOK.md section 5: a pathway's eligibility
    set publishes complete or not at all -- this check is what enforces
    that mechanically."""
    by_entity: dict[str, list[ClaimRow]] = defaultdict(list)
    for row in rows:
        if row.entity_key:
            by_entity[row.entity_key].append(row)

    violations: list[Violation] = []
    for entity_key, entity_rows in by_entity.items():
        required: frozenset[str] = frozenset()
        for row in entity_rows:
            required |= row.required_fields
        if not required:
            continue  # this entity does not declare a required set at all

        present_fields = {row.field for row in entity_rows if row.field and row.value}
        missing = required - present_fields
        if missing:
            violations.append(
                Violation(
                    row_number=None,
                    entity_key=entity_key,
                    reason="incomplete_eligibility_set",
                    detail=(
                        f"missing field(s) {sorted(missing)} out of required "
                        f"{sorted(required)} for entity {entity_key!r}"
                    ),
                )
            )
    return violations


def validate_rows(
    rows: list[ClaimRow],
    *,
    source_urls: dict[str, str] | None = None,
    allowed_domains: frozenset[str] | None = None,
) -> list[Violation]:
    """Run all four checks and return every violation found, in a
    stable, readable order (missing checked_by, missing quote, source
    problems, then eligibility completeness)."""
    if source_urls is None:
        source_urls = load_source_urls()
    if allowed_domains is None:
        allowed_domains = load_allowed_domains()

    violations: list[Violation] = []
    violations += check_missing_checked_by(rows)
    violations += check_missing_verbatim_quote(rows)
    violations += check_aggregator_domain(rows, source_urls, allowed_domains)
    violations += check_incomplete_eligibility_set(rows)
    return violations


def validate_csv(
    claims_path: Path = DEFAULT_CLAIMS_PATH,
    *,
    sources_register_path: Path = DEFAULT_REGISTER_PATH,
    allowed_domains_path: Path = DEFAULT_ALLOWED_DOMAINS_PATH,
) -> list[Violation]:
    rows = load_rows(claims_path)
    source_urls = load_source_urls(sources_register_path)
    allowed_domains = load_allowed_domains(allowed_domains_path)
    return validate_rows(rows, source_urls=source_urls, allowed_domains=allowed_domains)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--claims",
        type=Path,
        default=DEFAULT_CLAIMS_PATH,
        help="Path to the claims-import CSV (default: content/curation/trial_subset.csv)",
    )
    parser.add_argument(
        "--register",
        type=Path,
        default=DEFAULT_REGISTER_PATH,
        help="Path to sources_register.csv (default: content/sources_register.csv)",
    )
    parser.add_argument(
        "--allowed-domains",
        type=Path,
        default=DEFAULT_ALLOWED_DOMAINS_PATH,
        help="Path to allowed_domains.txt (default: content/allowed_domains.txt)",
    )
    args = parser.parse_args(argv)

    rows = load_rows(args.claims)
    print(f"Loaded {len(rows)} row(s) from {args.claims}")
    if not rows:
        print("Nothing to validate.")
        return 0

    violations = validate_csv(
        args.claims,
        sources_register_path=args.register,
        allowed_domains_path=args.allowed_domains,
    )
    if violations:
        print(f"{len(violations)} violation(s):")
        for v in violations:
            where = f"row {v.row_number}" if v.row_number is not None else "entity-level"
            print(f"  {where} (entity_key={v.entity_key!r}): {v.reason} -- {v.detail}")
    else:
        print("No violations.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
