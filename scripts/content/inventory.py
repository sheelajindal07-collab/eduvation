"""CONTENT-3 — offline draft extractor and inventory.

Reads every unverified research draft under ``docs/content-drafts/`` and
writes a structured coverage/gap report to
``docs/content-drafts/INVENTORY.md``.

This is a **checkable artefact, not a database import**: it does not
propose typed field values, does not write to ``content/staging/`` and is
never consulted by the app at runtime. Nothing in ``docs/content-drafts/``
is a verified fact (see ``CLAUDE.md`` non-negotiables and
``docs/DATA.md``'s maker-checker workflow) — this script only reports on
what the draft files already say about themselves (row counts, confidence
buckets, sourcing gaps), it never verifies anything.

Pure Python, standard library only: no database connection, no network
call and no AI provider. It is strictly read-only against the drafts — it
never edits a draft file, and its only output is ``INVENTORY.md`` (plus,
optionally, a copy printed to stdout with ``--print``). It does not
overwrite ``docs/content-drafts/INDEX.md``, which stays the hand-kept
"who is researching what" coordination doc; this script instead reports
what the drafts that already exist actually contain.

Usage::

    python scripts/content/inventory.py

``INVENTORY.md`` is generated output — edit this script and re-run it,
don't hand-edit the file.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRAFTS_DIR = REPO_ROOT / "docs" / "content-drafts"
OUTPUT_PATH = DRAFTS_DIR / "INVENTORY.md"
INDEX_FILENAME = "INDEX.md"

# The line every batch-researched draft carries is:
#   "Researcher: automated agent (session run for <email>), ..."
# That is a researcher's personal account, not an official source's
# published contact address (e.g. "cmat@nta.ac.in" elsewhere in the same
# files is fine and must never be flagged here). Matched narrowly on
# purpose so this report — and CONTENT-18's scrub — never touches an
# official contact email.
RESEARCHER_EMAIL_RE = re.compile(
    r"session run for\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    re.IGNORECASE,
)
RESEARCH_DATE_RE = re.compile(r"Research date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
CONFIDENCE_WORDS = ("high", "medium", "low", "not verified")

# A handful of drafts (seen so far: gujcet-eligibility.md,
# neet-ug-eligibility.md) write their facts as narrative bullet points
# instead of the standard 5-column table. Without this, those files would
# silently show as ~0 fact rows, which would misreport "not researched"
# for files that actually have substantial research in a different shape.
NARRATIVE_FACT_RE = re.compile(r"^-\s+\*\*Fact:?\*\*", re.MULTILINE)
NARRATIVE_CONFIDENCE_RE = re.compile(r"^-\s+\*\*Confidence:?\*\*\s*(.*)$", re.MULTILINE)


@dataclass
class TableStats:
    """Aggregated stats for one markdown table found in a draft."""

    header: tuple[str, ...]
    is_fact_table: bool
    row_count: int = 0
    confidence_counts: Counter[str] = field(default_factory=Counter)
    rows_without_url: int = 0


@dataclass
class FileReport:
    filename: str
    area: str
    title: str | None = None
    research_date: str | None = None
    has_front_matter: bool = True
    header_variants: set[tuple[str, ...]] = field(default_factory=set)
    fact_rows: int = 0
    confidence_counts: Counter[str] = field(default_factory=Counter)
    rows_without_url: int = 0
    other_table_rows: int = 0
    not_confirmed_items: int = 0
    has_researcher_email: bool = False
    parse_notes: list[str] = field(default_factory=list)


def classify_area(filename: str) -> str:
    """Bucket a draft filename into a reporting area.

    Matches the groupings already used informally in INDEX.md (exams,
    scholarships, institutions/NIRF, foreign pathways, states/UTs) so this
    report reads alongside it.
    """
    name = filename.removesuffix(".md")
    if name.startswith("foreign-pathway"):
        return "Foreign pathways"
    if name.startswith("state-admission-rules") or name.startswith(
        "state-institutions-scholarships"
    ):
        return "States/UTs"
    if "scholarship" in name or name.startswith("nsp-scheme"):
        return "Scholarships"
    if name.startswith("nirf-top") or "institution" in name or "universities" in name:
        return "Institutions / NIRF"
    if name.endswith("-eligibility"):
        return "Exams (eligibility)"
    return "Other / synthesis"


def _split_row(line: str) -> list[str]:
    """Split one markdown table row into stripped cell strings.

    Not a full markdown-table parser (escaped pipes inside a cell are not
    unescaped) — good enough for aggregate counts, which is all this
    report needs.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_row(line: str) -> bool:
    return bool(re.match(r"^\|?[\s:|-]+\|?$", line.strip())) and "-" in line


def _confidence_bucket(cell_text: str) -> str:
    lowered = cell_text.lower()
    for word in CONFIDENCE_WORDS:
        if lowered.startswith(word) or f" {word}" in lowered:
            return word
    return "unlabelled"


