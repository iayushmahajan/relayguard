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

## Destinations

`POST /api/v1/integrations/{integration_slug}/destinations`

```json
{
  "name": "Billing Service",
  "destination_type": "http",
  "endpoint_url": "https://example.invalid/webhooks/billing",
  "configuration": {
    "timeout_seconds": 10
  },
  "status": "active"
}
```

Returns HTTP `201` with safe destination metadata. Unknown integrations return `404`.
The `endpoint_url` must be HTTP or HTTPS. Status must be `active` or `disabled`.
Configuration must not contain secrets.

`GET /api/v1/integrations/{integration_slug}/destinations`

Returns safe destination metadata only.

## Routing Rules

`POST /api/v1/integrations/{integration_slug}/routing-rules`

```json
{
  "name": "Invoice paid to billing",
  "destination_id": "00000000-0000-0000-0000-000000000000",
  "event_type": "invoice.paid",
  "priority": 100,
  "status": "active"
}
```

Returns HTTP `201` with safe routing rule metadata. Unknown integrations return `404`.
The destination must belong to the same integration. Lower `priority` values are evaluated first.
Routing rules match deterministically when their stored `event_type` equals the canonical event's
`event_type`.

`GET /api/v1/integrations/{integration_slug}/routing-rules`

Returns safe routing rule metadata sorted by priority, creation time, then stable ID.

## Delivery Scheduling

`POST /api/v1/events/{event_id}/schedule-deliveries`

Schedules durable `event_deliveries` records for matching active routing rules and active
destinations. Unknown events return `404`. Events that are not `accepted` return `409`.
When no active route matches, the endpoint returns HTTP `200` with zero counts.

```json
{
  "event_id": "00000000-0000-0000-0000-000000000000",
  "status": "accepted",
  "scheduled_count": 1,
  "already_scheduled_count": 0
}
```

Scheduling is idempotent for each event, destination, and routing rule. Repeated scheduling
returns `scheduled_count: 0` and reports the matching existing deliveries in
`already_scheduled_count`.

`GET /api/v1/events/{event_id}/deliveries`

Returns safe delivery metadata only:

```json
[
  {
    "delivery_id": "00000000-0000-0000-0000-000000000000",
    "event_id": "00000000-0000-0000-0000-000000000000",
    "destination_id": "00000000-0000-0000-0000-000000000000",
    "routing_rule_id": "00000000-0000-0000-0000-000000000000",
    "status": "scheduled",
    "next_attempt_at": "2026-07-10T00:00:00Z",
    "attempt_count": 0,
    "created_at": "2026-07-10T00:00:00Z",
    "updated_at": "2026-07-10T00:00:00Z"
  }
]
```

Delivery listing never returns payload contents, raw webhook data, destination configuration, or
secrets.
