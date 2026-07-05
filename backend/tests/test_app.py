import asyncio

from fastapi import FastAPI
from starlette.types import Message

from app.main import create_app


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)


def test_create_app_metadata() -> None:
    app = create_app()

    assert app.title == "RelayGuard API"
    assert app.version == "0.1.0"
    assert app.description == "RelayGuard backend API."


def test_health_reports_process_status_only() -> None:
    app = create_app()

    messages = asyncio.run(_request(app, "/api/v1/health"))

    assert messages[0]["status"] == 200
    assert messages[1]["body"] == b'{"status":"ok"}'
    headers = dict(messages[0]["headers"])
    assert b"x-correlation-id" in headers
    assert b"correlation_id" not in messages[1]["body"]


async def _request(app: FastAPI, path: str) -> list[Message]:
    messages: list[Message] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(scope, receive, send)
    return messages
