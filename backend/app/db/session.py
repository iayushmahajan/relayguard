"""Lazy async SQLAlchemy engine and sessionmaker infrastructure."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_async_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the process-global async engine, creating it without connecting."""
    global _engine
    if _engine is None:
        resolved_settings = settings or get_settings()
        _engine = create_async_engine(resolved_settings.database_url, pool_pre_ping=True)
    return _engine


def get_async_sessionmaker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return the process-global async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_async_engine(settings),
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async database session."""
    async_sessionmaker_ = get_async_sessionmaker()
    async with async_sessionmaker_() as session:
        yield session


async def dispose_async_engine() -> None:
    """Dispose the process-global async engine if it has been created."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
