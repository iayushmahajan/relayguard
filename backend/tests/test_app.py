from fastapi import FastAPI

from app.main import create_app


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)


def test_create_app_metadata() -> None:
    app = create_app()

    assert app.title == "RelayGuard API"
    assert app.version == "0.1.0"
    assert app.description == "RelayGuard backend foundation (Phase 0)."
