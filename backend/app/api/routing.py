"""Destination and routing rule routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.routing import (
    DestinationCreateRequest,
    DestinationResponse,
    DestinationUpdateRequest,
    RoutingRuleCreateRequest,
    RoutingRuleResponse,
    RoutingRuleUpdateRequest,
)
from app.services.destinations import create_destination, list_destinations, update_destination
from app.services.routing import create_routing_rule, list_routing_rules, update_routing_rule

router = APIRouter(prefix="/api/v1/integrations", tags=["routing"])


@router.post("/{integration_slug}/destinations", response_model=DestinationResponse)
async def create_integration_destination(
    integration_slug: str,
    request: DestinationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Create a downstream destination for an integration."""
    try:
        destination = await create_destination(
            session=session,
            integration_slug=integration_slug,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if destination is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return JSONResponse(status_code=201, content=destination.model_dump(mode="json"))


@router.get("/{integration_slug}/destinations", response_model=list[DestinationResponse])
async def list_integration_destinations(
    integration_slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DestinationResponse]:
    """List downstream destinations for an integration."""
    destinations = await list_destinations(session=session, integration_slug=integration_slug)
    if destinations is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return destinations


@router.patch(
    "/{integration_slug}/destinations/{destination_id}",
    response_model=DestinationResponse,
)
async def update_integration_destination(
    integration_slug: str,
    destination_id: str,
    request: DestinationUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DestinationResponse:
    """Update safe downstream destination metadata for an integration."""
    try:
        destination = await update_destination(
            session=session,
            integration_slug=integration_slug,
            destination_id=destination_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if destination is None:
        raise HTTPException(status_code=404, detail="destination not found")
    return destination


@router.post("/{integration_slug}/routing-rules", response_model=RoutingRuleResponse)
async def create_integration_routing_rule(
    integration_slug: str,
    request: RoutingRuleCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Create a deterministic routing rule for an integration."""
    try:
        routing_rule = await create_routing_rule(
            session=session,
            integration_slug=integration_slug,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if routing_rule is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return JSONResponse(status_code=201, content=routing_rule.model_dump(mode="json"))


@router.get("/{integration_slug}/routing-rules", response_model=list[RoutingRuleResponse])
async def list_integration_routing_rules(
    integration_slug: str,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[RoutingRuleResponse]:
    """List deterministic routing rules for an integration."""
    routing_rules = await list_routing_rules(session=session, integration_slug=integration_slug)
    if routing_rules is None:
        raise HTTPException(status_code=404, detail="integration not found")
    return routing_rules


@router.patch(
    "/{integration_slug}/routing-rules/{routing_rule_id}",
    response_model=RoutingRuleResponse,
)
async def update_integration_routing_rule(
    integration_slug: str,
    routing_rule_id: str,
    request: RoutingRuleUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> RoutingRuleResponse:
    """Update safe routing-rule metadata for an integration."""
    try:
        routing_rule = await update_routing_rule(
            session=session,
            integration_slug=integration_slug,
            routing_rule_id=routing_rule_id,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if routing_rule is None:
        raise HTTPException(status_code=404, detail="routing rule not found")
    return routing_rule
