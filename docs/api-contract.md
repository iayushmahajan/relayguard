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

## Delivery Execution

`POST /api/v1/deliveries/{delivery_id}/execute`

Executes one due delivery with status `scheduled` or `failed`. Unknown deliveries return `404`.
Deliveries that are already delivered, dead-lettered, cancelled, in progress, or not due return
`409`.

RelayGuard sends an HTTP `POST` to the destination URL using the stored canonical event payload as
the JSON request body and `Content-Type: application/json`. Phase 4 does not add signatures or
secrets. Timeout defaults to 10 seconds and can be overridden by destination
`configuration.timeout_seconds`.

```json
{
  "delivery_id": "00000000-0000-0000-0000-000000000000",
  "status": "delivered",
  "attempt_number": 1,
  "retry_scheduled": false,
  "dead_lettered": false,
  "next_attempt_at": null
}
```

Every execution attempt creates one `delivery_attempts` row. HTTP `2xx` marks the delivery
`delivered`. HTTP `429`, `500`, `502`, `503`, `504`, timeout, and network/connect errors are
retryable until the configured max attempts is exhausted. HTTP `400`, `401`, `403`, `404`, `405`,
`409`, `410`, `422`, and other terminal responses dead-letter the delivery.

## Retry Jobs

`POST /api/v1/retry-jobs/{retry_job_id}/execute`

Executes one due pending retry job by claiming it, running the same delivery execution path, then
marking the retry job completed.

```json
{
  "retry_job_id": "00000000-0000-0000-0000-000000000000",
  "delivery_id": "00000000-0000-0000-0000-000000000000",
  "retry_status": "completed",
  "delivery_status": "delivered"
}
```

Future, claimed, completed, and cancelled retry jobs return `409`.

`GET /api/v1/deliveries/{delivery_id}/retry-jobs`

Returns safe retry metadata only:

```json
[
  {
    "retry_job_id": "00000000-0000-0000-0000-000000000000",
    "delivery_id": "00000000-0000-0000-0000-000000000000",
    "status": "pending",
    "run_at": "2026-07-10T00:01:00Z",
    "claimed_at": null,
    "completed_at": null,
    "created_at": "2026-07-10T00:00:00Z",
    "updated_at": "2026-07-10T00:00:00Z"
  }
]
```

## Delivery Attempts

`GET /api/v1/deliveries/{delivery_id}/attempts`

Returns safe delivery attempt metadata only:

```json
[
  {
    "attempt_id": "00000000-0000-0000-0000-000000000000",
    "delivery_id": "00000000-0000-0000-0000-000000000000",
    "attempt_number": 1,
    "outcome": "failed",
    "response_status_code": 503,
    "error_code": "http_503",
    "error_message": "downstream returned HTTP 503",
    "is_retryable": true,
    "started_at": "2026-07-10T00:00:00Z",
    "finished_at": "2026-07-10T00:00:01Z",
    "created_at": "2026-07-10T00:00:00Z"
  }
]
```

The endpoint never returns request payloads or response bodies.

## Dead Letters

`GET /api/v1/dead-letters`

Optional filters: `resolution_status` and `severity`.

```json
[
  {
    "dead_letter_id": "00000000-0000-0000-0000-000000000000",
    "delivery_id": "00000000-0000-0000-0000-000000000000",
    "severity": "high",
    "reason_code": "http_404",
    "reason_message": "downstream returned HTTP 404",
    "resolution_status": "open",
    "dead_lettered_at": "2026-07-10T00:00:00Z",
    "resolved_at": null,
    "created_at": "2026-07-10T00:00:00Z",
    "updated_at": "2026-07-10T00:00:00Z"
  }
]
```

Dead-letter listing never returns payload contents, response bodies, destination configuration, or
secrets.