def _parse_tables(lines: list[str]) -> list[TableStats]:
    tables: list[TableStats] = []
    i = 0
    n = len(lines)
    while i < n - 1:
        line = lines[i]
        if line.strip().startswith("|") and _is_separator_row(lines[i + 1]):
            header_cells = tuple(_split_row(line))
            header_lower = [c.lower() for c in header_cells]
            confidence_idx = next(
                (idx for idx, c in enumerate(header_lower) if "confidence" in c), None
            )
            source_idx = next((idx for idx, c in enumerate(header_lower) if "source" in c), None)
            stats = TableStats(header=header_cells, is_fact_table=confidence_idx is not None)
            j = i + 2
            while j < n and lines[j].strip().startswith("|"):
                row = lines[j]
                if not _is_separator_row(row):
                    cells = _split_row(row)
                    stats.row_count += 1
                    if stats.is_fact_table and confidence_idx is not None:
                        conf_cell = cells[confidence_idx] if confidence_idx < len(cells) else ""
                        stats.confidence_counts[_confidence_bucket(conf_cell)] += 1
                        source_cell = cells[source_idx] if (
                            source_idx is not None and source_idx < len(cells)
                        ) else ""
                        if "http" not in source_cell.lower():
                            stats.rows_without_url += 1
                j += 1
            tables.append(stats)
            i = j
        else:
            i += 1
    return tables


def _count_not_confirmed_items(text: str) -> int:
    """Count bullet items under a '## Not confirmed / needs manual
    verification'-style heading (every draft carries some variant of
    this section calling out its own gaps)."""
    match = re.search(
        r"^##\s*Not confirmed.*$", text, re.MULTILINE | re.IGNORECASE
    )
    if not match:
        return 0
    rest = text[match.end():]
    next_heading = re.search(r"^##\s", rest, re.MULTILINE)
    section = rest[: next_heading.start()] if next_heading else rest
    return len(re.findall(r"^\s*\d+\.\s+\S", section, re.MULTILINE))


def analyze_file(path: Path) -> FileReport:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    report = FileReport(filename=path.name, area=classify_area(path.name))

    report.has_front_matter = text.startswith("---")
    if not report.has_front_matter:
        report.parse_notes.append("no '---' front-matter delimiter")

    title_match = TITLE_RE.search(text)
    if title_match:
        report.title = title_match.group(1)
    else:
        report.parse_notes.append("no top-level '# ' title found")

    date_match = RESEARCH_DATE_RE.search(text)
    if date_match:
        report.research_date = date_match.group(1)

    report.has_researcher_email = bool(RESEARCHER_EMAIL_RE.search(text))

    report.not_confirmed_items = _count_not_confirmed_items(text)

    for table in _parse_tables(lines):
        if table.is_fact_table:
            report.header_variants.add(table.header)
            report.fact_rows += table.row_count
            report.confidence_counts.update(table.confidence_counts)
            report.rows_without_url += table.rows_without_url
        else:
            report.other_table_rows += table.row_count

    narrative_facts = len(NARRATIVE_FACT_RE.findall(text))
    if narrative_facts:
        confidence_texts = NARRATIVE_CONFIDENCE_RE.findall(text)
        report.fact_rows += narrative_facts
        for conf_text in confidence_texts:
            report.confidence_counts[_confidence_bucket(conf_text)] += 1
        unlabelled_extra = narrative_facts - len(confidence_texts)
        if unlabelled_extra > 0:
            report.confidence_counts["unlabelled"] += unlabelled_extra
        report.parse_notes.append(
            f"{narrative_facts} narrative bullet-style fact(s), non-tabular format "
            "(not counted in 'no URL' totals)"
        )

    return report


def _load_index_status_counts() -> Counter[str]:
    """Very light read of INDEX.md's own status markers, purely to give a
    rough planned-vs-drafted picture. INDEX.md's prose sections aren't
    machine-parsed further than this — it stays the authoritative,
    hand-kept source for "what topic is whose", this is just a count."""
    index_path = DRAFTS_DIR / INDEX_FILENAME
    counts: Counter[str] = Counter()
    if not index_path.exists():
        return counts
    text = index_path.read_text(encoding="utf-8").lower()
    counts["done"] = len(re.findall(r"\bdone\b", text))
    counts["in-progress"] = len(re.findall(r"\bin-progress\b", text))
    counts["not yet claimed"] = len(re.findall(r"\bnot yet claimed\b", text))
    return counts


def discover_draft_files() -> list[Path]:
    return sorted(
        p for p in DRAFTS_DIR.glob("*.md") if p.name != INDEX_FILENAME and p.name != "INVENTORY.md"
    )


def build_reports() -> list[FileReport]:
    return [analyze_file(p) for p in discover_draft_files()]


