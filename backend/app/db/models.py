"""RelayGuard normalized persistence models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    """Return a UUID primary-key column."""
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_column() -> Mapped[datetime]:
    """Return a UTC-aware creation timestamp column."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Mapped[datetime]:
    """Return a UTC-aware update timestamp column."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Base):
    """Operator identity."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="user_status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    simulation_runs: Mapped[list[SimulationRun]] = relationship(back_populates="user")
    requested_replays: Mapped[list[ReplayRequest]] = relationship(
        back_populates="requested_by_user",
        foreign_keys="ReplayRequest.requested_by_user_id",
    )
    approved_replays: Mapped[list[ReplayRequest]] = relationship(
        back_populates="approved_by_user",
        foreign_keys="ReplayRequest.approved_by_user_id",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="actor")


class Role(Base):
    """Named authorization role."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    users: Mapped[list[UserRole]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class UserRole(Base):
    """Many-to-many user and role link."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


class AuthSession(Base):
    """User authentication session state."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(back_populates="sessions")


class Integration(Base):
    """Webhook source integration configuration."""

    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint("status IN ('disabled', 'active', 'paused')", name="integration_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="disabled")
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    secrets: Mapped[list[WebhookSecret]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    schemas: Mapped[list[EventSchema]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    destinations: Mapped[list[DownstreamDestination]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    routing_rules: Mapped[list[RoutingRule]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
    )
    receipts: Mapped[list[WebhookReceipt]] = relationship(back_populates="integration")
    events: Mapped[list[Event]] = relationship(back_populates="integration")
    simulation_runs: Mapped[list[SimulationRun]] = relationship(back_populates="integration")


class WebhookSecret(Base):
    """Hashed webhook secret for an integration."""

    __tablename__ = "webhook_secrets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'expired')", name="webhook_secret_status"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    integration: Mapped[Integration] = relationship(back_populates="secrets")


class EventSchema(Base):
    """Versioned event schema document for an integration."""

    __tablename__ = "event_schemas"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "version", name="uq_event_schemas_integration_id_version"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    integration: Mapped[Integration] = relationship(back_populates="schemas")


class DownstreamDestination(Base):
    """Destination endpoint for event delivery."""

    __tablename__ = "downstream_destinations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'paused')",
            name="downstream_destination_status",
        ),
        UniqueConstraint(
            "integration_id",
            "name",
            name="uq_downstream_destinations_integration_id_name",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="disabled")
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    integration: Mapped[Integration] = relationship(back_populates="destinations")
    routing_rules: Mapped[list[RoutingRule]] = relationship(back_populates="destination")
    deliveries: Mapped[list[EventDelivery]] = relationship(back_populates="destination")


class RoutingRule(Base):
    """Routing rule from an integration to a downstream destination."""

    __tablename__ = "routing_rules"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="routing_rule_status"),
        UniqueConstraint("integration_id", "name", name="uq_routing_rules_integration_id_name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("downstream_destinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    match_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    integration: Mapped[Integration] = relationship(back_populates="routing_rules")
    destination: Mapped[DownstreamDestination] = relationship(back_populates="routing_rules")
    deliveries: Mapped[list[EventDelivery]] = relationship(back_populates="routing_rule")


class WebhookReceipt(Base):
    """Every inbound webhook attempt received by RelayGuard."""

    __tablename__ = "webhook_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'accepted', 'rejected')",
            name="webhook_receipt_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    source_ip: Mapped[str | None] = mapped_column(String(64))
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    query_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_body_hash: Mapped[str | None] = mapped_column(String(255))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    integration: Mapped[Integration] = relationship(back_populates="receipts")
    events: Mapped[list[Event]] = relationship(back_populates="receipt")


class Event(Base):
    """Accepted canonical event."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'processing', 'delivered', 'failed', 'dead_lettered')",
            name="event_status",
        ),
        UniqueConstraint(
            "integration_id",
            "deduplication_key",
            name="uq_events_integration_id_deduplication_key",
        ),
        Index(
            "uq_events_integration_id_source_event_id_not_null",
            "integration_id",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id"),
        nullable=False,
    )
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_receipts.id"),
    )
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="accepted")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    integration: Mapped[Integration] = relationship(back_populates="events")
    receipt: Mapped[WebhookReceipt | None] = relationship(back_populates="events")
    payload: Mapped[EventPayload | None] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    state_transitions: Mapped[list[EventStateTransition]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    deliveries: Mapped[list[EventDelivery]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    ai_analyses: Mapped[list[AiAnalysis]] = relationship(back_populates="event")


class EventPayload(Base):
    """Canonical event payload document."""

    __tablename__ = "event_payloads"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    payload_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_column()

    event: Mapped[Event] = relationship(back_populates="payload")


class EventStateTransition(Base):
    """Status transition history for events."""

    __tablename__ = "event_state_transitions"
    __table_args__ = (
        CheckConstraint(
            "from_status IS NULL OR from_status IN ("
            "'accepted', 'processing', 'delivered', 'partially_failed', "
            "'dead_lettered', 'cancelled'"
            ")",
            name="event_state_transition_from_status",
        ),
        CheckConstraint(
            "to_status IN ("
            "'accepted', 'processing', 'delivered', 'partially_failed', "
            "'dead_lettered', 'cancelled'"
            ")",
            name="event_state_transition_to_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    transition_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()

    event: Mapped[Event] = relationship(back_populates="state_transitions")


class EventDelivery(Base):
    """Delivery state for an event and downstream destination."""

    __tablename__ = "event_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending', 'scheduled', 'in_progress', 'succeeded', 'failed', 'dead_lettered'"
            ")",
            name="event_delivery_status",
        ),
        Index("ix_event_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("downstream_destinations.id"),
        nullable=False,
    )
    routing_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routing_rules.id"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    event: Mapped[Event] = relationship(back_populates="deliveries")
    destination: Mapped[DownstreamDestination] = relationship(back_populates="deliveries")
    routing_rule: Mapped[RoutingRule | None] = relationship(back_populates="deliveries")
    attempts: Mapped[list[DeliveryAttempt]] = relationship(
        back_populates="delivery",
        cascade="all, delete-orphan",
    )
    retry_jobs: Mapped[list[RetryJob]] = relationship(
        back_populates="delivery",
        cascade="all, delete-orphan",
    )
    dead_letter_event: Mapped[DeadLetterEvent | None] = relationship(
        back_populates="delivery",
        cascade="all, delete-orphan",
    )
    ai_analyses: Mapped[list[AiAnalysis]] = relationship(back_populates="delivery")


class DeliveryAttempt(Base):
    """Individual attempt to deliver an event."""

    __tablename__ = "delivery_attempts"
    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'failed')", name="delivery_attempt_status"),
        UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_delivery_attempts_delivery_id_attempt_number",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_deliveries.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_status_code: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    delivery: Mapped[EventDelivery] = relationship(back_populates="attempts")


class RetryJob(Base):
    """Durable retry job record without worker behavior."""

    __tablename__ = "retry_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'cancelled', 'failed')",
            name="retry_job_status",
        ),
        Index("ix_retry_jobs_status_run_at", "status", "run_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_deliveries.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    delivery: Mapped[EventDelivery] = relationship(back_populates="retry_jobs")


class DeadLetterEvent(Base):
    """Dead-letter record for a failed delivery."""

    __tablename__ = "dead_letter_events"
    __table_args__ = (
        CheckConstraint(
            "resolution_status IN ('open', 'acknowledged', 'resolved')",
            name="dead_letter_event_resolution_status",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="dead_letter_event_severity",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_deliveries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="open"
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False, server_default="medium")
    dead_lettered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    delivery: Mapped[EventDelivery] = relationship(back_populates="dead_letter_event")
    replay_requests: Mapped[list[ReplayRequest]] = relationship(
        back_populates="dead_letter_event",
        cascade="all, delete-orphan",
    )
    ai_analyses: Mapped[list[AiAnalysis]] = relationship(back_populates="dead_letter_event")


class SimulationRun(Base):
    """Simulation run metadata for recovery planning."""

    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="simulation_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    integration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integrations.id"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    input_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    integration: Mapped[Integration | None] = relationship(back_populates="simulation_runs")
    user: Mapped[User | None] = relationship(back_populates="simulation_runs")


class ReplayRequest(Base):
    """Request to replay a dead-letter event."""

    __tablename__ = "replay_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'running', 'completed', 'rejected', 'cancelled')",
            name="replay_request_status",
        ),
        Index(
            "uq_replay_requests_active_dead_letter_event_id",
            "dead_letter_event_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dead_letter_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dead_letter_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    request_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dead_letter_event: Mapped[DeadLetterEvent] = relationship(back_populates="replay_requests")
    requested_by_user: Mapped[User | None] = relationship(
        back_populates="requested_replays",
        foreign_keys=[requested_by_user_id],
    )
    approved_by_user: Mapped[User | None] = relationship(
        back_populates="approved_replays",
        foreign_keys=[approved_by_user_id],
    )


class AiAnalysis(Base):
    """Stored AI analysis summary without execution behavior."""

    __tablename__ = "ai_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ai_analysis_status",
        ),
        CheckConstraint(
            "((event_id IS NOT NULL)::integer + "
            "(delivery_id IS NOT NULL)::integer + "
            "(dead_letter_event_id IS NOT NULL)::integer) = 1",
            name="ai_analysis_exactly_one_target",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"))
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_deliveries.id"),
    )
    dead_letter_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dead_letter_events.id"),
    )
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    summary: Mapped[str | None] = mapped_column(Text)
    detail_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event | None] = relationship(back_populates="ai_analyses")
    delivery: Mapped[EventDelivery | None] = relationship(back_populates="ai_analyses")
    dead_letter_event: Mapped[DeadLetterEvent | None] = relationship(back_populates="ai_analyses")
    evaluation_runs: Mapped[list[AiEvaluationRun]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )


class AiEvaluationRun(Base):
    """Evaluation result for a stored AI analysis."""

    __tablename__ = "ai_evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ai_evaluation_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ai_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    score: Mapped[int | None] = mapped_column(Integer)
    evaluation_document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    analysis: Mapped[AiAnalysis] = relationship(back_populates="evaluation_runs")


class AuditLog(Base):
    """Immutable audit log document."""

    __tablename__ = "audit_logs"
    __table_args__ = ()

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    audit_document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    actor: Mapped[User | None] = relationship(back_populates="audit_logs")


Index(
    "ix_events_integration_id_status_received_at",
    Event.integration_id,
    Event.status,
    Event.received_at.desc(),
)
Index("ix_events_received_at", Event.received_at.desc())
Index(
    "ix_dle_resolution_status_severity_dead_lettered_at",
    DeadLetterEvent.resolution_status,
    DeadLetterEvent.severity,
    DeadLetterEvent.dead_lettered_at.desc(),
)
Index(
    "ix_audit_logs_resource_type_resource_id_created_at",
    AuditLog.resource_type,
    AuditLog.resource_id,
    AuditLog.created_at.desc(),
)
Index("ix_audit_logs_actor_id_created_at", AuditLog.actor_id, AuditLog.created_at.desc())
