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


class DestinationUpdateRequest(BaseModel):
    """Request body for updating safe destination metadata."""

    name: StrictStr | None = Field(default=None, max_length=200)
    endpoint_url: StrictStr | None = None
    configuration: dict[str, Any] | None = None
    status: StrictStr | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "status", mode="before")
    @classmethod
    def trim_string(cls, value: object) -> object:
        """Trim string fields before validation."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name")
    @classmethod
    def reject_empty_name(cls, value: str | None) -> str | None:
        """Reject empty names."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str | None) -> str | None:
        """Require an HTTP or HTTPS URL when provided."""
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be a valid http or https URL")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        """Allow only active or disabled destination statuses."""
        if value is not None and value not in _ALLOWED_STATUS:
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


class RoutingRuleUpdateRequest(BaseModel):
    """Request body for updating safe routing-rule metadata."""

    name: StrictStr | None = Field(default=None, max_length=200)
    destination_id: UUID | None = None
    event_type: StrictStr | None = Field(default=None, max_length=255)
    priority: int | None = None
    status: StrictStr | None = None

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
    def reject_empty_string(cls, value: str | None) -> str | None:
        """Reject empty strings when provided."""
        if value == "":
            raise ValueError("must not be empty")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        """Allow only active or disabled routing-rule statuses."""
        if value is not None and value not in _ALLOWED_STATUS:
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


class RecentDeliveryResponse(BaseModel):
    """Safe recent delivery metadata with display context."""

    delivery_id: UUID
    event_id: UUID
    event_type: str
    destination_id: UUID
    destination_name: str
    routing_rule_id: UUID | None
    routing_rule_name: str | None
    status: str
    attempt_count: int
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    created_at: datetime
    updated_at: datetime
