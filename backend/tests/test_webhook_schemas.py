import pytest
from pydantic import ValidationError

from app.schemas.webhooks import WebhookEnvelope


def test_webhook_envelope_trims_required_fields() -> None:
    envelope = WebhookEnvelope.model_validate(
        {
            "event_type": " invoice.paid ",
            "deduplication_key": " key-1 ",
            "source_event_id": " source-1 ",
            "payload": {"ok": True},
        }
    )

    assert envelope.event_type == "invoice.paid"
    assert envelope.deduplication_key == "key-1"
    assert envelope.source_event_id == "source-1"


@pytest.mark.parametrize(
    "document",
    [
        {"event_type": " ", "deduplication_key": "key", "payload": {}},
        {"event_type": "invoice.paid", "deduplication_key": "", "payload": {}},
        {"event_type": "invoice.paid", "deduplication_key": "key", "payload": []},
        {"event_type": "invoice.paid", "deduplication_key": "key"},
    ],
)
def test_webhook_envelope_rejects_invalid_documents(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WebhookEnvelope.model_validate(document)
