"""BCION Lite — FastAPI application factory.

M3: sign-in is wired in (tasks/BCI-004.md). See STATUS.md for the full
list of what's live.
"""

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.claims import router as claims_router
from app.api.compare import router as compare_router
from app.api.eligibility import router as eligibility_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.api.timeline import router as timeline_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BCION Lite",
        description="A 10-100 user career-decision pilot. See docs/PRODUCT.md.",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
    )
    app.include_router(health_router)
    app.include_router(explore_router)
    app.include_router(compare_router)
    app.include_router(eligibility_router)
    app.include_router(timeline_router)
    app.include_router(auth_router)
    app.include_router(plans_router)
    app.include_router(claims_router)
    return app


app = create_app()
