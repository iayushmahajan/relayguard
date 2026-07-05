"""Pure ASGI correlation-ID middleware."""

from uuid import UUID, uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

CORRELATION_ID_HEADER = "x-correlation-id"
_CORRELATION_ID_HEADER_BYTES = CORRELATION_ID_HEADER.encode("ascii")


class CorrelationIdMiddleware:
    """Bind a request correlation ID and echo it in the response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = _get_or_create_correlation_id(scope)
        clear_contextvars()
        bind_contextvars(correlation_id=correlation_id)
        response_started = False

        async def send_with_correlation_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers.append((_CORRELATION_ID_HEADER_BYTES, correlation_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        except Exception:
            structlog.get_logger(__name__).exception("request_failed")
            if response_started:
                raise
            await _send_internal_server_error(send, correlation_id)
        finally:
            clear_contextvars()


def _get_or_create_correlation_id(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() == _CORRELATION_ID_HEADER_BYTES:
            try:
                return str(UUID(value.decode("ascii")))
            except (UnicodeDecodeError, ValueError):
                return str(uuid4())
    return str(uuid4())


async def _send_internal_server_error(send: Send, correlation_id: str) -> None:
    body = b'{"detail":"Internal Server Error"}'
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (_CORRELATION_ID_HEADER_BYTES, correlation_id.encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
