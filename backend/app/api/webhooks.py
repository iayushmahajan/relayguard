"""Webhook intake routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.webhooks import WebhookIntakeResponse, WebhookRejectedResponse
from app.services.webhook_intake import ingest_webhook

router = APIRouter(prefix="/api/v1/integrations", tags=["webhooks"])


@router.post("/{integration_slug}/webhooks")
async def receive_webhook(
    integration_slug: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Receive one known integration webhook attempt."""
    result = await ingest_webhook(
        session=session,
        request=request,
        integration_slug=integration_slug,
    )
    if result.event_id is None:
        rejected = WebhookRejectedResponse(detail=result.detail or "request rejected")
        if result.receipt_id is not None:
            rejected.receipt_id = result.receipt_id
        return JSONResponse(
            status_code=result.status_code,
            content=rejected.model_dump(mode="json"),
        )

    accepted = WebhookIntakeResponse(
        receipt_id=_require_uuid(result.receipt_id),
        event_id=result.event_id,
        status="accepted",
        duplicate=result.duplicate,
    )
    return JSONResponse(
        status_code=result.status_code,
        content=accepted.model_dump(mode="json"),
    )


def _require_uuid(value: UUID | None) -> UUID:
    if value is None:
        raise RuntimeError("webhook intake response is missing a receipt ID")
    return value
