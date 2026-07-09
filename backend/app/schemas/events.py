"""Event API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EventMetadataResponse(BaseModel):
    """Safe canonical event metadata response."""

    event_id: UUID
    integration_id: UUID
    event_type: str
    source_event_id: str | None
    status: str
    received_at: datetime
    accepted_at: datetime
