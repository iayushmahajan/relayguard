import asyncio
from uuid import UUID

from fastapi import FastAPI
from starlette.types import Message

from app.main import create_app


def test_valid_inbound_correlation_id_is_reused() -> None:
    correlation_id = "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db"
    messages = asyncio.run(
        _request(
            create_app(),
            [(b"x-correlation-id", correlation_id.encode("ascii"))],
        )
    )

    response_headers = dict(messages[0]["headers"])
    assert response_headers[b"x-correlation-id"] == correlation_id.encode("ascii")


def test_invalid_inbound_correlation_id_is_replaced() -> None:
    messages = asyncio.run(
        _request(
            create_app(),
            [(b"x-correlation-id", b"not-a-uuid")],
        )
    )

    response_headers = dict(messages[0]["headers"])
    generated = response_headers[b"x-correlation-id"].decode("ascii")
    assert generated != "not-a-uuid"
    assert str(UUID(generated)) == generated


async def _request(app: FastAPI, headers: list[tuple[bytes, bytes]]) -> list[Message]:
    messages: list[Message] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/health",
        "raw_path": b"/api/v1/health",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(scope, receive, send)
    return messages
