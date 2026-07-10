"""Routing and delivery scheduling API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

_ALLOWED_STATUS = {"active", "disabled"}


class DestinationCreateRequest(BaseModel):
    """Request body for creating a downstream destination."""

    name: StrictStr = Field(max_length=200)
    destination_type: StrictStr = Field(max_length=100)
    endpoint_url: StrictStr
    configuration: dict[str, Any] = Field(default_factory=dict)
    status: StrictStr = "active"

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "destination_type", "status", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name", "destination_type")
    @classmethod
    def reject_empty_string(cls, value: str) -> str:
        """Reject empty strings."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        """Require an HTTP or HTTPS URL."""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be a valid http or https URL")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Allow only Phase 3 destination statuses."""
        if value not in _ALLOWED_STATUS:
            raise ValueError("must be active or disabled")
        return value


class DestinationResponse(BaseModel):
    """Safe downstream destination metadata."""

    destination_id: UUID
    integration_id: UUID
    name: str
    destination_type: str
    endpoint_url: str
    configuration: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class RoutingRuleCreateRequest(BaseModel):
    """Request body for creating a routing rule."""

    name: StrictStr = Field(max_length=200)
    destination_id: UUID
    event_type: StrictStr = Field(max_length=255)
    priority: int = 100
    status: StrictStr = "active"

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "event_type", "status", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name", "event_type")
    @classmethod
    def reject_empty_string(cls, value: str) -> str:
        """Reject empty strings."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Allow only Phase 3 routing-rule statuses."""
        if value not in _ALLOWED_STATUS:
            raise ValueError("must be active or disabled")
        return value


class RoutingRuleResponse(BaseModel):
    """Safe routing rule metadata."""

    routing_rule_id: UUID
    integration_id: UUID
    destination_id: UUID
    name: str
    event_type: str
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime


class DeliveryScheduleResponse(BaseModel):
    """Delivery scheduling response."""

    event_id: UUID
    status: str
    scheduled_count: int
    already_scheduled_count: int


class DeliveryResponse(BaseModel):
    """Safe delivery metadata."""

    delivery_id: UUID
    event_id: UUID
    destination_id: UUID
    routing_rule_id: UUID | None
    status: str
    next_attempt_at: datetime | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
