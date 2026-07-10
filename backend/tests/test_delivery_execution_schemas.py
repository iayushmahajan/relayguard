from datetime import datetime, timezone

from app.schemas.delivery_execution import (
    DeadLetterResponse,
    DeliveryAttemptResponse,
    DeliveryExecutionResponse,
    RetryJobExecutionResponse,
    RetryJobResponse,
)

_UUID = "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db"
_NOW = datetime.now(timezone.utc)


def test_delivery_execution_response_serializes_safe_metadata() -> None:
    response = DeliveryExecutionResponse.model_validate(
        {
            "delivery_id": _UUID,
            "status": "delivered",
            "attempt_number": 1,
            "retry_scheduled": False,
            "dead_lettered": False,
            "next_attempt_at": None,
        }
    )

    assert response.status == "delivered"
    assert response.attempt_number == 1


def test_retry_job_execution_response_serializes_safe_metadata() -> None:
    response = RetryJobExecutionResponse.model_validate(
        {
            "retry_job_id": _UUID,
            "delivery_id": _UUID,
            "retry_status": "completed",
            "delivery_status": "delivered",
        }
    )

    assert response.retry_status == "completed"


def test_metadata_responses_do_not_require_payload_fields() -> None:
    attempt = DeliveryAttemptResponse.model_validate(
        {
            "attempt_id": _UUID,
            "delivery_id": _UUID,
            "attempt_number": 1,
            "outcome": "failed",
            "response_status_code": 503,
            "error_code": "http_503",
            "error_message": "downstream returned HTTP 503",
            "is_retryable": True,
            "started_at": _NOW,
            "finished_at": _NOW,
            "created_at": _NOW,
        }
    )
    retry_job = RetryJobResponse.model_validate(
        {
            "retry_job_id": _UUID,
            "delivery_id": _UUID,
            "status": "pending",
            "run_at": _NOW,
            "claimed_at": None,
            "completed_at": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )
    dead_letter = DeadLetterResponse.model_validate(
        {
            "dead_letter_id": _UUID,
            "delivery_id": _UUID,
            "severity": "high",
            "reason_code": "http_404",
            "reason_message": "downstream returned HTTP 404",
            "resolution_status": "open",
            "dead_lettered_at": _NOW,
            "resolved_at": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }
    )

    assert "payload" not in attempt.model_dump()
    assert "payload" not in retry_job.model_dump()
    assert "payload" not in dead_letter.model_dump()
