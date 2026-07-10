"""Add delivery execution support columns."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_delivery_execution"
down_revision: str | None = "0004_routing_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DELIVERY_STATUS_CONSTRAINT = "ck_event_deliveries_event_delivery_status"
_DELIVERY_STATUS_CHECK = (
    "status IN ("
    "'pending', 'scheduled', 'in_progress', 'delivered', 'succeeded', "
    "'failed', 'dead_lettered', 'cancelled'"
    ")"
)
_DELIVERY_ORIGINAL_STATUS_CHECK = (
    "status IN ('pending', 'scheduled', 'in_progress', 'succeeded', 'failed', 'dead_lettered')"
)
_ATTEMPT_OUTCOME_CONSTRAINT = "ck_delivery_attempts_delivery_attempt_outcome"
_ATTEMPT_OUTCOME_CHECK = "outcome IN ('succeeded', 'failed', 'timed_out')"
_RETRY_JOB_STATUS_CONSTRAINT = "ck_retry_jobs_retry_job_status"
_RETRY_JOB_STATUS_CHECK = (
    "status IN ('pending', 'claimed', 'completed', 'cancelled', 'running', 'succeeded', 'failed')"
)
_RETRY_JOB_ORIGINAL_STATUS_CHECK = (
    "status IN ('pending', 'running', 'succeeded', 'cancelled', 'failed')"
)
_PENDING_RETRY_INDEX = "uq_retry_jobs_pending_delivery_run_at"


def upgrade() -> None:
    """Apply Phase 4 delivery execution schema support."""
    op.drop_constraint(op.f(_DELIVERY_STATUS_CONSTRAINT), "event_deliveries", type_="check")
    op.create_check_constraint(
        op.f(_DELIVERY_STATUS_CONSTRAINT),
        "event_deliveries",
        sa.text(_DELIVERY_STATUS_CHECK),
    )
    op.add_column("event_deliveries", sa.Column("delivered_at", sa.DateTime(timezone=True)))
    op.add_column("event_deliveries", sa.Column("last_error_code", sa.String(length=100)))
    op.add_column("event_deliveries", sa.Column("last_error_message", sa.Text()))

    op.add_column(
        "delivery_attempts",
        sa.Column("outcome", sa.String(length=32), server_default="failed", nullable=False),
    )
    op.add_column("delivery_attempts", sa.Column("error_code", sa.String(length=100)))
    op.add_column(
        "delivery_attempts",
        sa.Column("is_retryable", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "delivery_attempts",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f(_ATTEMPT_OUTCOME_CONSTRAINT),
        "delivery_attempts",
        sa.text(_ATTEMPT_OUTCOME_CHECK),
    )

    op.drop_constraint(op.f(_RETRY_JOB_STATUS_CONSTRAINT), "retry_jobs", type_="check")
    op.create_check_constraint(
        op.f(_RETRY_JOB_STATUS_CONSTRAINT),
        "retry_jobs",
        sa.text(_RETRY_JOB_STATUS_CHECK),
    )
    op.add_column("retry_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("retry_jobs", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "retry_jobs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        _PENDING_RETRY_INDEX,
        "retry_jobs",
        ["delivery_id", "run_at"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.add_column(
        "dead_letter_events",
        sa.Column("reason_code", sa.String(length=100), server_default="delivery_failed"),
    )
    op.add_column("dead_letter_events", sa.Column("reason_message", sa.Text()))
    op.execute("UPDATE dead_letter_events SET reason_message = reason WHERE reason_message IS NULL")
    op.alter_column("dead_letter_events", "reason_code", nullable=False)
    op.alter_column("dead_letter_events", "reason_message", nullable=False)
    op.add_column("dead_letter_events", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.add_column(
        "dead_letter_events",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "dead_letter_events",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Restore the Phase 3 schema surface."""
    op.drop_column("dead_letter_events", "updated_at")
    op.drop_column("dead_letter_events", "created_at")
    op.drop_column("dead_letter_events", "resolved_at")
    op.drop_column("dead_letter_events", "reason_message")
    op.drop_column("dead_letter_events", "reason_code")

    op.drop_index(
        _PENDING_RETRY_INDEX,
        table_name="retry_jobs",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_column("retry_jobs", "updated_at")
    op.drop_column("retry_jobs", "completed_at")
    op.drop_column("retry_jobs", "claimed_at")
    op.execute("UPDATE retry_jobs SET status = 'running' WHERE status = 'claimed'")
    op.execute("UPDATE retry_jobs SET status = 'succeeded' WHERE status = 'completed'")
    op.drop_constraint(op.f(_RETRY_JOB_STATUS_CONSTRAINT), "retry_jobs", type_="check")
    op.create_check_constraint(
        op.f(_RETRY_JOB_STATUS_CONSTRAINT),
        "retry_jobs",
        sa.text(_RETRY_JOB_ORIGINAL_STATUS_CHECK),
    )

    op.drop_constraint(op.f(_ATTEMPT_OUTCOME_CONSTRAINT), "delivery_attempts", type_="check")
    op.drop_column("delivery_attempts", "created_at")
    op.drop_column("delivery_attempts", "is_retryable")
    op.drop_column("delivery_attempts", "error_code")
    op.drop_column("delivery_attempts", "outcome")

    op.drop_column("event_deliveries", "last_error_message")
    op.drop_column("event_deliveries", "last_error_code")
    op.drop_column("event_deliveries", "delivered_at")
    op.execute("UPDATE event_deliveries SET status = 'succeeded' WHERE status = 'delivered'")
    op.execute("UPDATE event_deliveries SET status = 'failed' WHERE status = 'cancelled'")
    op.drop_constraint(op.f(_DELIVERY_STATUS_CONSTRAINT), "event_deliveries", type_="check")
    op.create_check_constraint(
        op.f(_DELIVERY_STATUS_CONSTRAINT),
        "event_deliveries",
        sa.text(_DELIVERY_ORIGINAL_STATUS_CHECK),
    )
