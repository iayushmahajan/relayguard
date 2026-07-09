"""Event metadata routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.events import EventMetadataResponse
from app.services.events import get_event_metadata

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/{event_id}", response_model=EventMetadataResponse)
async def read_event_metadata(
    event_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> EventMetadataResponse:
    """Return safe canonical event metadata without payload contents."""
    event = await get_event_metadata(session=session, event_id=event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    return event
