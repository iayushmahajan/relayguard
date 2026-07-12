import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select
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


def test_unknown_integration_cannot_create_destination(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/integrations/missing/destinations",
                json=_destination_document(),
            )

        assert response.status_code == 404
        _assert_correlation_id(response)
        async with session_factory() as session:
            assert await _count(session, models.DownstreamDestination) == 0

    asyncio.run(exercise())


def test_active_integration_can_create_and_list_destination(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        async with _client(app) as client:
            create_response = await client.post(
                f"/api/v1/integrations/{integration.slug}/destinations",
                json=_destination_document(configuration={"timeout_seconds": 10}),
            )
            list_response = await client.get(
                f"/api/v1/integrations/{integration.slug}/destinations"
            )

        assert create_response.status_code == 201
        _assert_correlation_id(create_response)
        _assert_correlation_id(list_response)
        created = create_response.json()
        assert created["integration_id"] == str(integration.id)
        assert created["name"] == "Billing Service"
        assert created["destination_type"] == "http"
        assert created["endpoint_url"] == "https://example.invalid/webhooks/billing"
        assert created["configuration"] == {"timeout_seconds": 10}
        assert created["status"] == "active"
        assert list_response.status_code == 200
        assert list_response.json() == [created]

    asyncio.run(exercise())


def test_invalid_destination_endpoint_url_is_rejected(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        async with _client(app) as client:
            response = await client.post(
                f"/api/v1/integrations/{integration.slug}/destinations",
                json=_destination_document(endpoint_url="ftp://example.invalid/webhook"),
            )

        assert response.status_code == 422
        _assert_correlation_id(response)
        async with session_factory() as session:
            assert await _count(session, models.DownstreamDestination) == 0

    asyncio.run(exercise())


def test_destination_update_changes_endpoint_status_and_configuration(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        destination = await _create_destination(session_factory, integration.id)

        async with _client(app) as client:
            response = await client.patch(
                f"/api/v1/integrations/{integration.slug}/destinations/{destination.id}",
                json={
                    "endpoint_url": "http://127.0.0.1:9000/success",
                    "configuration": {"timeout_seconds": 2},
                    "status": "active",
                },
            )
            missing = await client.patch(
                f"/api/v1/integrations/{integration.slug}/destinations/{uuid.uuid4()}",
                json={"status": "active"},
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        _assert_correlation_id(missing)
        assert response.json()["destination_id"] == str(destination.id)
        assert response.json()["endpoint_url"] == "http://127.0.0.1:9000/success"
        assert response.json()["configuration"] == {"timeout_seconds": 2}
        assert response.json()["status"] == "active"
        assert missing.status_code == 404
        async with session_factory() as session:
            stored = await session.get(models.DownstreamDestination, destination.id)
            assert stored is not None
            assert stored.endpoint_url == "http://127.0.0.1:9000/success"
            assert stored.configuration == {
                "destination_type": "http",
                "settings": {"timeout_seconds": 2},
            }

    asyncio.run(exercise())


def test_unknown_integration_cannot_create_routing_rule(
    app: FastAPI,
) -> None:
    async def exercise() -> None:
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/integrations/missing/routing-rules",
                json=_routing_rule_document(destination_id=uuid.uuid4()),
            )

        assert response.status_code == 404
        _assert_correlation_id(response)

    asyncio.run(exercise())


def test_routing_rule_update_changes_route_and_status(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        first_destination = await _create_destination(session_factory, integration.id)
        second_destination = await _create_destination(session_factory, integration.id)
        routing_rule = await _create_routing_rule(
            session_factory,
            integration.id,
            first_destination.id,
            event_type="invoice.paid",
        )

        async with _client(app) as client:
            response = await client.patch(
                f"/api/v1/integrations/{integration.slug}/routing-rules/{routing_rule.id}",
                json={
                    "destination_id": str(second_destination.id),
                    "event_type": "demo.success",
                    "priority": 25,
                    "status": "disabled",
                },
            )
            missing = await client.patch(
                f"/api/v1/integrations/{integration.slug}/routing-rules/{uuid.uuid4()}",
                json={"status": "active"},
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        _assert_correlation_id(missing)
        assert response.json()["routing_rule_id"] == str(routing_rule.id)
        assert response.json()["destination_id"] == str(second_destination.id)
        assert response.json()["event_type"] == "demo.success"
        assert response.json()["priority"] == 25
        assert response.json()["status"] == "disabled"
        assert missing.status_code == 404

    asyncio.run(exercise())


def test_routing_rule_destination_must_belong_to_same_integration(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        first_integration = await _create_integration(session_factory)
        second_integration = await _create_integration(session_factory)
        other_destination = await _create_destination(session_factory, second_integration.id)
        async with _client(app) as client:
            response = await client.post(
                f"/api/v1/integrations/{first_integration.slug}/routing-rules",
                json=_routing_rule_document(destination_id=other_destination.id),
            )

        assert response.status_code == 400
        _assert_correlation_id(response)
        assert response.json()["detail"] == "destination not found for integration"
        async with session_factory() as session:
            assert await _count(session, models.RoutingRule) == 0

    asyncio.run(exercise())


def test_active_integration_can_create_and_list_sorted_routing_rules(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        destination = await _create_destination(session_factory, integration.id)
        async with _client(app) as client:
            later_response = await client.post(
                f"/api/v1/integrations/{integration.slug}/routing-rules",
                json=_routing_rule_document(
                    destination_id=destination.id,
                    name="Later",
                    priority=200,
                ),
            )
            earlier_response = await client.post(
                f"/api/v1/integrations/{integration.slug}/routing-rules",
                json=_routing_rule_document(
                    destination_id=destination.id,
                    name="Earlier",
                    priority=50,
                ),
            )
            list_response = await client.get(
                f"/api/v1/integrations/{integration.slug}/routing-rules"
            )

        assert later_response.status_code == 201
        assert earlier_response.status_code == 201
        _assert_correlation_id(later_response)
        _assert_correlation_id(earlier_response)
        _assert_correlation_id(list_response)
        assert [rule["name"] for rule in list_response.json()] == ["Earlier", "Later"]
        assert list_response.json()[0]["event_type"] == "invoice.paid"

    asyncio.run(exercise())


def test_schedule_deliveries_for_matching_active_route(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        event = await _create_routable_event(session_factory)
        async with _client(app) as client:
            response = await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json() == {
            "event_id": str(event.id),
            "status": "accepted",
            "scheduled_count": 1,
            "already_scheduled_count": 0,
        }
        async with session_factory() as session:
            delivery = await session.scalar(select(models.EventDelivery))
            refreshed_event = await session.get(models.Event, event.id)
            assert delivery is not None
            assert delivery.status == "scheduled"
            assert delivery.attempt_count == 0
            assert delivery.next_attempt_at is not None
            assert refreshed_event is not None
            assert refreshed_event.status == "accepted"
            assert await _count(session, models.EventDelivery) == 1
            assert await _count(session, models.EventStateTransition) == 0

    asyncio.run(exercise())


def test_recent_deliveries_list_returns_safe_metadata_and_filters(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        event = await _create_routable_event(session_factory)
        async with _client(app) as client:
            await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")
            response = await client.get("/api/v1/deliveries?limit=10")
            scoped_response = await client.get(f"/api/v1/deliveries?event_id={event.id}")
            status_response = await client.get("/api/v1/deliveries?status=scheduled")
            limit_response = await client.get("/api/v1/deliveries?limit=101")

        assert response.status_code == 200
        assert scoped_response.status_code == 200
        assert status_response.status_code == 200
        assert limit_response.status_code == 422
        _assert_correlation_id(response)
        _assert_correlation_id(scoped_response)
        _assert_correlation_id(status_response)
        _assert_correlation_id(limit_response)
        data = response.json()
        assert len(data) == 1
        assert data == scoped_response.json()
        assert data == status_response.json()
        assert data[0]["event_id"] == str(event.id)
        assert data[0]["event_type"] == "invoice.paid"
        assert data[0]["destination_name"].startswith("Destination ")
        assert data[0]["routing_rule_name"].startswith("Rule ")
        assert data[0]["status"] == "scheduled"
        assert set(data[0]) == {
            "delivery_id",
            "event_id",
            "event_type",
            "destination_id",
            "destination_name",
            "routing_rule_id",
            "routing_rule_name",
            "status",
            "attempt_count",
            "next_attempt_at",
            "last_attempt_at",
            "created_at",
            "updated_at",
        }
        assert "payload" not in str(data).lower()
        assert "response_body" not in str(data).lower()
        assert "secret" not in str(data).lower()

    asyncio.run(exercise())


def test_schedule_deliveries_is_idempotent(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        event = await _create_routable_event(session_factory)
        async with _client(app) as client:
            first_response = await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")
            second_response = await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        _assert_correlation_id(first_response)
        _assert_correlation_id(second_response)
        assert first_response.json()["scheduled_count"] == 1
        assert first_response.json()["already_scheduled_count"] == 0
        assert second_response.json()["scheduled_count"] == 0
        assert second_response.json()["already_scheduled_count"] == 1
        async with session_factory() as session:
            assert await _count(session, models.EventDelivery) == 1

    asyncio.run(exercise())


def test_schedule_deliveries_ignores_non_matching_disabled_rules_and_destinations(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory)
        event = await _create_event(session_factory, integration.id, event_type="invoice.paid")
        active_destination = await _create_destination(session_factory, integration.id)
        disabled_destination = await _create_destination(
            session_factory,
            integration.id,
            status="disabled",
        )
        await _create_routing_rule(
            session_factory,
            integration.id,
            active_destination.id,
            event_type="invoice.created",
        )
        await _create_routing_rule(
            session_factory,
            integration.id,
            active_destination.id,
            event_type="invoice.paid",
            status="disabled",
            name="Disabled rule",
        )
        await _create_routing_rule(
            session_factory,
            integration.id,
            disabled_destination.id,
            event_type="invoice.paid",
            name="Disabled destination",
        )

        async with _client(app) as client:
            response = await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json()["scheduled_count"] == 0
        assert response.json()["already_scheduled_count"] == 0
        async with session_factory() as session:
            assert await _count(session, models.EventDelivery) == 0

    asyncio.run(exercise())


def test_delivery_listing_returns_safe_metadata_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        event = await _create_routable_event(session_factory)
        async with _client(app) as client:
            await client.post(f"/api/v1/events/{event.id}/schedule-deliveries")
            response = await client.get(f"/api/v1/events/{event.id}/deliveries")

        assert response.status_code == 200
        _assert_correlation_id(response)
        data = response.json()
        assert len(data) == 1
        assert set(data[0]) == {
            "delivery_id",
            "event_id",
            "destination_id",
            "routing_rule_id",
            "status",
            "next_attempt_at",
            "attempt_count",
            "created_at",
            "updated_at",
        }
        assert data[0]["event_id"] == str(event.id)
        assert data[0]["status"] == "scheduled"
        assert "payload" not in data[0]
        assert "endpoint_url" not in data[0]

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_integration(
    session_factory: async_sessionmaker[AsyncSession],
) -> models.Integration:
    async with session_factory() as session:
        integration = models.Integration(
            name=f"Integration {uuid.uuid4()}",
            slug=f"integration-{uuid.uuid4()}",
            enabled=True,
            status="active",
        )
        session.add(integration)
        await session.commit()
        return integration


async def _create_destination(
    session_factory: async_sessionmaker[AsyncSession],
    integration_id: uuid.UUID,
    *,
    status: str = "active",
) -> models.DownstreamDestination:
    async with session_factory() as session:
        destination = models.DownstreamDestination(
            integration_id=integration_id,
            name=f"Destination {uuid.uuid4()}",
            endpoint_url="https://example.invalid/webhook",
            status=status,
            configuration={"destination_type": "http", "settings": {}},
        )
        session.add(destination)
        await session.commit()
        return destination


async def _create_routing_rule(
    session_factory: async_sessionmaker[AsyncSession],
    integration_id: uuid.UUID,
    destination_id: uuid.UUID,
    *,
    event_type: str,
    status: str = "active",
    name: str | None = None,
) -> models.RoutingRule:
    async with session_factory() as session:
        routing_rule = models.RoutingRule(
            integration_id=integration_id,
            destination_id=destination_id,
            name=name or f"Rule {uuid.uuid4()}",
            status=status,
            match_configuration={"event_type": event_type},
        )
        session.add(routing_rule)
        await session.commit()
        return routing_rule


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
            status="accepted",
        )
        session.add(event)
        await session.commit()
        return event


async def _create_routable_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> models.Event:
    integration = await _create_integration(session_factory)
    destination = await _create_destination(session_factory, integration.id)
    event = await _create_event(session_factory, integration.id, event_type="invoice.paid")
    await _create_routing_rule(
        session_factory,
        integration.id,
        destination.id,
        event_type=event.event_type,
    )
    return event


def _destination_document(
    *,
    endpoint_url: str = "https://example.invalid/webhooks/billing",
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": "Billing Service",
        "destination_type": "http",
        "endpoint_url": endpoint_url,
        "configuration": configuration or {},
        "status": "active",
    }


def _routing_rule_document(
    *,
    destination_id: uuid.UUID,
    name: str = "Invoice paid to billing",
    priority: int = 100,
    status: str = "active",
) -> dict[str, Any]:
    return {
        "name": name,
        "destination_id": str(destination_id),
        "event_type": "invoice.paid",
        "priority": priority,
        "status": status,
    }


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _count(session: AsyncSession, model: type[Base]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
