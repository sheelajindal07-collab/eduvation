"""BCION Lite — FastAPI application factory.

M3: sign-in is wired in (tasks/BCI-004.md). M4: maker-checker + the
publishing console API (tasks/BCI-005.md). The first real UI
(`app/web/`) is wired in too -- see STATUS.md for the full list of
what's live.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.claims import router as claims_router
from app.api.compare import router as compare_router
from app.api.eligibility import router as eligibility_router
from app.api.explore import router as explore_router
from app.api.health import router as health_router
from app.api.plans import router as plans_router
from app.api.timeline import router as timeline_router
from app.core.config import get_settings
from app.web.pages import router as pages_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BCION Lite",
        description="A 10-100 user career-decision pilot. See docs/PRODUCT.md.",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
    )
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(health_router)
    app.include_router(explore_router)
    app.include_router(compare_router)
    app.include_router(eligibility_router)
    app.include_router(timeline_router)
    app.include_router(auth_router)
    app.include_router(plans_router)
    app.include_router(claims_router)
    app.include_router(pages_router)
    return app


app = create_app()
