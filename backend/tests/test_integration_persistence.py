import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.commands.seed import seed_database
from app.core.config import Settings
from app.db import models
from app.db.base import Base

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


def test_alembic_migration_is_applied(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async def check_revision() -> str:
        async with session_factory() as session:
            return str(await session.scalar(text("SELECT version_num FROM alembic_version")))

    assert asyncio.run(check_revision()) == "0006_replay_workflow"


def test_seed_command_is_idempotent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async def run_seed_and_count() -> tuple[int, int, list[tuple[str, bool, str]]]:
        first_result = await seed_database(session_factory)
        second_result = await seed_database(session_factory)
        async with session_factory() as session:
            role_count = await session.scalar(select(func.count()).select_from(models.Role))
            integration_count = await session.scalar(
                select(func.count()).select_from(models.Integration)
            )
            integrations = (
                await session.execute(
                    select(
                        models.Integration.slug,
                        models.Integration.enabled,
                        models.Integration.status,
                    )
                    .where(
                        models.Integration.slug.in_(
                            ["github-sandbox", "stripe-sandbox"],
                        )
                    )
                    .order_by(models.Integration.slug)
                )
            ).all()
        assert first_result.roles_created == 3
        assert first_result.integrations_created == 2
        assert second_result.roles_created == 0
        assert second_result.integrations_created == 0
        return (
            int(role_count or 0),
            int(integration_count or 0),
            [(slug, enabled, status) for slug, enabled, status in integrations],
        )

    role_count, integration_count, integrations = asyncio.run(run_seed_and_count())

    assert role_count == 3
    assert integration_count == 2
    assert integrations == [
        ("github-sandbox", False, "disabled"),
        ("stripe-sandbox", False, "disabled"),
    ]


def test_event_deduplication_key_unique_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            integration = await _create_integration(session)
            session.add_all(
                [
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="same-key",
                        event_type="example.created",
                    ),
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="same-key",
                        event_type="example.updated",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_event_source_event_id_partial_unique_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            integration = await _create_integration(session)
            session.add_all(
                [
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="key-1",
                        source_event_id="source-1",
                        event_type="example.created",
                    ),
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="key-2",
                        source_event_id="source-1",
                        event_type="example.updated",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_events_with_null_source_event_id_are_permitted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> int:
        async with session_factory() as session:
            integration = await _create_integration(session)
            session.add_all(
                [
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="key-1",
                        event_type="example.created",
                    ),
                    models.Event(
                        integration_id=integration.id,
                        deduplication_key="key-2",
                        event_type="example.updated",
                    ),
                ]
            )
            await session.commit()
            return int(await session.scalar(select(func.count()).select_from(models.Event)) or 0)

    assert asyncio.run(exercise()) == 2


def test_event_payload_is_one_to_one_per_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            event = await _create_event(session)
            session.add_all(
                [
                    models.EventPayload(event_id=event.id, payload={"sequence": 1}),
                    models.EventPayload(event_id=event.id, payload={"sequence": 2}),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_dead_letter_event_is_one_to_one_per_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            delivery = await _create_delivery(session)
            session.add_all(
                [
                    models.DeadLetterEvent(delivery_id=delivery.id, reason="failed"),
                    models.DeadLetterEvent(delivery_id=delivery.id, reason="failed again"),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_event_delivery_route_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            event, destination, routing_rule = await _create_event_route(session)
            session.add_all(
                [
                    models.EventDelivery(
                        event_id=event.id,
                        destination_id=destination.id,
                        routing_rule_id=routing_rule.id,
                    ),
                    models.EventDelivery(
                        event_id=event.id,
                        destination_id=destination.id,
                        routing_rule_id=routing_rule.id,
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_pending_retry_job_delivery_run_target_is_unique(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            delivery = await _create_delivery(session)
            run_at = datetime.now(timezone.utc)
            session.add_all(
                [
                    models.RetryJob(delivery_id=delivery.id, status="pending", run_at=run_at),
                    models.RetryJob(delivery_id=delivery.id, status="pending", run_at=run_at),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_only_one_active_replay_request_per_dead_letter_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            dead_letter_event = await _create_dead_letter_event(session)
            session.add_all(
                [
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status="pending",
                    ),
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status="approved",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


def test_running_replay_request_blocks_another_active_request(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def exercise() -> None:
        async with session_factory() as session:
            dead_letter_event = await _create_dead_letter_event(session)
            session.add_all(
                [
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status="running",
                    ),
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status="pending",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(exercise())


@pytest.mark.parametrize("terminal_status", ["resolved", "rejected", "executed", "cancelled"])
def test_terminal_replay_request_does_not_block_new_pending_request(
    session_factory: async_sessionmaker[AsyncSession],
    terminal_status: str,
) -> None:
    async def exercise() -> int:
        async with session_factory() as session:
            dead_letter_event = await _create_dead_letter_event(session)
            session.add_all(
                [
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status=terminal_status,
                    ),
                    models.ReplayRequest(
                        dead_letter_event_id=dead_letter_event.id,
                        status="pending",
                    ),
                ]
            )
            await session.commit()
            return int(
                await session.scalar(select(func.count()).select_from(models.ReplayRequest)) or 0
            )

    assert asyncio.run(exercise()) == 2


async def _clear_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        async with session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))


async def _create_integration(session: AsyncSession) -> models.Integration:
    integration = models.Integration(
        name=f"Integration {uuid.uuid4()}",
        slug=f"integration-{uuid.uuid4()}",
    )
    session.add(integration)
    await session.flush()
    return integration


async def _create_event(session: AsyncSession) -> models.Event:
    integration = await _create_integration(session)
    event = models.Event(
        integration_id=integration.id,
        deduplication_key=f"event-{uuid.uuid4()}",
        event_type="example.created",
    )
    session.add(event)
    await session.flush()
    return event


async def _create_delivery(session: AsyncSession) -> models.EventDelivery:
    integration = await _create_integration(session)
    destination = models.DownstreamDestination(
        integration_id=integration.id,
        name=f"Destination {uuid.uuid4()}",
        endpoint_url="https://example.test/webhook",
    )
    event = models.Event(
        integration_id=integration.id,
        deduplication_key=f"event-{uuid.uuid4()}",
        event_type="example.created",
    )
    session.add_all([destination, event])
    await session.flush()
    delivery = models.EventDelivery(event_id=event.id, destination_id=destination.id)
    session.add(delivery)
    await session.flush()
    return delivery


async def _create_event_route(
    session: AsyncSession,
) -> tuple[models.Event, models.DownstreamDestination, models.RoutingRule]:
    integration = await _create_integration(session)
    destination = models.DownstreamDestination(
        integration_id=integration.id,
        name=f"Destination {uuid.uuid4()}",
        endpoint_url="https://example.test/webhook",
    )
    event = models.Event(
        integration_id=integration.id,
        deduplication_key=f"event-{uuid.uuid4()}",
        event_type="example.created",
    )
    session.add_all([destination, event])
    await session.flush()
    routing_rule = models.RoutingRule(
        integration_id=integration.id,
        destination_id=destination.id,
        name=f"Rule {uuid.uuid4()}",
        match_configuration={"event_type": event.event_type},
    )
    session.add(routing_rule)
    await session.flush()
    return event, destination, routing_rule


async def _create_dead_letter_event(session: AsyncSession) -> models.DeadLetterEvent:
    delivery = await _create_delivery(session)
    dead_letter_event = models.DeadLetterEvent(
        delivery_id=delivery.id,
        reason="failed",
        reason_code="delivery_failed",
        reason_message="failed",
    )
    session.add(dead_letter_event)
    await session.flush()
    return dead_letter_event
