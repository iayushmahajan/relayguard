import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime, timezone
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

from app.api.delivery_execution import get_delivery_http_client
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


def test_replay_request_creation_validation_and_audit_logging(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        unknown_dead_letter_id = uuid.uuid4()
        async with _client(app) as client:
            unknown_response = await client.post(
                f"/api/v1/dead-letters/{unknown_dead_letter_id}/replay-requests",
                json=_replay_create_document(),
            )

        assert unknown_response.status_code == 404
        _assert_correlation_id(unknown_response)

        delivery_id, dead_letter_id = await _create_dead_lettered_delivery(app, session_factory)
        async with _client(app) as client:
            create_response = await client.post(
                f"/api/v1/dead-letters/{dead_letter_id}/replay-requests",
                json=_replay_create_document(),
            )
            duplicate_response = await client.post(
                f"/api/v1/dead-letters/{dead_letter_id}/replay-requests",
                json=_replay_create_document(reason="try again"),
            )

        assert create_response.status_code == 201
        assert duplicate_response.status_code == 409
        _assert_correlation_id(create_response)
        _assert_correlation_id(duplicate_response)
        created = create_response.json()
        assert created["status"] == "pending"
        assert created["delivery_id"] == str(delivery_id)
        assert created["dead_letter_id"] == str(dead_letter_id)
        assert created["reason"] == "Downstream recovered"
        assert created["requested_by"] == "system-operator"
        assert "payload" not in created

        resolved_dead_letter_id = await _create_resolved_dead_letter(session_factory)
        async with _client(app) as client:
            resolved_response = await client.post(
                f"/api/v1/dead-letters/{resolved_dead_letter_id}/replay-requests",
                json=_replay_create_document(),
            )

        assert resolved_response.status_code == 409
        _assert_correlation_id(resolved_response)
        async with session_factory() as session:
            assert await _count(session, models.ReplayRequest) == 1
            assert await _audit_count(session, "replay_request.created") == 1

    asyncio.run(exercise())


def test_replay_request_approval_and_rejection_transitions(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        _delivery_id, dead_letter_id = await _create_dead_lettered_delivery(app, session_factory)
        replay_request_id = await _create_replay_request(app, dead_letter_id)
        async with _client(app) as client:
            approve_response = await client.post(
                f"/api/v1/replay-requests/{replay_request_id}/approve",
                json={"approved_by": "system-operator", "note": "destination checked"},
            )
            reapprove_response = await client.post(
                f"/api/v1/replay-requests/{replay_request_id}/approve",
                json={"approved_by": "system-operator"},
            )
            reject_approved_response = await client.post(
                f"/api/v1/replay-requests/{replay_request_id}/reject",
                json={"rejected_by": "system-operator", "reason": "pause replay"},
            )

        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"
        assert approve_response.json()["approved_by"] == "system-operator"
        assert reapprove_response.status_code == 409
        assert reject_approved_response.status_code == 200
        assert reject_approved_response.json()["status"] == "rejected"
        _assert_correlation_id(approve_response)
        _assert_correlation_id(reapprove_response)
        _assert_correlation_id(reject_approved_response)

        second_dead_letter_id = (await _create_dead_lettered_delivery(app, session_factory))[1]
        rejected_request_id = await _create_replay_request(app, second_dead_letter_id)
        async with _client(app) as client:
            reject_response = await client.post(
                f"/api/v1/replay-requests/{rejected_request_id}/reject",
                json={"rejected_by": "system-operator", "reason": "unsafe"},
            )
            approve_rejected_response = await client.post(
                f"/api/v1/replay-requests/{rejected_request_id}/approve",
                json={"approved_by": "system-operator"},
            )
            execute_rejected_response = await client.post(
                f"/api/v1/replay-requests/{rejected_request_id}/execute"
            )

        assert reject_response.status_code == 200
        assert approve_rejected_response.status_code == 409
        assert execute_rejected_response.status_code == 409
        _assert_correlation_id(reject_response)
        _assert_correlation_id(approve_rejected_response)
        _assert_correlation_id(execute_rejected_response)
        async with session_factory() as session:
            assert await _audit_count(session, "replay_request.approved") == 1
            assert await _audit_count(session, "replay_request.rejected") == 2

    asyncio.run(exercise())


def test_replay_rejects_running_and_terminal_requests(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        for status in ["running", "completed", "resolved", "executed"]:
            replay_request_id = await _create_replay_request_with_status(session_factory, status)
            async with _client(app) as client:
                response = await client.post(
                    f"/api/v1/replay-requests/{replay_request_id}/reject",
                    json={"rejected_by": "system-operator", "reason": "no"},
                )
            assert response.status_code == 409
            _assert_correlation_id(response)

    asyncio.run(exercise())


def test_successful_replay_execution_resolves_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery_id, dead_letter_id = await _create_dead_lettered_delivery(app, session_factory)
        replay_request_id = await _create_replay_request(app, dead_letter_id)
        await _approve_replay_request(app, replay_request_id)
        _override_http_client(app, lambda request: httpx.Response(204, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/replay-requests/{replay_request_id}/execute")
            second_response = await client.post(
                f"/api/v1/replay-requests/{replay_request_id}/execute"
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json() == {
            "replay_request_id": str(replay_request_id),
            "delivery_id": str(delivery_id),
            "replay_status": "resolved",
            "delivery_status": "delivered",
            "attempt_recorded": True,
            "dead_letter_resolved": True,
        }
        assert second_response.status_code == 409
        _assert_correlation_id(second_response)
        async with session_factory() as session:
            delivery = await session.get(models.EventDelivery, delivery_id)
            dead_letter = await session.get(models.DeadLetterEvent, dead_letter_id)
            replay_request = await session.get(models.ReplayRequest, replay_request_id)
            assert delivery is not None
            assert dead_letter is not None
            assert replay_request is not None
            assert delivery.status == "delivered"
            assert dead_letter.resolution_status == "resolved"
            assert dead_letter.resolved_at is not None
            assert replay_request.status == "resolved"
            assert replay_request.executed_at is not None
            assert replay_request.resolved_at is not None
            assert await _count(session, models.DeliveryAttempt) == 2
            assert await _count(session, models.DeadLetterEvent) == 1
            assert await _audit_count(session, "replay_request.executed") == 1
            assert await _audit_count(session, "replay_request.resolved") == 1

    asyncio.run(exercise())


def test_retryable_replay_failure_records_attempt_without_resolving_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery_id, dead_letter_id = await _create_dead_lettered_delivery(app, session_factory)
        replay_request_id = await _create_replay_request(app, dead_letter_id)
        await _approve_replay_request(app, replay_request_id)
        _override_http_client(app, lambda request: httpx.Response(503, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/replay-requests/{replay_request_id}/execute")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json()["replay_status"] == "executed"
        assert response.json()["delivery_status"] == "failed"
        assert response.json()["attempt_recorded"] is True
        assert response.json()["dead_letter_resolved"] is False
        async with session_factory() as session:
            delivery = await session.get(models.EventDelivery, delivery_id)
            dead_letter = await session.get(models.DeadLetterEvent, dead_letter_id)
            assert delivery is not None
            assert dead_letter is not None
            assert delivery.status == "failed"
            assert dead_letter.resolution_status == "open"
            assert await _count(session, models.DeliveryAttempt) == 2
            assert await _count(session, models.RetryJob) == 1
            assert await _count(session, models.DeadLetterEvent) == 1
            assert await _audit_count(session, "replay_request.executed_unresolved") == 1

    asyncio.run(exercise())


def test_non_retryable_replay_failure_does_not_duplicate_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery_id, dead_letter_id = await _create_dead_lettered_delivery(app, session_factory)
        replay_request_id = await _create_replay_request(app, dead_letter_id)
        await _approve_replay_request(app, replay_request_id)
        _override_http_client(app, lambda request: httpx.Response(400, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/replay-requests/{replay_request_id}/execute")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json()["replay_status"] == "executed"
        assert response.json()["delivery_status"] == "dead_lettered"
        assert response.json()["dead_letter_resolved"] is False
        async with session_factory() as session:
            delivery = await session.get(models.EventDelivery, delivery_id)
            dead_letter = await session.get(models.DeadLetterEvent, dead_letter_id)
            assert delivery is not None
            assert dead_letter is not None
            assert delivery.status == "dead_lettered"
            assert dead_letter.resolution_status == "open"
            assert await _count(session, models.DeliveryAttempt) == 2
            assert await _count(session, models.DeadLetterEvent) == 1
            assert await _count(session, models.RetryJob) == 0

    asyncio.run(exercise())


def test_invalid_replay_execution_transitions_and_unknown_request(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        dead_letter_id = (await _create_dead_lettered_delivery(app, session_factory))[1]
        pending_request_id = await _create_replay_request(app, dead_letter_id)
        unknown_request_id = uuid.uuid4()

        async with _client(app) as client:
            pending_execute_response = await client.post(
                f"/api/v1/replay-requests/{pending_request_id}/execute"
            )
            unknown_response = await client.get(f"/api/v1/replay-requests/{unknown_request_id}")
            unknown_execute_response = await client.post(
                f"/api/v1/replay-requests/{unknown_request_id}/execute"
            )

        assert pending_execute_response.status_code == 409
        assert unknown_response.status_code == 404
        assert unknown_execute_response.status_code == 404
        _assert_correlation_id(pending_execute_response)
        _assert_correlation_id(unknown_response)
        _assert_correlation_id(unknown_execute_response)

    asyncio.run(exercise())


def test_replay_request_metadata_apis_are_safe_and_filterable(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        dead_letter_id = (
            await _create_dead_lettered_delivery(
                app,
                session_factory,
                payload={"secret_payload": "hidden"},
            )
        )[1]
        replay_request_id = await _create_replay_request(app, dead_letter_id)

        async with _client(app) as client:
            list_response = await client.get("/api/v1/replay-requests?status=pending")
            filtered_response = await client.get(
                f"/api/v1/replay-requests?dead_letter_id={dead_letter_id}"
            )
            get_response = await client.get(f"/api/v1/replay-requests/{replay_request_id}")

        assert list_response.status_code == 200
        assert filtered_response.status_code == 200
        assert get_response.status_code == 200
        _assert_correlation_id(list_response)
        _assert_correlation_id(filtered_response)
        _assert_correlation_id(get_response)
        listed = list_response.json()
        assert len(listed) == 1
        assert filtered_response.json() == listed
        assert get_response.json() == listed[0]
        assert set(listed[0]) == {
            "replay_request_id",
            "status",
            "event_id",
            "delivery_id",
            "dead_letter_id",
            "reason",
            "requested_by",
            "approved_by",
            "rejected_by",
            "created_at",
            "updated_at",
            "executed_at",
            "resolved_at",
        }
        assert "secret_payload" not in json.dumps(listed)
        assert "response body" not in json.dumps(listed)

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_dead_lettered_delivery(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    delivery = await _create_delivery(session_factory, payload=payload)
    _override_http_client(app, lambda request: httpx.Response(404, request=request))
    async with _client(app) as client:
        response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")
    assert response.status_code == 200
    async with session_factory() as session:
        dead_letter_id = await session.scalar(
            select(models.DeadLetterEvent.id).where(
                models.DeadLetterEvent.delivery_id == delivery.id
            )
        )
        assert dead_letter_id is not None
        return delivery.id, dead_letter_id


async def _create_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    payload: dict[str, Any] | None = None,
) -> models.EventDelivery:
    async with session_factory() as session:
        integration = models.Integration(
            name=f"Integration {uuid.uuid4()}",
            slug=f"integration-{uuid.uuid4()}",
            enabled=True,
            status="active",
        )
        destination = models.DownstreamDestination(
            integration=integration,
            name=f"Destination {uuid.uuid4()}",
            endpoint_url="https://downstream.test/webhook",
            status="active",
            configuration={
                "destination_type": "http",
                "settings": {},
            },
        )
        event = models.Event(
            integration=integration,
            deduplication_key=f"event-{uuid.uuid4()}",
            event_type="invoice.paid",
            status="accepted",
        )
        event_payload = models.EventPayload(
            event=event,
            payload=payload or {"invoice": "paid"},
            content_type="application/json",
        )
        delivery = models.EventDelivery(
            event=event,
            destination=destination,
            status="scheduled",
            next_attempt_at=datetime.now(timezone.utc),
            attempt_count=0,
        )
        session.add_all([integration, destination, event, event_payload, delivery])
        await session.commit()
        return delivery


async def _create_replay_request(app: FastAPI, dead_letter_id: uuid.UUID) -> uuid.UUID:
    async with _client(app) as client:
        response = await client.post(
            f"/api/v1/dead-letters/{dead_letter_id}/replay-requests",
            json=_replay_create_document(),
        )
    assert response.status_code == 201
    return uuid.UUID(response.json()["replay_request_id"])


async def _approve_replay_request(app: FastAPI, replay_request_id: uuid.UUID) -> None:
    async with _client(app) as client:
        response = await client.post(
            f"/api/v1/replay-requests/{replay_request_id}/approve",
            json={"approved_by": "system-operator", "note": "destination checked"},
        )
    assert response.status_code == 200


async def _create_resolved_dead_letter(
    session_factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    async with session_factory() as session:
        delivery = await _create_delivery_in_session(session)
        delivery.status = "dead_lettered"
        dead_letter = models.DeadLetterEvent(
            delivery_id=delivery.id,
            resolution_status="resolved",
            severity="high",
            reason="failed",
            reason_code="http_404",
            reason_message="failed",
            resolved_at=datetime.now(timezone.utc),
        )
        session.add(dead_letter)
        await session.commit()
        return dead_letter.id


async def _create_replay_request_with_status(
    session_factory: async_sessionmaker[AsyncSession],
    status: str,
) -> uuid.UUID:
    async with session_factory() as session:
        delivery = await _create_delivery_in_session(session)
        delivery.status = "dead_lettered"
        dead_letter = models.DeadLetterEvent(
            delivery_id=delivery.id,
            severity="high",
            reason="failed",
            reason_code="http_404",
            reason_message="failed",
        )
        replay_request = models.ReplayRequest(
            dead_letter_event=dead_letter,
            status=status,
            request_document={"reason": "recover", "requested_by": "operator"},
        )
        session.add_all([dead_letter, replay_request])
        await session.commit()
        return replay_request.id


async def _create_delivery_in_session(session: AsyncSession) -> models.EventDelivery:
    integration = models.Integration(
        name=f"Integration {uuid.uuid4()}",
        slug=f"integration-{uuid.uuid4()}",
        enabled=True,
        status="active",
    )
    destination = models.DownstreamDestination(
        integration=integration,
        name=f"Destination {uuid.uuid4()}",
        endpoint_url="https://downstream.test/webhook",
        status="active",
        configuration={"destination_type": "http", "settings": {}},
    )
    event = models.Event(
        integration=integration,
        deduplication_key=f"event-{uuid.uuid4()}",
        event_type="invoice.paid",
        status="accepted",
    )
    delivery = models.EventDelivery(
        event=event,
        destination=destination,
        status="scheduled",
        next_attempt_at=datetime.now(timezone.utc),
    )
    session.add_all([integration, destination, event, delivery])
    await session.flush()
    return delivery


def _replay_create_document(*, reason: str = "Downstream recovered") -> dict[str, str]:
    return {
        "reason": reason,
        "requested_by": "system-operator",
    }


def _override_http_client(
    app: FastAPI,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async def override() -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    app.dependency_overrides[get_delivery_http_client] = override


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _count(session: AsyncSession, model: type[Base]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _audit_count(session: AsyncSession, action: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(models.AuditLog)
            .where(models.AuditLog.action == action)
        )
        or 0
    )


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
