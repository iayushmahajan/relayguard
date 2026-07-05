from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db import session


def test_async_engine_is_created_lazily_without_connecting() -> None:
    settings = Settings(
        postgres_db="relayguard_test",
        postgres_user="relayguard",
        postgres_password="secret",
        postgres_host="localhost",
        postgres_port=5434,
    )

    engine = session.get_async_engine(settings)

    assert isinstance(engine, AsyncEngine)
    assert str(engine.url) == "postgresql+asyncpg://relayguard:***@localhost:5434/relayguard_test"


def test_async_sessionmaker_is_typed_factory() -> None:
    settings = Settings(
        postgres_db="relayguard_test",
        postgres_user="relayguard",
        postgres_password="secret",
        postgres_host="localhost",
        postgres_port=5434,
    )

    sessionmaker = session.get_async_sessionmaker(settings)

    assert isinstance(sessionmaker, async_sessionmaker)
    assert sessionmaker.class_ is AsyncSession
