"""Dead-letter metadata service operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.delivery_execution import DeadLetterResponse

_ALLOWED_RESOLUTION_STATUSES = {"open", "acknowledged", "resolved"}
_ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


async def list_dead_letters(
    *,
    session: AsyncSession,
    resolution_status: str | None = None,
    severity: str | None = None,
) -> list[DeadLetterResponse]:
    """Return safe dead-letter metadata with optional safe filters."""
    if resolution_status is not None and resolution_status not in _ALLOWED_RESOLUTION_STATUSES:
        raise ValueError("invalid resolution_status")
    if severity is not None and severity not in _ALLOWED_SEVERITIES:
        raise ValueError("invalid severity")

    statement = select(models.DeadLetterEvent)
    if resolution_status is not None:
        statement = statement.where(models.DeadLetterEvent.resolution_status == resolution_status)
    if severity is not None:
        statement = statement.where(models.DeadLetterEvent.severity == severity)
    dead_letters = (
        await session.scalars(
            statement.order_by(
                models.DeadLetterEvent.dead_lettered_at.desc(),
                models.DeadLetterEvent.id.asc(),
            )
        )
    ).all()
    return [_to_dead_letter_response(dead_letter) for dead_letter in dead_letters]


def _to_dead_letter_response(dead_letter: models.DeadLetterEvent) -> DeadLetterResponse:
    return DeadLetterResponse(
        dead_letter_id=dead_letter.id,
        delivery_id=dead_letter.delivery_id,
        severity=dead_letter.severity,
        reason_code=dead_letter.reason_code,
        reason_message=dead_letter.reason_message,
        resolution_status=dead_letter.resolution_status,
        dead_lettered_at=dead_letter.dead_lettered_at,
        resolved_at=dead_letter.resolved_at,
        created_at=dead_letter.created_at,
        updated_at=dead_letter.updated_at,
    )
