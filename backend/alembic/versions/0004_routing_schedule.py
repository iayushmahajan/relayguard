"""Add routing schedule idempotency constraint."""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_routing_schedule"
down_revision: str | None = "0003_webhook_intake_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "uq_event_deliveries_event_destination_routing_rule"


def upgrade() -> None:
    """Prevent duplicate scheduled deliveries for the same event route."""
    op.create_unique_constraint(
        _CONSTRAINT_NAME,
        "event_deliveries",
        ["event_id", "destination_id", "routing_rule_id"],
    )


def downgrade() -> None:
    """Remove Phase 3 delivery scheduling idempotency constraint."""
    op.drop_constraint(_CONSTRAINT_NAME, "event_deliveries", type_="unique")
