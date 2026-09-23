#!/usr/bin/env python
"""Sweep test/fixture residue out of a Supabase project (QA-12).

**DRY RUN IS THE DEFAULT.** Running this script with no arguments only
LISTS what it found — it never deletes anything. Deletion only ever
happens when `--apply` is passed explicitly:

    python scripts/sweep_test_residue.py            # list only, writes nothing
    python scripts/sweep_test_residue.py --apply     # actually delete

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment,
same convention as scripts/seed_synthetic.py.

WHY THIS SCRIPT HAS NO "REFUSE PRODUCTION" GUARD
-------------------------------------------------
scripts/seed_synthetic.py must NEVER be pointed at the real project — it
refuses production on sight. This script is the opposite case: its whole
job is eventually pointing at the real, live project and removing the
test/fixture rows that accumulated there (CI's own `tests/db` job runs
against real repo-secret credentials — see docs/TESTING.md — so genuine
residue is an expected, disclosed possibility, not a hypothetical). There
is deliberately no environment/project-ref guard here: whatever
SUPABASE_URL points at is exactly what `--apply` will modify, on purpose.

**Because of that, `--apply` is an OWNER-ONLY action.** Nobody working on
this codebase — dev agent or otherwise — may run `--apply` against any
real or shared project, under any circumstance, "just to test it"
included. The only place `--apply`'s actual deletion behaviour may be
exercised is a throwaway local test stack, with rows seeded (and that
would be deleted anyway) for exactly that purpose. See CLAUDE.md and the
QA-12 task card.

WHAT COUNTS AS "RESIDUE" — AN EXPLICIT, ANCHORED MARKER SET
-------------------------------------------------------------
This script does not guess. It matches only the following, exactly as
named by the QA-12 task card, and nothing looser:

  1. The literal phrases 'E2E', 'RLS test', 'SYNTHETIC', 'TEST FIXTURE'
     — checked against `sources.authority_name`, `careers.name`,
     `pathways.name`/`description`, and `claims.verifier`/`value`. These
     are exactly the conventions this repo's own test suite already uses
     (`tests/db/conftest.py`'s `run_name`, e.g. "E2E smoke test career",
     "RLS test career (SYNTHETIC)"; `tests/fixtures/synthetic_data.py`'s
     "TEST FIXTURE — not a real authority").
  2. The verifier names 'e2e-smoke-test-fixture' and 'test-fixture' —
     checked against `claims.verifier` specifically (the literal values
     `tests/db/conftest.py`'s `run_name("test-fixture")` /
     `run_name("e2e-smoke-test-fixture")` produce).
  3. The domain `example.invalid` — checked against `sources.official_url`
     and every Supabase Auth user's email (this is `tests/db/conftest.py`'s
     `run_email`'s own default domain, and RFC 2606 guarantees nothing
     real is ever reachable there).
  4. Email addresses whose local part starts with `bcion-test-` or
     `bcion-e2e-` AND whose domain is `example.com` EXACTLY (not
     `example.invalid`, not any other domain) — checked against every
     Supabase Auth user's email.

EVERY MATCH IS WORD-BOUNDARY ANCHORED AND CASE-SENSITIVE, on purpose.
`docs/DATA.md`/CLAUDE.md's own worry, in the QA-12 card's own words: "a
real career or pathway name that merely CONTAINS the substring 'test' as
part of an unrelated real word must never match." Two concrete, real
shapes that trap a naive `substring in text` check, both defended against
here (and both covered by tests/unit/test_sweep_test_residue.py):

  * A career/pathway/source name like "LATEST FIXTURE ROOM" contains the
    literal substring "TEST FIXTURE" purely because "LATEST" ends in
    "TEST" — a bare substring search would flag it. A word-boundary
    match does not: there is no boundary between the "A" of "LA" and the
    "T" of "TEST" inside "LATEST".
  * A hostname like "notexample.invalid" contains the literal substring
    "example.invalid" purely by coincidence — matched here by comparing
    the actual parsed hostname (`==` or a dot-anchored suffix), never a
    raw substring search, so "notexample.invalid" is correctly rejected
    while "sub.example.invalid" is correctly accepted.

This is a narrow, explicit list, not a general "contains the word test"
heuristic — anything not named above (a plan's free-text `notes`, a
guardian email using some other fixture convention, ...) is intentionally
out of scope for this script; expanding the marker set is a decision for
whoever owns this card next, not something to guess at here.

ORDERING (foreign keys)
------------------------
Deletion happens in dependency order, same reasoning as
`scripts/seed_synthetic.py`'s own `purge()` and `tests/db/conftest.py`'s
own `_sweep_leftover_rows`: claims first (both claims that match on their
own fields, and claims that merely reference a matched source/pathway/
career/user — `claims.source_id`/`entity_id` have no `on delete cascade`,
and `entity_id` has no foreign key at all, so an orphaned claim pointing
at a deleted pathway is exactly the kind of residue a sweep should not
leave behind), then pathways, then careers, then sources, then Auth
users last (a user's `claims.created_by`/`reviewed_by` row has no
`on delete cascade` either — see `db/migrations/0001_init.sql` — so it
must already be gone by the time the user itself is deleted, or Postgres
refuses the delete outright).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

# ---------------------------------------------------------------------
# The marker set (QA-12's own words, anchored — see module docstring)
# ---------------------------------------------------------------------

GENERAL_MARKERS: tuple[str, ...] = ("E2E", "RLS test", "SYNTHETIC", "TEST FIXTURE")

# Checked ONLY against claims.verifier, on top of GENERAL_MARKERS.
VERIFIER_MARKERS: tuple[str, ...] = ("e2e-smoke-test-fixture", "test-fixture")

_EXAMPLE_INVALID = "example.invalid"
_EXAMPLE_COM = "example.com"
EMAIL_PREFIXES: tuple[str, ...] = ("bcion-test-", "bcion-e2e-")


def _boundary_pattern(literal: str) -> re.Pattern[str]:
    """A case-sensitive, word-boundary-anchored pattern for one literal
    marker phrase. `\\b` treats letters/digits/underscore as "word"
    characters and everything else (spaces, hyphens, punctuation) as
    non-word — so a marker is only matched when it starts and ends at a
    real word edge, never merely as a run of characters that happens to
    appear inside something longer (see module docstring: "LATEST
    FIXTURE" vs "TEST FIXTURE")."""
    return re.compile(r"\b" + re.escape(literal) + r"\b")


_GENERAL_PATTERNS: dict[str, re.Pattern[str]] = {m: _boundary_pattern(m) for m in GENERAL_MARKERS}
_VERIFIER_PATTERNS: dict[str, re.Pattern[str]] = {m: _boundary_pattern(m) for m in VERIFIER_MARKERS}


def marker_in_text(
    text: Any, patterns: dict[str, re.Pattern[str]] = _GENERAL_PATTERNS
) -> str | None:
    """The first marker (by iteration order) whose word-boundary pattern
    matches `text`, or None. `text` may be None, a number, a list, a
    dict, ... (claims.value is JSONB) — anything that isn't a non-empty
    string simply cannot match."""
    if not isinstance(text, str) or not text:
        return None
    for label, pattern in patterns.items():
        if pattern.search(text):
            return f"marker:{label}"
    return None


def verifier_marker(text: Any) -> str | None:
    """`claims.verifier` is checked against BOTH the general markers
    (a verifier could in principle carry "TEST FIXTURE" too) and the two
    verifier-specific literal names the QA-12 card names."""
    return marker_in_text(text, _GENERAL_PATTERNS) or marker_in_text(text, _VERIFIER_PATTERNS)


def value_as_text(value: Any) -> str:
    """`claims.value` is JSONB — a plain string most of the time, but a
    number/list/dict/bool/null is legal too. Non-string values are
    JSON-dumped so a marker embedded inside a structured value is still
    found; there is nothing to find in `None`."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------
# Domain / email matching — parsed, never a raw substring search
# ---------------------------------------------------------------------


def _hostname(value: str) -> str | None:
    """The lowercased hostname of a URL, or of a bare `user@host` email.
    Returns None for anything that doesn't parse to a hostname at all."""
    value = value.strip()
    if not value:
        return None
    if "@" in value and "://" not in value:
        host = value.rsplit("@", 1)[-1].strip().lower()
        return host or None
    host = (urlsplit(value).hostname or "").strip().lower()
    return host or None


def _is_example_invalid(host: str | None) -> bool:
    """True only for the exact domain or a real subdomain of it — never
    for a hostname that merely ends with the same letters (module
    docstring: "notexample.invalid" must not match)."""
    if not host:
        return False
    return host == _EXAMPLE_INVALID or host.endswith("." + _EXAMPLE_INVALID)


def url_marker(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    if _is_example_invalid(_hostname(url)):
        return f"domain:{_EXAMPLE_INVALID}"
    return None


def email_marker(email: Any) -> str | None:
    """Every email-specific rule the QA-12 card names, in order, plus the
    general literal markers as a last resort (harmless: email syntax
    essentially never contains a space, so `RLS test` can never appear in
    practice — included only for completeness/consistency with every
    other text field this script scans)."""
    if not isinstance(email, str) or not email or "@" not in email:
        return None
    local, _, domain_raw = email.rpartition("@")
    domain = domain_raw.strip().lower()
    if _is_example_invalid(domain):
        return f"domain:{_EXAMPLE_INVALID}"
    if domain == _EXAMPLE_COM:
        local_lower = local.strip().lower()
        for prefix in EMAIL_PREFIXES:
            if local_lower.startswith(prefix):
                return f"email-prefix:{prefix}@{_EXAMPLE_COM}"
    return marker_in_text(email)


# ---------------------------------------------------------------------
# Matching rows (pure — no I/O, fully unit-testable)
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    table: str
    row_id: str
    reason: str
    preview: str


def scan_sources(rows: list[dict[str, Any]]) -> list[Match]:
    out = []
    for row in rows:
        reason = marker_in_text(row.get("authority_name")) or url_marker(row.get("official_url"))
        if reason:
            out.append(Match("sources", str(row["id"]), reason, str(row.get("authority_name", ""))))
    return out


def scan_careers(rows: list[dict[str, Any]]) -> list[Match]:
    out = []
    for row in rows:
        reason = marker_in_text(row.get("name"))
        if reason:
            out.append(Match("careers", str(row["id"]), reason, str(row.get("name", ""))))
    return out


def scan_pathways(rows: list[dict[str, Any]]) -> list[Match]:
    out = []
    for row in rows:
        reason = marker_in_text(row.get("name")) or marker_in_text(row.get("description"))
        if reason:
            out.append(Match("pathways", str(row["id"]), reason, str(row.get("name", ""))))
    return out


def scan_claims(rows: list[dict[str, Any]]) -> list[Match]:
    out = []
    for row in rows:
        value_text = value_as_text(row.get("value"))
        reason = verifier_marker(row.get("verifier")) or marker_in_text(value_text)
        if reason:
            preview = f"verifier={row.get('verifier')!r} value={value_text!r}"
            out.append(Match("claims", str(row["id"]), reason, preview))
    return out


def scan_users(rows: list[dict[str, Any]]) -> list[Match]:
    out = []
    for row in rows:
        reason = email_marker(row.get("email"))
        if reason:
            out.append(Match("auth.users", str(row["id"]), reason, str(row.get("email", ""))))
    return out


# ---------------------------------------------------------------------
# The deletion plan — still pure, given already-fetched rows
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class DeletionPlan:
    claims: set[str] = field(default_factory=set)
    pathways: set[str] = field(default_factory=set)
    careers: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    users: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not (self.claims or self.pathways or self.careers or self.sources or self.users)

    def total(self) -> int:
        return (
            len(self.claims)
            + len(self.pathways)
            + len(self.careers)
            + len(self.sources)
            + len(self.users)
        )


def compute_deletion_plan(
    *,
    sources: list[dict[str, Any]],
    careers: list[dict[str, Any]],
    pathways: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> DeletionPlan:
    matched_sources = {m.row_id for m in scan_sources(sources)}
    matched_careers = {m.row_id for m in scan_careers(careers)}
    matched_pathways = {m.row_id for m in scan_pathways(pathways)}
    matched_users = {m.row_id for m in scan_users(users)}
    matched_claims = {m.row_id for m in scan_claims(claims)}

    # A claim that doesn't itself carry a marker, but references a
    # matched source/pathway/career/user, is fixture residue too — and
    # must be swept before its parent to avoid an FK violation (module
    # docstring, "ORDERING").
    for claim in claims:
        claim_id = str(claim["id"])
        if claim_id in matched_claims:
            continue
        source_id = claim.get("source_id")
        entity_id = claim.get("entity_id")
        created_by = claim.get("created_by")
        reviewed_by = claim.get("reviewed_by")
        if (
            (source_id is not None and str(source_id) in matched_sources)
            or (entity_id is not None and str(entity_id) in matched_pathways)
            or (entity_id is not None and str(entity_id) in matched_careers)
            or (created_by is not None and str(created_by) in matched_users)
            or (reviewed_by is not None and str(reviewed_by) in matched_users)
        ):
            matched_claims.add(claim_id)

    return DeletionPlan(
        claims=matched_claims,
        pathways=matched_pathways,
        careers=matched_careers,
        sources=matched_sources,
        users=matched_users,
    )


# ---------------------------------------------------------------------
# I/O — fetching and applying (never exercised by the unit tests above)
# ---------------------------------------------------------------------


def fetch_table(client: Any, table: str, columns: str) -> list[dict[str, Any]]:
    return list(client.table(table).select(columns).execute().data or [])


def fetch_users(client: Any) -> list[dict[str, Any]]:
    """Every Supabase Auth user, not just GoTrue's default first page —
    same reasoning and shape as `tests/db/conftest.py`'s own
    `_paginated_users`."""
    out: list[dict[str, Any]] = []
    page = 1
    per_page = 200
    while True:
        batch = client.auth.admin.list_users(page=page, per_page=per_page)
        if not batch:
            return out
        out.extend({"id": str(u.id), "email": u.email or ""} for u in batch)
        if len(batch) < per_page:
            return out
        page += 1


def fetch_all(client: Any) -> dict[str, list[dict[str, Any]]]:
    return {
        "sources": fetch_table(client, "sources", "id, authority_name, official_url"),
        "careers": fetch_table(client, "careers", "id, name"),
        "pathways": fetch_table(client, "pathways", "id, name, description"),
        "claims": fetch_table(
            client, "claims", "id, verifier, value, source_id, entity_id, created_by, reviewed_by"
        ),
        "users": fetch_users(client),
    }


def apply_plan(client: Any, plan: DeletionPlan) -> dict[str, int]:
    """Deletes exactly the plan, in FK-safe order. Never called unless
    `--apply` was passed (see `main`)."""
    counts = {"claims": 0, "pathways": 0, "careers": 0, "sources": 0, "users": 0}
    if plan.claims:
        client.table("claims").delete().in_("id", sorted(plan.claims)).execute()
        counts["claims"] = len(plan.claims)
    if plan.pathways:
        client.table("pathways").delete().in_("id", sorted(plan.pathways)).execute()
        counts["pathways"] = len(plan.pathways)
    if plan.careers:
        client.table("careers").delete().in_("id", sorted(plan.careers)).execute()
        counts["careers"] = len(plan.careers)
    if plan.sources:
        client.table("sources").delete().in_("id", sorted(plan.sources)).execute()
        counts["sources"] = len(plan.sources)
    for user_id in sorted(plan.users):
        client.auth.admin.delete_user(user_id)
    counts["users"] = len(plan.users)
    return counts


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------


def render_report(
    *,
    url: str,
    apply_mode: bool,
    matches_by_table: dict[str, list[Match]],
) -> str:
    lines: list[str] = []
    if apply_mode:
        banner = "APPLY MODE — the rows/users below WILL BE DELETED"
    else:
        banner = "DRY RUN — nothing will be deleted (pass --apply to actually delete)"
    lines.append(banner)
    lines.append(f"target: {url}")
    lines.append("")

    total = 0
    for table, matches in matches_by_table.items():
        lines.append(f"{table}: {len(matches)} match(es)")
        for m in matches:
            lines.append(f"  - {m.row_id}  reason={m.reason}  {m.preview!r}")
        total += len(matches)

    lines.append("")
    lines.append(f"TOTAL: {total} row(s)/user(s) matched.")
    return "\n".join(lines)


def _matches_by_table(
    *,
    sources: list[dict[str, Any]],
    careers: list[dict[str, Any]],
    pathways: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> dict[str, list[Match]]:
    return {
        "sources": scan_sources(sources),
        "careers": scan_careers(careers),
        "pathways": scan_pathways(pathways),
        "claims": scan_claims(claims),
        "auth.users": scan_users(users),
    }


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


class SweepRefused(Exception):
    """This invocation must not run. Never caught and downgraded to a
    warning anywhere in this file — same convention as
    `scripts/seed_synthetic.py`'s `SeedRefused`."""


def _parse_args(argv: list[str]) -> bool:
    """Returns whether `--apply` was passed. Any other argument is
    refused outright rather than silently ignored — the same reasoning
    `scripts/seed_synthetic.py`'s `_parse_args` gives: a typo like
    `--aply` must not silently fall back to the (harmless) dry-run
    default when the caller's intent was actually to delete."""
    known = {"--apply"}
    apply_mode = False
    for arg in argv:
        if arg not in known:
            raise SweepRefused(f"unrecognised argument {arg!r}. Known flags: --apply.")
        apply_mode = True
    return apply_mode


def main(argv: list[str] | None = None) -> int:
    try:
        apply_mode = _parse_args(sys.argv[1:] if argv is None else argv)
    except SweepRefused as exc:
        print(exc, file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url:
        print("SUPABASE_URL is not set. Refusing rather than guessing a target.", file=sys.stderr)
        return 1
    if not key:
        print(
            "SUPABASE_SERVICE_ROLE_KEY is not set. This script needs the "
            "owner's admin credential (the same one tests/db/conftest.py and "
            "scripts/seed_synthetic.py use); the application itself never "
            "reads it.",
            file=sys.stderr,
        )
        return 1

    from supabase import create_client

    client = create_client(url, key)
    fetched = fetch_all(client)
    plan = compute_deletion_plan(
        sources=fetched["sources"],
        careers=fetched["careers"],
        pathways=fetched["pathways"],
        claims=fetched["claims"],
        users=fetched["users"],
    )
    matches_by_table = _matches_by_table(
        sources=fetched["sources"],
        careers=fetched["careers"],
        pathways=fetched["pathways"],
        claims=fetched["claims"],
        users=fetched["users"],
    )
    print(render_report(url=url, apply_mode=apply_mode, matches_by_table=matches_by_table))

    if not apply_mode:
        return 0

    if plan.is_empty():
        print("\nnothing matched — apply is a no-op.")
        return 0

    print(
        "\n--apply was passed: deleting every row/user listed above now. "
        "This must only ever be run by the project owner, against the "
        "project they intend to clean — see this file's own module "
        "docstring."
    )
    counts = apply_plan(client, plan)
    print(f"done: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
