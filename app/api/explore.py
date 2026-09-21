"""GET /careers — Explore screen (docs/UI.md, docs/PRODUCT.md).

Lists published careers and their pathways. Public: works for a guest,
no login required ("Public tools work without login", docs/UI.md). RLS
on the `careers`/`pathways` tables (db/migrations/0001_init.sql) is what
actually enforces "world-readable" here — this route does no filtering
of its own, by design, so there is exactly one place access rules live.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client

from app.api.deps import get_db_client

router = APIRouter(tags=["explore"])


class CareerSummary(BaseModel):
    id: str
    name: str
    nco_anchor: str | None = None


class PathwaySummary(BaseModel):
    id: str
    career_id: str
    name: str
    description: str


class ExploreResponse(BaseModel):
    careers: list[CareerSummary]
    pathways: list[PathwaySummary]
    demo_mode: bool = False
    """DATA-12: this stack is serving clearly-labelled SAMPLE data, so the
    Explore screen must show the sample-data notice (docs/CONTRACTS.md
    "Settled — `is_sample`": a sample row "carries a visible label
    wherever it appears").

    Deliberately a screen-level flag here rather than a per-row
    `is_sample`, because it would be dishonest to put one on these rows:
    `careers`/`pathways` carry no source and no status of their own —
    only `claims` do — so there is no evidence on a career row from which
    "this one is sample" could be derived. Inventing a per-row label
    from the global flag would mark real careers as samples the moment
    demo mode came on. The truthful per-row signal lives where the
    evidence does, on Compare's claim-backed field values
    (`app/api/compare.py`'s `FieldValueOut.is_sample`).

    Read from the DATABASE's own `demo_mode()` function, not from
    `Settings.demo_mode`: the database is what actually decides whether
    any sample row is visible (db/migrations/0007_demo_mode.sql), so
    asking it directly means the banner can never disagree with what the
    page is showing. Additive with a False default."""


def _demo_mode(db: Client) -> bool:
    """Ask the database whether demo mode is on.

    Fails closed to False on any error — most importantly in the window
    where this code has deployed but 0007_demo_mode.sql has not been
    applied to the target yet, where the RPC simply does not exist. A
    missing function must degrade to "no banner" (and there are no
    sample rows to label either, since the policy that reveals them is in
    the same migration), never to a 500 on the public Explore screen.
    """
    try:
        result = db.rpc("demo_mode", {}).execute()
    except Exception:  # noqa: BLE001 — any failure here means "not on"
        return False
    return result.data is True


@router.get("/careers", response_model=ExploreResponse)
def list_careers(db: Client = Depends(get_db_client)) -> ExploreResponse:
    careers_result = db.table("careers").select("id, name, nco_anchor").execute()
    pathways_result = db.table("pathways").select("id, career_id, name, description").execute()
    return ExploreResponse(
        careers=[CareerSummary.model_validate(row) for row in careers_result.data],
        pathways=[PathwaySummary.model_validate(row) for row in pathways_result.data],
        demo_mode=_demo_mode(db),
    )
