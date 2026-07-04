"""FastAPI application foundation for RelayGuard Phase 0."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(
        title="RelayGuard API",
        description="RelayGuard backend foundation (Phase 0).",
        version="0.1.0",
    )


app = create_app()
