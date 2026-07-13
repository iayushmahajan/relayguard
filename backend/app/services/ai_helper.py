"""Safe AI operator-helper service operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models
from app.schemas.ai_helper import (
    DraftReplayNoteResponse,
    ExplainDeliveryResponse,
    SampleWebhookPayloadRequest,
    SampleWebhookPayloadResponse,
)
from app.services.destinations import unpack_destination_type

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 405, 409, 410, 422}


@dataclass(frozen=True)
class DeliveryExplanationContext:
    """Metadata-only context for delivery explanation."""

    delivery: models.EventDelivery
    event: models.Event | None
    destination: models.DownstreamDestination | None
    attempts: list[models.DeliveryAttempt]
    retry_jobs: list[models.RetryJob]
    dead_letter: models.DeadLetterEvent | None


@dataclass(frozen=True)
class ReplayDraftContext:
    """Metadata-only context for replay-note drafting."""

    dead_letter: models.DeadLetterEvent
    delivery: models.EventDelivery | None
    attempts: list[models.DeliveryAttempt]
    replay_requests: list[models.ReplayRequest]


class AiHelperProvider(Protocol):
    """Provider abstraction for safe structured helper output."""

    def explain_delivery(self, context: DeliveryExplanationContext) -> ExplainDeliveryResponse:
        """Explain a delivery using metadata-only context."""

    def draft_replay_note(self, context: ReplayDraftContext) -> DraftReplayNoteResponse:
        """Draft replay text using metadata-only context."""

    def sample_webhook_payload(
        self, request: SampleWebhookPayloadRequest
    ) -> SampleWebhookPayloadResponse:
        """Generate a safe sample webhook envelope."""


class FallbackAiHelperProvider:
    """Deterministic local helper used when no AI provider is configured."""

    mode: Literal["fallback"] = "fallback"

    def explain_delivery(self, context: DeliveryExplanationContext) -> ExplainDeliveryResponse:
        """Explain a delivery with deterministic metadata rules."""
        last_attempt = context.attempts[-1] if context.attempts else None
        pending_retry_count = sum(
            1 for retry_job in context.retry_jobs if retry_job.status == "pending"
        )
        facts = _delivery_facts(context=context, pending_retry_count=pending_retry_count)

        if context.delivery.status == "delivered":
            return ExplainDeliveryResponse(
                mode=self.mode,
                summary="This delivery is already marked delivered.",
                likely_cause="No active failure detected.",
                recommended_action="No action needed.",
                risk_level="low",
                supporting_facts=facts,
            )

        if last_attempt is None:
            return ExplainDeliveryResponse(
                mode=self.mode,
                summary="This delivery has not recorded an execution attempt yet.",
                likely_cause="No delivery attempt has run.",
                recommended_action="Execute the delivery when it is due.",
                risk_level="medium"
                if context.delivery.status in {"scheduled", "failed"}
                else "low",
                supporting_facts=facts,
            )

        if last_attempt.outcome == "timed_out":
            return ExplainDeliveryResponse(
                mode=self.mode,
                summary="The last delivery attempt timed out before a response was recorded.",
                likely_cause="Temporary downstream timeout.",
                recommended_action="Retry after confirming the downstream service is reachable.",
                risk_level="medium",
                supporting_facts=facts,
            )

        if (
            last_attempt.response_status_code in _RETRYABLE_STATUS_CODES
            or last_attempt.is_retryable
        ):
            return ExplainDeliveryResponse(
                mode=self.mode,
                summary="The last delivery attempt failed with a retryable downstream response.",
                likely_cause="Temporary downstream outage.",
                recommended_action=(
                    "Wait for the pending retry job or retry after checking downstream health."
                    if pending_retry_count > 0
                    else "Inspect downstream health before retrying manually."
                ),
                risk_level="medium",
                supporting_facts=facts,
            )

        if (
            last_attempt.response_status_code in _NON_RETRYABLE_STATUS_CODES
            or context.dead_letter is not None
            or context.delivery.status == "dead_lettered"
        ):
            return ExplainDeliveryResponse(
                mode=self.mode,
                summary="The downstream endpoint rejected the delivery as a terminal failure.",
                likely_cause="Permanent downstream rejection.",
                recommended_action=(
                    "Inspect the destination endpoint and create a replay request only after the "
                    "downstream issue is fixed."
                ),
                risk_level="high",
                supporting_facts=facts,
            )

        return ExplainDeliveryResponse(
            mode=self.mode,
            summary="RelayGuard recorded a delivery failure, but the cause is not specific enough.",
            likely_cause="Unknown delivery failure.",
            recommended_action="Inspect delivery metadata, destination status, and retry jobs.",
            risk_level="medium",
            supporting_facts=facts,
        )

    def draft_replay_note(self, context: ReplayDraftContext) -> DraftReplayNoteResponse:
        """Draft replay text without creating or approving a replay request."""
        last_attempt = context.attempts[-1] if context.attempts else None
        reason_code = context.dead_letter.reason_code
        status_code = last_attempt.response_status_code if last_attempt else None
        status_detail = f"HTTP {status_code}" if status_code is not None else reason_code
        warnings = [
            "Confirm the downstream destination is fixed before executing replay.",
            "Replay should be reviewed by an operator; this draft does not approve or execute it.",
        ]
        if context.replay_requests:
            warnings.append("Existing replay request history is present for this dead letter.")
        return DraftReplayNoteResponse(
            mode=self.mode,
            reason=(
                "Downstream recovery has been verified after terminal delivery failure "
                f"{status_detail}; replay is requested for the original delivery."
            ),
            approval_note=(
                "Approved for replay after confirming the destination endpoint is healthy and "
                "the failed delivery remains appropriate to resend."
            ),
            operator_summary=(
                f"Dead letter {context.dead_letter.id} is {context.dead_letter.resolution_status} "
                f"with severity {context.dead_letter.severity} and reason {reason_code}."
            ),
            warnings=warnings,
        )

    def sample_webhook_payload(
        self, request: SampleWebhookPayloadRequest
    ) -> SampleWebhookPayloadResponse:
        """Generate a deterministic safe sample webhook envelope."""
        sample_id = uuid.uuid4().hex[:12]
        description = (request.description or "").lower()
        currency = "EUR" if "eur" in description or "europe" in description else "USD"
        amount = 4999 if currency == "EUR" else 4200
        event_token = request.event_type.replace(".", "_").replace("-", "_")
        payload = {
            "invoice_id": f"inv_sample_{sample_id}",
            "customer_id": f"cus_sample_{sample_id[:8]}",
            "amount": amount,
            "currency": currency,
            "event_type": request.event_type,
        }
        if request.integration_slug is not None:
            payload["integration_slug"] = request.integration_slug
        if request.description is not None:
            payload["description"] = request.description
        return SampleWebhookPayloadResponse(
            mode=self.mode,
            event_type=request.event_type,
            deduplication_key=f"sample-{event_token}-{sample_id}",
            source_event_id=f"sample_evt_{sample_id}",
            payload=payload,
        )


def get_ai_helper_provider() -> AiHelperProvider:
    """Return the configured helper provider.

    Phase 9 intentionally uses the deterministic fallback provider. Future AI providers must keep
    the same metadata-only context and structured output contract.
    """
    return FallbackAiHelperProvider()


async def explain_delivery(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
    provider: AiHelperProvider | None = None,
) -> ExplainDeliveryResponse | None:
    """Return a safe explanation for one delivery."""
    context = await _load_delivery_context(session=session, delivery_id=delivery_id)
    if context is None:
        return None
    return (provider or get_ai_helper_provider()).explain_delivery(context)


async def draft_replay_note(
    *,
    session: AsyncSession,
    dead_letter_id: uuid.UUID,
    provider: AiHelperProvider | None = None,
) -> DraftReplayNoteResponse | None:
    """Return a safe replay-note draft for one dead letter."""
    context = await _load_replay_context(session=session, dead_letter_id=dead_letter_id)
    if context is None:
        return None
    return (provider or get_ai_helper_provider()).draft_replay_note(context)


def sample_webhook_payload(
    *,
    request: SampleWebhookPayloadRequest,
    provider: AiHelperProvider | None = None,
) -> SampleWebhookPayloadResponse:
    """Return a generated sample webhook envelope for user review."""
    return (provider or get_ai_helper_provider()).sample_webhook_payload(request)


async def _load_delivery_context(
    *,
    session: AsyncSession,
    delivery_id: uuid.UUID,
) -> DeliveryExplanationContext | None:
    delivery = await session.get(models.EventDelivery, delivery_id)
    if delivery is None:
        return None
    event = await session.get(models.Event, delivery.event_id)
    destination = await session.get(models.DownstreamDestination, delivery.destination_id)
    attempts = (
        await session.scalars(
            select(models.DeliveryAttempt)
            .where(models.DeliveryAttempt.delivery_id == delivery.id)
            .order_by(models.DeliveryAttempt.attempt_number.asc(), models.DeliveryAttempt.id.asc())
        )
    ).all()
    retry_jobs = (
        await session.scalars(
            select(models.RetryJob)
            .where(models.RetryJob.delivery_id == delivery.id)
            .order_by(models.RetryJob.run_at.asc(), models.RetryJob.id.asc())
        )
    ).all()
    dead_letter = await session.scalar(
        select(models.DeadLetterEvent).where(models.DeadLetterEvent.delivery_id == delivery.id)
    )
    return DeliveryExplanationContext(
        delivery=delivery,
        event=event,
        destination=destination,
        attempts=list(attempts),
        retry_jobs=list(retry_jobs),
        dead_letter=dead_letter,
    )


async def _load_replay_context(
    *,
    session: AsyncSession,
    dead_letter_id: uuid.UUID,
) -> ReplayDraftContext | None:
    dead_letter = await session.get(models.DeadLetterEvent, dead_letter_id)
    if dead_letter is None:
        return None
    delivery = await session.get(models.EventDelivery, dead_letter.delivery_id)
    attempts = []
    replay_requests = []
    if delivery is not None:
        attempts = list(
            (
                await session.scalars(
                    select(models.DeliveryAttempt)
                    .where(models.DeliveryAttempt.delivery_id == delivery.id)
                    .order_by(
                        models.DeliveryAttempt.attempt_number.asc(),
                        models.DeliveryAttempt.id.asc(),
                    )
                )
            ).all()
        )
    replay_requests = list(
        (
            await session.scalars(
                select(models.ReplayRequest)
                .where(models.ReplayRequest.dead_letter_event_id == dead_letter.id)
                .order_by(models.ReplayRequest.created_at.asc(), models.ReplayRequest.id.asc())
            )
        ).all()
    )
    return ReplayDraftContext(
        dead_letter=dead_letter,
        delivery=delivery,
        attempts=attempts,
        replay_requests=replay_requests,
    )


def _delivery_facts(
    *,
    context: DeliveryExplanationContext,
    pending_retry_count: int,
) -> list[str]:
    facts = [
        f"Delivery status is {context.delivery.status}.",
        f"Attempt count is {context.delivery.attempt_count}.",
    ]
    if context.event is not None:
        facts.append(
            f"Event type is {context.event.event_type} with status {context.event.status}."
        )
    if context.destination is not None:
        destination_type = unpack_destination_type(context.destination.configuration) or "unknown"
        facts.append(
            f"Destination {context.destination.name} is {context.destination.status} "
            f"and type {destination_type}."
        )
    if context.attempts:
        last_attempt = context.attempts[-1]
        if last_attempt.response_status_code is not None:
            facts.append(f"Last attempt returned HTTP {last_attempt.response_status_code}.")
        else:
            facts.append(f"Last attempt outcome was {last_attempt.outcome}.")
        if last_attempt.error_code is not None:
            facts.append(f"Last attempt error code was {last_attempt.error_code}.")
        facts.append(f"Last attempt retryable flag is {last_attempt.is_retryable}.")
    else:
        facts.append("No delivery attempts have been recorded.")
    if pending_retry_count > 0:
        facts.append(f"{pending_retry_count} pending retry job exists.")
    if context.dead_letter is not None:
        facts.append(
            f"Dead letter is {context.dead_letter.resolution_status} with severity "
            f"{context.dead_letter.severity}."
        )
        facts.append(f"Dead-letter reason code is {context.dead_letter.reason_code}.")
    return facts
