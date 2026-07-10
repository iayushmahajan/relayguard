"""Event metadata routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.events import EventMetadataResponse
from app.schemas.routing import DeliveryResponse, DeliveryScheduleResponse
from app.services.deliveries import list_deliveries_for_event, schedule_deliveries_for_event
from app.services.events import get_event_metadata, list_recent_events

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=list[EventMetadataResponse])
async def list_event_metadata(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    integration_slug: Annotated[str | None, Query()] = None,
) -> list[EventMetadataResponse]:
    """List recent safe event metadata without payload contents."""
    events = await list_recent_events(
        session=session,
        limit=limit,
        integration_slug=integration_slug,
    )
    if events is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return events


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


@router.post("/{event_id}/schedule-deliveries", response_model=DeliveryScheduleResponse)
async def schedule_event_deliveries(
    event_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Schedule durable delivery records for matching active routes."""
    result = await schedule_deliveries_for_event(session=session, event_id=event_id)
    if result.response is None:
        raise HTTPException(status_code=result.status_code, detail=result.detail)
    return JSONResponse(
        status_code=result.status_code,
        content=result.response.model_dump(mode="json"),
    )


@router.get("/{event_id}/deliveries", response_model=list[DeliveryResponse])
async def list_event_deliveries(
    event_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DeliveryResponse]:
    """List safe delivery metadata for an event."""
    deliveries = await list_deliveries_for_event(session=session, event_id=event_id)
    if deliveries is None:
        raise HTTPException(status_code=404, detail="event not found")
    return deliveries
