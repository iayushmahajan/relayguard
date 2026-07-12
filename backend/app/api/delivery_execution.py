"""Delivery execution, retry job, attempt, and dead-letter routes."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.schemas.delivery_execution import (
    DeadLetterResponse,
    DeliveryAttemptResponse,
    DeliveryExecutionResponse,
    RetryJobExecutionResponse,
    RetryJobResponse,
)
from app.schemas.routing import RecentDeliveryResponse
from app.services.dead_letters import list_dead_letters
from app.services.deliveries import list_recent_deliveries
from app.services.delivery_execution import execute_delivery, list_delivery_attempts
from app.services.retry_jobs import execute_retry_job, list_retry_jobs_for_delivery

router = APIRouter(prefix="/api/v1", tags=["delivery execution"])


async def get_delivery_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield the runtime HTTP client used for downstream deliveries."""
    async with httpx.AsyncClient() as client:
        yield client


@router.get("/deliveries", response_model=list[RecentDeliveryResponse])
async def list_recent_delivery_metadata(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    status: Annotated[str | None, Query()] = None,
    event_id: Annotated[UUID | None, Query()] = None,
) -> list[RecentDeliveryResponse]:
    """List recent safe delivery metadata without payloads or response bodies."""
    return await list_recent_deliveries(
        session=session,
        limit=limit,
        status=status,
        event_id=event_id,
    )


@router.post("/deliveries/{delivery_id}/execute", response_model=DeliveryExecutionResponse)
async def execute_scheduled_delivery(
    delivery_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_delivery_http_client)],
) -> JSONResponse:
    """Execute one due scheduled delivery."""
    result = await execute_delivery(
        session=session,
        delivery_id=delivery_id,
        http_client=http_client,
    )
    if result.response is None:
        raise HTTPException(status_code=result.status_code, detail=result.detail)
    return JSONResponse(
        status_code=result.status_code,
        content=result.response.model_dump(mode="json"),
    )


@router.post("/retry-jobs/{retry_job_id}/execute", response_model=RetryJobExecutionResponse)
async def execute_due_retry_job(
    retry_job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    http_client: Annotated[httpx.AsyncClient, Depends(get_delivery_http_client)],
) -> JSONResponse:
    """Execute one due retry job."""
    result = await execute_retry_job(
        session=session,
        retry_job_id=retry_job_id,
        http_client=http_client,
    )
    if result.response is None:
        raise HTTPException(status_code=result.status_code, detail=result.detail)
    return JSONResponse(
        status_code=result.status_code,
        content=result.response.model_dump(mode="json"),
    )


@router.get("/deliveries/{delivery_id}/retry-jobs", response_model=list[RetryJobResponse])
async def list_delivery_retry_jobs(
    delivery_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[RetryJobResponse]:
    """List safe retry job metadata for a delivery."""
    retry_jobs = await list_retry_jobs_for_delivery(session=session, delivery_id=delivery_id)
    if retry_jobs is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    return retry_jobs


@router.get("/deliveries/{delivery_id}/attempts", response_model=list[DeliveryAttemptResponse])
async def list_delivery_attempt_metadata(
    delivery_id: UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[DeliveryAttemptResponse]:
    """List safe attempt metadata for a delivery."""
    attempts = await list_delivery_attempts(session=session, delivery_id=delivery_id)
    if attempts is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    return attempts


@router.get("/dead-letters", response_model=list[DeadLetterResponse])
async def list_dead_letter_metadata(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    resolution_status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
) -> list[DeadLetterResponse]:
    """List safe dead-letter metadata."""
    try:
        return await list_dead_letters(
            session=session,
            resolution_status=resolution_status,
            severity=severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
