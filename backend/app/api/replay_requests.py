"""Replay request workflow routes."""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.delivery_execution import get_delivery_http_client
from app.core.correlation import CORRELATION_ID_HEADER
from app.db.session import get_async_session
from app.schemas.replay_requests import (
    ReplayExecutionResponse,
    ReplayRequestApproveRequest,
    ReplayRequestCreateRequest,
    ReplayRequestRejectRequest,
    ReplayRequestResponse,
)
from app.services.replay_requests import (
    ReplayConflictError,
    ReplayNotFoundError,
    approve_replay_request,
    create_replay_request,
    execute_replay_request,
    get_replay_request,
    list_replay_requests,
    reject_replay_request,
)

router = APIRouter(prefix="/api/v1", tags=["replay requests"])


@router.post(
    "/dead-letters/{dead_letter_id}/replay-requests",
    response_model=ReplayRequestResponse,
)
async def create_dead_letter_replay_request(
    dead_letter_id: UUID,
    replay_request: ReplayRequestCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Create a pending replay request for a dead letter."""
    try:
        response = await create_replay_request(
            session=session,
            dead_letter_id=dead_letter_id,
            request=replay_request,
            correlation_id=_correlation_id_from_request(request),
        )
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(status_code=201, content=response.model_dump(mode="json"))


@router.get("/replay-requests", response_model=list[ReplayRequestResponse])
async def list_replay_request_metadata(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status: Annotated[str | None, Query()] = None,
    event_id: Annotated[UUID | None, Query()] = None,
    dead_letter_id: Annotated[UUID | None, Query()] = None,
) -> list[ReplayRequestResponse]:
    """List safe replay request metadata."""
    return await list_replay_requests(
        session=session,
        status=status,
        event_id=event_id,
        dead_letter_id=dead_letter_id,
    )


@router.get("/replay-requests/{replay_request_id}", response_model=ReplayRequestResponse)
async def read_replay_request_metadata(
    replay_request_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReplayRequestResponse:
    """Return safe replay request metadata."""
    try:
        return await get_replay_request(session=session, replay_request_id=replay_request_id)
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/replay-requests/{replay_request_id}/approve", response_model=ReplayRequestResponse)
async def approve_replay_request_route(
    replay_request_id: UUID,
    approval: ReplayRequestApproveRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReplayRequestResponse:
    """Approve a pending replay request."""
    try:
        return await approve_replay_request(
            session=session,
            replay_request_id=replay_request_id,
            request=approval,
            correlation_id=_correlation_id_from_request(request),
        )
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/replay-requests/{replay_request_id}/reject", response_model=ReplayRequestResponse)
async def reject_replay_request_route(
    replay_request_id: UUID,
    rejection: ReplayRequestRejectRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReplayRequestResponse:
    """Reject a replay request that has not started running."""
    try:
        return await reject_replay_request(
            session=session,
            replay_request_id=replay_request_id,
            request=rejection,
            correlation_id=_correlation_id_from_request(request),
        )
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/replay-requests/{replay_request_id}/execute", response_model=ReplayExecutionResponse)
async def execute_replay_request_route(
    replay_request_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_delivery_http_client)],
) -> ReplayExecutionResponse:
    """Execute an approved replay request."""
    try:
        return await execute_replay_request(
            session=session,
            replay_request_id=replay_request_id,
            http_client=http_client,
            correlation_id=_correlation_id_from_request(request),
        )
    except ReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _correlation_id_from_request(request: Request) -> str | None:
    return request.headers.get(CORRELATION_ID_HEADER)
