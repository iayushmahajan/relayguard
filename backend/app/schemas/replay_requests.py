"""Replay request API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class ReplayRequestCreateRequest(BaseModel):
    """Request body for creating a replay request from a dead letter."""

    reason: StrictStr = Field(max_length=1000)
    requested_by: StrictStr = Field(max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reason", "requested_by", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("reason", "requested_by")
    @classmethod
    def reject_empty_string(cls, value: str) -> str:
        """Reject empty strings."""
        if value == "":
            raise ValueError("must not be empty")
        return value


class ReplayRequestApproveRequest(BaseModel):
    """Request body for approving a replay request."""

    approved_by: StrictStr = Field(max_length=200)
    note: StrictStr | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("approved_by", "note", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("approved_by")
    @classmethod
    def reject_empty_actor(cls, value: str) -> str:
        """Reject empty approver names."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("note")
    @classmethod
    def reject_empty_note(cls, value: str | None) -> str | None:
        """Reject empty notes when present."""
        if value == "":
            raise ValueError("must not be empty")
        return value


class ReplayRequestRejectRequest(BaseModel):
    """Request body for rejecting a replay request."""

    rejected_by: StrictStr = Field(max_length=200)
    reason: StrictStr = Field(max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("rejected_by", "reason", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("rejected_by", "reason")
    @classmethod
    def reject_empty_string(cls, value: str) -> str:
        """Reject empty strings."""
        if value == "":
            raise ValueError("must not be empty")
        return value


class ReplayRequestResponse(BaseModel):
    """Safe replay request metadata."""

    replay_request_id: UUID
    status: str
    event_id: UUID
    delivery_id: UUID
    dead_letter_id: UUID
    reason: str | None
    requested_by: str | None
    approved_by: str | None
    rejected_by: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    resolved_at: datetime | None


class ReplayExecutionResponse(BaseModel):
    """Safe replay execution metadata."""

    replay_request_id: UUID
    delivery_id: UUID
    replay_status: str
    delivery_status: str
    attempt_recorded: bool
    dead_letter_resolved: bool
