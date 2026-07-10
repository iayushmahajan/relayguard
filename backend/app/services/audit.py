"""Safe audit log helpers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models


async def write_audit_log(
    *,
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    document: dict[str, Any],
    correlation_id: str | None,
) -> None:
    """Write one safe audit log entry without payload or secret material."""
    session.add(
        models.AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            audit_document=document,
        )
    )
