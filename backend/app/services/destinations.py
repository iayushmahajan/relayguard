"""Downstream destination service operations."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.routing import DestinationCreateRequest, DestinationResponse

_CONFIG_DESTINATION_TYPE = "destination_type"
_CONFIG_SETTINGS = "settings"
_SENSITIVE_KEY_FRAGMENTS = ("secret", "password", "token", "credential", "api_key")

logger = structlog.get_logger(__name__)


async def create_destination(
    *,
    session: AsyncSession,
    integration_slug: str,
    request: DestinationCreateRequest,
) -> DestinationResponse | None:
    """Create one downstream destination for a known integration."""
    integration = await _get_integration_by_slug(session, integration_slug)
    if integration is None:
        return None
    if _contains_sensitive_key(request.configuration):
        raise ValueError("configuration must not contain secrets")

    destination = models.DownstreamDestination(
        integration_id=integration.id,
        name=request.name,
        endpoint_url=request.endpoint_url,
        status=request.status,
        configuration=_pack_configuration(
            destination_type=request.destination_type,
            settings=request.configuration,
        ),
    )
    session.add(destination)
    await session.commit()
    await session.refresh(destination)
    logger.info(
        "destination_created",
        integration_slug=integration.slug,
        destination_id=str(destination.id),
    )
    return _to_destination_response(destination)


async def list_destinations(
    *,
    session: AsyncSession,
    integration_slug: str,
) -> list[DestinationResponse] | None:
    """List safe downstream destination metadata for an integration."""
    integration = await _get_integration_by_slug(session, integration_slug)
    if integration is None:
        return None
    destinations = (
        await session.scalars(
            select(models.DownstreamDestination)
            .where(models.DownstreamDestination.integration_id == integration.id)
            .order_by(
                models.DownstreamDestination.created_at.asc(),
                models.DownstreamDestination.id.asc(),
            )
        )
    ).all()
    return [_to_destination_response(destination) for destination in destinations]


async def _get_integration_by_slug(
    session: AsyncSession,
    integration_slug: str,
) -> models.Integration | None:
    return await session.scalar(
        select(models.Integration).where(models.Integration.slug == integration_slug)
    )


def _pack_configuration(*, destination_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        _CONFIG_DESTINATION_TYPE: destination_type,
        _CONFIG_SETTINGS: settings,
    }


def unpack_destination_type(configuration: dict[str, Any] | None) -> str:
    """Return the destination type stored in the destination configuration document."""
    if configuration is None:
        return ""
    destination_type = configuration.get(_CONFIG_DESTINATION_TYPE)
    if isinstance(destination_type, str):
        return destination_type
    return ""


def unpack_destination_settings(configuration: dict[str, Any] | None) -> dict[str, Any]:
    """Return safe caller-provided destination settings."""
    if configuration is None:
        return {}
    settings = configuration.get(_CONFIG_SETTINGS)
    if isinstance(settings, dict):
        return settings
    return {}


def _to_destination_response(destination: models.DownstreamDestination) -> DestinationResponse:
    return DestinationResponse(
        destination_id=destination.id,
        integration_id=destination.integration_id,
        name=destination.name,
        destination_type=unpack_destination_type(destination.configuration),
        endpoint_url=destination.endpoint_url,
        configuration=unpack_destination_settings(destination.configuration),
        status=destination.status,
        created_at=destination.created_at,
        updated_at=destination.updated_at,
    )


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            lowered_key = str(key).lower()
            if any(fragment in lowered_key for fragment in _SENSITIVE_KEY_FRAGMENTS):
                return True
            if _contains_sensitive_key(nested_value):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
