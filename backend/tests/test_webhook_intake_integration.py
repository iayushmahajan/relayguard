import asyncio
import hashlib
import json
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


def test_valid_webhook_creates_initial_lifecycle(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        raw_body = _webhook_body(deduplication_key="key-accepted", source_event_id="source-1")
        response = await _post_webhook(app, integration.slug, raw_body)

        assert response.status_code == 202
        _assert_correlation_id(response)
        data = response.json()
        assert data["status"] == "accepted"
        assert data["duplicate"] is False

        async with session_factory() as session:
            receipt = await session.get(models.WebhookReceipt, uuid.UUID(data["receipt_id"]))
            event = await session.get(models.Event, uuid.UUID(data["event_id"]))
            receipt_count = await _count(session, models.WebhookReceipt)
            payload_count = await _count(session, models.EventPayload)
            transition_count = await _count(session, models.EventStateTransition)
            transition = await session.scalar(select(models.EventStateTransition))
            payload = await session.scalar(select(models.EventPayload))

        assert receipt is not None
        assert receipt.status == "accepted"
        assert receipt_count == 1
        assert receipt.request_method == "POST"
        assert receipt.request_path == f"/api/v1/integrations/{integration.slug}/webhooks"
        assert receipt.content_type == "application/json"
        assert receipt.body_size_bytes == len(raw_body)
        assert receipt.correlation_id is not None
        assert receipt.raw_body_hash == hashlib.sha256(raw_body).hexdigest()
        assert event is not None
        assert event.status == "accepted"
        assert event.accepted_at is not None
        assert event.receipt_id == receipt.id
        assert payload_count == 1
        assert transition_count == 1
        assert payload is not None
        assert payload.payload == {"amount": 4200}
        assert payload.payload_hash == receipt.raw_body_hash
        assert transition is not None
        assert transition.from_status is None
        assert transition.to_status == "accepted"

    asyncio.run(exercise())


def test_duplicate_deduplication_key_creates_duplicate_receipt_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        first = await _post_webhook(app, integration.slug, _webhook_body(deduplication_key="same"))
        second = await _post_webhook(app, integration.slug, _webhook_body(deduplication_key="same"))

        assert first.status_code == 202
        assert second.status_code == 200
        _assert_correlation_id(first)
        _assert_correlation_id(second)
        assert second.json()["duplicate"] is True
        assert second.json()["event_id"] == first.json()["event_id"]

        async with session_factory() as session:
            receipt_statuses = (
                await session.scalars(
                    select(models.WebhookReceipt.status).order_by(models.WebhookReceipt.received_at)
                )
            ).all()
            assert receipt_statuses == ["accepted", "duplicate"]
            assert await _count(session, models.Event) == 1
            assert await _count(session, models.EventPayload) == 1
            assert await _count(session, models.EventStateTransition) == 1

    asyncio.run(exercise())


def test_duplicate_source_event_id_maps_to_original_event(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        first = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="key-1", source_event_id="provider-1"),
        )
        second = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="key-2", source_event_id="provider-1"),
        )

        assert first.status_code == 202
        assert second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["event_id"] == first.json()["event_id"]
        async with session_factory() as session:
            assert await _count(session, models.WebhookReceipt) == 2
            assert await _count(session, models.Event) == 1
            assert await _count(session, models.EventPayload) == 1
            assert await _count(session, models.EventStateTransition) == 1

    asyncio.run(exercise())


def test_null_source_event_id_allows_distinct_deduplication_keys(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        first = await _post_webhook(app, integration.slug, _webhook_body(deduplication_key="key-1"))
        second = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="key-2"),
        )

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["event_id"] != second.json()["event_id"]
        async with session_factory() as session:
            assert await _count(session, models.WebhookReceipt) == 2
            assert await _count(session, models.Event) == 2
            assert await _count(session, models.EventPayload) == 2
            assert await _count(session, models.EventStateTransition) == 2

    asyncio.run(exercise())


def test_disabled_integration_creates_rejected_receipt_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=False)
        response = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="disabled"),
        )

        assert response.status_code == 409
        _assert_correlation_id(response)
        assert response.json()["detail"] == "integration disabled"
        async with session_factory() as session:
            receipt = await session.scalar(select(models.WebhookReceipt))
            assert receipt is not None
            assert receipt.status == "rejected"
            assert receipt.rejection_reason == "integration disabled"
            assert await _count(session, models.Event) == 0
            assert await _count(session, models.EventPayload) == 0
            assert await _count(session, models.EventStateTransition) == 0

    asyncio.run(exercise())


