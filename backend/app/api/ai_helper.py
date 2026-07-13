"""AI operator-helper routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.ai_helper import (
    DraftReplayNoteRequest,
    DraftReplayNoteResponse,
    ExplainDeliveryRequest,
    ExplainDeliveryResponse,
    SampleWebhookPayloadRequest,
    SampleWebhookPayloadResponse,
)
from app.services.ai_helper import (
    draft_replay_note,
    explain_delivery,
    sample_webhook_payload,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai helper"])


@router.post("/explain-delivery", response_model=ExplainDeliveryResponse)
async def explain_delivery_failure(
    request: ExplainDeliveryRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ExplainDeliveryResponse:
    """Explain a delivery using safe metadata only."""
    response = await explain_delivery(session=session, delivery_id=request.delivery_id)
    if response is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    return response


@router.post("/draft-replay-note", response_model=DraftReplayNoteResponse)
async def draft_replay_request_note(
    request: DraftReplayNoteRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DraftReplayNoteResponse:
    """Draft replay request text without creating or approving a replay."""
    response = await draft_replay_note(session=session, dead_letter_id=request.dead_letter_id)
    if response is None:
        raise HTTPException(status_code=404, detail="dead letter not found")
    return response


@router.post("/sample-webhook-payload", response_model=SampleWebhookPayloadResponse)
async def generate_sample_webhook_payload(
    request: SampleWebhookPayloadRequest,
) -> SampleWebhookPayloadResponse:
    """Generate a safe sample webhook envelope for user review."""
    return sample_webhook_payload(request=request)
