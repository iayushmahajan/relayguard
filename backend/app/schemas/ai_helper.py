"""AI helper API schemas."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

AiMode = Literal["fallback", "ai"]
RiskLevel = Literal["low", "medium", "high"]


class ExplainDeliveryRequest(BaseModel):
    """Request body for explaining a delivery outcome."""

    delivery_id: UUID

    model_config = ConfigDict(extra="forbid")


class ExplainDeliveryResponse(BaseModel):
    """Structured operator explanation for a delivery."""

    mode: AiMode
    summary: str
    likely_cause: str
    recommended_action: str
    risk_level: RiskLevel
    supporting_facts: list[str]


class DraftReplayNoteRequest(BaseModel):
    """Request body for drafting replay request text."""

    dead_letter_id: UUID

    model_config = ConfigDict(extra="forbid")


class DraftReplayNoteResponse(BaseModel):
    """Structured replay note draft."""

    mode: AiMode
    reason: str
    approval_note: str
    operator_summary: str
    warnings: list[str]


class SampleWebhookPayloadRequest(BaseModel):
    """Request body for generating a safe sample webhook envelope."""

    event_type: StrictStr = Field(max_length=255)
    description: StrictStr | None = Field(default=None, max_length=500)
    integration_slug: StrictStr | None = Field(default=None, max_length=120)

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_type", "description", "integration_slug", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim optional string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("event_type")
    @classmethod
    def reject_empty_event_type(cls, value: str) -> str:
        """Reject empty event types."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("description", "integration_slug")
    @classmethod
    def reject_empty_optional_strings(cls, value: str | None) -> str | None:
        """Reject empty optional strings when provided."""
        if value == "":
            raise ValueError("must not be empty")
        return value


class SampleWebhookPayloadResponse(BaseModel):
    """Generated safe sample webhook envelope for user review."""

    mode: AiMode
    event_type: str
    deduplication_key: str
    source_event_id: str
    payload: dict[str, Any]
