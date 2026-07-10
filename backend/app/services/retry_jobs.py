"""Retry job service operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.delivery_execution import RetryJobExecutionResponse, RetryJobResponse
from app.services.delivery_execution import delivery_needs_no_retry, execute_delivery

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RetryJobExecutionResult:
    """Service result for retry job execution."""

    status_code: int
    detail: str | None
    response: RetryJobExecutionResponse | None


async def execute_retry_job(
    *,
    session: AsyncSession,
    retry_job_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    now: datetime | None = None,
) -> RetryJobExecutionResult:
    """Claim and execute one due retry job."""
    current_time = now or datetime.now(timezone.utc)
    retry_job = await session.scalar(
        select(models.RetryJob).where(models.RetryJob.id == retry_job_id)
    )
    if retry_job is None:
        return RetryJobExecutionResult(status_code=404, detail="retry job not found", response=None)
    if retry_job.status != "pending":
        return RetryJobExecutionResult(
            status_code=409,
            detail="retry job is not pending",
            response=None,
        )
    if retry_job.run_at > current_time:
        return RetryJobExecutionResult(
            status_code=409,
            detail="retry job is not due",
            response=None,
        )
    delivery = await session.get(models.EventDelivery, retry_job.delivery_id)
    if delivery is None or delivery_needs_no_retry(delivery):
        retry_job.status = "cancelled"
        await session.commit()
        return RetryJobExecutionResult(
            status_code=409,
            detail="retry job delivery is no longer executable",
            response=None,
        )

    retry_job.status = "claimed"
    retry_job.claimed_at = current_time
    retry_job.locked_at = current_time
    retry_job.attempts += 1
    await session.commit()

    delivery_result = await execute_delivery(
        session=session,
        delivery_id=retry_job.delivery_id,
        http_client=http_client,
        now=current_time,
    )
    if delivery_result.response is None:
        retry_job.status = "cancelled"
        await session.commit()
        return RetryJobExecutionResult(
            status_code=delivery_result.status_code,
            detail=delivery_result.detail,
            response=None,
        )

    retry_job.status = "completed"
    retry_job.completed_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "retry_job_completed",
        retry_job_id=str(retry_job.id),
        delivery_id=str(retry_job.delivery_id),
        delivery_status=delivery_result.response.status,
    )
    return RetryJobExecutionResult(
        status_code=200,
        detail=None,
        response=RetryJobExecutionResponse(
            retry_job_id=retry_job.id,
            delivery_id=retry_job.delivery_id,
            retry_status=retry_job.status,
            delivery_status=delivery_result.response.status,
        ),
    )


async def list_retry_jobs_for_delivery(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
) -> list[RetryJobResponse] | None:
    """Return safe retry job metadata for a delivery."""
    delivery_exists = await session.scalar(
        select(models.EventDelivery.id).where(models.EventDelivery.id == delivery_id)
    )
    if delivery_exists is None:
        return None
    retry_jobs = (
        await session.scalars(
            select(models.RetryJob)
            .where(models.RetryJob.delivery_id == delivery_id)
            .order_by(models.RetryJob.run_at.asc(), models.RetryJob.id.asc())
        )
    ).all()
    return [_to_retry_job_response(retry_job) for retry_job in retry_jobs]


def _to_retry_job_response(retry_job: models.RetryJob) -> RetryJobResponse:
    return RetryJobResponse(
        retry_job_id=retry_job.id,
        delivery_id=retry_job.delivery_id,
        status=retry_job.status,
        run_at=retry_job.run_at,
        claimed_at=retry_job.claimed_at,
        completed_at=retry_job.completed_at,
        created_at=retry_job.created_at,
        updated_at=retry_job.updated_at,
    )
