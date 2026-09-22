"""Derived jurisdiction coverage — SCOPE-6.

docs/CONTRACTS.md "Settled — coverage": "absence of a published claim
reads 'not verified yet' — never 'no', never zero, never blank. Coverage
is derived from published claims, never hand-maintained." A hand-kept
"is this jurisdiction live yet" flag would be a second publication path
that could drift out of sync with what maker-checker actually approved —
exactly the risk this module exists to avoid, by deriving the answer from
the same `claims` rows every other screen's trust label already comes
from (`app/planning/comparison.py`'s `field_value_for` is that pattern:
never a second, independently-maintained status test).

Unlike `app/planning/comparison.py` (pure functions only, no I/O — see
its own module docstring: callers there already have the relevant
claims/sources fetched), this module DOES talk to the database directly.
There is no existing caller that has already fetched "every claim on
every pathway" the way Compare's per-pathway callers do, and asking each
future caller (`app/web/explore_pages.py`, `app/web/requirements_pages.py`,
and this card's own note: a future AI retrieval pipeline) to re-derive
the same set independently would be exactly the drift risk this module
exists to prevent. `covered_jurisdictions` is the ONE place this query is
written.
"""

from __future__ import annotations

from typing import Any, cast

from supabase import Client

from app.data.models import SourceType

_PATHWAY_ENTITY_TYPE = "Pathway"
"""Matches the literal every other claims query in this codebase already
uses to scope a claim to a pathway (app/api/compare.py, app/web/
detail_pages.py, app/web/timeline_pages.py, app/api/eligibility.py) — not
an enum member, because none of those call sites uses one either;
introducing one here alone would just be a second spelling to keep in
sync with the rest."""


def covered_jurisdictions(db: Client) -> set[str]:
    """Every jurisdiction code (`pathways.jurisdiction` — ISO 3166-1
    alpha-2 for a country, ISO 3166-2 for an Indian state/UT) with at
    least one PUBLISHED, NON-SYNTHETIC claim on a pathway in it.

    This is the one "is X covered yet" answer the rest of the app should
    ever consult — never re-derived locally, never hand-maintained as a
    separate flag.

    Two safeguards below are both applied IN CODE, after the fetch, not
    trusted to the query's own `.eq("status", "published")` filter alone
    — the filter is an optimisation (fewer rows to carry across the
    process boundary), not the actual gate. That matters here because the
    caller's own RLS-scoped client can legally see MORE than
    published+non-synthetic rows, and this function must give the exact
    same answer regardless of who is asking (a guest, a signed-in
    reviewer, or demo mode being on) — the same "RLS is not the only
    check" lesson this codebase has already learned once:

    - `claims_select_published` (db/migrations/0001_init.sql) ORs in
      every draft/in_review claim for a reviewer's own client: `using
      (status = 'published' or is_reviewer())`. A signed-in reviewer's
      RLS-scoped client is NOT filtered down to published-only rows by
      RLS alone — this function must never assume it is.
    - `claims_select_demo_synthetic` (db/migrations/0007_demo_mode.sql)
      additionally widens even a GUEST's own view, while demo mode is on,
      to include `in_review` claims backed by a `synthetic` source.

    Re-checking `status == "published"` and the claim's source
    `source_type != "synthetic"` here, in Python, after the fetch, is the
    same belt-and-braces `trust_label_for_claim`
    (app/planning/comparison.py) already applies to every other
    published-claim read in this codebase: "the DB trigger forbids this
    state from ever existing for real, but never trust the trigger alone
    to be the only thing standing between a draft/synthetic row and a
    public result."

    Deliberately three broad `select()` calls (claims, then sources for
    the claims' own source ids, then pathways for the claims' own entity
    ids) rather than a single joined query — matches the "two queries
    total, not one per pathway" shape `app/api/compare.py`'s
    `assemble_comparisons` already uses; at Lite's pilot scale (10-100
    users, a handful of pathways) this is cheap, and it keeps every query
    here a plain `.select().eq()/.in_()` postgrest-py call with no
    embedded-relationship syntax to get wrong.

    No jurisdiction registry is consulted and none is hardcoded here:
    docs/CONTRACTS.md forbids a hardcoded covered-set list until SCOPE-1
    is answered, and this derivation is exactly the alternative that
    means nobody ever needs one.
    """
    claims_result = (
        db.table("claims")
        .select("entity_id, source_id, status")
        .eq("entity_type", _PATHWAY_ENTITY_TYPE)
        .eq("status", "published")
        .execute()
    )
    claims = cast("list[dict[str, Any]]", claims_result.data)
    # Defensive re-check (see docstring above) -- never trust the query's
    # own filter as the sole gate.
    published_claims = [claim for claim in claims if claim.get("status") == "published"]
    if not published_claims:
        return set()

    source_ids = sorted(
        {claim["source_id"] for claim in published_claims if claim.get("source_id")}
    )
    non_synthetic_source_ids: set[str] = set()
    if source_ids:
        sources_result = (
            db.table("sources").select("id, source_type").in_("id", source_ids).execute()
        )
        sources = cast("list[dict[str, Any]]", sources_result.data)
        non_synthetic_source_ids = {
            source["id"]
            for source in sources
            if source.get("source_type") != SourceType.synthetic.value
        }

    pathway_ids = sorted(
        {
            claim["entity_id"]
            for claim in published_claims
            if claim.get("source_id") in non_synthetic_source_ids
        }
    )
    if not pathway_ids:
        return set()

    pathways_result = (
        db.table("pathways").select("id, jurisdiction").in_("id", pathway_ids).execute()
    )
    pathways = cast("list[dict[str, Any]]", pathways_result.data)
    return {pathway["jurisdiction"] for pathway in pathways if pathway.get("jurisdiction")}


def covered_jurisdictions_or_none(db: Client) -> set[str] | None:
    """`covered_jurisdictions`, degraded to `None` on any failure — for a
    WEB PAGE caller only (`app/web/explore_pages.py`,
    `app/web/requirements_pages.py`), which must never 500 a public
    screen just because this derivation's own query failed: a transient
    DB hiccup, a stack that has not applied
    db/migrations/0008_jurisdiction_currency.sql yet, or a test double
    that does not implement the full postgrest-py query-builder chain
    this function's real queries use. Mirrors `app/api/explore.py`'s own
    `_demo_mode()`: "Fails closed... never to a 500 on the public Explore
    screen."

    `None` — never an empty set — on failure, so a caller can tell
    "genuinely nothing published yet" (an empty set: every "not verified
    yet" panel that applies should show) apart from "could not tell right
    now" (`None`: show none of them). A false "not verified" warning on a
    page that is otherwise serving real published content fine is worse
    than silently skipping the coverage check for one request.

    A future non-web caller (this card's own note: an AI retrieval
    pipeline) should call `covered_jurisdictions` directly instead — it
    needs to know a real failure happened, not have one silently
    swallowed into "nothing is covered".
    """
    try:
        return covered_jurisdictions(db)
    except Exception:  # noqa: BLE001 — see docstring: never 500 a public page over this
        return None
