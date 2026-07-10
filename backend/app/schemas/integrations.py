"""Integration management API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

_ALLOWED_INTEGRATION_STATUSES = {"active", "disabled"}


class IntegrationStatusUpdateRequest(BaseModel):
    """Request body for dashboard-safe integration status updates."""

    status: StrictStr

    model_config = ConfigDict(extra="forbid")

    @field_validator("status", mode="before")
    @classmethod
    def trim_status(cls, value: object) -> object:
        """Trim status before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Allow only dashboard-supported integration statuses."""
        if value not in _ALLOWED_INTEGRATION_STATUSES:
            raise ValueError("must be active or disabled")
        return value


class IntegrationResponse(BaseModel):
    """Safe integration metadata."""

    integration_id: UUID
    slug: str
    name: str
    status: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
