"""Delivery scheduling service operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.routing import (
    DeliveryResponse,
    DeliveryScheduleResponse,
    RecentDeliveryResponse,
)
from app.services.routing import routing_rule_event_type

_ACCEPTED_STATUS = "accepted"
_SCHEDULED_STATUS = "scheduled"

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ScheduleDeliveriesResult:
    """Service result for delivery scheduling."""

    status_code: int
    detail: str | None
    response: DeliveryScheduleResponse | None


async def schedule_deliveries_for_event(
    *,
    session: AsyncSession,
    event_id: uuid.UUID,
) -> ScheduleDeliveriesResult:
    """Schedule durable delivery records for matching active routes."""
    event = await session.scalar(select(models.Event).where(models.Event.id == event_id))
    if event is None:
        return ScheduleDeliveriesResult(status_code=404, detail="event not found", response=None)
    if event.status != _ACCEPTED_STATUS:
        return ScheduleDeliveriesResult(
            status_code=409,
            detail="event is not accepted",
            response=None,
        )

    matched_routes = await _load_matching_routes(session=session, event=event)
    if not matched_routes:
        return ScheduleDeliveriesResult(
            status_code=200,
            detail=None,
            response=DeliveryScheduleResponse(
                event_id=event.id,
                status=event.status,
                scheduled_count=0,
                already_scheduled_count=0,
            ),
        )

    inserted_count = await _insert_missing_deliveries(
        session=session,
        event=event,
        matched_routes=matched_routes,
    )
    await session.commit()
    already_scheduled_count = len(matched_routes) - inserted_count
    logger.info(
        "deliveries_scheduled",
        event_id=str(event.id),
        scheduled_count=inserted_count,
        already_scheduled_count=already_scheduled_count,
    )
    return ScheduleDeliveriesResult(
        status_code=200,
        detail=None,
        response=DeliveryScheduleResponse(
            event_id=event.id,
            status=event.status,
            scheduled_count=inserted_count,
            already_scheduled_count=already_scheduled_count,
        ),
    )


async def list_deliveries_for_event(
    *,
    session: AsyncSession,
    event_id: uuid.UUID,
) -> list[DeliveryResponse] | None:
    """Return safe delivery metadata for an event."""
    event_exists = await session.scalar(select(models.Event.id).where(models.Event.id == event_id))
    if event_exists is None:
        return None
    deliveries = (
        await session.scalars(
            select(models.EventDelivery)
            .where(models.EventDelivery.event_id == event_id)
            .order_by(models.EventDelivery.created_at.asc(), models.EventDelivery.id.asc())
        )
    ).all()
    return [_to_delivery_response(delivery) for delivery in deliveries]


async def list_recent_deliveries(
    *,
    session: AsyncSession,
    limit: int,
    status: str | None = None,
    event_id: uuid.UUID | None = None,
) -> list[RecentDeliveryResponse]:
    """Return recent safe delivery metadata with display context."""
    statement = (
        select(
            models.EventDelivery,
            models.Event.event_type,
            models.DownstreamDestination.name.label("destination_name"),
            models.RoutingRule.name.label("routing_rule_name"),
        )
        .join(models.Event, models.EventDelivery.event_id == models.Event.id)
        .join(
            models.DownstreamDestination,
            models.EventDelivery.destination_id == models.DownstreamDestination.id,
        )
        .outerjoin(
            models.RoutingRule, models.EventDelivery.routing_rule_id == models.RoutingRule.id
        )
        .order_by(models.EventDelivery.created_at.desc(), models.EventDelivery.id.desc())
        .limit(limit)
    )
    if status is not None:
        statement = statement.where(models.EventDelivery.status == status)
    if event_id is not None:
        statement = statement.where(models.EventDelivery.event_id == event_id)

    rows = (await session.execute(statement)).all()
    return [
        RecentDeliveryResponse(
            delivery_id=delivery.id,
            event_id=delivery.event_id,
            event_type=event_type,
            destination_id=delivery.destination_id,
            destination_name=destination_name,
            routing_rule_id=delivery.routing_rule_id,
            routing_rule_name=routing_rule_name,
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            next_attempt_at=delivery.next_attempt_at,
            last_attempt_at=delivery.last_attempt_at,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )
        for delivery, event_type, destination_name, routing_rule_name in rows
    ]


async def _load_matching_routes(
    *,
    session: AsyncSession,
    event: models.Event,
) -> list[models.RoutingRule]:
    active_routes = (
        await session.scalars(
            select(models.RoutingRule)
            .join(
                models.DownstreamDestination,
                models.RoutingRule.destination_id == models.DownstreamDestination.id,
            )
            .where(
                models.RoutingRule.integration_id == event.integration_id,
                models.RoutingRule.status == "active",
                models.DownstreamDestination.status == "active",
            )
            .order_by(
                models.RoutingRule.priority.asc(),
                models.RoutingRule.created_at.asc(),
                models.RoutingRule.id.asc(),
            )
        )
    ).all()
    return [
        routing_rule
        for routing_rule in active_routes
        if routing_rule_event_type(routing_rule) == event.event_type
    ]


async def _insert_missing_deliveries(
    *,
    session: AsyncSession,
    event: models.Event,
    matched_routes: list[models.RoutingRule],
) -> int:
    now = datetime.now(timezone.utc)
    statement = (
        pg_insert(models.EventDelivery)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "event_id": event.id,
                    "destination_id": routing_rule.destination_id,
                    "routing_rule_id": routing_rule.id,
                    "status": _SCHEDULED_STATUS,
                    "next_attempt_at": now,
                    "attempt_count": 0,
                }
                for routing_rule in matched_routes
            ]
        )
        .on_conflict_do_nothing(
            index_elements=[
                models.EventDelivery.event_id,
                models.EventDelivery.destination_id,
                models.EventDelivery.routing_rule_id,
            ]
        )
        .returning(models.EventDelivery.id)
    )
    return len((await session.scalars(statement)).all())


def _to_delivery_response(delivery: models.EventDelivery) -> DeliveryResponse:
    return DeliveryResponse(
        delivery_id=delivery.id,
        event_id=delivery.event_id,
        destination_id=delivery.destination_id,
        routing_rule_id=delivery.routing_rule_id,
        status=delivery.status,
        next_attempt_at=delivery.next_attempt_at,
        attempt_count=delivery.attempt_count,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )
