"""Deterministic webhook intake orchestration."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import get_contextvars

from app.db import models
from app.schemas.webhooks import WebhookEnvelope

_JSON_CONTENT_TYPE = "application/json"
_ACCEPTED_STATUS = "accepted"
_DUPLICATE_STATUS = "duplicate"
_REJECTED_STATUS = "rejected"

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WebhookIntakeResult:
    """HTTP-facing webhook intake service result."""

    status_code: int
    detail: str | None
    receipt_id: uuid.UUID | None
    event_id: uuid.UUID | None
    duplicate: bool


@dataclass(frozen=True)
class RequestMetadata:
    """Safe request metadata stored with each known-integration receipt."""

    method: str
    path: str
    content_type: str | None
    body_size_bytes: int
    source_ip: str | None
    correlation_id: str | None
    query_params: dict[str, str]
    raw_body_hash: str


async def ingest_webhook(
    *,
    session: AsyncSession,
    request: Request,
    integration_slug: str,
) -> WebhookIntakeResult:
    """Process one inbound webhook attempt for a known integration."""
    integration = await session.scalar(
        select(models.Integration).where(models.Integration.slug == integration_slug)
    )
    if integration is None:
        return WebhookIntakeResult(
            status_code=404,
            detail="integration not found",
            receipt_id=None,
            event_id=None,
            duplicate=False,
        )

    raw_body = await request.body()
    metadata = _build_request_metadata(request, raw_body)

    if not _is_json_content_type(metadata.content_type):
        receipt = await _create_rejected_receipt(
            session=session,
            integration_id=integration.id,
            metadata=metadata,
            reason="unsupported content type",
        )
        await session.commit()
        return _rejected_result(415, "unsupported content type", receipt.id)

    if not integration.enabled or integration.status != "active":
        receipt = await _create_rejected_receipt(
            session=session,
            integration_id=integration.id,
            metadata=metadata,
            reason="integration disabled",
        )
        await session.commit()
        return _rejected_result(409, "integration disabled", receipt.id)

    try:
        document = json.loads(raw_body)
    except json.JSONDecodeError:
        receipt = await _create_rejected_receipt(
            session=session,
            integration_id=integration.id,
            metadata=metadata,
            reason="invalid json",
        )
        await session.commit()
        return _rejected_result(400, "invalid json", receipt.id)

    try:
        envelope = WebhookEnvelope.model_validate(document)
    except ValidationError:
        receipt = await _create_rejected_receipt(
            session=session,
            integration_id=integration.id,
            metadata=metadata,
            reason="invalid webhook envelope",
        )
        await session.commit()
        return _rejected_result(422, "invalid webhook envelope", receipt.id)

    receipt = models.WebhookReceipt(
        integration_id=integration.id,
        status="received",
        source_ip=metadata.source_ip,
        request_method=metadata.method,
        request_path=metadata.path,
        content_type=metadata.content_type,
        body_size_bytes=metadata.body_size_bytes,
        correlation_id=metadata.correlation_id,
        headers=None,
        query_params=metadata.query_params,
        raw_body_hash=metadata.raw_body_hash,
    )
    session.add(receipt)
    await session.flush()

    event_id = await _insert_event_if_not_duplicate(
        session=session,
        integration_id=integration.id,
        receipt_id=receipt.id,
        envelope=envelope,
    )
    if event_id is None:
        existing_event_id = await _get_duplicate_event_id(
            session=session,
            integration_id=integration.id,
            envelope=envelope,
        )
        receipt.status = _DUPLICATE_STATUS
        await session.commit()
        logger.info(
            "webhook_duplicate_recorded",
            integration_slug=integration.slug,
            receipt_id=str(receipt.id),
            event_id=str(existing_event_id),
        )
        return WebhookIntakeResult(
            status_code=200,
            detail=None,
            receipt_id=receipt.id,
            event_id=existing_event_id,
            duplicate=True,
        )

    session.add_all(
        [
            models.EventPayload(
                event_id=event_id,
                payload=envelope.payload,
                content_type=metadata.content_type,
                payload_hash=metadata.raw_body_hash,
            ),
            models.EventStateTransition(
                event_id=event_id,
                from_status=None,
                to_status=_ACCEPTED_STATUS,
                reason="webhook accepted",
                transition_metadata=None,
            ),
        ]
    )
    receipt.status = _ACCEPTED_STATUS
    await session.commit()
    logger.info(
        "webhook_accepted",
        integration_slug=integration.slug,
        receipt_id=str(receipt.id),
        event_id=str(event_id),
    )
    return WebhookIntakeResult(
        status_code=202,
        detail=None,
        receipt_id=receipt.id,
        event_id=event_id,
        duplicate=False,
    )


async def _insert_event_if_not_duplicate(
    *,
    session: AsyncSession,
    integration_id: uuid.UUID,
    receipt_id: uuid.UUID,
    envelope: WebhookEnvelope,
) -> uuid.UUID | None:
    event_id = uuid.uuid4()
    statement = (
        pg_insert(models.Event)
        .values(
            id=event_id,
            integration_id=integration_id,
            receipt_id=receipt_id,
            deduplication_key=envelope.deduplication_key,
            source_event_id=envelope.source_event_id,
            event_type=envelope.event_type,
            status=_ACCEPTED_STATUS,
        )
        .on_conflict_do_nothing()
        .returning(models.Event.id)
    )
    return await session.scalar(statement)


async def _get_duplicate_event_id(
    *,
    session: AsyncSession,
    integration_id: uuid.UUID,
    envelope: WebhookEnvelope,
) -> uuid.UUID:
    conditions = [models.Event.deduplication_key == envelope.deduplication_key]
    if envelope.source_event_id is not None:
        conditions.append(models.Event.source_event_id == envelope.source_event_id)

    event_id = await session.scalar(
        select(models.Event.id)
        .where(models.Event.integration_id == integration_id, or_(*conditions))
        .order_by(models.Event.received_at.asc(), models.Event.id.asc())
        .limit(1)
    )
    if event_id is None:
        raise RuntimeError("duplicate event conflict was not readable")
    return event_id


async def _create_rejected_receipt(
    *,
    session: AsyncSession,
    integration_id: uuid.UUID,
    metadata: RequestMetadata,
    reason: str,
) -> models.WebhookReceipt:
    receipt = models.WebhookReceipt(
        integration_id=integration_id,
        status=_REJECTED_STATUS,
        source_ip=metadata.source_ip,
        request_method=metadata.method,
        request_path=metadata.path,
        content_type=metadata.content_type,
        body_size_bytes=metadata.body_size_bytes,
        correlation_id=metadata.correlation_id,
        headers=None,
        query_params=metadata.query_params,
        raw_body_hash=metadata.raw_body_hash,
        rejection_reason=reason,
    )
    session.add(receipt)
    await session.flush()
    logger.info("webhook_rejected", receipt_id=str(receipt.id), reason=reason)
    return receipt


def _build_request_metadata(request: Request, raw_body: bytes) -> RequestMetadata:
    context = get_contextvars()
    client = request.client
    content_type = request.headers.get("content-type")
    return RequestMetadata(
        method=request.method[:16],
        path=request.url.path,
        content_type=content_type[:255] if content_type is not None else None,
        body_size_bytes=len(raw_body),
        source_ip=client.host[:64] if client is not None else None,
        correlation_id=_optional_string(context.get("correlation_id"), max_length=64),
        query_params=dict(request.query_params),
        raw_body_hash=hashlib.sha256(raw_body).hexdigest(),
    )


def _is_json_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == _JSON_CONTENT_TYPE


def _optional_string(value: Any, *, max_length: int) -> str | None:
    if isinstance(value, str) and value:
        return value[:max_length]
    return None


def _rejected_result(status_code: int, detail: str, receipt_id: uuid.UUID) -> WebhookIntakeResult:
    return WebhookIntakeResult(
        status_code=status_code,
        detail=detail,
        receipt_id=receipt_id,
        event_id=None,
        duplicate=False,
    )
