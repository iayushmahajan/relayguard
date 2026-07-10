"""Add replay workflow support columns."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_replay_workflow"
down_revision: str | None = "0005_delivery_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_REPLAY_INDEX = "uq_replay_requests_active_dead_letter_event_id"
_OLD_ACTIVE_STATUSES = "status IN ('pending', 'approved')"
_NEW_ACTIVE_STATUSES = "status IN ('pending', 'approved', 'running')"


def upgrade() -> None:
    """Apply Phase 5 replay workflow schema support."""
    op.drop_index(
        _ACTIVE_REPLAY_INDEX,
        table_name="replay_requests",
        postgresql_where=sa.text(_OLD_ACTIVE_STATUSES),
    )
    op.create_index(
        _ACTIVE_REPLAY_INDEX,
        "replay_requests",
        ["dead_letter_event_id"],
        unique=True,
        postgresql_where=sa.text(_NEW_ACTIVE_STATUSES),
    )
    op.add_column(
        "replay_requests",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column("replay_requests", sa.Column("executed_at", sa.DateTime(timezone=True)))
    op.add_column("replay_requests", sa.Column("resolved_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    """Restore the Phase 4 replay request schema surface."""
    op.drop_column("replay_requests", "resolved_at")
    op.drop_column("replay_requests", "executed_at")
    op.drop_column("replay_requests", "updated_at")
    op.drop_index(
        _ACTIVE_REPLAY_INDEX,
        table_name="replay_requests",
        postgresql_where=sa.text(_NEW_ACTIVE_STATUSES),
    )
    op.create_index(
        _ACTIVE_REPLAY_INDEX,
        "replay_requests",
        ["dead_letter_event_id"],
        unique=True,
        postgresql_where=sa.text(_OLD_ACTIVE_STATUSES),
    )
