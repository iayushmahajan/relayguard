from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.replay_requests import (
    ReplayExecutionResponse,
    ReplayRequestApproveRequest,
    ReplayRequestCreateRequest,
    ReplayRequestRejectRequest,
    ReplayRequestResponse,
)

_UUID = "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db"
_NOW = datetime.now(timezone.utc)


def test_replay_request_create_trims_fields() -> None:
    request = ReplayRequestCreateRequest.model_validate(
        {
            "reason": " Downstream recovered ",
            "requested_by": " system-operator ",
        }
    )

    assert request.reason == "Downstream recovered"
    assert request.requested_by == "system-operator"


@pytest.mark.parametrize(
    "document",
    [
        {"reason": "", "requested_by": "operator"},
        {"reason": "recover", "requested_by": ""},
        {"reason": "recover", "requested_by": "operator", "extra": "nope"},
    ],
)
def test_replay_request_create_rejects_invalid_documents(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReplayRequestCreateRequest.model_validate(document)


def test_replay_approval_and_rejection_validate_actors() -> None:
    approval = ReplayRequestApproveRequest.model_validate(
        {"approved_by": " operator ", "note": " checked "}
    )
    rejection = ReplayRequestRejectRequest.model_validate(
        {"rejected_by": " operator ", "reason": " unsafe "}
    )

    assert approval.approved_by == "operator"
    assert approval.note == "checked"
    assert rejection.rejected_by == "operator"
    assert rejection.reason == "unsafe"


def test_replay_responses_do_not_require_payload_fields() -> None:
    replay = ReplayRequestResponse.model_validate(
        {
            "replay_request_id": _UUID,
            "status": "pending",
            "event_id": _UUID,
            "delivery_id": _UUID,
            "dead_letter_id": _UUID,
            "reason": "Downstream recovered",
            "requested_by": "operator",
            "approved_by": None,
            "rejected_by": None,
            "created_at": _NOW,
            "updated_at": _NOW,
            "executed_at": None,
            "resolved_at": None,
        }
    )
    execution = ReplayExecutionResponse.model_validate(
        {
            "replay_request_id": _UUID,
            "delivery_id": _UUID,
            "replay_status": "resolved",
            "delivery_status": "delivered",
            "attempt_recorded": True,
            "dead_letter_resolved": True,
        }
    )

    assert "payload" not in replay.model_dump()
    assert "payload" not in execution.model_dump()
