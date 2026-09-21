"""CONTENT-4 (dev part) -- official-domain allow-list checker.

Ordinary, deterministic code (CLAUDE.md: "ordinary code for facts, rules
and arithmetic") -- no model call, no network fetch, no DB connection.
It answers one narrow question for one URL, or for a whole
``sources_register.csv``: is this an http(s) URL on an allow-listed
official domain, and is it not a known secondary aggregator / marketing
portal?

This is an **allow-list** checker (default-deny): a domain is only
accepted if it appears in ``content/allowed_domains.txt`` (or an
explicitly passed-in list). The aggregator block-list
(:data:`AGGREGATOR_DOMAINS`) is checked *before* the allow-list and
wins even if a domain were mistakenly allow-listed -- it exists so an
editor's slip does not silently let a known secondary source back in.

What this script does NOT do: it does not decide whether a source is
trustworthy beyond "http(s) scheme, allow-listed domain, not a known
aggregator" -- that judgement, and the actual population and sign-off of
``content/allowed_domains.txt``, is the named editor's job (CONTENT-4's
human part). It never writes ``verified``/``published`` anywhere; it has
no concept of a Claim.

Pure Python, standard library only: no database connection, no network
call and no AI provider. Strictly read-only.

Usage::

    python scripts/content/check_sources.py
    python scripts/content/check_sources.py --register path/to/register.csv \\
        --allowed-domains path/to/allowed_domains.txt
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER_PATH = REPO_ROOT / "content" / "sources_register.csv"
DEFAULT_ALLOWED_DOMAINS_PATH = REPO_ROOT / "content" / "allowed_domains.txt"

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Known secondary aggregator / comparison / marketing-portal domains seen
# in the draft research (docs/content-drafts/INVENTORY.md's per-file
# "No URL" and Source-cell notes) and named explicitly in
# docs/plan/inventory-2-trust-content.md ("aggregators and marketing
# portals are leads", "British Council, Study-in-X portals and
# aggregators are leads only", acceptance line "fail ... Wikipedia or
# Careers360").
#
# PROPOSED starting list, same caveat as content/allowed_domains.txt:
# not signed off by the editor. It is intentionally a distinct,
# explicit block-list (checked ahead of the allow-list) rather than
# "just leave it off the allow-list", so a future accidental allow-list
# entry for one of these still gets rejected with a clear reason.
AGGREGATOR_DOMAINS: frozenset[str] = frozenset(
    {
        "wikipedia.org",
        "wikimedia.org",
        "careers360.com",
        "shiksha.com",
        "collegedunia.com",
        "getmyuni.com",
        "collegedekho.com",
        "leverageedu.com",
        "jagranjosh.com",
        "aglasem.com",
        "successcds.net",
        "careerguide.com",
        "collegevidya.com",
        "yocket.com",
        "idp.com",
        "britishcouncil.org",
        "studyabroad.com",
        "topuniversities.com",
        "timeshighereducation.com",
        "quora.com",
    }
)


@dataclass(frozen=True)
class UrlCheck:
    """Result of checking a single URL."""

    url: str
    ok: bool
    reason: str  # "ok", "invalid_scheme", "unparseable_url",
    # "aggregator_domain", "domain_not_allowlisted"
    domain: str | None = None


@dataclass(frozen=True)
class RegisterRowResult:
    """Result of checking one row of a sources register CSV."""

    row_number: int  # 1-based, header excluded
    source_key: str
    check: UrlCheck


def load_allowed_domains(path: Path = DEFAULT_ALLOWED_DOMAINS_PATH) -> frozenset[str]:
    """Read the allow-list file: one lowercase domain per line, blank
    lines and ``#``-comments ignored. Missing file -> empty set (fails
    closed: nothing is allow-listed until the file exists and is
    populated)."""
    if not path.exists():
        return frozenset()
    domains: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if not line or line.startswith("#"):
            continue
        domains.add(line.removeprefix("www."))
    return frozenset(domains)


def _normalise_host(host: str) -> str:
    return host.strip().lower().removeprefix("www.")


def _domain_in_set(host: str, domains: frozenset[str]) -> bool:
    """True if `host` equals a domain in `domains`, or is a subdomain of
    one (e.g. "jeemain.nta.ac.in" matches allow-listed "nta.ac.in")."""
    return any(host == d or host.endswith(f".{d}") for d in domains)


def check_url(
    url: str,
    allowed_domains: frozenset[str],
    *,
    aggregator_domains: frozenset[str] = AGGREGATOR_DOMAINS,
) -> UrlCheck:
    """Check one URL against the scheme rule, the aggregator block-list
    and the allow-list, in that order."""
    url = (url or "").strip()
    if not url:
        return UrlCheck(url=url, ok=False, reason="unparseable_url")

    try:
        parsed = urlparse(url)
    except ValueError:
        return UrlCheck(url=url, ok=False, reason="unparseable_url")

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return UrlCheck(url=url, ok=False, reason="invalid_scheme")

    host = parsed.hostname
    if not host:
        return UrlCheck(url=url, ok=False, reason="unparseable_url")
    host = _normalise_host(host)

    if _domain_in_set(host, aggregator_domains):
        return UrlCheck(url=url, ok=False, reason="aggregator_domain", domain=host)

    if not _domain_in_set(host, allowed_domains):
        return UrlCheck(url=url, ok=False, reason="domain_not_allowlisted", domain=host)

    return UrlCheck(url=url, ok=True, reason="ok", domain=host)


def check_register(
    register_path: Path = DEFAULT_REGISTER_PATH,
    allowed_domains: frozenset[str] | None = None,
    *,
    aggregator_domains: frozenset[str] = AGGREGATOR_DOMAINS,
) -> list[RegisterRowResult]:
    """Check every row of a sources_register.csv (columns include at
    least ``source_key`` and ``url`` -- see CONTENT-4's schema in
    content/sources_register.csv's header row). Returns one result per
    data row, in file order."""
    if allowed_domains is None:
        allowed_domains = load_allowed_domains()

    results: list[RegisterRowResult] = []
    if not register_path.exists():
        return results

    with register_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=1):
            source_key = (row.get("source_key") or "").strip()
            url = (row.get("url") or "").strip()
            check = check_url(url, allowed_domains, aggregator_domains=aggregator_domains)
            results.append(
                RegisterRowResult(row_number=row_number, source_key=source_key, check=check)
            )
    return results


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    allowed = load_allowed_domains(args.allowed_domains)
    results = check_register(args.register, allowed)

    violations = [r for r in results if not r.check.ok]
    print(f"Checked {len(results)} row(s) from {args.register}")
    print(f"Allow-list: {len(allowed)} domain(s) from {args.allowed_domains}")
    if violations:
        print(f"{len(violations)} violation(s):")
        for result in violations:
            print(
                f"  row {result.row_number} (source_key={result.source_key!r}): "
                f"{result.check.reason} -- {result.check.url!r}"
            )
    else:
        print("No violations.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
