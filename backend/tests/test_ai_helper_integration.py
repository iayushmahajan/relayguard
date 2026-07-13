import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone

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


def test_fallback_explain_delivery_returns_safe_structured_response(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery_id = await _create_failed_delivery(session_factory, response_status_code=503)
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/ai/explain-delivery",
                json={"delivery_id": str(delivery_id)},
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        data = response.json()
        assert data["mode"] == "fallback"
        assert data["likely_cause"] == "Temporary downstream outage."
        assert data["recommended_action"]
        assert data["risk_level"] == "medium"
        assert "Last attempt returned HTTP 503." in data["supporting_facts"]
        response_text = json.dumps(data)
        assert "secret_payload" not in response_text
        assert "response body" not in response_text
        assert "credential" not in response_text.lower()

    asyncio.run(exercise())


def test_explain_delivery_returns_404_for_unknown_delivery(app: FastAPI) -> None:
    async def exercise() -> None:
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/ai/explain-delivery",
                json={"delivery_id": str(uuid.uuid4())},
            )

        assert response.status_code == 404
        _assert_correlation_id(response)
        assert response.json()["detail"] == "delivery not found"

    asyncio.run(exercise())


def test_fallback_draft_replay_note_is_safe_and_has_no_side_effects(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery_id = await _create_failed_delivery(
            session_factory,
            delivery_status="dead_lettered",
            response_status_code=404,
            create_dead_letter=True,
        )
        async with session_factory() as session:
            dead_letter = await session.scalar(
                select(models.DeadLetterEvent).where(
                    models.DeadLetterEvent.delivery_id == delivery_id
                )
            )
            assert dead_letter is not None
            dead_letter_id = dead_letter.id

        async with _client(app) as client:
            response = await client.post(
                "/api/v1/ai/draft-replay-note",
                json={"dead_letter_id": str(dead_letter_id)},
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        data = response.json()
        assert data["mode"] == "fallback"
        assert "replay" in data["reason"].lower()
        assert "Approved for replay" in data["approval_note"]
        assert data["warnings"]
        response_text = json.dumps(data)
        assert "secret_payload" not in response_text
        assert "response body" not in response_text
        async with session_factory() as session:
            delivery = await session.get(models.EventDelivery, delivery_id)
            stored_dead_letter = await session.get(models.DeadLetterEvent, dead_letter_id)
            assert delivery is not None
            assert stored_dead_letter is not None
            assert delivery.status == "dead_lettered"
            assert stored_dead_letter.resolution_status == "open"
            assert await _count(session, models.ReplayRequest) == 0

    asyncio.run(exercise())


def test_draft_replay_note_returns_404_for_unknown_dead_letter(app: FastAPI) -> None:
    async def exercise() -> None:
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/ai/draft-replay-note",
                json={"dead_letter_id": str(uuid.uuid4())},
            )

        assert response.status_code == 404
        _assert_correlation_id(response)
        assert response.json()["detail"] == "dead letter not found"

    asyncio.run(exercise())


def test_fallback_sample_webhook_payload_returns_safe_json_object(app: FastAPI) -> None:
    async def exercise() -> None:
        async with _client(app) as client:
            response = await client.post(
                "/api/v1/ai/sample-webhook-payload",
                json={
                    "event_type": "invoice.paid",
                    "description": "A paid invoice event for a European customer",
                    "integration_slug": "stripe-sandbox",
                },
            )

        assert response.status_code == 200
        _assert_correlation_id(response)
        data = response.json()
        assert data["mode"] == "fallback"
        assert data["event_type"] == "invoice.paid"
        assert data["deduplication_key"].startswith("sample-invoice_paid-")
        assert data["source_event_id"].startswith("sample_evt_")
        assert isinstance(data["payload"], dict)
        assert data["payload"]["currency"] == "EUR"
        assert data["payload"]["amount"] == 4999
        response_text = json.dumps(data).lower()
        assert "secret" not in response_text
        assert "password" not in response_text
        assert "token" not in response_text

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_failed_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    delivery_status: str = "failed",
    response_status_code: int,
    create_dead_letter: bool = False,
) -> uuid.UUID:
    async with session_factory() as session:
        integration = models.Integration(
            name=f"Integration {uuid.uuid4()}",
            slug=f"integration-{uuid.uuid4()}",
            enabled=True,
            status="active",
        )
        destination = models.DownstreamDestination(
            integration=integration,
            name="Billing Service",
            endpoint_url="https://downstream.test/webhook",
            status="active",
            configuration={"destination_type": "http", "settings": {"timeout_seconds": 10}},
        )
        event = models.Event(
            integration=integration,
            deduplication_key=f"event-{uuid.uuid4()}",
            event_type="invoice.paid",
            status="accepted",
        )
        event_payload = models.EventPayload(
            event=event,
            payload={"invoice_id": "secret_payload", "amount": 4999},
            content_type="application/json",
        )
        delivery = models.EventDelivery(
            event=event,
            destination=destination,
            status=delivery_status,
            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            attempt_count=1,
            last_attempt_at=datetime.now(timezone.utc),
            last_error_code=f"http_{response_status_code}",
            last_error_message="Safe downstream status metadata only.",
        )
        attempt = models.DeliveryAttempt(
            delivery=delivery,
            attempt_number=1,
            status="failed",
            outcome="failed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            request_headers={"content-type": "application/json"},
            response_status_code=response_status_code,
            response_headers={"x-response-body": "metadata-only"},
            error_code=f"http_{response_status_code}",
            error_message="Safe downstream status metadata only.",
            is_retryable=response_status_code in {429, 500, 502, 503, 504},
        )
        session.add_all([integration, destination, event, event_payload, delivery, attempt])
        await session.flush()
        if response_status_code in {429, 500, 502, 503, 504}:
            session.add(
                models.RetryJob(
                    delivery=delivery,
                    status="pending",
                    run_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                )
            )
        if create_dead_letter:
            session.add(
                models.DeadLetterEvent(
                    delivery=delivery,
                    resolution_status="open",
                    severity="high",
                    reason="Terminal delivery rejection.",
                    reason_code=f"http_{response_status_code}",
                    reason_message="Downstream rejected the delivery.",
                )
            )
        await session.commit()
        return delivery.id


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _count(session: AsyncSession, model: type[Base]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
