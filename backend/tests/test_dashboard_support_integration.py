import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db import models
from app.db.base import Base
from app.db.session import get_async_session
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    settings = Settings(postgres_port=int(os.environ.get("POSTGRES_PORT", "0")))
    assert settings.postgres_port == 5434
    return settings


@pytest.fixture(scope="session")
def integration_engine(integration_settings: Settings) -> Iterator[AsyncEngine]:
    engine = create_async_engine(integration_settings.database_url, poolclass=NullPool)
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture()
def session_factory(
    integration_engine: AsyncEngine,
) -> Iterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(bind=integration_engine, expire_on_commit=False)
    asyncio.run(_clear_database(factory))
    yield factory
    asyncio.run(_clear_database(factory))


@pytest.fixture()
def app(session_factory: async_sessionmaker[AsyncSession]) -> Iterator[FastAPI]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session
    yield app
    app.dependency_overrides.clear()


def test_integration_list_returns_safe_metadata(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        await _create_integration(session_factory, slug="stripe-sandbox", active=False)
        await _create_integration(session_factory, slug="github-sandbox", active=True)

        async with _client(app) as client:
            response = await client.get("/api/v1/integrations")

        assert response.status_code == 200
        _assert_correlation_id(response)
        integrations = response.json()
        assert [integration["slug"] for integration in integrations] == [
            "stripe-sandbox",
            "github-sandbox",
        ]
        assert set(integrations[0]) == {
            "integration_id",
            "slug",
            "name",
            "status",
            "enabled",
            "created_at",
            "updated_at",
        }
        assert "secret" not in json.dumps(integrations).lower()
        assert "configuration" not in integrations[0]

    asyncio.run(exercise())


def test_integration_status_patch_activates_and_disables(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(
            session_factory, slug="stripe-sandbox", active=False
        )

        async with _client(app) as client:
            activate = await client.patch(
                f"/api/v1/integrations/{integration.slug}",
                json={"status": "active"},
            )
            disable = await client.patch(
                f"/api/v1/integrations/{integration.slug}",
                json={"status": "disabled"},
            )
            invalid = await client.patch(
                f"/api/v1/integrations/{integration.slug}",
                json={"status": "paused"},
            )
            missing = await client.patch("/api/v1/integrations/missing", json={"status": "active"})

        assert activate.status_code == 200
        assert activate.json()["status"] == "active"
        assert activate.json()["enabled"] is True
        assert disable.status_code == 200
        assert disable.json()["status"] == "disabled"
        assert disable.json()["enabled"] is False
        assert invalid.status_code == 422
        assert missing.status_code == 404
        _assert_correlation_id(activate)
        _assert_correlation_id(disable)
        _assert_correlation_id(invalid)
        _assert_correlation_id(missing)

        async with session_factory() as session:
            stored = await session.scalar(
                select(models.Integration).where(models.Integration.slug == integration.slug)
            )
            assert stored is not None
            assert stored.status == "disabled"
            assert stored.enabled is False

    asyncio.run(exercise())


def test_recent_events_list_returns_safe_metadata_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        first = await _create_integration(session_factory, slug="stripe-sandbox", active=True)
        second = await _create_integration(session_factory, slug="github-sandbox", active=True)
        await _create_event(session_factory, first.id, event_type="invoice.paid")
        await _create_event(session_factory, second.id, event_type="issue.opened")

        async with _client(app) as client:
            all_response = await client.get("/api/v1/events?limit=10")
            scoped_response = await client.get(
                f"/api/v1/events?integration_slug={first.slug}&limit=10"
            )
            missing_response = await client.get("/api/v1/events?integration_slug=missing")

        assert all_response.status_code == 200
        assert scoped_response.status_code == 200
        assert missing_response.status_code == 404
        _assert_correlation_id(all_response)
        _assert_correlation_id(scoped_response)
        _assert_correlation_id(missing_response)
        all_events = all_response.json()
        scoped_events = scoped_response.json()
        assert len(all_events) == 2
        assert len(scoped_events) == 1
        assert scoped_events[0]["integration_id"] == str(first.id)
        assert set(all_events[0]) == {
            "event_id",
            "integration_id",
            "event_type",
            "source_event_id",
            "status",
            "received_at",
            "accepted_at",
        }
        assert "payload" not in json.dumps(all_events)
        assert "classified" not in json.dumps(all_events)

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_integration(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    slug: str,
    active: bool,
) -> models.Integration:
    async with session_factory() as session:
        integration = models.Integration(
            name=f"Integration {slug}",
            slug=slug,
            enabled=active,
            status="active" if active else "disabled",
            configuration={"secret": "must-not-return"},
        )
        session.add(integration)
        await session.commit()
        return integration


async def _create_event(
    session_factory: async_sessionmaker[AsyncSession],
    integration_id: uuid.UUID,
    *,
    event_type: str,
) -> models.Event:
    async with session_factory() as session:
        event = models.Event(
            integration_id=integration_id,
            deduplication_key=f"event-{uuid.uuid4()}",
            event_type=event_type,
            source_event_id=f"source-{uuid.uuid4()}",
            status="accepted",
            event_metadata={"internal_note": "classified"},
        )
        payload = models.EventPayload(event=event, payload={"payload": "hidden"})
        session.add_all([event, payload])
        await session.commit()
        return event


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
