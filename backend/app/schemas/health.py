"""Health endpoint schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Process health response body."""

    status: str
