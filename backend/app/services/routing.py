"""Routing rule service operations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.routing import (
    RoutingRuleCreateRequest,
    RoutingRuleResponse,
    RoutingRuleUpdateRequest,
)

_MATCH_EVENT_TYPE = "event_type"

logger = structlog.get_logger(__name__)


async def create_routing_rule(
    *,
    session: AsyncSession,
    integration_slug: str,
    request: RoutingRuleCreateRequest,
) -> RoutingRuleResponse | None:
    """Create one deterministic event-type routing rule."""
    integration = await _get_integration_by_slug(session, integration_slug)
    if integration is None:
        return None
    destination = await session.scalar(
        select(models.DownstreamDestination).where(
            models.DownstreamDestination.id == request.destination_id,
            models.DownstreamDestination.integration_id == integration.id,
        )
    )
    if destination is None:
        raise ValueError("destination not found for integration")

    routing_rule = models.RoutingRule(
        integration_id=integration.id,
        destination_id=destination.id,
        name=request.name,
        priority=request.priority,
        status=request.status,
        match_configuration={_MATCH_EVENT_TYPE: request.event_type},
    )
    session.add(routing_rule)
    await session.commit()
    await session.refresh(routing_rule)
    logger.info(
        "routing_rule_created",
        integration_slug=integration.slug,
        routing_rule_id=str(routing_rule.id),
        destination_id=str(destination.id),
    )
    return _to_routing_rule_response(routing_rule)


async def list_routing_rules(
    *,
    session: AsyncSession,
    integration_slug: str,
) -> list[RoutingRuleResponse] | None:
    """List safe routing rule metadata for an integration."""
    integration = await _get_integration_by_slug(session, integration_slug)
    if integration is None:
        return None
    routing_rules = (
        await session.scalars(
            select(models.RoutingRule)
            .where(models.RoutingRule.integration_id == integration.id)
            .order_by(
                models.RoutingRule.priority.asc(),
                models.RoutingRule.created_at.asc(),
                models.RoutingRule.id.asc(),
            )
        )
    ).all()
    return [_to_routing_rule_response(routing_rule) for routing_rule in routing_rules]


async def update_routing_rule(
    *,
    session: AsyncSession,
    integration_slug: str,
    routing_rule_id: str,
    request: RoutingRuleUpdateRequest,
) -> RoutingRuleResponse | None:
    """Update safe routing-rule metadata for a known integration."""
    integration = await _get_integration_by_slug(session, integration_slug)
    if integration is None:
        return None
    routing_rule = await session.scalar(
        select(models.RoutingRule).where(
            models.RoutingRule.id == routing_rule_id,
            models.RoutingRule.integration_id == integration.id,
        )
    )
    if routing_rule is None:
        return None

    if request.destination_id is not None:
        destination = await session.scalar(
            select(models.DownstreamDestination).where(
                models.DownstreamDestination.id == request.destination_id,
                models.DownstreamDestination.integration_id == integration.id,
            )
        )
        if destination is None:
            raise ValueError("destination not found for integration")
        routing_rule.destination_id = destination.id
    if request.name is not None:
        routing_rule.name = request.name
    if request.priority is not None:
        routing_rule.priority = request.priority
    if request.status is not None:
        routing_rule.status = request.status
    if request.event_type is not None:
        routing_rule.match_configuration = {_MATCH_EVENT_TYPE: request.event_type}

    await session.commit()
    await session.refresh(routing_rule)
    logger.info(
        "routing_rule_updated",
        integration_slug=integration.slug,
        routing_rule_id=str(routing_rule.id),
    )
    return _to_routing_rule_response(routing_rule)


def routing_rule_event_type(routing_rule: models.RoutingRule) -> str:
    """Return the deterministic event type matched by a routing rule."""
    event_type = routing_rule.match_configuration.get(_MATCH_EVENT_TYPE)
    if isinstance(event_type, str):
        return event_type
    return ""


async def _get_integration_by_slug(
    session: AsyncSession,
    integration_slug: str,
) -> models.Integration | None:
    return await session.scalar(
        select(models.Integration).where(models.Integration.slug == integration_slug)
    )


def _to_routing_rule_response(routing_rule: models.RoutingRule) -> RoutingRuleResponse:
    return RoutingRuleResponse(
        routing_rule_id=routing_rule.id,
        integration_id=routing_rule.integration_id,
        destination_id=routing_rule.destination_id,
        name=routing_rule.name,
        event_type=routing_rule_event_type(routing_rule),
        priority=routing_rule.priority,
        status=routing_rule.status,
        created_at=routing_rule.created_at,
        updated_at=routing_rule.updated_at,
    )
