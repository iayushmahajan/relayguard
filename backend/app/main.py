"""FastAPI application foundation for RelayGuard."""

from fastapi import FastAPI

from app.api.health import router as health_router
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
    return app


app = create_app()
