"""Integration dashboard support routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.integrations import IntegrationResponse, IntegrationStatusUpdateRequest
from app.services.integrations import list_integrations, update_integration_status

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationResponse])
async def list_integration_metadata(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[IntegrationResponse]:
    """List safe integration metadata."""
    return await list_integrations(session=session)


@router.patch("/{integration_slug}", response_model=IntegrationResponse)
async def patch_integration_status(
    integration_slug: str,
    request: IntegrationStatusUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> IntegrationResponse:
    """Activate or disable a known integration."""
    integration = await update_integration_status(
        session=session,
        integration_slug=integration_slug,
        request=request,
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return integration
