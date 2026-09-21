#!/usr/bin/env python
"""Seed clearly-labelled SYNTHETIC sample content for dev and staging (DATA-8).

Staging needs something on the screen before real verified content
exists. This inserts a handful of sources, careers, pathways and claims
that are obviously, unmistakably sample data — and it cannot make any of
it look verified, because the database will not let it:

  * every Source it creates is `source_type = 'synthetic'`;
  * `forbid_publishing_synthetic_claims()` (db/migrations/0001_init.sql)
    refuses a `published` claim on a synthetic source outright, for every
    caller including service_role, so "no seeded claim is published" is
    enforced by Postgres, not by this script remembering to behave;
  * every claim it writes stops at `in_review`, which is exactly what
    demo mode (db/migrations/0007_demo_mode.sql) reveals and nothing
    more;
  * every row's name carries a visible SAMPLE label.

**This script never weakens the 0001 trigger to make the demo work.**
That is DATA-8's own stated risk, and the answer is demo mode: a read
policy that shows sample rows, not a write path that publishes them.

Usage:
    python scripts/seed_synthetic.py                    # insert/refresh
    python scripts/seed_synthetic.py --dry-run          # show, write nothing
    python scripts/seed_synthetic.py --purge            # remove everything it seeded
    python scripts/seed_synthetic.py --enable-demo-mode # ... and turn demo mode on

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.
The service-role key is the owner's own admin credential — the same one
tests/db/conftest.py uses and that `app/core/config.py` deliberately
never reads. Never put it in `.env` next to the application's own
values, and never paste it into chat.

Idempotency
-----------
Every row's primary key is a UUIDv5 derived from a fixed namespace and a
stable key ("synthetic:career:marine-biologist"), so re-running writes
the SAME ids rather than a second copy. Two runs give identical row
counts, and `--purge` knows exactly which rows are its own without
pattern-matching on names.

THE PRODUCTION GUARD
--------------------
Two independent checks, both of which must pass, because either one
alone has a hole (DATA-8: "Refuses when environment is production OR the
URL matches the production project ref"):

  1. **Environment.** `APP_ENV=production` refuses. On its own this
     trusts a variable that is easy to forget to set — a shell with a
     production URL and no APP_ENV at all would sail through.
  2. **Target.** The Supabase project ref in `SUPABASE_URL` is checked
     against `BCION_PRODUCTION_PROJECT_REF`, and any non-loopback target
     is refused unless its exact origin is in `BCION_SEED_TARGET`. On
     its own this trusts an allowlist somebody has to maintain.

Together they mean seeding production requires both mislabelling the
environment and allow-listing the production origin by hand. The
fail-closed direction is "refuse": an unrecognised, non-loopback target
is refused rather than seeded.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

# ---------------------------------------------------------------------
# Identity of the seeded rows
# ---------------------------------------------------------------------

# A fixed namespace, so UUIDv5 ids are stable across runs and machines.
# Any constant UUID works; this one is arbitrary and public.
SEED_NAMESPACE = uuid.UUID("b1c10e11-0000-5000-8000-000000000001")

# Carried in every seeded name. Visible in every UI that renders a name,
# and the thing a human scanning a staging database looks for.
SAMPLE_LABEL = "[SAMPLE DATA - NOT VERIFIED]"

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

TODAY = date.today()
REVIEW_DUE = TODAY + timedelta(days=180)


def seed_id(key: str) -> str:
    """The stable id for a seeded row. Same key -> same id, always."""
    return str(uuid.uuid5(SEED_NAMESPACE, f"bcion-lite-synthetic:{key}"))


# ---------------------------------------------------------------------
# The content itself — deliberately small and obviously fictional
# ---------------------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {
        "id": seed_id("source:sample-authority"),
        "authority_name": f"Sample Authority {SAMPLE_LABEL}",
        "official_url": "https://example.invalid/sample-authority",
        "source_type": "synthetic",
        "jurisdiction": "IN",
    },
    {
        "id": seed_id("source:sample-institution"),
        "authority_name": f"Sample Institution Prospectus {SAMPLE_LABEL}",
        "official_url": "https://example.invalid/sample-institution",
        "source_type": "synthetic",
        "jurisdiction": "IN-MH",
    },
]

CAREERS: list[dict[str, Any]] = [
    {
        "id": seed_id("career:marine-biologist"),
        "name": f"Marine Biologist {SAMPLE_LABEL}",
        "nco_anchor": None,
    },
    {
        "id": seed_id("career:data-analyst"),
        "name": f"Data Analyst {SAMPLE_LABEL}",
        "nco_anchor": None,
    },
    {
        "id": seed_id("career:civil-engineer"),
        "name": f"Civil Engineer {SAMPLE_LABEL}",
        "nco_anchor": None,
    },
]

PATHWAYS: list[dict[str, Any]] = [
    {
        "id": seed_id("pathway:marine-bsc"),
        "career_id": seed_id("career:marine-biologist"),
        "name": f"BSc Zoology then MSc Marine Biology {SAMPLE_LABEL}",
        "description": "Sample pathway for demonstration only. Not a verified route.",
        "jurisdiction": "IN",
    },
    {
        "id": seed_id("pathway:data-bsc"),
        "career_id": seed_id("career:data-analyst"),
        "name": f"BSc Statistics then analytics role {SAMPLE_LABEL}",
        "description": "Sample pathway for demonstration only. Not a verified route.",
        "jurisdiction": "IN",
    },
    {
        "id": seed_id("pathway:data-diploma"),
        "career_id": seed_id("career:data-analyst"),
        "name": f"Diploma then lateral entry {SAMPLE_LABEL}",
        "description": "Sample pathway for demonstration only. Not a verified route.",
        "jurisdiction": "IN-MH",
    },
    {
        "id": seed_id("pathway:civil-btech"),
        "career_id": seed_id("career:civil-engineer"),
        "name": f"BTech Civil Engineering {SAMPLE_LABEL}",
        "description": "Sample pathway for demonstration only. Not a verified route.",
        "jurisdiction": "IN",
    },
]


def _claim(
    key: str,
    pathway_key: str,
    field: str,
    value: Any,
    source_key: str,
    *,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "id": seed_id(f"claim:{key}"),
        "entity_type": "Pathway",
        "entity_id": seed_id(pathway_key),
        "field": field,
        "value": value,
        "source_id": seed_id(source_key),
        "verification_date": TODAY.isoformat(),
        # NEVER a real person's name or identifier on a synthetic row.
        "verifier": f"seed-script {SAMPLE_LABEL}",
        # in_review, never published, never draft: this is precisely what
        # db/migrations/0007_demo_mode.sql's policy reveals, and nothing
        # wider. `status: "published"` here would be rejected by the 0001
        # trigger anyway — see this module's docstring.
        "status": "in_review",
        "review_due_date": REVIEW_DUE.isoformat(),
        "jurisdiction": "IN",
        "academic_cycle": "2026-27",
        "currency": currency,
        "extracted_by": "human",
    }


CLAIMS: list[dict[str, Any]] = [
    _claim(
        "marine-entry", "pathway:marine-bsc", "entry_requirements",
        "Sample requirement text - not verified.", "source:sample-authority",
    ),
    _claim(
        "marine-time", "pathway:marine-bsc", "time_range",
        "5 years (sample)", "source:sample-authority",
    ),
    _claim(
        "marine-charges", "pathway:marine-bsc", "verified_charges",
        60000, "source:sample-institution", currency="INR",
    ),
    _claim(
        "data-entry", "pathway:data-bsc", "entry_requirements",
        "Sample requirement text - not verified.", "source:sample-authority",
    ),
    _claim(
        "data-charges", "pathway:data-bsc", "verified_charges",
        45000, "source:sample-institution", currency="INR",
    ),
    _claim(
        "data-location", "pathway:data-bsc", "location",
        "Sample city (sample)", "source:sample-authority",
    ),
    _claim(
        "diploma-charges", "pathway:data-diploma", "verified_charges",
        30000, "source:sample-institution", currency="INR",
    ),
    _claim(
        "civil-charges", "pathway:civil-btech", "verified_charges",
        90000, "source:sample-institution", currency="INR",
    ),
    _claim(
        "civil-stages", "pathway:civil-btech", "main_stages",
        "Sample stage list - not verified.", "source:sample-authority",
    ),
]


# ---------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------


class SeedRefused(Exception):
    """This script must not run against this target. Never caught and
    downgraded to a warning anywhere in this file."""


def project_ref(url: str) -> str | None:
    """The Supabase project ref in a URL, or None if there isn't one.

    A hosted Supabase URL is `https://<ref>.supabase.co`, so the ref is
    the first label of the hostname. A loopback URL has no ref, which is
    the None case — not an error, just "this is a local stack".
    """
    host = (urlsplit(url).hostname or "").strip().lower()
    if not host or host in _LOOPBACK_HOSTS:
        return None
    first, _, rest = host.partition(".")
    return first if rest else None


def _allowlisted_origins() -> set[str]:
    """`BCION_SEED_TARGET`: comma-separated EXACT origins.

    Exact matching, never a substring or suffix test — the same rule
    tests/db/conftest.py's `_allowlisted_targets` documents, and for the
    same reason: an "endswith" allowlist is how `evil-supabase.co` gets
    accepted as `supabase.co`.
    """
    raw = os.environ.get("BCION_SEED_TARGET", "")
    return {entry.strip().rstrip("/") for entry in raw.split(",") if entry.strip()}


def guard_problem(
    *,
    app_env: str,
    url: str,
    production_ref: str | None,
    allowlisted: set[str] | None = None,
) -> str | None:
    """Why this run must not proceed, or None if it may.

    Pure and side-effect free so tests/unit/test_seed_guard.py can
    exercise every branch without a database, a network or an
    environment.
    """
    allowlisted = allowlisted if allowlisted is not None else set()

    # --- Check 1: the declared environment.
    if app_env.strip().lower() == "production":
        return (
            "REFUSING TO SEED: APP_ENV=production. This script writes "
            "clearly-labelled SAMPLE rows, which must never exist on the "
            "production database (CLAUDE.md: synthetic fixtures are never "
            "published as verified facts)."
        )

    if not url.strip():
        return (
            "REFUSING TO SEED: SUPABASE_URL is not set. Refusing rather than "
            "guessing a target."
        )

    # --- Check 2: the actual target, independently of what the
    # environment variable claims.
    ref = project_ref(url)
    if ref is None:
        return None  # loopback: always fine

    if production_ref and ref == production_ref.strip().lower():
        return (
            f"REFUSING TO SEED: SUPABASE_URL points at project ref {ref!r}, "
            "which matches BCION_PRODUCTION_PROJECT_REF. That is the "
            "production database."
        )

    if url.strip().rstrip("/") not in allowlisted:
        return (
            f"REFUSING TO SEED: {url!r} is not a local stack and is not in "
            "BCION_SEED_TARGET. Add its exact origin there if it really is a "
            "disposable dev/staging project the owner has approved — an "
            "unrecognised remote target is refused, never seeded on the "
            "assumption that it is probably fine."
        )

    return None


# ---------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------

SEEDED_CLAIM_IDS = [row["id"] for row in CLAIMS]
SEEDED_PATHWAY_IDS = [row["id"] for row in PATHWAYS]
SEEDED_CAREER_IDS = [row["id"] for row in CAREERS]
SEEDED_SOURCE_IDS = [row["id"] for row in SOURCES]


def _parse_args(argv: list[str]) -> dict[str, bool]:
    known = {"--dry-run", "--purge", "--enable-demo-mode"}
    flags = dict.fromkeys(known, False)
    for arg in argv:
        if arg not in known:
            raise SeedRefused(
                f"unrecognised argument {arg!r}. Known flags: "
                f"{', '.join(sorted(known))}."
            )
        flags[arg] = True
    return flags


def seed(client: Any) -> dict[str, int]:
    """Upsert every seeded row. Returns per-table counts.

    Insert order matters: `pathways.career_id` references `careers`, and
    `claims.source_id` references `sources` (db/migrations/0001_init.sql).

    `upsert` rather than insert is what makes a second run a no-op
    instead of a duplicate-key error — the ids are deterministic, so the
    second run rewrites the same rows with the same values.
    """
    client.table("sources").upsert(SOURCES).execute()
    client.table("careers").upsert(CAREERS).execute()
    client.table("pathways").upsert(PATHWAYS).execute()
    client.table("claims").upsert(CLAIMS).execute()
    return {
        "sources": len(SOURCES),
        "careers": len(CAREERS),
        "pathways": len(PATHWAYS),
        "claims": len(CLAIMS),
    }


def purge(client: Any) -> None:
    """Remove exactly what this script seeded, by id — never by a name
    pattern, which could match something a person typed by hand.

    Reverse of the insert order, for the same foreign keys.
    """
    client.table("claims").delete().in_("id", SEEDED_CLAIM_IDS).execute()
    client.table("pathways").delete().in_("id", SEEDED_PATHWAY_IDS).execute()
    client.table("careers").delete().in_("id", SEEDED_CAREER_IDS).execute()
    client.table("sources").delete().in_("id", SEEDED_SOURCE_IDS).execute()


def set_demo_mode(client: Any, *, on: bool) -> None:
    """Flip `app_settings.demo_mode` (db/migrations/0007_demo_mode.sql).

    Only ever called when `--enable-demo-mode` was passed: seeding and
    revealing are separate decisions, and seeding must never silently
    change what a visitor can see.
    """
    client.table("app_settings").update({"demo_mode": on}).eq("id", True).execute()


def main(argv: list[str] | None = None) -> int:
    try:
        flags = _parse_args(sys.argv[1:] if argv is None else argv)
    except SeedRefused as exc:
        print(exc, file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL", "")
    problem = guard_problem(
        app_env=os.environ.get("APP_ENV", ""),
        url=url,
        production_ref=os.environ.get("BCION_PRODUCTION_PROJECT_REF"),
        allowlisted=_allowlisted_origins(),
    )
    if problem is not None:
        print(problem, file=sys.stderr)
        return 1

    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        print(
            "SUPABASE_SERVICE_ROLE_KEY is not set. This script needs the "
            "owner's admin credential (the same one tests/db/conftest.py "
            "uses); the application itself never reads it.",
            file=sys.stderr,
        )
        return 1

    if flags["--dry-run"]:
        print(f"--dry-run against {url}")
        print(
            f"would write: {len(SOURCES)} sources, {len(CAREERS)} careers, "
            f"{len(PATHWAYS)} pathways, {len(CLAIMS)} claims "
            f"(all synthetic, all in_review, all labelled {SAMPLE_LABEL!r})"
        )
        if flags["--purge"]:
            print("would purge those same ids instead")
        if flags["--enable-demo-mode"]:
            print("would set app_settings.demo_mode = true")
        return 0

    from supabase import create_client

    client = create_client(url, key)

    if flags["--purge"]:
        purge(client)
        print(f"purged every seeded row from {url}")
        if flags["--enable-demo-mode"]:
            print(
                "note: --enable-demo-mode ignored alongside --purge; "
                "leaving demo mode untouched.",
                file=sys.stderr,
            )
        return 0

    counts = seed(client)
    print(
        f"seeded {counts['sources']} sources, {counts['careers']} careers, "
        f"{counts['pathways']} pathways, {counts['claims']} claims into {url}"
    )
    print(f"every row is synthetic-sourced, in_review, and labelled {SAMPLE_LABEL!r}")

    if flags["--enable-demo-mode"]:
        set_demo_mode(client, on=True)
        print("app_settings.demo_mode = true — sample rows are now visible to visitors")
    else:
        print(
            "demo mode NOT changed. Sample rows stay invisible to visitors until "
            "someone passes --enable-demo-mode (or sets the flag directly)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
