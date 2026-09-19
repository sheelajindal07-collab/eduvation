"""BCION Lite — FastAPI application factory.

M0 scope only: the smallest runnable shell plus a health endpoint. The
first real vertical slice (explore -> compare on synthetic fixtures) lands
at M1 — see STATUS.md and tasks/BCI-002.md.
"""

from fastapi import FastAPI

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
    return app


app = create_app()
