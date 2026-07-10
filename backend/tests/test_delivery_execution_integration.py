import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime, timedelta, timezone
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


def test_successful_delivery_posts_payload_and_records_attempt(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, payload={"invoice": "paid"})
        requests: list[dict[str, Any]] = []
        _override_http_client(
            app,
            lambda request: _json_response(request, 204, requests=requests),
        )

        async with _client(app) as client:
            response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json() == {
            "delivery_id": str(delivery.id),
            "status": "delivered",
            "attempt_number": 1,
            "retry_scheduled": False,
            "dead_lettered": False,
            "next_attempt_at": None,
        }
        assert requests == [
            {
                "url": "https://downstream.test/webhook",
                "body": {"invoice": "paid"},
                "content_type": "application/json",
            }
        ]
        async with session_factory() as session:
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            refreshed_event = await session.get(models.Event, delivery.event_id)
            attempt = await session.scalar(select(models.DeliveryAttempt))
            assert refreshed_delivery is not None
            assert refreshed_delivery.status == "delivered"
            assert refreshed_delivery.delivered_at is not None
            assert refreshed_delivery.attempt_count == 1
            assert refreshed_event is not None
            assert refreshed_event.status == "delivered"
            assert attempt is not None
            assert attempt.outcome == "succeeded"
            assert attempt.response_status_code == 204
            assert attempt.is_retryable is False
            assert await _count(session, models.RetryJob) == 0
            assert await _count(session, models.DeadLetterEvent) == 0
            transition = await session.scalar(select(models.EventStateTransition))
            assert transition is not None
            assert transition.from_status == "accepted"
            assert transition.to_status == "delivered"

    asyncio.run(exercise())


