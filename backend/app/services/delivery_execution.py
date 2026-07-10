"""HTTP delivery execution service operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.delivery_execution import DeliveryAttemptResponse, DeliveryExecutionResponse
from app.services.destinations import unpack_destination_settings

_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF_SECONDS = [60, 300]
_EXECUTABLE_STATUSES = {"scheduled", "failed"}
_CONFLICT_STATUSES = {"delivered", "dead_lettered", "cancelled", "in_progress", "succeeded"}
_NO_RETRY_NEEDED_STATUSES = {"delivered", "dead_lettered", "cancelled"}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 405, 409, 410, 422}

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeliveryExecutionResult:
    """Service result for delivery execution."""

    status_code: int
    detail: str | None
    response: DeliveryExecutionResponse | None


@dataclass(frozen=True)
class _HttpOutcome:
    outcome: str
    response_status_code: int | None
    error_code: str | None
    error_message: str | None
    is_retryable: bool
    is_success: bool
    severity: str | None = None


async def execute_delivery(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    now: datetime | None = None,
) -> DeliveryExecutionResult:
    """Execute one due scheduled delivery and persist the result."""
    current_time = now or datetime.now(timezone.utc)
    delivery = await session.scalar(
        select(models.EventDelivery).where(models.EventDelivery.id == delivery_id)
    )
    if delivery is None:
        return DeliveryExecutionResult(status_code=404, detail="delivery not found", response=None)
    conflict = _validate_delivery_executable(delivery=delivery, now=current_time)
    if conflict is not None:
        return conflict

    event = await session.get(models.Event, delivery.event_id)
    destination = await session.get(models.DownstreamDestination, delivery.destination_id)
    event_payload = await session.scalar(
        select(models.EventPayload).where(models.EventPayload.event_id == delivery.event_id)
    )
    if event is None or destination is None or event_payload is None:
        return DeliveryExecutionResult(
            status_code=409,
            detail="delivery is missing required execution metadata",
            response=None,
        )

    destination_settings = unpack_destination_settings(destination.configuration)
    timeout_seconds = _configured_timeout_seconds(destination_settings)
    max_attempts = _configured_max_attempts(destination_settings)
    backoff_seconds = _configured_backoff_seconds(destination_settings)
    attempt_number = await _next_attempt_number(session=session, delivery_id=delivery.id)

    started_at = current_time
    outcome = await _post_payload(
        http_client=http_client,
        endpoint_url=destination.endpoint_url,
        payload=event_payload.payload,
        timeout_seconds=timeout_seconds,
    )
    finished_at = datetime.now(timezone.utc)
    retry_scheduled = False
    dead_lettered = False
    next_attempt_at: datetime | None = None

    if outcome.is_success:
        _mark_delivery_delivered(delivery=delivery, now=finished_at, attempt_number=attempt_number)
        await cancel_pending_retry_jobs_for_delivery(
            session=session,
            delivery_id=delivery.id,
            now=finished_at,
        )
        await _mark_event_delivered_when_complete(session=session, event=event, now=finished_at)
    elif outcome.is_retryable and attempt_number < max_attempts:
        next_attempt_at = finished_at + timedelta(
            seconds=_backoff_for_attempt(
                attempt_number=attempt_number,
                backoff_seconds=backoff_seconds,
            )
        )
        _mark_delivery_failed(
            delivery=delivery,
            outcome=outcome,
            now=finished_at,
            attempt_number=attempt_number,
            next_attempt_at=next_attempt_at,
        )
        retry_scheduled = await _create_pending_retry_job(
            session=session,
            delivery_id=delivery.id,
            run_at=next_attempt_at,
        )
    else:
        _mark_delivery_dead_lettered(
            delivery=delivery,
            outcome=outcome,
            now=finished_at,
            attempt_number=attempt_number,
        )
        await _create_dead_letter(
            session=session,
            delivery_id=delivery.id,
            outcome=outcome,
            exhausted=outcome.is_retryable,
        )
        await cancel_pending_retry_jobs_for_delivery(
            session=session,
            delivery_id=delivery.id,
            now=finished_at,
        )
        dead_lettered = True

    session.add(
        models.DeliveryAttempt(
            delivery_id=delivery.id,
            attempt_number=attempt_number,
            status="succeeded" if outcome.is_success else "failed",
            outcome=outcome.outcome,
            started_at=started_at,
            completed_at=finished_at,
            request_headers={"content-type": "application/json"},
            response_status_code=outcome.response_status_code,
            response_headers=None,
            error_code=outcome.error_code,
            error_message=outcome.error_message,
            is_retryable=outcome.is_retryable,
        )
    )
    await session.commit()
    logger.info(
        "delivery_execution_completed",
        delivery_id=str(delivery.id),
        status=delivery.status,
        attempt_number=attempt_number,
        retry_scheduled=retry_scheduled,
        dead_lettered=dead_lettered,
    )
    return DeliveryExecutionResult(
        status_code=200,
        detail=None,
        response=DeliveryExecutionResponse(
            delivery_id=delivery.id,
            status=delivery.status,
            attempt_number=attempt_number,
            retry_scheduled=retry_scheduled,
            dead_lettered=dead_lettered,
            next_attempt_at=next_attempt_at,
        ),
    )


async def list_delivery_attempts(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
) -> list[DeliveryAttemptResponse] | None:
    """Return safe attempt metadata for a delivery."""
    delivery_exists = await session.scalar(
        select(models.EventDelivery.id).where(models.EventDelivery.id == delivery_id)
    )
    if delivery_exists is None:
        return None
    attempts = (
        await session.scalars(
            select(models.DeliveryAttempt)
            .where(models.DeliveryAttempt.delivery_id == delivery_id)
            .order_by(
                models.DeliveryAttempt.attempt_number.asc(),
                models.DeliveryAttempt.id.asc(),
            )
        )
    ).all()
    return [_to_attempt_response(attempt) for attempt in attempts]


async def cancel_pending_retry_jobs_for_delivery(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
    now: datetime,
) -> None:
    """Cancel pending retry jobs when a delivery no longer needs retry execution."""
    await session.execute(
        update(models.RetryJob)
        .where(
            models.RetryJob.delivery_id == delivery_id,
            models.RetryJob.status == "pending",
        )
        .values(status="cancelled", updated_at=now)
    )


def delivery_needs_no_retry(delivery: models.EventDelivery) -> bool:
    """Return whether a delivery is terminal for retry-job purposes."""
    return delivery.status in _NO_RETRY_NEEDED_STATUSES


def _to_attempt_response(attempt: models.DeliveryAttempt) -> DeliveryAttemptResponse:
    return DeliveryAttemptResponse(
        attempt_id=attempt.id,
        delivery_id=attempt.delivery_id,
        attempt_number=attempt.attempt_number,
        outcome=attempt.outcome,
        response_status_code=attempt.response_status_code,
        error_code=attempt.error_code,
        error_message=attempt.error_message,
        is_retryable=attempt.is_retryable,
        started_at=attempt.started_at,
        finished_at=attempt.completed_at,
        created_at=attempt.created_at,
    )


def _validate_delivery_executable(
    *,
    delivery: models.EventDelivery,
    now: datetime,
) -> DeliveryExecutionResult | None:
    if delivery.status in _CONFLICT_STATUSES or delivery.status not in _EXECUTABLE_STATUSES:
        return DeliveryExecutionResult(
            status_code=409,
            detail="delivery is not executable",
            response=None,
        )
    if delivery.next_attempt_at is not None and delivery.next_attempt_at > now:
        return DeliveryExecutionResult(
            status_code=409,
            detail="delivery is not due",
            response=None,
        )
    return None


async def _post_payload(
    *,
    http_client: httpx.AsyncClient,
    endpoint_url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> _HttpOutcome:
    try:
        response = await http_client.post(
            endpoint_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException:
        return _HttpOutcome(
            outcome="timed_out",
            response_status_code=None,
            error_code="timeout",
            error_message="downstream request timed out",
            is_retryable=True,
            is_success=False,
        )
    except httpx.RequestError:
        return _HttpOutcome(
            outcome="failed",
            response_status_code=None,
            error_code="network_error",
            error_message="downstream request failed",
            is_retryable=True,
            is_success=False,
        )

    status_code = response.status_code
    if 200 <= status_code <= 299:
        return _HttpOutcome(
            outcome="succeeded",
            response_status_code=status_code,
            error_code=None,
            error_message=None,
            is_retryable=False,
            is_success=True,
        )
    if status_code in _RETRYABLE_STATUS_CODES:
        return _HttpOutcome(
            outcome="failed",
            response_status_code=status_code,
            error_code=f"http_{status_code}",
            error_message=f"downstream returned HTTP {status_code}",
            is_retryable=True,
            is_success=False,
            severity="critical",
        )
    severity = "high" if status_code in _NON_RETRYABLE_STATUS_CODES else "medium"
    return _HttpOutcome(
        outcome="failed",
        response_status_code=status_code,
        error_code=f"http_{status_code}",
        error_message=f"downstream returned HTTP {status_code}",
        is_retryable=False,
        is_success=False,
        severity=severity,
    )


async def _next_attempt_number(*, session: AsyncSession, delivery_id: uuid.UUID) -> int:
    max_attempt = await session.scalar(
        select(func.max(models.DeliveryAttempt.attempt_number)).where(
            models.DeliveryAttempt.delivery_id == delivery_id
        )
    )
    return int(max_attempt or 0) + 1


def _mark_delivery_delivered(
    *,
    delivery: models.EventDelivery,
    now: datetime,
    attempt_number: int,
) -> None:
    delivery.status = "delivered"
    delivery.attempt_count = attempt_number
    delivery.last_attempt_at = now
    delivery.delivered_at = now
    delivery.next_attempt_at = None
    delivery.last_error_code = None
    delivery.last_error_message = None


def _mark_delivery_failed(
    *,
    delivery: models.EventDelivery,
    outcome: _HttpOutcome,
    now: datetime,
    attempt_number: int,
    next_attempt_at: datetime,
) -> None:
    delivery.status = "failed"
    delivery.attempt_count = attempt_number
    delivery.last_attempt_at = now
    delivery.next_attempt_at = next_attempt_at
    delivery.last_error_code = outcome.error_code
    delivery.last_error_message = outcome.error_message


def _mark_delivery_dead_lettered(
    *,
    delivery: models.EventDelivery,
    outcome: _HttpOutcome,
    now: datetime,
    attempt_number: int,
) -> None:
    delivery.status = "dead_lettered"
    delivery.attempt_count = attempt_number
    delivery.last_attempt_at = now
    delivery.next_attempt_at = None
    delivery.last_error_code = outcome.error_code
    delivery.last_error_message = outcome.error_message


async def _create_pending_retry_job(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
    run_at: datetime,
) -> bool:
    statement = (
        pg_insert(models.RetryJob)
        .values(
            id=uuid.uuid4(),
            delivery_id=delivery_id,
            status="pending",
            run_at=run_at,
            attempts=0,
        )
        .on_conflict_do_nothing(
            index_elements=[
                models.RetryJob.delivery_id,
                models.RetryJob.run_at,
            ],
            index_where=models.RetryJob.status == "pending",
        )
        .returning(models.RetryJob.id)
    )
    return (await session.scalar(statement)) is not None


async def _create_dead_letter(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
    outcome: _HttpOutcome,
    exhausted: bool,
) -> None:
    reason_code = "retry_exhausted" if exhausted else outcome.error_code or "delivery_failed"
    reason_message = (
        "retry attempts exhausted" if exhausted else outcome.error_message or "delivery failed"
    )
    severity = _dead_letter_severity(outcome=outcome, exhausted=exhausted)
    statement = (
        pg_insert(models.DeadLetterEvent)
        .values(
            id=uuid.uuid4(),
            delivery_id=delivery_id,
            resolution_status="open",
            severity=severity,
            reason=reason_message,
            reason_code=reason_code,
            reason_message=reason_message,
            context_document={
                "response_status_code": outcome.response_status_code,
                "retryable_failure": outcome.is_retryable,
            },
        )
        .on_conflict_do_nothing(index_elements=[models.DeadLetterEvent.delivery_id])
    )
    await session.execute(statement)


def _dead_letter_severity(*, outcome: _HttpOutcome, exhausted: bool) -> str:
    if exhausted:
        return "critical"
    if outcome.severity in {"critical", "high", "medium"}:
        return outcome.severity
    return "medium"


async def _mark_event_delivered_when_complete(
    *,
    session: AsyncSession,
    event: models.Event,
    now: datetime,
) -> None:
    remaining_count = await session.scalar(
        select(func.count())
        .select_from(models.EventDelivery)
        .where(
            models.EventDelivery.event_id == event.id,
            models.EventDelivery.status != "delivered",
        )
    )
    if int(remaining_count or 0) != 0 or event.status == "delivered":
        return
    from_status = event.status
    event.status = "delivered"
    session.add(
        models.EventStateTransition(
            event_id=event.id,
            from_status=from_status,
            to_status="delivered",
            reason="all deliveries delivered",
            transition_metadata={"phase": "delivery_execution"},
            created_at=now,
        )
    )


def _configured_timeout_seconds(settings: dict[str, Any]) -> float:
    timeout = settings.get("timeout_seconds")
    if isinstance(timeout, int | float) and not isinstance(timeout, bool) and timeout > 0:
        return float(timeout)
    if timeout is not None:
        logger.warning("invalid_destination_timeout_seconds")
    return _DEFAULT_TIMEOUT_SECONDS


def _configured_max_attempts(settings: dict[str, Any]) -> int:
    max_attempts = settings.get("max_attempts")
    if isinstance(max_attempts, int) and max_attempts > 0:
        return max_attempts
    if max_attempts is not None:
        logger.warning("invalid_destination_max_attempts")
    return _DEFAULT_MAX_ATTEMPTS


def _configured_backoff_seconds(settings: dict[str, Any]) -> list[int]:
    backoff = settings.get("retry_backoff_seconds")
    if (
        isinstance(backoff, list)
        and backoff
        and all(isinstance(seconds, int) and seconds > 0 for seconds in backoff)
    ):
        return backoff
    if backoff is not None:
        logger.warning("invalid_destination_retry_backoff_seconds")
    return _DEFAULT_BACKOFF_SECONDS


def _backoff_for_attempt(*, attempt_number: int, backoff_seconds: list[int]) -> int:
    index = max(0, attempt_number - 1)
    if index >= len(backoff_seconds):
        return backoff_seconds[-1]
    return backoff_seconds[index]
