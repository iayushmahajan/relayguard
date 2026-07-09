"""Add webhook intake support columns."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_webhook_intake_support"
down_revision: str | None = "0002_replay_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEBHOOK_RECEIPT_STATUS_CONSTRAINT = "ck_webhook_receipts_webhook_receipt_status"
_WEBHOOK_RECEIPT_STATUS_CHECK = "status IN ('received', 'accepted', 'duplicate', 'rejected')"
_WEBHOOK_RECEIPT_ORIGINAL_STATUS_CHECK = "status IN ('received', 'accepted', 'rejected')"


def upgrade() -> None:
    """Apply Phase 2 webhook intake schema support."""
    op.drop_constraint(
        op.f(_WEBHOOK_RECEIPT_STATUS_CONSTRAINT),
        "webhook_receipts",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_WEBHOOK_RECEIPT_STATUS_CONSTRAINT),
        "webhook_receipts",
        sa.text(_WEBHOOK_RECEIPT_STATUS_CHECK),
    )
    op.add_column("webhook_receipts", sa.Column("request_method", sa.String(length=16)))
    op.add_column("webhook_receipts", sa.Column("request_path", sa.Text()))
    op.add_column("webhook_receipts", sa.Column("content_type", sa.String(length=255)))
    op.add_column("webhook_receipts", sa.Column("body_size_bytes", sa.Integer()))
    op.add_column("webhook_receipts", sa.Column("correlation_id", sa.String(length=64)))
    op.alter_column(
        "events",
        "event_type",
        existing_type=sa.String(length=200),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.add_column(
        "events",
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Restore the Phase 1C schema surface."""
    op.drop_column("events", "accepted_at")
    op.execute(
        "UPDATE events SET event_type = left(event_type, 200) WHERE length(event_type) > 200"
    )
    op.alter_column(
        "events",
        "event_type",
        existing_type=sa.String(length=255),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
    op.drop_column("webhook_receipts", "correlation_id")
    op.drop_column("webhook_receipts", "body_size_bytes")
    op.drop_column("webhook_receipts", "content_type")
    op.drop_column("webhook_receipts", "request_path")
    op.drop_column("webhook_receipts", "request_method")
    op.execute("UPDATE webhook_receipts SET status = 'rejected' WHERE status = 'duplicate'")
    op.drop_constraint(
        op.f(_WEBHOOK_RECEIPT_STATUS_CONSTRAINT),
        "webhook_receipts",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_WEBHOOK_RECEIPT_STATUS_CONSTRAINT),
        "webhook_receipts",
        sa.text(_WEBHOOK_RECEIPT_ORIGINAL_STATUS_CHECK),
    )
