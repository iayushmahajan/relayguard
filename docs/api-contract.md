# API Contract

## Health

`GET /api/v1/health`

Returns process-only health:

```json
{"status": "ok"}
```

## Webhook Intake

`POST /api/v1/integrations/{integration_slug}/webhooks`

Requires `Content-Type: application/json`.

```json
{
  "event_type": "invoice.paid",
  "deduplication_key": "stable-source-or-provider-key",
  "source_event_id": "optional-provider-event-id",
  "payload": {
    "any": "JSON object"
  }
}
```

Validation:

- `event_type` and `deduplication_key` are required, trimmed, non-empty strings up to 255 characters.
- `source_event_id` is optional. When present, it is trimmed, non-empty, and up to 255 characters.
- `payload` is required and must be a JSON object.
- Unknown integration slugs return `404` and create no receipt.
- Disabled known integrations create one rejected receipt and return `409`.
- Invalid known-integration requests create one rejected receipt and return a clear 4xx response.

Accepted response, HTTP `202`:

```json
{
  "receipt_id": "00000000-0000-0000-0000-000000000000",
  "event_id": "00000000-0000-0000-0000-000000000000",
  "status": "accepted",
  "duplicate": false
}
```

Duplicate response, HTTP `200`:

```json
{
  "receipt_id": "00000000-0000-0000-0000-000000000000",
  "event_id": "00000000-0000-0000-0000-000000000000",
  "status": "accepted",
  "duplicate": true
}
```

## Event Metadata

`GET /api/v1/events/{event_id}`

Returns safe metadata only:

```json
{
  "event_id": "00000000-0000-0000-0000-000000000000",
  "integration_id": "00000000-0000-0000-0000-000000000000",
  "event_type": "invoice.paid",
  "source_event_id": "optional-provider-event-id-or-null",
  "status": "accepted",
  "received_at": "2026-07-09T00:00:00Z",
  "accepted_at": "2026-07-09T00:00:00Z"
}
```

The endpoint never returns payload contents or raw webhook data.
