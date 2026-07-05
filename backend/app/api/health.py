"""Process health endpoint."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return process-only health, without checking database readiness."""
    return HealthResponse(status="ok")
