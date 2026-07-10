"""Safe integration metadata service operations."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.integrations import IntegrationResponse, IntegrationStatusUpdateRequest

logger = structlog.get_logger(__name__)


async def list_integrations(*, session: AsyncSession) -> list[IntegrationResponse]:
    """List safe integration metadata for the operator dashboard."""
    integrations = (
        await session.scalars(
            select(models.Integration).order_by(
                models.Integration.created_at.asc(),
                models.Integration.slug.asc(),
            )
        )
    ).all()
    return [_to_integration_response(integration) for integration in integrations]


async def update_integration_status(
    *,
    session: AsyncSession,
    integration_slug: str,
    request: IntegrationStatusUpdateRequest,
) -> IntegrationResponse | None:
    """Activate or disable one known integration."""
    integration = await session.scalar(
        select(models.Integration).where(models.Integration.slug == integration_slug)
    )
    if integration is None:
        return None

    integration.status = request.status
    integration.enabled = request.status == "active"
    await session.commit()
    await session.refresh(integration)
    logger.info(
        "integration_status_updated",
        integration_slug=integration.slug,
        status=integration.status,
    )
    return _to_integration_response(integration)


def _to_integration_response(integration: models.Integration) -> IntegrationResponse:
    return IntegrationResponse(
        integration_id=integration.id,
        slug=integration.slug,
        name=integration.name,
        status=integration.status,
        enabled=integration.enabled,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )
