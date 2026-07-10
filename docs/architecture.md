# RelayGuard Phase 3 Architecture

```mermaid
flowchart LR
  U[Developer Browser] --> F[Frontend\nReact + TypeScript + Vite + Tailwind]
  W[Known Integration] --> B[Backend\nFastAPI API v1]
  F -. API calls in later phases .-> B
  B --> C[Pure ASGI Correlation Middleware\nX-Correlation-ID]
  B --> L[structlog JSON Logs\ncontextvars correlation_id]
  B --> S[Service Layer\nwebhook_intake + events]
  S --> R[Routing + Scheduling\nDestinations, Rules, Deliveries]
  S --> D[(PostgreSQL\nNormalized persistence schema)]
  R --> D
  M[Alembic Async Migrations] --> D
  CI[GitHub Actions CI\nNode 24.x + Python 3.10/3.13] --> F
  CI --> B
```

PostgreSQL remains unconnected during startup and normal unit tests. Phase 1B added SQLAlchemy ORM metadata and an immutable initial Alembic migration for the normalized persistence foundation. Phase 1C adds idempotent seeding, PostgreSQL-only integration validation against the isolated test database on host port `5434`, and a forward `0002` migration that expands replay-request terminal statuses. Phase 2 adds `0003_webhook_intake_support` for receipt request metadata, duplicate receipt status, event-type length alignment, and accepted event timestamps. Phase 3 adds `0004_routing_schedule` to enforce idempotent delivery scheduling for each event, destination, and routing rule.

The schema uses UUID primary keys, UTC-aware timestamp columns, string status columns with check constraints, JSONB only for payload/configuration/schema/audit documents, and PostgreSQL partial unique indexes where domain rules require them.

## Phase 2 intake flow

1. `POST /api/v1/integrations/{integration_slug}/webhooks` looks up the integration by slug before parsing the body.
2. Unknown integrations return `404` and create no receipt, because no integration foreign key exists.
3. Known integrations read the raw body, compute a SHA-256 hash, capture safe request metadata, and manually validate content type, JSON, and the envelope.
4. Disabled or invalid known-integration requests create one rejected `webhook_receipts` row and create no canonical event, payload, state transition, delivery, retry, replay, dead-letter, or AI record.
5. Active valid requests create a receipt, then insert a canonical `events` row with PostgreSQL conflict-safe behavior. The unique `(integration_id, deduplication_key)` constraint and partial unique `(integration_id, source_event_id)` index enforce deterministic deduplication.
6. Accepted inserts create exactly one `event_payloads` row and one initial `event_state_transitions` row from `NULL` to `accepted`.
7. Duplicate inserts update the new receipt to `duplicate` and return the existing event ID without creating another event, payload, or state transition.
8. `GET /api/v1/events/{event_id}` returns safe metadata only and never returns payload contents.

Normal health/startup behavior and `make check` remain database-free. Delivery execution, retry execution, replay execution, authentication behavior, signature verification, and AI execution remain deferred.

## Phase 3 routing and scheduling flow

1. Operators can create downstream destination metadata for a known integration. Destination configuration is checked for secret-like keys and is never used to execute HTTP calls in Phase 3.
2. Operators can create routing rules for destinations in the same integration. A rule stores deterministic match criteria in `routing_rules.match_configuration`, currently `{"event_type": "..."}`.
3. `POST /api/v1/events/{event_id}/schedule-deliveries` loads an accepted canonical event, active routing rules for its integration, and active destinations.
4. A route matches only when its configured `event_type` exactly equals the canonical event's `event_type`. Disabled rules, disabled destinations, and non-matching rules are ignored.
5. For each matched active route, RelayGuard inserts one `event_deliveries` row with status `scheduled`, `attempt_count` zero, and `next_attempt_at` set to the current UTC timestamp.
6. The Phase 3 uniqueness constraint prevents duplicate delivery rows for the same event, destination, and routing rule. Repeated scheduling calls report existing matched deliveries without creating duplicates.
7. Phase 3 keeps canonical events in `accepted` status while delivery records wait for a future execution phase. No delivery attempts, retry jobs, dead letters, replay requests, or AI records are created.
