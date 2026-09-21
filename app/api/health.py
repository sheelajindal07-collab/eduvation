"""Health and readiness endpoints.

Used for the M0 smoke check and, later, uptime monitoring
(docs/SECURITY.md). Reports configuration status honestly — never claims a
dependency is ready when it isn't configured.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from supabase import Client

from app.core.config import get_settings
from app.db import SupabaseNotConfiguredError, get_anon_client

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, object]:
    """Liveness check. Always 200 if the process is up and serving."""
    settings = get_settings()
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "db_configured": settings.db_configured,
        "ai_configured": settings.ai_configured,
    }


def _anon_client_or_none() -> Client | None:
    """Same "degrade to None rather than propagate" contract as
    app/web/common.py's `_db_client_or_none`, but with no bearer-token
    resolution at all -- /readyz is an ops/uptime check, never a
    per-user request, so it only ever needs the guest/anon client for
    one cheap published-table read."""
    try:
        return get_anon_client()
    except SupabaseNotConfiguredError:
        return None


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness check (DEPLOY-5): a distinct, more thorough check than
    `/healthz` -- actually exercises the database with one cheap,
    read-only query against a published table (`careers`), via the
    guest/anon client so RLS applies exactly as it would for a real
    guest request. No PII is read or returned, and no credential value
    (a connection string, a key, a raw exception message that might
    embed one) is ever included in the response -- only booleans and the
    already-public `AI_ENABLED` flag per docs/CONTRACTS.md.

    503 whenever the database isn't configured or the query fails for
    any reason (`except Exception` — deliberately broad: a DB-down
    condition can surface as a postgrest.exceptions.APIError, a raw
    httpx connection error, or something else entirely, and every one of
    them means "not ready", not "crash the health check itself" — same
    reasoning app/web/reviewer_pages.py's own DB-unavailable handling
    already uses)."""
    settings = get_settings()
    client = _anon_client_or_none()

    database_reachable = False
    if client is not None:
        try:
            client.table("careers").select("id").limit(1).execute()
            database_reachable = True
        except Exception:
            database_reachable = False
        finally:
            client.postgrest.aclose()

    body = {
        "status": "ready" if database_reachable else "not_ready",
        "app_env": settings.app_env,
        "ai_enabled": settings.ai_enabled,
        "database_reachable": database_reachable,
    }
    return JSONResponse(status_code=200 if database_reachable else 503, content=body)
