"""BCION Lite — FastAPI application factory.

M1: the first real vertical slice — explore -> compare, backed by the
live Supabase project — is wired in. See STATUS.md and tasks/BCI-002.md.
"""

from fastapi import FastAPI

from app.api.compare import router as compare_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
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
    return app


app = create_app()