def test_retryable_http_failure_creates_pending_retry_job(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory)
        _override_http_client(app, lambda request: httpx.Response(503, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert response.status_code == 200
        _assert_correlation_id(response)
        data = response.json()
        assert data["status"] == "failed"
        assert data["attempt_number"] == 1
        assert data["retry_scheduled"] is True
        assert data["dead_lettered"] is False
        assert data["next_attempt_at"] is not None
        async with session_factory() as session:
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            attempt = await session.scalar(select(models.DeliveryAttempt))
            retry_job = await session.scalar(select(models.RetryJob))
            assert refreshed_delivery is not None
            assert refreshed_delivery.status == "failed"
            assert refreshed_delivery.next_attempt_at is not None
            assert refreshed_delivery.last_error_code == "http_503"
            assert attempt is not None
            assert attempt.outcome == "failed"
            assert attempt.response_status_code == 503
            assert attempt.is_retryable is True
            assert retry_job is not None
            assert retry_job.status == "pending"
            assert retry_job.run_at == refreshed_delivery.next_attempt_at
            assert await _count(session, models.DeadLetterEvent) == 0

    asyncio.run(exercise())


def test_non_retryable_http_failure_creates_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory)
        _override_http_client(app, lambda request: httpx.Response(404, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert response.status_code == 200
        _assert_correlation_id(response)
        assert response.json()["status"] == "dead_lettered"
        assert response.json()["retry_scheduled"] is False
        assert response.json()["dead_lettered"] is True
        async with session_factory() as session:
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            attempt = await session.scalar(select(models.DeliveryAttempt))
            dead_letter = await session.scalar(select(models.DeadLetterEvent))
            assert refreshed_delivery is not None
            assert refreshed_delivery.status == "dead_lettered"
            assert attempt is not None
            assert attempt.outcome == "failed"
            assert attempt.response_status_code == 404
            assert attempt.is_retryable is False
            assert dead_letter is not None
            assert dead_letter.severity == "high"
            assert dead_letter.reason_code == "http_404"
            assert await _count(session, models.RetryJob) == 0

    asyncio.run(exercise())


def test_timeout_failure_records_safe_error_and_schedules_retry(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory)

        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("secret payload value", request=request)

        _override_http_client(app, raise_timeout)

        async with _client(app) as client:
            execute_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")
            attempts_response = await client.get(f"/api/v1/deliveries/{delivery.id}/attempts")

        assert execute_response.status_code == 200
        _assert_correlation_id(execute_response)
        assert execute_response.json()["status"] == "failed"
        assert execute_response.json()["retry_scheduled"] is True
        assert attempts_response.status_code == 200
        _assert_correlation_id(attempts_response)
        attempts = attempts_response.json()
        assert attempts[0]["outcome"] == "timed_out"
        assert attempts[0]["error_code"] == "timeout"
        assert attempts[0]["error_message"] == "downstream request timed out"
        assert "secret" not in json.dumps(attempts)
        async with session_factory() as session:
            assert await _count(session, models.RetryJob) == 1
            assert await _count(session, models.DeadLetterEvent) == 0

    asyncio.run(exercise())


def test_due_retry_job_executes_delivery_and_completed_jobs_conflict(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory)
        responses = [httpx.Response(500), httpx.Response(200)]

        def handler(request: httpx.Request) -> httpx.Response:
            response = responses.pop(0)
            response.request = request
            return response

        _override_http_client(app, handler)
        async with _client(app) as client:
            first_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert first_response.status_code == 200
        async with session_factory() as session:
            retry_job = await session.scalar(select(models.RetryJob))
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            assert retry_job is not None
            assert refreshed_delivery is not None
            due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            retry_job.run_at = due_at
            refreshed_delivery.next_attempt_at = due_at
            await session.commit()
            retry_job_id = retry_job.id

        async with _client(app) as client:
            retry_response = await client.post(f"/api/v1/retry-jobs/{retry_job_id}/execute")
            completed_response = await client.post(f"/api/v1/retry-jobs/{retry_job_id}/execute")

        assert retry_response.status_code == 200
        _assert_correlation_id(retry_response)
        assert retry_response.json()["retry_status"] == "completed"
        assert retry_response.json()["delivery_status"] == "delivered"
        assert completed_response.status_code == 409
        _assert_correlation_id(completed_response)
        async with session_factory() as session:
            assert await _count(session, models.DeliveryAttempt) == 2
            retry_job = await session.get(models.RetryJob, retry_job_id)
            assert retry_job is not None
            assert retry_job.status == "completed"
            assert retry_job.claimed_at is not None
            assert retry_job.completed_at is not None

    asyncio.run(exercise())


def test_stale_pending_retry_job_is_cancelled_after_direct_success(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory)
        responses = [httpx.Response(500), httpx.Response(200)]

        def handler(request: httpx.Request) -> httpx.Response:
            response = responses.pop(0)
            response.request = request
            return response

        _override_http_client(app, handler)
        async with _client(app) as client:
            first_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert first_response.status_code == 200
        retry_job_id = await _make_pending_retry_due(session_factory, delivery.id)

        async with _client(app) as client:
            direct_success_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")
            stale_retry_response = await client.post(f"/api/v1/retry-jobs/{retry_job_id}/execute")

        assert direct_success_response.status_code == 200
        assert direct_success_response.json()["status"] == "delivered"
        assert stale_retry_response.status_code == 409
        _assert_correlation_id(direct_success_response)
        _assert_correlation_id(stale_retry_response)
        async with session_factory() as session:
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            retry_job = await session.get(models.RetryJob, retry_job_id)
            assert refreshed_delivery is not None
            assert refreshed_delivery.status == "delivered"
            assert retry_job is not None
            assert retry_job.status == "cancelled"
            assert retry_job.status != "pending"
            assert retry_job.status != "claimed"
            assert await _count(session, models.DeliveryAttempt) == 2
            assert await _count(session, models.DeadLetterEvent) == 0

    asyncio.run(exercise())


def test_stale_pending_retry_job_is_cancelled_after_direct_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, configuration={"max_attempts": 2})
        _override_http_client(app, lambda request: httpx.Response(500, request=request))

        async with _client(app) as client:
            first_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert first_response.status_code == 200
        retry_job_id = await _make_pending_retry_due(session_factory, delivery.id)

        async with _client(app) as client:
            terminal_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert terminal_response.status_code == 200
        assert terminal_response.json()["status"] == "dead_lettered"
        _assert_correlation_id(terminal_response)
        async with session_factory() as session:
            refreshed_delivery = await session.get(models.EventDelivery, delivery.id)
            retry_job = await session.get(models.RetryJob, retry_job_id)
            assert refreshed_delivery is not None
            assert refreshed_delivery.status == "dead_lettered"
            assert retry_job is not None
            assert retry_job.status == "cancelled"
            assert retry_job.status != "claimed"
            assert await _count(session, models.DeadLetterEvent) == 1

    asyncio.run(exercise())


def test_future_and_cancelled_retry_jobs_return_conflict(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, status="failed")
        future_job_id = await _create_retry_job(
            session_factory,
            delivery.id,
            status="pending",
            run_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        cancelled_job_id = await _create_retry_job(
            session_factory,
            delivery.id,
            status="cancelled",
            run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        _override_http_client(app, lambda request: httpx.Response(200, request=request))

        async with _client(app) as client:
            future_response = await client.post(f"/api/v1/retry-jobs/{future_job_id}/execute")
            cancelled_response = await client.post(f"/api/v1/retry-jobs/{cancelled_job_id}/execute")

        assert future_response.status_code == 409
        assert cancelled_response.status_code == 409
        _assert_correlation_id(future_response)
        _assert_correlation_id(cancelled_response)

    asyncio.run(exercise())


def test_claimed_retry_job_returns_conflict_and_remains_claimed(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, status="failed")
        claimed_job_id = await _create_retry_job(
            session_factory,
            delivery.id,
            status="claimed",
            run_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        _override_http_client(app, lambda request: httpx.Response(200, request=request))

        async with _client(app) as client:
            response = await client.post(f"/api/v1/retry-jobs/{claimed_job_id}/execute")

        assert response.status_code == 409
        _assert_correlation_id(response)
        async with session_factory() as session:
            retry_job = await session.get(models.RetryJob, claimed_job_id)
            assert retry_job is not None
            assert retry_job.status == "claimed"
            assert await _count(session, models.DeliveryAttempt) == 0

    asyncio.run(exercise())


def test_retry_exhaustion_creates_one_critical_dead_letter(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, configuration={"max_attempts": 1})
        _override_http_client(app, lambda request: httpx.Response(500, request=request))

        async with _client(app) as client:
            first_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")
            second_response = await client.post(f"/api/v1/deliveries/{delivery.id}/execute")

        assert first_response.status_code == 200
        assert first_response.json()["status"] == "dead_lettered"
        assert first_response.json()["dead_lettered"] is True
        assert second_response.status_code == 409
        _assert_correlation_id(first_response)
        _assert_correlation_id(second_response)
        async with session_factory() as session:
            dead_letter = await session.scalar(select(models.DeadLetterEvent))
            assert dead_letter is not None
            assert dead_letter.severity == "critical"
            assert dead_letter.reason_code == "retry_exhausted"
            assert await _count(session, models.DeadLetterEvent) == 1
            assert await _count(session, models.RetryJob) == 0

    asyncio.run(exercise())


def test_metadata_apis_return_safe_documents(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        delivery = await _create_delivery(session_factory, payload={"secret_payload": "hidden"})
        _override_http_client(app, lambda request: httpx.Response(400, request=request))

        async with _client(app) as client:
            await client.post(f"/api/v1/deliveries/{delivery.id}/execute")
            attempts_response = await client.get(f"/api/v1/deliveries/{delivery.id}/attempts")
            retry_jobs_response = await client.get(f"/api/v1/deliveries/{delivery.id}/retry-jobs")
            dead_letters_response = await client.get("/api/v1/dead-letters?severity=high")

        assert attempts_response.status_code == 200
        assert retry_jobs_response.status_code == 200
        assert dead_letters_response.status_code == 200
        _assert_correlation_id(attempts_response)
        _assert_correlation_id(retry_jobs_response)
        _assert_correlation_id(dead_letters_response)
        attempts = attempts_response.json()
        retry_jobs = retry_jobs_response.json()
        dead_letters = dead_letters_response.json()
        assert set(attempts[0]) == {
            "attempt_id",
            "delivery_id",
            "attempt_number",
            "outcome",
            "response_status_code",
            "error_code",
            "error_message",
            "is_retryable",
            "started_at",
            "finished_at",
            "created_at",
        }
        assert retry_jobs == []
        assert set(dead_letters[0]) == {
            "dead_letter_id",
            "delivery_id",
            "severity",
            "reason_code",
            "reason_message",
            "resolution_status",
            "dead_lettered_at",
            "resolved_at",
            "created_at",
            "updated_at",
        }
        response_text = json.dumps(
            {
                "attempts": attempts,
                "retry_jobs": retry_jobs,
                "dead_letters": dead_letters,
            }
        )
        assert "secret_payload" not in response_text
        assert "response body" not in response_text

    asyncio.run(exercise())


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    configuration: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    status: str = "scheduled",
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
                "settings": configuration or {},
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
            status=status,
            next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            attempt_count=0,
        )
        session.add_all([integration, destination, event, event_payload, delivery])
        await session.commit()
        return delivery


async def _create_retry_job(
    session_factory: async_sessionmaker[AsyncSession],
    delivery_id: uuid.UUID,
    *,
    status: str,
    run_at: datetime,
) -> uuid.UUID:
    async with session_factory() as session:
        retry_job = models.RetryJob(
            delivery_id=delivery_id,
            status=status,
            run_at=run_at,
        )
        session.add(retry_job)
        await session.commit()
        return retry_job.id


async def _make_pending_retry_due(
    session_factory: async_sessionmaker[AsyncSession],
    delivery_id: uuid.UUID,
) -> uuid.UUID:
    async with session_factory() as session:
        retry_job = await session.scalar(
            select(models.RetryJob).where(
                models.RetryJob.delivery_id == delivery_id,
                models.RetryJob.status == "pending",
            )
        )
        delivery = await session.get(models.EventDelivery, delivery_id)
        assert retry_job is not None
        assert delivery is not None
        due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        retry_job.run_at = due_at
        delivery.next_attempt_at = due_at
        await session.commit()
        return retry_job.id


def _override_http_client(
    app: FastAPI,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async def override() -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            yield client

    app.dependency_overrides[get_delivery_http_client] = override


def _json_response(
    request: httpx.Request,
    status_code: int,
    *,
    requests: list[dict[str, Any]],
) -> httpx.Response:
    requests.append(
        {
            "url": str(request.url),
            "body": json.loads(request.content),
            "content_type": request.headers["content-type"],
        }
    )
    return httpx.Response(status_code, request=request)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _count(session: AsyncSession, model: type[Base]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_correlation_id(response: httpx.Response) -> None:
    header = response.headers["x-correlation-id"]
    assert str(uuid.UUID(header)) == header
