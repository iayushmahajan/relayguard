"""FastAPI application foundation for RelayGuard."""

from fastapi import FastAPI

from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.core.config import get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        description="RelayGuard backend API.",
        version=settings.app_version,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(events_router)
    return app


app = create_app()