def test_disabled_integration_rejects_before_content_type_validation(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=False)
        raw_body = b"disabled plain text body"
        response = await _post_webhook(
            app,
            integration.slug,
            raw_body,
            content_type="text/plain",
        )

        assert response.status_code == 409
        _assert_correlation_id(response)
        assert response.json()["detail"] == "integration disabled"
        async with session_factory() as session:
            receipt = await session.scalar(select(models.WebhookReceipt))
            assert receipt is not None
            assert receipt.status == "rejected"
            assert receipt.rejection_reason == "integration disabled"
            assert receipt.content_type == "text/plain"
            assert receipt.body_size_bytes == len(raw_body)
            assert receipt.request_method == "POST"
            assert receipt.request_path == f"/api/v1/integrations/{integration.slug}/webhooks"
            assert receipt.correlation_id is not None
            assert receipt.raw_body_hash == hashlib.sha256(raw_body).hexdigest()
            assert await _count(session, models.WebhookReceipt) == 1
            assert await _count(session, models.Event) == 0
            assert await _count(session, models.EventPayload) == 0
            assert await _count(session, models.EventStateTransition) == 0

    asyncio.run(exercise())


def test_invalid_known_integration_request_creates_rejected_receipt_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        response = await _post_webhook(
            app,
            integration.slug,
            json.dumps(
                {
                    "event_type": "invoice.paid",
                    "deduplication_key": "invalid",
                    "payload": [],
                }
            ).encode("utf-8"),
        )

        assert response.status_code == 422
        _assert_correlation_id(response)
        assert response.json()["detail"] == "invalid webhook envelope"
        async with session_factory() as session:
            receipt = await session.scalar(select(models.WebhookReceipt))
            assert receipt is not None
            assert receipt.status == "rejected"
            assert receipt.rejection_reason == "invalid webhook envelope"
            assert await _count(session, models.Event) == 0
            assert await _count(session, models.EventPayload) == 0
            assert await _count(session, models.EventStateTransition) == 0

    asyncio.run(exercise())


def test_invalid_json_for_known_integration_creates_rejected_receipt_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        response = await _post_webhook(app, integration.slug, b"{not-json")

        assert response.status_code == 400
        _assert_correlation_id(response)
        assert response.json()["detail"] == "invalid json"
        async with session_factory() as session:
            receipt = await session.scalar(select(models.WebhookReceipt))
            assert receipt is not None
            assert receipt.status == "rejected"
            assert receipt.rejection_reason == "invalid json"
            assert await _count(session, models.Event) == 0

    asyncio.run(exercise())


def test_unsupported_content_type_for_known_integration_creates_rejected_receipt_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        response = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="bad-content-type"),
            content_type="text/plain",
        )

        assert response.status_code == 415
        _assert_correlation_id(response)
        assert response.json()["detail"] == "unsupported content type"
        async with session_factory() as session:
            receipt = await session.scalar(select(models.WebhookReceipt))
            assert receipt is not None
            assert receipt.status == "rejected"
            assert receipt.rejection_reason == "unsupported content type"
            assert await _count(session, models.Event) == 0

    asyncio.run(exercise())


def test_unknown_integration_creates_no_receipt(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        response = await _post_webhook(app, "missing", _webhook_body(deduplication_key="missing"))

        assert response.status_code == 404
        _assert_correlation_id(response)
        assert response.json()["detail"] == "integration not found"
        async with session_factory() as session:
            assert await _count(session, models.WebhookReceipt) == 0

    asyncio.run(exercise())


def test_event_metadata_endpoint_returns_safe_fields_only(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        integration = await _create_integration(session_factory, active=True)
        intake_response = await _post_webhook(
            app,
            integration.slug,
            _webhook_body(deduplication_key="metadata", source_event_id="metadata-source"),
        )
        event_id = intake_response.json()["event_id"]

        async with _client(app) as client:
            metadata_response = await client.get(f"/api/v1/events/{event_id}")

        assert metadata_response.status_code == 200
        _assert_correlation_id(metadata_response)
        data = metadata_response.json()
        assert set(data) == {
            "event_id",
            "integration_id",
            "event_type",
            "source_event_id",
            "status",
            "received_at",
            "accepted_at",
        }
        assert data["event_id"] == event_id
        assert data["integration_id"] == str(integration.id)
        assert data["event_type"] == "invoice.paid"
        assert data["source_event_id"] == "metadata-source"
        assert data["status"] == "accepted"
        assert "payload" not in data

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_integration(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    active: bool,
) -> models.Integration:
    async with session_factory() as session:
        integration = models.Integration(
            name=f"Integration {uuid.uuid4()}",
            slug=f"integration-{uuid.uuid4()}",
            enabled=active,
            status="active" if active else "disabled",
        )
        session.add(integration)
        await session.commit()
        return integration


async def _post_webhook(
    app: FastAPI,
    integration_slug: str,
    raw_body: bytes,
    *,
    content_type: str = "application/json",
) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(
            f"/api/v1/integrations/{integration_slug}/webhooks",
            content=raw_body,
            headers={"content-type": content_type},
        )


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def _webhook_body(
    *,
    deduplication_key: str,
    source_event_id: str | None = None,
) -> bytes:
    document: dict[str, Any] = {
        "event_type": "invoice.paid",
        "deduplication_key": deduplication_key,
        "payload": {"amount": 4200},
    }
    if source_event_id is not None:
        document["source_event_id"] = source_event_id
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


async def _count(session: AsyncSession, model: type[Base]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
