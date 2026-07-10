"""Replay request workflow service operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.replay_requests import (
    ReplayExecutionResponse,
    ReplayRequestApproveRequest,
    ReplayRequestCreateRequest,
    ReplayRequestRejectRequest,
    ReplayRequestResponse,
)
from app.services.audit import write_audit_log
from app.services.delivery_execution import (
    cancel_pending_retry_jobs_for_delivery,
    execute_delivery,
)

_ACTIVE_REPLAY_STATUSES = {"pending", "approved", "running"}
_SUCCESS_STATUS = "resolved"
_UNRESOLVED_EXECUTED_STATUS = "executed"

logger = structlog.get_logger(__name__)


class ReplayNotFoundError(Exception):
    """Raised when a replay workflow resource does not exist."""


class ReplayConflictError(Exception):
    """Raised when a replay workflow transition is invalid."""


async def create_replay_request(
    *,
    session: AsyncSession,
    dead_letter_id: uuid.UUID,
    request: ReplayRequestCreateRequest,
    correlation_id: str | None,
) -> ReplayRequestResponse:
    """Create one pending replay request for a dead-lettered delivery."""
    context = await _load_dead_letter_context(session=session, dead_letter_id=dead_letter_id)
    if context is None:
        raise ReplayNotFoundError("dead letter not found")
    dead_letter, delivery, event = context
    if delivery.status != "dead_lettered":
        raise ReplayConflictError("dead letter delivery is not dead_lettered")
    if dead_letter.resolution_status == "resolved":
        raise ReplayConflictError("dead letter is already resolved")
    existing = await _active_replay_request_for_dead_letter(
        session=session,
        dead_letter_id=dead_letter.id,
    )
    if existing is not None:
        raise ReplayConflictError("active replay request already exists")

    replay_request = models.ReplayRequest(
        dead_letter_event_id=dead_letter.id,
        status="pending",
        request_document={
            "reason": request.reason,
            "requested_by": request.requested_by,
        },
    )
    session.add(replay_request)
    await session.flush()
    await _write_replay_audit(
        session=session,
        action="replay_request.created",
        replay_request=replay_request,
        delivery=delivery,
        dead_letter=dead_letter,
        correlation_id=correlation_id,
        metadata={"requested_by": request.requested_by},
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ReplayConflictError("active replay request already exists") from exc
    await session.refresh(replay_request)
    logger.info(
        "replay_request_created",
        replay_request_id=str(replay_request.id),
        dead_letter_id=str(dead_letter.id),
        delivery_id=str(delivery.id),
    )
    return _to_replay_response(
        replay_request=replay_request,
        dead_letter=dead_letter,
        delivery=delivery,
        event=event,
    )


async def list_replay_requests(
    *,
    session: AsyncSession,
    status: str | None = None,
    event_id: uuid.UUID | None = None,
    dead_letter_id: uuid.UUID | None = None,
) -> list[ReplayRequestResponse]:
    """Return safe replay request metadata."""
    statement = (
        select(models.ReplayRequest, models.DeadLetterEvent, models.EventDelivery, models.Event)
        .join(
            models.DeadLetterEvent,
            models.ReplayRequest.dead_letter_event_id == models.DeadLetterEvent.id,
        )
        .join(models.EventDelivery, models.DeadLetterEvent.delivery_id == models.EventDelivery.id)
        .join(models.Event, models.EventDelivery.event_id == models.Event.id)
    )
    if status is not None:
        statement = statement.where(models.ReplayRequest.status == status)
    if event_id is not None:
        statement = statement.where(models.Event.id == event_id)
    if dead_letter_id is not None:
        statement = statement.where(models.DeadLetterEvent.id == dead_letter_id)
    rows = (
        await session.execute(
            statement.order_by(
                models.ReplayRequest.created_at.desc(),
                models.ReplayRequest.id.asc(),
            )
        )
    ).all()
    return [
        _to_replay_response(
            replay_request=replay_request,
            dead_letter=dead_letter,
            delivery=delivery,
            event=event,
        )
        for replay_request, dead_letter, delivery, event in rows
    ]


async def get_replay_request(
    *,
    session: AsyncSession,
    replay_request_id: uuid.UUID,
) -> ReplayRequestResponse:
    """Return safe metadata for one replay request."""
    context = await _load_replay_context(session=session, replay_request_id=replay_request_id)
    if context is None:
        raise ReplayNotFoundError("replay request not found")
    replay_request, dead_letter, delivery, event = context
    return _to_replay_response(
        replay_request=replay_request,
        dead_letter=dead_letter,
        delivery=delivery,
        event=event,
    )


async def approve_replay_request(
    *,
    session: AsyncSession,
    replay_request_id: uuid.UUID,
    request: ReplayRequestApproveRequest,
    correlation_id: str | None,
) -> ReplayRequestResponse:
    """Approve a pending replay request."""
    context = await _load_replay_context(session=session, replay_request_id=replay_request_id)
    if context is None:
        raise ReplayNotFoundError("replay request not found")
    replay_request, dead_letter, delivery, event = context
    if replay_request.status != "pending":
        raise ReplayConflictError("only pending replay requests can be approved")
    now = datetime.now(timezone.utc)
    document = _request_document(replay_request)
    document["approved_by"] = request.approved_by
    document["approval_note"] = request.note
    replay_request.status = "approved"
    replay_request.approved_at = now
    replay_request.updated_at = now
    replay_request.request_document = document
    await _write_replay_audit(
        session=session,
        action="replay_request.approved",
        replay_request=replay_request,
        delivery=delivery,
        dead_letter=dead_letter,
        correlation_id=correlation_id,
        metadata={"approved_by": request.approved_by},
    )
    await session.commit()
    return _to_replay_response(
        replay_request=replay_request,
        dead_letter=dead_letter,
        delivery=delivery,
        event=event,
    )


async def reject_replay_request(
    *,
    session: AsyncSession,
    replay_request_id: uuid.UUID,
    request: ReplayRequestRejectRequest,
    correlation_id: str | None,
) -> ReplayRequestResponse:
    """Reject a pending or not-yet-running approved replay request."""
    context = await _load_replay_context(session=session, replay_request_id=replay_request_id)
    if context is None:
        raise ReplayNotFoundError("replay request not found")
    replay_request, dead_letter, delivery, event = context
    if replay_request.status not in {"pending", "approved"}:
        raise ReplayConflictError("replay request cannot be rejected")
    now = datetime.now(timezone.utc)
    document = _request_document(replay_request)
    document["rejected_by"] = request.rejected_by
    document["rejection_reason"] = request.reason
    replay_request.status = "rejected"
    replay_request.updated_at = now
    replay_request.request_document = document
    await _write_replay_audit(
        session=session,
        action="replay_request.rejected",
        replay_request=replay_request,
        delivery=delivery,
        dead_letter=dead_letter,
        correlation_id=correlation_id,
        metadata={"rejected_by": request.rejected_by},
    )
    await session.commit()
    return _to_replay_response(
        replay_request=replay_request,
        dead_letter=dead_letter,
        delivery=delivery,
        event=event,
    )


async def execute_replay_request(
    *,
    session: AsyncSession,
    replay_request_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    correlation_id: str | None,
) -> ReplayExecutionResponse:
    """Execute one approved replay request through the delivery execution path."""
    context = await _load_replay_context(session=session, replay_request_id=replay_request_id)
    if context is None:
        raise ReplayNotFoundError("replay request not found")
    replay_request, dead_letter, delivery, _event = context
    if replay_request.status != "approved":
        raise ReplayConflictError("only approved replay requests can be executed")
    if dead_letter.resolution_status == "resolved":
        raise ReplayConflictError("dead letter is already resolved")

    now = datetime.now(timezone.utc)
    replay_request.status = "running"
    replay_request.updated_at = now
    delivery.status = "failed"
    delivery.next_attempt_at = now
    delivery.delivered_at = None
    await cancel_pending_retry_jobs_for_delivery(session=session, delivery_id=delivery.id, now=now)
    await session.commit()

    attempts_before = await _delivery_attempt_count(session=session, delivery_id=delivery.id)
    delivery_result = await execute_delivery(
        session=session,
        delivery_id=delivery.id,
        http_client=http_client,
        now=now,
    )
    attempts_after = await _delivery_attempt_count(session=session, delivery_id=delivery.id)
    attempt_recorded = attempts_after > attempts_before
    finished_at = datetime.now(timezone.utc)
    refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
    refreshed_dead_letter = await session.get(models.DeadLetterEvent, dead_letter.id)
    if refreshed_delivery is None or refreshed_dead_letter is None:
        raise ReplayConflictError("replay target no longer exists")

    if delivery_result.response is not None and refreshed_delivery.status == "delivered":
        replay_request.status = _SUCCESS_STATUS
        replay_request.executed_at = finished_at
        replay_request.resolved_at = finished_at
        replay_request.updated_at = finished_at
        refreshed_dead_letter.resolution_status = "resolved"
        refreshed_dead_letter.resolved_at = finished_at
        refreshed_dead_letter.updated_at = finished_at
        await _write_replay_audit(
            session=session,
            action="replay_request.executed",
            replay_request=replay_request,
            delivery=refreshed_delivery,
            dead_letter=refreshed_dead_letter,
            correlation_id=correlation_id,
            metadata={"delivery_status": refreshed_delivery.status},
        )
        await _write_replay_audit(
            session=session,
            action="replay_request.resolved",
            replay_request=replay_request,
            delivery=refreshed_delivery,
            dead_letter=refreshed_dead_letter,
            correlation_id=correlation_id,
            metadata={"delivery_status": refreshed_delivery.status},
        )
        dead_letter_resolved = True
    else:
        replay_request.status = _UNRESOLVED_EXECUTED_STATUS
        replay_request.executed_at = finished_at
        replay_request.updated_at = finished_at
        await _write_replay_audit(
            session=session,
            action="replay_request.executed",
            replay_request=replay_request,
            delivery=refreshed_delivery,
            dead_letter=refreshed_dead_letter,
            correlation_id=correlation_id,
            metadata={"delivery_status": refreshed_delivery.status},
        )
        await _write_replay_audit(
            session=session,
            action="replay_request.executed_unresolved",
            replay_request=replay_request,
            delivery=refreshed_delivery,
            dead_letter=refreshed_dead_letter,
            correlation_id=correlation_id,
            metadata={"delivery_status": refreshed_delivery.status},
        )
        dead_letter_resolved = False

    await session.commit()
    logger.info(
        "replay_request_executed",
        replay_request_id=str(replay_request.id),
        delivery_id=str(refreshed_delivery.id),
        replay_status=replay_request.status,
        delivery_status=refreshed_delivery.status,
    )
    return ReplayExecutionResponse(
        replay_request_id=replay_request.id,
        delivery_id=refreshed_delivery.id,
        replay_status=replay_request.status,
        delivery_status=refreshed_delivery.status,
        attempt_recorded=attempt_recorded,
        dead_letter_resolved=dead_letter_resolved,
    )


async def _load_dead_letter_context(
    *,
    session: AsyncSession,
    dead_letter_id: uuid.UUID,
) -> tuple[models.DeadLetterEvent, models.EventDelivery, models.Event] | None:
    row = (
        await session.execute(
            select(models.DeadLetterEvent, models.EventDelivery, models.Event)
            .join(
                models.EventDelivery,
                models.DeadLetterEvent.delivery_id == models.EventDelivery.id,
            )
            .join(models.Event, models.EventDelivery.event_id == models.Event.id)
            .where(models.DeadLetterEvent.id == dead_letter_id)
        )
    ).one_or_none()
    if row is None:
        return None
    dead_letter, delivery, event = row
    return dead_letter, delivery, event


async def _load_replay_context(
    *,
    session: AsyncSession,
    replay_request_id: uuid.UUID,
) -> tuple[models.ReplayRequest, models.DeadLetterEvent, models.EventDelivery, models.Event] | None:
    row = (
        await session.execute(
            select(models.ReplayRequest, models.DeadLetterEvent, models.EventDelivery, models.Event)
            .join(
                models.DeadLetterEvent,
                models.ReplayRequest.dead_letter_event_id == models.DeadLetterEvent.id,
            )
            .join(
                models.EventDelivery,
                models.DeadLetterEvent.delivery_id == models.EventDelivery.id,
            )
            .join(models.Event, models.EventDelivery.event_id == models.Event.id)
            .where(models.ReplayRequest.id == replay_request_id)
        )
    ).one_or_none()
    if row is None:
        return None
    replay_request, dead_letter, delivery, event = row
    return replay_request, dead_letter, delivery, event


async def _active_replay_request_for_dead_letter(
    *,
    session: AsyncSession,
    dead_letter_id: uuid.UUID,
) -> models.ReplayRequest | None:
    return await session.scalar(
        select(models.ReplayRequest).where(
            models.ReplayRequest.dead_letter_event_id == dead_letter_id,
            models.ReplayRequest.status.in_(_ACTIVE_REPLAY_STATUSES),
        )
    )


async def _delivery_attempt_count(*, session: AsyncSession, delivery_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(models.DeliveryAttempt)
        .where(models.DeliveryAttempt.delivery_id == delivery_id)
    )
    return int(count or 0)


async def _write_replay_audit(
    *,
    session: AsyncSession,
    action: str,
    replay_request: models.ReplayRequest,
    delivery: models.EventDelivery,
    dead_letter: models.DeadLetterEvent,
    correlation_id: str | None,
    metadata: dict[str, Any],
) -> None:
    await write_audit_log(
        session=session,
        action=action,
        resource_type="replay_request",
        resource_id=replay_request.id,
        correlation_id=correlation_id,
        document={
            "replay_request_id": str(replay_request.id),
            "dead_letter_id": str(dead_letter.id),
            "delivery_id": str(delivery.id),
            "status": replay_request.status,
            **metadata,
        },
    )


def _to_replay_response(
    *,
    replay_request: models.ReplayRequest,
    dead_letter: models.DeadLetterEvent,
    delivery: models.EventDelivery,
    event: models.Event,
) -> ReplayRequestResponse:
    document = _request_document(replay_request)
    return ReplayRequestResponse(
        replay_request_id=replay_request.id,
        status=replay_request.status,
        event_id=event.id,
        delivery_id=delivery.id,
        dead_letter_id=dead_letter.id,
        reason=_string_or_none(document.get("reason")),
        requested_by=_string_or_none(document.get("requested_by")),
        approved_by=_string_or_none(document.get("approved_by")),
        rejected_by=_string_or_none(document.get("rejected_by")),
        created_at=replay_request.created_at,
        updated_at=replay_request.updated_at,
        executed_at=replay_request.executed_at,
        resolved_at=replay_request.resolved_at,
    )


def _request_document(replay_request: models.ReplayRequest) -> dict[str, Any]:
    if isinstance(replay_request.request_document, dict):
        return dict(replay_request.request_document)
    return {}


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None
