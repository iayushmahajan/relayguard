"""Event metadata service operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.events import EventMetadataResponse


async def get_event_metadata(
    *,
    session: AsyncSession,
    event_id: uuid.UUID,
) -> EventMetadataResponse | None:
    """Return safe event metadata for one canonical event."""
    event = await session.scalar(select(models.Event).where(models.Event.id == event_id))
    if event is None:
        return None
    return EventMetadataResponse(
        event_id=event.id,
        integration_id=event.integration_id,
        event_type=event.event_type,
        source_event_id=event.source_event_id,
        status=event.status,
        received_at=event.received_at,
        accepted_at=event.accepted_at,
    )
