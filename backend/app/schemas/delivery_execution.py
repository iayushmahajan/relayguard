"""Delivery execution, retry, and dead-letter API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DeliveryExecutionResponse(BaseModel):
    """Safe metadata returned after one delivery execution attempt."""

    delivery_id: UUID
    status: str
    attempt_number: int
    retry_scheduled: bool
    dead_lettered: bool
    next_attempt_at: datetime | None


class RetryJobExecutionResponse(BaseModel):
    """Safe metadata returned after one retry job execution."""

    retry_job_id: UUID
    delivery_id: UUID
    retry_status: str
    delivery_status: str


class RetryJobResponse(BaseModel):
    """Safe retry job metadata."""

    retry_job_id: UUID
    delivery_id: UUID
    status: str
    run_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DeliveryAttemptResponse(BaseModel):
    """Safe delivery attempt metadata."""

    attempt_id: UUID
    delivery_id: UUID
    attempt_number: int
    outcome: str
    response_status_code: int | None
    error_code: str | None
    error_message: str | None
    is_retryable: bool
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class DeadLetterResponse(BaseModel):
    """Safe dead-letter event metadata."""

    dead_letter_id: UUID
    delivery_id: UUID
    severity: str
    reason_code: str
    reason_message: str
    resolution_status: str
    dead_lettered_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
