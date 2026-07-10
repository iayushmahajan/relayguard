import pytest
from pydantic import ValidationError

from app.schemas.routing import DestinationCreateRequest, RoutingRuleCreateRequest


def test_destination_request_trims_and_defaults() -> None:
    request = DestinationCreateRequest.model_validate(
        {
            "name": " Billing Service ",
            "destination_type": " http ",
            "endpoint_url": "https://example.invalid/webhooks/billing",
        }
    )

    assert request.name == "Billing Service"
    assert request.destination_type == "http"
    assert request.configuration == {}
    assert request.status == "active"


@pytest.mark.parametrize(
    "document",
    [
        {
            "name": "",
            "destination_type": "http",
            "endpoint_url": "https://example.invalid/webhook",
        },
        {
            "name": "Billing",
            "destination_type": "",
            "endpoint_url": "https://example.invalid/webhook",
        },
        {
            "name": "Billing",
            "destination_type": "http",
            "endpoint_url": "ftp://example.invalid/webhook",
        },
        {
            "name": "Billing",
            "destination_type": "http",
            "endpoint_url": "https://example.invalid/webhook",
            "status": "paused",
        },
    ],
)
def test_destination_request_rejects_invalid_documents(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DestinationCreateRequest.model_validate(document)


def test_routing_rule_request_trims_and_defaults() -> None:
    request = RoutingRuleCreateRequest.model_validate(
        {
            "name": " Invoice paid ",
            "destination_id": "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db",
            "event_type": " invoice.paid ",
        }
    )

    assert request.name == "Invoice paid"
    assert request.event_type == "invoice.paid"
    assert request.priority == 100
    assert request.status == "active"


@pytest.mark.parametrize(
    "document",
    [
        {
            "name": "",
            "destination_id": "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db",
            "event_type": "invoice.paid",
        },
        {
            "name": "Invoice paid",
            "destination_id": "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db",
            "event_type": "",
        },
        {
            "name": "Invoice paid",
            "destination_id": "0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db",
            "event_type": "invoice.paid",
            "status": "paused",
        },
    ],
)
def test_routing_rule_request_rejects_invalid_documents(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RoutingRuleCreateRequest.model_validate(document)
