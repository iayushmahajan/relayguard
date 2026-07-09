"""Webhook intake API schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class WebhookEnvelope(BaseModel):
    """Known integration webhook request envelope."""

    event_type: StrictStr = Field(max_length=255)
    deduplication_key: StrictStr = Field(max_length=255)
    source_event_id: StrictStr | None = Field(default=None, max_length=255)
    payload: dict[str, Any]

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_type", "deduplication_key", mode="before")
    @classmethod
    def trim_required_string(cls, value: object) -> object:
        """Trim required string fields before length and emptiness validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("source_event_id", mode="before")
    @classmethod
    def trim_optional_string(cls, value: object) -> object:
        """Trim optional provider event IDs before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("event_type", "deduplication_key", "source_event_id")
    @classmethod
    def reject_empty_string(cls, value: str | None) -> str | None:
        """Reject blank strings after trimming."""
        if value == "":
            raise ValueError("must not be empty")
        return value


class WebhookIntakeResponse(BaseModel):
    """Accepted or duplicate webhook intake response."""

    receipt_id: UUID
    event_id: UUID
    status: str
    duplicate: bool


class WebhookRejectedResponse(BaseModel):
    """Rejected webhook intake response."""

    detail: str
    receipt_id: UUID | None = None
