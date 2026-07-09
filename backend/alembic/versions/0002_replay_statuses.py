"""Expanded replay request terminal statuses."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_replay_statuses"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_replay_requests_replay_request_status"

_EXPANDED_STATUS_CHECK = (
    "status IN ("
    "'pending', 'approved', 'running', 'completed', 'resolved', "
    "'rejected', 'executed', 'cancelled'"
    ")"
)

_ORIGINAL_STATUS_CHECK = (
    "status IN ('pending', 'approved', 'running', 'completed', 'rejected', 'cancelled')"
)


def upgrade() -> None:
    """Expand permitted terminal replay-request statuses."""
    op.drop_constraint(op.f(_CONSTRAINT_NAME), "replay_requests", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "replay_requests",
        sa.text(_EXPANDED_STATUS_CHECK),
    )


def downgrade() -> None:
    """Restore the original replay-request status set."""
    op.drop_constraint(op.f(_CONSTRAINT_NAME), "replay_requests", type_="check")
    op.create_check_constraint(
        op.f(_CONSTRAINT_NAME),
        "replay_requests",
        sa.text(_ORIGINAL_STATUS_CHECK),
    )
