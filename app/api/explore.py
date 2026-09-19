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


@router.get("/careers", response_model=ExploreResponse)
def list_careers(db: Client = Depends(get_db_client)) -> ExploreResponse:
    careers_result = db.table("careers").select("id, name, nco_anchor").execute()
    pathways_result = db.table("pathways").select("id, career_id, name, description").execute()
    return ExploreResponse(
        careers=[CareerSummary.model_validate(row) for row in careers_result.data],
        pathways=[PathwaySummary.model_validate(row) for row in pathways_result.data],
    )
