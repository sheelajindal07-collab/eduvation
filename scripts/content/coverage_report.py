"""CONTENT-8 -- coverage, freshness and publication-integrity report.

A READ-ONLY, owner/reviewer-run diagnostic over the LIVE `claims` table
(never a CSV -- that is CONTENT-4/CONTENT-6's job, `scripts/content/
check_sources.py` and `scripts/content/validation.py`, both reused here
rather than re-implemented, per this codebase's own "one place a check
lives" convention). Reports:

  * counts per entity type and status;
  * "not available" field counts per published pathway;
  * claims with `review_due_date` within 14 and 30 days;
  * claims stale by their own tier;
  * pending-review age;
  * claims processed per reviewer-hour (reported as "not available" --
    see `REVIEWER_HOUR_THROUGHPUT_NOTE` -- there is no reviewer
    time-tracking data anywhere in this schema to compute a real number
    from, and CLAUDE.md's "AI never invents facts" applies just as much
    to this script's own arithmetic as it does to a model).

Plus an INTEGRITY section that FAILS this script's own exit code (never
just a warning) the moment it finds any of:

  1. a published claim backed by a synthetic source;
  2. a published claim backed by a non-http(s) or non-allow-listed
     source URL (delegated to `scripts.content.check_sources.check_url`,
     never re-implemented here);
  3. a published claim with no named verifier;
  4. a claim where `created_by` equals `reviewed_by` (maker = checker --
     the exact violation the maker-checker system exists to prevent);
  5. a claim with an incomplete eligibility set (delegated to
     `scripts.content.validation.check_incomplete_eligibility_set`, see
     "THE 'required_fields' CONVENTION ON A LIVE CLAIM" below).

## WHY A REVIEWER SESSION, NOT SERVICE ROLE
`draft`/`in_review` claims are reviewer-only-readable
(`db/migrations/0001_init.sql`'s `claims_select_published` policy:
`status = 'published' or is_reviewer()`) -- this report needs to see
those too (the coverage/pending-review-age sections are meaningless
without them), so it must sign in as a genuine reviewer account, exactly
the way a human reviewer would. This deliberately reuses the ONE
existing auth path rather than inventing a second one: `app.api.auth.
authenticate()` (the single function both `POST /auth/sign-in` and
`app/web/reviewer/auth.py`'s `POST /reviewer/sign-in` already call) to
turn an email/password into a real Supabase session, then `app.db.
get_user_scoped_client()` (the same factory `app.api.deps.require_auth`
and `app/web/reviewer/auth.py`'s `get_reviewer_session` both use) to get
an RLS-scoped client from that session's access token. This script never
reads `SUPABASE_SERVICE_ROLE_KEY` and never could see more than a real
reviewer's own browser session sees -- unlike `scripts/ai_spend_report.py`
(which needs service role for a different, documented reason: reading
`ai_usage_caps`/other identities' raw rows, which no reviewer login can
ever see at all), this report's whole point is "what does the reviewer
console's own worldview look like", so a reviewer login is not merely
sufficient here, it is the more correct credential.

Needs `BCION_REVIEWER_EMAIL` / `BCION_REVIEWER_PASSWORD` in the
environment (never a CLI flag -- a password must never appear in a
shell history or a process list; CLAUDE.md "no secrets in repo memory").
`SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` come from `app.core.config.
Settings`, exactly as the running application reads them.

## READ-ONLY, GENUINELY -- NOT JUST ON THE HAPPY PATH
Every database call in this module is a `.select(...).execute()`. There
is no `.insert(`, `.update(`, `.delete(`, `.upsert(` or `.rpc(` call
anywhere in this file, including inside an `except:` branch --
`tests/db/test_coverage_report.py` proves this by real AST inspection
(not a substring/regex scan, which a comment could fool either way), and
separately proves that scanner is not vacuous (a revert-to-prove check).
A caller who wants to fix a violation this script finds must do it
through the ordinary reviewer console / claims API -- this script only
ever reports.

## THE "required_fields" CONVENTION ON A LIVE CLAIM
`scripts/content/validation.py`'s own docstring already says its CSV
`required_fields` column is "optional and CSV-internal to this
validator... not yet part of any frozen contract file". The live
`claims` table has no such column at all -- there is nowhere in the
schema today for a pathway to declare which of its own fields must all
be published before its eligibility set counts as complete. Rather than
inventing a NEW mechanism, this script extends the existing CSV-internal
idea by the smallest possible step: an ordinary claim row with
`field = "required_fields"` and a comma-separated `value` (e.g.
`"eligibility.minimum_age,eligibility.category"`) attached to the same
`entity_id` -- read by `_build_eligibility_claim_rows` below and handed,
unchanged in shape, to `scripts.content.validation.check_incomplete_
eligibility_set` via a normal `ClaimRow`. An entity that never declares
this way is simply not checked (matches CONTENT-6's own "this entity
does not declare a required set at all" vacuous-pass behaviour). This is
this card's own reasonable reading of an otherwise-unanswered question,
same as RULES-8's `rule_key` and RULES-9's `stage:<order>:...` claim-field
conventions before it (see `docs/DECISIONS.md`'s 2026-09-22 entries for
both) -- flagged for the lead rather than silently treated as settled.

Usage (run with `-m`, from the repo root, so `scripts` resolves as a
package -- same reason `scripts/ai_spend_report.py` and
`scripts/run_ai_eval.py` both say this)::

    python -m scripts.content.coverage_report --format markdown
    python -m scripts.content.coverage_report --format csv --out report.csv
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException
from supabase import Client

from app.api.auth import authenticate
from app.data.models import ClaimStatus, SourceType
from app.db import get_anon_client, get_user_scoped_client
from scripts.content.check_sources import (
    AGGREGATOR_DOMAINS,
    DEFAULT_ALLOWED_DOMAINS_PATH,
    check_url,
    load_allowed_domains,
)
from scripts.content.validation import ClaimRow, check_incomplete_eligibility_set

REPO_ROOT = Path(__file__).resolve().parents[2]

# The one entity_type this codebase actually resolves to a table today
# (`app/web/reviewer/queue.py`'s own `_ENTITY_TABLES`) -- "per published
# pathway" in this card's own wording means this string, matching every
# other route/test that seeds a pathway-shaped claim (see e.g.
# `tests/db/test_reviewer_console.py`'s `_draft_payload`).
PATHWAY_ENTITY_TYPE = "Pathway"

# The claim-field convention this script reads for eligibility-set
# completeness -- see the module docstring's "THE 'required_fields'
# CONVENTION ON A LIVE CLAIM" section.
REQUIRED_FIELDS_DECLARATION_FIELD = "required_fields"

REVIEWER_HOUR_THROUGHPUT_NOTE = (
    "not available -- this schema has no reviewer time-tracking data "
    "(no session-duration log, no per-action timestamp attributable to "
    "hours worked) to compute a real per-reviewer-hour figure from. "
    "Reporting a made-up number here would be exactly the kind of "
    "invented fact CLAUDE.md's non-negotiables forbid, applied to this "
    "script's own arithmetic rather than a model's."
)

_FRESHNESS_SCOPE_NOTE = (
    "published claims only -- a draft/in_review claim's own review_due_date "
    "is a queue-workflow concern, not yet a publication-freshness one, "
    "since it has not reached a student at all"
)


# ---------------------------------------------------------------------
# Fetched-row shapes (plain dataclasses, not the API's pydantic models --
# this script reads columns app/api/claims.py's ClaimOut does not expose,
# e.g. entity_type/entity_id/created_at/updated_at, and needs no HTTP
# validation layer of its own).
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimRecord:
    id: str
    entity_type: str
    entity_id: str
    field: str
    value: Any
    source_id: str
    verification_date: date
    verifier: str
    status: str
    review_due_date: date
    created_by: str | None
    reviewed_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SourceRecord:
    id: str
    authority_name: str
    official_url: str
    source_type: str


# ---------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class EntityStatusCount:
    entity_type: str
    status: str
    count: int


@dataclass(frozen=True)
class PathwayCoverageRow:
    """One published pathway's "not available" field gap -- fields the
    pathway has SOME claim for (any status) that have never reached
    `published`, so a student still sees "not available" for them
    today."""

    pathway_id: str
    published_field_count: int
    not_available_field_count: int
    not_available_fields: tuple[str, ...]


@dataclass(frozen=True)
class FreshnessSummary:
    due_within_14_days: int
    due_within_30_days: int
    stale_past_review_due: int
    scope_note: str


@dataclass(frozen=True)
class PendingReviewAgeRow:
    status: str
    count: int
    average_age_days: float | None
    oldest_age_days: int | None


@dataclass(frozen=True)
class IntegrityFinding:
    check: str
    claim_id: str
    entity_type: str
    entity_id: str
    detail: str


@dataclass(frozen=True)
class CoverageReport:
    generated_at: datetime
    as_of: date
    entity_status_counts: tuple[EntityStatusCount, ...]
    pathway_coverage: tuple[PathwayCoverageRow, ...]
    freshness: FreshnessSummary
    pending_review_age: tuple[PendingReviewAgeRow, ...]
    reviewer_hour_throughput: str
    integrity_findings: tuple[IntegrityFinding, ...]

    @property
    def integrity_ok(self) -> bool:
        return len(self.integrity_findings) == 0


def exit_code_for(report: CoverageReport) -> int:
    """The ONE place this script's exit-code decision lives -- `main()`
    below calls this, and so does `tests/db/test_coverage_report.py`, so
    the test can assert the real decision function directly against a
    live-fetched report without needing to re-run the whole CLI (argv
    parsing, stdout rendering) just to check one `if`."""
    return 0 if report.integrity_ok else 1


# ---------------------------------------------------------------------
# I/O layer -- the only functions in this file that touch the network.
# Every one of them is a SELECT. See module docstring "READ-ONLY,
# GENUINELY".
# ---------------------------------------------------------------------


def build_reviewer_client(*, email: str, password: str) -> Client:
    """Sign in as a real reviewer via the one existing auth path
    (`app.api.auth.authenticate`, the same call `app/web/reviewer/auth.py`'s
    sign-in route makes) and return the RLS-scoped client
    `app.db.get_user_scoped_client` builds from that session's access
    token -- see module docstring "WHY A REVIEWER SESSION, NOT SERVICE
    ROLE". Raises `fastapi.HTTPException` on a bad login, unchanged from
    `authenticate()`'s own contract -- callers decide how to present
    that (see `main()` below)."""
    anon = get_anon_client()
    try:
        session = authenticate(anon, email, password)
    finally:
        _stop_background_token_refresh(anon)
        anon.postgrest.aclose()
    assert session.access_token is not None  # Session.access_token is non-Optional
    return get_user_scoped_client(session.access_token)


def _stop_background_token_refresh(client: Client) -> None:
    """`sign_in_with_password` (inside `authenticate()` above) starts a
    background `threading.Timer` that keeps auto-refreshing the session
    token (supabase_auth's `_start_auto_refresh_token`), which keeps
    `client` reachable from a live thread indefinitely. This script
    signs in once per run and exits almost immediately afterwards, so
    that timer would otherwise outlive any real use for it -- cancelled
    the same way `tests/db/conftest.py`'s own `_release_test_client`
    already does for every other short-lived signed-in client this
    codebase creates (that file's own docstring: without this, a
    process that signs in repeatedly climbs to hundreds of live threads
    and can crash with "too many open files")."""
    auth = getattr(client, "auth", None)
    timer = getattr(auth, "_refresh_token_timer", None)
    if timer is not None:
        with contextlib.suppress(Exception):  # best-effort cleanup only
            timer.cancel()


_CLAIM_COLUMNS = (
    "id, entity_type, entity_id, field, value, source_id, verification_date, "
    "verifier, status, review_due_date, created_by, reviewed_by, created_at, "
    "updated_at"
)


def _parse_claim_row(row: dict[str, Any]) -> ClaimRecord:
    return ClaimRecord(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        field=row["field"],
        value=row.get("value"),
        source_id=row["source_id"],
        verification_date=date.fromisoformat(row["verification_date"]),
        verifier=row.get("verifier") or "",
        status=row["status"],
        review_due_date=date.fromisoformat(row["review_due_date"]),
        created_by=row.get("created_by"),
        reviewed_by=row.get("reviewed_by"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def fetch_claims(client: Client) -> list[ClaimRecord]:
    """Every claim this caller's RLS scope can see -- a genuine reviewer
    sees every status (0001_init.sql's `claims_select_published`); a
    non-reviewer would only ever see `published` rows, which would make
    every other section of this report silently look emptier than
    reality rather than fail loudly -- see `main()`'s own check that the
    signed-in account really is a reviewer before trusting this."""
    result = client.table("claims").select(_CLAIM_COLUMNS).execute()
    return [_parse_claim_row(row) for row in cast("list[dict[str, Any]]", result.data)]


def fetch_sources(client: Client) -> dict[str, SourceRecord]:
    """`sources` is world-readable (0001_init.sql `sources_select_all`),
    so this returns the same rows for any caller -- fetched here, rather
    than joined per-claim, in exactly one query (same batching shape as
    `app/web/reviewer/queue.py`'s `_resolve_queue_rows`)."""
    result = (
        client.table("sources")
        .select("id, authority_name, official_url, source_type")
        .execute()
    )
    return {
        row["id"]: SourceRecord(
            id=row["id"],
            authority_name=row["authority_name"],
            official_url=row["official_url"],
            source_type=row["source_type"],
        )
        for row in cast("list[dict[str, Any]]", result.data)
    }


# ---------------------------------------------------------------------
# Pure report-building logic -- no I/O below this line, fully testable
# against hand-built ClaimRecord/SourceRecord lists.
# ---------------------------------------------------------------------


def _stringify_value(value: Any) -> str:
    """jsonb -> str for a presence/truthiness check only (this script
    never renders a claim's own value to anyone). `None` and `""` both
    become `""` (falsy); a list/tuple joins on commas (so a
    `required_fields` declaration stored as a JSON array works exactly
    like the comma-string form the module docstring documents); anything
    else stringifies plainly."""
    if value is None or value == "":
        return ""
    if isinstance(value, list | tuple):
        return ",".join(str(item) for item in value)
    return str(value)


def _entity_status_counts(claims: Sequence[ClaimRecord]) -> tuple[EntityStatusCount, ...]:
    counts = Counter((c.entity_type, c.status) for c in claims)
    return tuple(
        EntityStatusCount(entity_type=entity_type, status=status, count=count)
        for (entity_type, status), count in sorted(counts.items())
    )


def _pathway_coverage(claims: Sequence[ClaimRecord]) -> tuple[PathwayCoverageRow, ...]:
    by_pathway: dict[str, list[ClaimRecord]] = defaultdict(list)
    for c in claims:
        if c.entity_type == PATHWAY_ENTITY_TYPE:
            by_pathway[c.entity_id].append(c)

    rows: list[PathwayCoverageRow] = []
    for pathway_id, group in by_pathway.items():
        published_fields = {c.field for c in group if c.status == ClaimStatus.published}
        if not published_fields:
            # Not "a published pathway" at all -- nothing has ever
            # reached a student for it, so there is no publication gap
            # to report yet (that pathway is entirely "not verified
            # yet", the ordinary, honest absence-of-coverage state).
            continue
        all_fields = {c.field for c in group}
        not_available = tuple(sorted(all_fields - published_fields))
        rows.append(
            PathwayCoverageRow(
                pathway_id=pathway_id,
                published_field_count=len(published_fields),
                not_available_field_count=len(not_available),
                not_available_fields=not_available,
            )
        )
    return tuple(sorted(rows, key=lambda r: r.pathway_id))


def _freshness_summary(claims: Sequence[ClaimRecord], *, as_of: date) -> FreshnessSummary:
    published = [c for c in claims if c.status == ClaimStatus.published]
    due_14 = sum(1 for c in published if as_of <= c.review_due_date <= as_of + timedelta(days=14))
    due_30 = sum(1 for c in published if as_of <= c.review_due_date <= as_of + timedelta(days=30))
    # "claims stale by their own tier": the live schema has no separate
    # freshness-tier column (docs/CONTRACTS.md's per-tier review_due_on
    # design has not landed in any migration yet) -- review_due_date is
    # already each claim's own, individually-set cadence marker, set at
    # authoring time rather than derived from a shared constant, so
    # "past its own tier" is implemented as "past its own review_due_date".
    stale = sum(1 for c in published if c.review_due_date < as_of)
    return FreshnessSummary(
        due_within_14_days=due_14,
        due_within_30_days=due_30,
        stale_past_review_due=stale,
        scope_note=_FRESHNESS_SCOPE_NOTE,
    )


_PENDING_STATUSES = (ClaimStatus.draft.value, ClaimStatus.in_review.value)


def _pending_review_age(
    claims: Sequence[ClaimRecord], *, as_of: date
) -> tuple[PendingReviewAgeRow, ...]:
    rows = []
    for status in _PENDING_STATUSES:
        group = [c for c in claims if c.status == status]
        if not group:
            rows.append(
                PendingReviewAgeRow(
                    status=status, count=0, average_age_days=None, oldest_age_days=None
                )
            )
            continue
        ages = [(as_of - c.created_at.date()).days for c in group]
        rows.append(
            PendingReviewAgeRow(
                status=status,
                count=len(group),
                average_age_days=round(sum(ages) / len(ages), 1),
                oldest_age_days=max(ages),
            )
        )
    return tuple(rows)


def _check_published_synthetic_source(
    claims: Sequence[ClaimRecord], sources: Mapping[str, SourceRecord]
) -> list[IntegrityFinding]:
    """Defense-in-depth: `db/migrations/0001_init.sql`'s
    `forbid_publishing_synthetic_claims` trigger already refuses this
    INSERT/UPDATE for every role, including service_role (proven live by
    `tests/db/test_ai_retrieval_live.py`'s
    `TestSyntheticSourceCanNeverBePublishedLive`), so a live row in this
    shape should be structurally impossible -- this check exists so a
    future migration that ever loosens that trigger is still caught
    here, not silently trusted."""
    findings = []
    for c in claims:
        if c.status != ClaimStatus.published:
            continue
        source = sources.get(c.source_id)
        if source is not None and source.source_type == SourceType.synthetic:
            findings.append(
                IntegrityFinding(
                    check="published_backed_by_synthetic_source",
                    claim_id=c.id,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    detail=f"source {c.source_id} has source_type=synthetic",
                )
            )
    return findings


def _check_published_bad_source_url(
    claims: Sequence[ClaimRecord],
    sources: Mapping[str, SourceRecord],
    *,
    allowed_domains: frozenset[str],
    aggregator_domains: frozenset[str],
) -> list[IntegrityFinding]:
    """Delegates the actual scheme/allow-list/aggregator decision to
    `scripts.content.check_sources.check_url` -- never re-implemented
    here, same "one place this logic lives" rule
    `scripts/content/validation.py`'s own `check_aggregator_domain`
    already follows for the CSV path."""
    findings = []
    for c in claims:
        if c.status != ClaimStatus.published:
            continue
        source = sources.get(c.source_id)
        if source is None:
            findings.append(
                IntegrityFinding(
                    check="published_source_missing",
                    claim_id=c.id,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    detail=f"source_id {c.source_id} not found among fetched sources",
                )
            )
            continue
        result = check_url(
            source.official_url, allowed_domains, aggregator_domains=aggregator_domains
        )
        if not result.ok:
            findings.append(
                IntegrityFinding(
                    check="published_backed_by_bad_source_url",
                    claim_id=c.id,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    detail=f"{result.reason}: {source.official_url!r}",
                )
            )
    return findings


def _check_published_no_named_verifier(claims: Sequence[ClaimRecord]) -> list[IntegrityFinding]:
    """Blank, or the literal "ai" -- `app/api/claims.py`'s
    `CreateClaimRequest.verifier_must_be_a_person` already rejects "ai"
    at the API layer ("verifier must be a person's identifier... never
    the literal 'ai'"); this is the same rule, checked again here for
    whatever reached `published` by any path, including a direct
    service-role write the API-layer validator never saw."""
    findings = []
    for c in claims:
        if c.status != ClaimStatus.published:
            continue
        verifier = c.verifier.strip()
        if not verifier or verifier.lower() == "ai":
            findings.append(
                IntegrityFinding(
                    check="published_no_named_verifier",
                    claim_id=c.id,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    detail=f"verifier={c.verifier!r}",
                )
            )
    return findings


def _check_maker_equals_checker(claims: Sequence[ClaimRecord]) -> list[IntegrityFinding]:
    """`db/migrations/0003_maker_checker.sql`'s `enforce_claims_workflow`
    trigger already rejects this transition for any non-service_role
    caller ("The author of a claim cannot approve their own claim") --
    but that trigger explicitly steps aside for `service_role`
    (`if auth.role() = 'service_role' then return new;`), so a direct
    service-role write (a seed script, a one-off fix) can still create
    this. Checked across every status, not just `published`, since the
    underlying guarantee ("a second person checked this") is what
    matters, not merely whether it already reached students."""
    findings = []
    for c in claims:
        if c.created_by is not None and c.reviewed_by is not None and c.created_by == c.reviewed_by:
            findings.append(
                IntegrityFinding(
                    check="maker_equals_checker",
                    claim_id=c.id,
                    entity_type=c.entity_type,
                    entity_id=c.entity_id,
                    detail=f"created_by == reviewed_by == {c.created_by}",
                )
            )
    return findings


def _build_eligibility_claim_rows(claims: Sequence[ClaimRecord]) -> list[ClaimRow]:
    """Live `ClaimRecord`s -> `scripts.content.validation.ClaimRow`s, so
    `check_incomplete_eligibility_set` (CONTENT-6, unchanged) can be
    reused directly rather than re-implemented against a second shape.
    See module docstring "THE 'required_fields' CONVENTION ON A LIVE
    CLAIM". Only PUBLISHED claims count as "present" (a draft/in_review
    row has not actually completed the entity's eligibility set from a
    student's point of view yet); a `required_fields` declaration itself
    is read from ANY status, since it is editorial metadata about
    intent, never a fact shown to a student."""
    required_by_entity: dict[str, str] = {}
    for c in claims:
        if c.field == REQUIRED_FIELDS_DECLARATION_FIELD:
            text = _stringify_value(c.value)
            if text:
                required_by_entity.setdefault(c.entity_id, text)

    rows: list[ClaimRow] = []
    for row_number, c in enumerate(claims, start=1):
        if c.status != ClaimStatus.published or c.field == REQUIRED_FIELDS_DECLARATION_FIELD:
            continue
        rows.append(
            ClaimRow(
                row_number=row_number,
                entity_type=c.entity_type,
                entity_key=c.entity_id,
                field=c.field,
                value=_stringify_value(c.value),
                unit="",
                jurisdiction="",
                cycle="",
                tier="",
                source_key="",
                section_ref="",
                quote="",
                checked_by="",
                checked_on="",
                raw={"required_fields": required_by_entity.get(c.entity_id, "")},
            )
        )
    return rows


def _check_incomplete_eligibility_sets(claims: Sequence[ClaimRecord]) -> list[IntegrityFinding]:
    published_claim_ids_by_entity: dict[str, list[str]] = defaultdict(list)
    entity_type_by_entity: dict[str, str] = {}
    for c in claims:
        if c.status == ClaimStatus.published and c.field != REQUIRED_FIELDS_DECLARATION_FIELD:
            published_claim_ids_by_entity[c.entity_id].append(c.id)
            entity_type_by_entity[c.entity_id] = c.entity_type

    eligibility_rows = _build_eligibility_claim_rows(claims)
    violations = check_incomplete_eligibility_set(eligibility_rows)
    findings = []
    for v in violations:
        claim_ids = sorted(published_claim_ids_by_entity.get(v.entity_key, []))
        findings.append(
            IntegrityFinding(
                check="incomplete_eligibility_set",
                claim_id=",".join(claim_ids) if claim_ids else "(no published claim yet)",
                entity_type=entity_type_by_entity.get(v.entity_key, ""),
                entity_id=v.entity_key,
                detail=v.detail,
            )
        )
    return findings


def build_report(
    claims: Sequence[ClaimRecord],
    sources: Mapping[str, SourceRecord],
    *,
    as_of: date,
    allowed_domains: frozenset[str] | None = None,
    aggregator_domains: frozenset[str] = AGGREGATOR_DOMAINS,
    generated_at: datetime | None = None,
) -> CoverageReport:
    """The one pure function this whole report is built from -- no I/O,
    fully testable against hand-built `ClaimRecord`/`SourceRecord`
    lists, exactly the split `app/planning/comparison.py` and
    `scripts/ai_spend_report.py`'s own `build_report` both already use
    (fetch elsewhere, assemble here)."""
    if allowed_domains is None:
        allowed_domains = load_allowed_domains()

    findings: list[IntegrityFinding] = []
    findings += _check_published_synthetic_source(claims, sources)
    findings += _check_published_bad_source_url(
        claims, sources, allowed_domains=allowed_domains, aggregator_domains=aggregator_domains
    )
    findings += _check_published_no_named_verifier(claims)
    findings += _check_maker_equals_checker(claims)
    findings += _check_incomplete_eligibility_sets(claims)

    return CoverageReport(
        generated_at=generated_at or datetime.now(UTC),
        as_of=as_of,
        entity_status_counts=_entity_status_counts(claims),
        pathway_coverage=_pathway_coverage(claims),
        freshness=_freshness_summary(claims, as_of=as_of),
        pending_review_age=_pending_review_age(claims, as_of=as_of),
        reviewer_hour_throughput=REVIEWER_HOUR_THROUGHPUT_NOTE,
        integrity_findings=tuple(findings),
    )


# ---------------------------------------------------------------------
# Rendering -- markdown and CSV, both pure string-in-string-out.
# ---------------------------------------------------------------------


def render_markdown(report: CoverageReport) -> str:
    lines: list[str] = []
    lines.append("# BCION Lite content coverage / freshness / integrity report")
    lines.append("")
    lines.append(
        f"Generated: {report.generated_at.isoformat()} | As of: {report.as_of.isoformat()}"
    )
    lines.append("")
    lines.append(
        "Read-only diagnostic -- see `scripts/content/coverage_report.py`'s own "
        "module docstring. Nothing here is published, verified or changed by "
        "running this report."
    )
    lines.append("")

    lines.append("## Counts per entity type and status")
    lines.append("")
    lines.append("| Entity type | Status | Count |")
    lines.append("| --- | --- | --- |")
    for count_row in report.entity_status_counts:
        lines.append(f"| {count_row.entity_type} | {count_row.status} | {count_row.count} |")
    if not report.entity_status_counts:
        lines.append("| (none) | | 0 |")
    lines.append("")

    lines.append('## "Not available" field counts per published pathway')
    lines.append("")
    lines.append(
        "Only pathways with at least one published field -- a pathway with "
        "none is entirely \"not verified yet\", not a coverage gap."
    )
    lines.append("")
    lines.append("| Pathway id | Published fields | Not-available fields | Field names |")
    lines.append("| --- | --- | --- | --- |")
    for coverage_row in report.pathway_coverage:
        names = (
            ", ".join(coverage_row.not_available_fields)
            if coverage_row.not_available_fields
            else "(none)"
        )
        lines.append(
            f"| {coverage_row.pathway_id} | {coverage_row.published_field_count} | "
            f"{coverage_row.not_available_field_count} | {names} |"
        )
    if not report.pathway_coverage:
        lines.append("| (no pathway has a published claim yet) | | | |")
    lines.append("")

    lines.append("## Freshness")
    lines.append("")
    lines.append(f"Scope: {report.freshness.scope_note}")
    lines.append("")
    lines.append(f"- Due within 14 days: **{report.freshness.due_within_14_days}**")
    lines.append(f"- Due within 30 days: **{report.freshness.due_within_30_days}**")
    lines.append(
        f"- Stale (past its own review_due_date): **{report.freshness.stale_past_review_due}**"
    )
    lines.append("")

    lines.append("## Pending-review age")
    lines.append("")
    lines.append("| Status | Count | Average age (days) | Oldest (days) |")
    lines.append("| --- | --- | --- | --- |")
    for age_row in report.pending_review_age:
        avg: float | str = "-" if age_row.average_age_days is None else age_row.average_age_days
        oldest: int | str = "-" if age_row.oldest_age_days is None else age_row.oldest_age_days
        lines.append(f"| {age_row.status} | {age_row.count} | {avg} | {oldest} |")
    lines.append("")

    lines.append("## Claims processed per reviewer-hour")
    lines.append("")
    lines.append(report.reviewer_hour_throughput)
    lines.append("")

    lines.append("## Integrity")
    lines.append("")
    if report.integrity_ok:
        lines.append("**PASS** -- no integrity violation found.")
    else:
        lines.append(f"**FAIL** -- {len(report.integrity_findings)} violation(s) found.")
        lines.append("")
        lines.append("| Check | Claim id(s) | Entity type | Entity id | Detail |")
        lines.append("| --- | --- | --- | --- | --- |")
        for f in report.integrity_findings:
            lines.append(
                f"| {f.check} | {f.claim_id} | {f.entity_type} | {f.entity_id} | {f.detail} |"
            )
    lines.append("")

    return "\n".join(lines)


def render_csv(report: CoverageReport) -> str:
    """One flat `section,item,field,value` long-format CSV -- every
    section this report has is heterogeneous in shape, so a single flat
    table (rather than several differently-shaped tables jammed into one
    file) is what stays trivially parseable by both a spreadsheet and a
    test's own row-count assertions."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "item", "field", "value"])

    for count_row in report.entity_status_counts:
        writer.writerow(
            ["entity_status_counts", count_row.entity_type, count_row.status, count_row.count]
        )

    for coverage_row in report.pathway_coverage:
        writer.writerow(
            [
                "pathway_coverage",
                coverage_row.pathway_id,
                "published_field_count",
                coverage_row.published_field_count,
            ]
        )
        writer.writerow(
            [
                "pathway_coverage",
                coverage_row.pathway_id,
                "not_available_field_count",
                coverage_row.not_available_field_count,
            ]
        )
        writer.writerow(
            [
                "pathway_coverage",
                coverage_row.pathway_id,
                "not_available_fields",
                "|".join(coverage_row.not_available_fields),
            ]
        )

    writer.writerow(
        ["freshness", "", "due_within_14_days", report.freshness.due_within_14_days]
    )
    writer.writerow(
        ["freshness", "", "due_within_30_days", report.freshness.due_within_30_days]
    )
    writer.writerow(
        ["freshness", "", "stale_past_review_due", report.freshness.stale_past_review_due]
    )
    writer.writerow(["freshness", "", "scope_note", report.freshness.scope_note])

    for age_row in report.pending_review_age:
        writer.writerow(["pending_review_age", age_row.status, "count", age_row.count])
        writer.writerow(
            ["pending_review_age", age_row.status, "average_age_days", age_row.average_age_days]
        )
        writer.writerow(
            ["pending_review_age", age_row.status, "oldest_age_days", age_row.oldest_age_days]
        )

    writer.writerow(["reviewer_hour_throughput", "", "status", report.reviewer_hour_throughput])

    writer.writerow(["integrity", "", "ok", report.integrity_ok])
    for f in report.integrity_findings:
        writer.writerow(["integrity", f.claim_id, f.check, f.detail])

    return buffer.getvalue()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("markdown", "csv", "both"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the rendered report here instead of stdout",
    )
    parser.add_argument(
        "--allowed-domains",
        type=Path,
        default=DEFAULT_ALLOWED_DOMAINS_PATH,
        help="path to allowed_domains.txt (default: content/allowed_domains.txt)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    email = _env("BCION_REVIEWER_EMAIL")
    password = _env("BCION_REVIEWER_PASSWORD")
    if not email or not password:
        print(
            "BCION_REVIEWER_EMAIL and BCION_REVIEWER_PASSWORD must both be set in "
            "the environment -- this report signs in as a real reviewer (see "
            "this module's own docstring for why, not a service-role key).",
            file=sys.stderr,
        )
        return 2

    try:
        client = build_reviewer_client(email=email, password=password)
    except HTTPException as exc:
        print(f"Could not sign in as reviewer: {exc.detail}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- e.g. SupabaseNotConfiguredError, a network error
        print(f"Could not reach the database to sign in: {exc}", file=sys.stderr)
        return 2

    try:
        claims = fetch_claims(client)
        sources = fetch_sources(client)
    except Exception as exc:  # noqa: BLE001 -- e.g. a network error mid-fetch
        print(f"Could not fetch data for this report: {exc}", file=sys.stderr)
        return 2
    finally:
        client.postgrest.aclose()

    allowed_domains = load_allowed_domains(args.allowed_domains)
    report = build_report(claims, sources, as_of=date.today(), allowed_domains=allowed_domains)

    rendered: list[str] = []
    if args.format in ("markdown", "both"):
        rendered.append(render_markdown(report))
    if args.format in ("csv", "both"):
        rendered.append(render_csv(report))
    text = "\n".join(rendered)

    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)

    code = exit_code_for(report)
    if code != 0:
        print(
            f"\n{len(report.integrity_findings)} integrity violation(s) found -- see the "
            "Integrity section above.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
