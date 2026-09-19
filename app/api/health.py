"""Health and readiness endpoints.

Used for the M0 smoke check and, later, uptime monitoring
(docs/SECURITY.md). Reports configuration status honestly — never claims a
dependency is ready when it isn't configured.
"""

from fastapi import APIRouter

from app.core.config import get_settings

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
