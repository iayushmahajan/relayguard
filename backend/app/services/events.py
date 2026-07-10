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


async def list_recent_events(
    *,
    session: AsyncSession,
    limit: int,
    integration_slug: str | None = None,
) -> list[EventMetadataResponse] | None:
    """Return recent safe event metadata, optionally scoped to one integration."""
    statement = select(models.Event)
    if integration_slug is not None:
        integration = await session.scalar(
            select(models.Integration).where(models.Integration.slug == integration_slug)
        )
        if integration is None:
            return None
        statement = statement.where(models.Event.integration_id == integration.id)
    events = (
        await session.scalars(
            statement.order_by(
                models.Event.received_at.desc(),
                models.Event.id.asc(),
            ).limit(limit)
        )
    ).all()
    return [
        EventMetadataResponse(
            event_id=event.id,
            integration_id=event.integration_id,
            event_type=event.event_type,
            source_event_id=event.source_event_id,
            status=event.status,
            received_at=event.received_at,
            accepted_at=event.accepted_at,
        )
        for event in events
    ]