def render_inventory(reports: list[FileReport]) -> str:
    by_area: dict[str, list[FileReport]] = defaultdict(list)
    for r in reports:
        by_area[r.area].append(r)

    total_files = len(reports)
    total_fact_rows = sum(r.fact_rows for r in reports)
    total_confidence: Counter[str] = Counter()
    for r in reports:
        total_confidence.update(r.confidence_counts)
    total_no_url = sum(r.rows_without_url for r in reports)
    total_not_confirmed = sum(r.not_confirmed_items for r in reports)
    files_no_front_matter = [r.filename for r in reports if not r.has_front_matter]
    files_with_email = [r.filename for r in reports if r.has_researcher_email]
    all_header_variants: set[tuple[str, ...]] = set()
    for r in reports:
        all_header_variants |= r.header_variants
    index_counts = _load_index_status_counts()

    lines: list[str] = []
    lines.append("# Content-draft inventory (generated, CONTENT-3)")
    lines.append("")
    lines.append(
        "Auto-generated by `python scripts/content/inventory.py` — do not "
        "hand-edit, re-run the script instead. Read-only report over "
        "`docs/content-drafts/*.md`; it does not verify, publish or import "
        "anything, and it does not replace `INDEX.md` (the hand-kept "
        "coordination doc for who is researching what)."
    )
    lines.append("")
    lines.append(
        "Every row counted below comes from **unverified draft research** "
        "(see `CLAUDE.md` non-negotiables and `docs/DATA.md`'s "
        "maker-checker workflow) — a High confidence bucket here means the "
        "researcher marked their own note as high-confidence, not that a "
        "human verifier has approved it."
    )
    lines.append("")

    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Draft files scanned: **{total_files}**")
    lines.append(f"- Fact-table rows: **{total_fact_rows}**")
    for bucket in (*CONFIDENCE_WORDS, "unlabelled"):
        lines.append(f"  - {bucket}: {total_confidence.get(bucket, 0)}")
    lines.append(f"- Fact rows with no URL in their source cell: **{total_no_url}**")
    lines.append(
        f"- Items listed under a file's own 'Not confirmed' section: **{total_not_confirmed}**"
    )
    lines.append(f"- Files with no '---' front-matter delimiter: **{len(files_no_front_matter)}**")
    if files_no_front_matter:
        lines.append("  - " + ", ".join(f"`{f}`" for f in files_no_front_matter))
    lines.append(
        f"- Files carrying the researcher-session email marker "
        f"(see CONTENT-18): **{len(files_with_email)}**"
    )
    lines.append(f"- Distinct fact-table header variants seen: **{len(all_header_variants)}**")
    for variant in sorted(all_header_variants):
        lines.append(f"  - `{' | '.join(variant)}`")
    if index_counts:
        lines.append("")
        lines.append(
            "- INDEX.md status-word counts (rough cross-check only, that "
            "file is the authoritative one): "
            + ", ".join(f"{k}={v}" for k, v in index_counts.items())
        )
    lines.append("")

    lines.append("## Coverage and gaps by area")
    lines.append("")
    lines.append(
        "| Area | Files | Fact rows | High | Medium | Low | Not verified | "
        "Unlabelled | No URL | Not-confirmed items |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for area in sorted(by_area):
        group = by_area[area]
        conf: Counter[str] = Counter()
        for r in group:
            conf.update(r.confidence_counts)
        lines.append(
            f"| {area} | {len(group)} | {sum(r.fact_rows for r in group)} | "
            f"{conf.get('high', 0)} | {conf.get('medium', 0)} | {conf.get('low', 0)} | "
            f"{conf.get('not verified', 0)} | {conf.get('unlabelled', 0)} | "
            f"{sum(r.rows_without_url for r in group)} | "
            f"{sum(r.not_confirmed_items for r in group)} |"
        )
    lines.append("")

    lines.append("## Per-file detail")
    lines.append("")
    for area in sorted(by_area):
        lines.append(f"### {area}")
        lines.append("")
        lines.append(
            "| File | Research date | Fact rows | High | Med | Low | NV | "
            "No URL | Not-confirmed | Notes |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in sorted(by_area[area], key=lambda r: r.filename):
            notes = list(r.parse_notes)
            if r.has_researcher_email:
                notes.append("has researcher email marker")
            if r.other_table_rows:
                notes.append(f"{r.other_table_rows} non-fact-table row(s)")
            notes_text = "; ".join(notes) if notes else ""
            lines.append(
                f"| `{r.filename}` | {r.research_date or '—'} | {r.fact_rows} | "
                f"{r.confidence_counts.get('high', 0)} | "
                f"{r.confidence_counts.get('medium', 0)} | "
                f"{r.confidence_counts.get('low', 0)} | "
                f"{r.confidence_counts.get('not verified', 0)} | "
                f"{r.rows_without_url} | {r.not_confirmed_items} | {notes_text} |"
            )
        lines.append("")

    lines.append("## Regenerating")
    lines.append("")
    lines.append("```")
    lines.append("python scripts/content/inventory.py")
    lines.append("```")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    reports = build_reports()
    inventory_text = render_inventory(reports)
    OUTPUT_PATH.write_text(inventory_text, encoding="utf-8")
    print(f"Scanned {len(reports)} draft files under {DRAFTS_DIR}")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
