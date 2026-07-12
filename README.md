# RelayGuard

RelayGuard Phase 6 provides an operator dashboard MVP, a backend FastAPI app foundation, developer tooling, CI quality checks, process health routing, typed configuration, structured logging, request correlation IDs, lazy PostgreSQL async session infrastructure, a normalized PostgreSQL persistence foundation, idempotent baseline seeding, PostgreSQL integration validation, deterministic known-integration webhook intake, canonical accepted-event creation, duplicate detection, rejected receipt recording, safe event metadata retrieval, deterministic routing rules, downstream destination management, durable delivery scheduling records, HTTP delivery execution, retry attempt recording, durable retry jobs, dead-letter records, and a human-reviewed replay workflow for dead-letter recovery.

Phase 6 intentionally includes **no startup database connection, background HTTP delivery worker, replay worker, authentication behavior, signature verification, AI execution, external queue, Redis, Celery, Kafka, or cloud service dependency**. Replay execution remains explicit API-driven recovery only.

## Prerequisites (WSL/Linux)

- Node `24.18.0` (`cat .nvmrc`)
- Python `3.10+` and `venv`
- Docker with Compose plugin

## Local setup

1. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
2. Install frontend dependencies:
   ```bash
   cd frontend && npm install
   ```
3. Create backend virtual environment and install dependencies:
   ```bash
   cd backend
   python -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -e ".[dev]"
   ```

## Docker database commands

```bash
docker compose up -d
docker compose down
docker compose -f docker-compose.test.yml up -d
docker compose -f docker-compose.test.yml down
```

The test Compose file defaults to host port `5434` to avoid common local PostgreSQL port conflicts.

## Backend API

- `GET /api/v1/health` - process-only health check
- `GET /api/v1/integrations` - list safe integration metadata
- `PATCH /api/v1/integrations/{integration_slug}` - activate or disable a known integration
- `POST /api/v1/integrations/{integration_slug}/webhooks` - deterministic known-integration webhook intake
- `GET /api/v1/events` - list recent safe canonical event metadata
- `GET /api/v1/events/{event_id}` - safe canonical event metadata lookup
- `POST /api/v1/integrations/{integration_slug}/destinations` - create downstream destination metadata
- `GET /api/v1/integrations/{integration_slug}/destinations` - list downstream destination metadata
- `POST /api/v1/integrations/{integration_slug}/routing-rules` - create deterministic event-type routing rule
- `GET /api/v1/integrations/{integration_slug}/routing-rules` - list routing rules
- `POST /api/v1/events/{event_id}/schedule-deliveries` - schedule durable delivery records
- `GET /api/v1/events/{event_id}/deliveries` - list safe delivery metadata
- `POST /api/v1/deliveries/{delivery_id}/execute` - execute one due scheduled delivery
- `POST /api/v1/retry-jobs/{retry_job_id}/execute` - execute one due pending retry job
- `GET /api/v1/deliveries/{delivery_id}/retry-jobs` - list safe retry job metadata
- `GET /api/v1/deliveries/{delivery_id}/attempts` - list safe delivery attempt metadata
- `GET /api/v1/dead-letters` - list safe dead-letter metadata
- `POST /api/v1/dead-letters/{dead_letter_id}/replay-requests` - create a human-reviewed replay request
- `GET /api/v1/replay-requests` - list safe replay request metadata
- `GET /api/v1/replay-requests/{replay_request_id}` - get safe replay request metadata
- `POST /api/v1/replay-requests/{replay_request_id}/approve` - approve a pending replay request
- `POST /api/v1/replay-requests/{replay_request_id}/reject` - reject a pending or unstarted approved replay request
- `POST /api/v1/replay-requests/{replay_request_id}/execute` - explicitly execute an approved replay request
- `X-Correlation-ID` response header - valid inbound UUIDs are reused; otherwise the backend generates a UUID4

The health endpoint does not check PostgreSQL readiness.

## Full local browser demo

Run the local backend with the isolated test database, start Vite, and run the
local downstream demo receiver:

```bash
make db-test-up
make migrate-test
make seed-backend-test
cd backend
POSTGRES_PORT=5434 .venv/bin/uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm run dev
```

In a third terminal:

```bash
python demo/receiver.py
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`. The dev server proxies
relative `/api` calls to `http://127.0.0.1:8000`, so the dashboard can use the backend without
hardcoded origins.

The demo receiver listens on `http://127.0.0.1:9000` and exposes:

- `GET /health` - returns `200`
- `POST /success` - returns `200` for successful delivery
- `POST /fail` - returns `503` for retryable failure
- `POST /reject` - returns `400` for non-retryable rejection
- `POST /slow` - sleeps before responding to exercise timeout behavior

The receiver prints only safe request metadata such as method, path, content type, body size, client
IP, user agent, and a body SHA-256 hash. It does not log payload contents or secrets.

Suggested operator demo flow:

1. Confirm the backend health badge is active.
2. Activate `stripe-sandbox`.
3. On Route Setup, create a destination pointing to `http://127.0.0.1:9000/success`.
4. Create an `invoice.paid` routing rule.
5. Submit the sample demo webhook from the Webhook Tester.
6. Select the accepted event and schedule deliveries.
7. Execute the scheduled delivery and inspect the delivered attempt.
8. Repeat with `http://127.0.0.1:9000/fail` to create a retry job.
9. Repeat with `http://127.0.0.1:9000/reject` to create a dead letter, then create, approve, and
   execute a replay request after repointing the destination to `/success`.
10. Use `http://127.0.0.1:9000/slow` with a short destination timeout to demonstrate timeout retry
    behavior.

The browser can trigger delivery and replay APIs without any external internet service.

Short browser flow without the receiver:

1. Confirm the backend health badge is active.
2. Activate `stripe-sandbox`.
3. Create an HTTP destination and an `invoice.paid` routing rule.
4. Submit a demo webhook from the event tester.
5. Select the accepted event and schedule deliveries.
6. Execute the scheduled delivery and inspect attempts/retry jobs.
7. If the example downstream URL fails, inspect the dead letter and create/approve/execute a replay request.

The included integration tests use in-process HTTP transports for success and failure cases without
external internet.

### Webhook intake example

Create or enable a known integration in PostgreSQL, then post the JSON envelope:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: 0d47f0f4-2bf1-4087-b6be-43e3b2d0b4db" \
  -d '{
    "event_type": "invoice.paid",
    "deduplication_key": "stable-source-or-provider-key",
    "source_event_id": "provider-event-123",
    "payload": {"amount": 4200}
  }' \
  http://localhost:8000/api/v1/integrations/stripe-sandbox/webhooks
```

An accepted active-integration request returns HTTP `202`:

```json
{
  "receipt_id": "00000000-0000-0000-0000-000000000000",
  "event_id": "00000000-0000-0000-0000-000000000000",
  "status": "accepted",
  "duplicate": false
}
```

A duplicate accepted envelope returns HTTP `200` with `duplicate: true` and the original `event_id`. A disabled known integration or invalid known-integration request records one rejected receipt and returns a clear 4xx response. An unknown integration returns `404` and creates no receipt because there is no integration foreign key target.

### Event metadata example

```bash
curl -i http://localhost:8000/api/v1/events/00000000-0000-0000-0000-000000000000
```

The response contains safe metadata only and never includes event payload contents.

### Destination and routing examples

Create a downstream destination:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Billing Service",
    "destination_type": "http",
    "endpoint_url": "https://example.invalid/webhooks/billing",
    "configuration": {"timeout_seconds": 10},
    "status": "active"
  }' \
  http://localhost:8000/api/v1/integrations/stripe-sandbox/destinations
```

Create an event-type routing rule for that destination:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Invoice paid to billing",
    "destination_id": "00000000-0000-0000-0000-000000000000",
    "event_type": "invoice.paid",
    "priority": 100,
    "status": "active"
  }' \
  http://localhost:8000/api/v1/integrations/stripe-sandbox/routing-rules
```

Schedule delivery records for an accepted event:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/events/00000000-0000-0000-0000-000000000000/schedule-deliveries
```

List scheduled deliveries:

```bash
curl -i \
  http://localhost:8000/api/v1/events/00000000-0000-0000-0000-000000000000/deliveries
```

### Delivery execution examples

Execute a due scheduled delivery:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/deliveries/00000000-0000-0000-0000-000000000000/execute
```

Execute a due retry job:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/retry-jobs/00000000-0000-0000-0000-000000000000/execute
```

List delivery attempts:

```bash
curl -i \
  http://localhost:8000/api/v1/deliveries/00000000-0000-0000-0000-000000000000/attempts
```

List retry jobs for a delivery:

```bash
curl -i \
  http://localhost:8000/api/v1/deliveries/00000000-0000-0000-0000-000000000000/retry-jobs
```

List open dead letters:

```bash
curl -i \
  "http://localhost:8000/api/v1/dead-letters?resolution_status=open"
```

Phase 4 sends one HTTP POST per explicit execution request. It records every attempt, creates durable retry jobs for retryable failures, and creates one dead-letter record per terminal delivery. It does not run a background worker.

### Replay workflow examples

Create a replay request from an open dead letter:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Downstream service has recovered.",
    "requested_by": "system-operator"
  }' \
  http://localhost:8000/api/v1/dead-letters/00000000-0000-0000-0000-000000000000/replay-requests
```

Approve the request after review:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "system-operator",
    "note": "Destination is healthy again."
  }' \
  http://localhost:8000/api/v1/replay-requests/00000000-0000-0000-0000-000000000000/approve
```

Reject a request that should not be replayed:

```bash
curl -i \
  -H "Content-Type: application/json" \
  -d '{
    "rejected_by": "system-operator",
    "reason": "Payload should not be resent."
  }' \
  http://localhost:8000/api/v1/replay-requests/00000000-0000-0000-0000-000000000000/reject
```

Execute an approved replay request:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/replay-requests/00000000-0000-0000-0000-000000000000/execute
```

List and inspect replay requests:

```bash
curl -i "http://localhost:8000/api/v1/replay-requests?status=pending"
curl -i http://localhost:8000/api/v1/replay-requests/00000000-0000-0000-0000-000000000000
```

Replay execution reuses the original delivery, preserves previous `delivery_attempts`, records a normal new attempt, writes audit log entries, and resolves the dead letter only when the replay delivery succeeds.

## Backend migrations

The backend uses SQLAlchemy 2 async metadata with Alembic's async migration bridge.
Phase 1C adds `0002_replay_statuses`, a forward migration that expands replay-request terminal statuses for integration-test compatibility while leaving the committed Phase 1B initial migration immutable. Phase 2 adds `0003_webhook_intake_support`, a forward migration that adds webhook receipt request metadata, permits duplicate receipt status, widens stored event types to the API contract, and records accepted event timestamps. Phase 3 adds `0004_routing_schedule`, a forward migration that prevents duplicate delivery schedules for the same event, destination, and routing rule. Phase 4 adds `0005_delivery_execution`, a forward migration that stores delivery execution timestamps/errors, attempt outcomes, retry job claim/completion metadata, a pending retry uniqueness rule, and dead-letter reason metadata. Phase 5 adds `0006_replay_workflow`, a forward migration that tracks replay request update/execution/resolution timestamps and expands active replay uniqueness to include `running` requests.

Use the isolated test database on host port `5434` for migration validation:

```bash
cd backend
POSTGRES_PORT=5434 .venv/bin/python -m alembic upgrade head
POSTGRES_PORT=5434 .venv/bin/python -m alembic downgrade base
```

Phase 7 adds the local demo receiver and sample browser workflow so successful delivery, retryable
failure, non-retryable failure, dead-lettering, and replay can be demonstrated without external
internet services. Background workers, authentication behavior, signature verification, and AI
execution remain deferred.

## Backend seed command

The backend seed command is idempotent and creates only baseline roles plus disabled sandbox integration stubs:

```bash
cd backend
.venv/bin/python -m app.commands.seed
```

It creates `admin`, `operator`, and `viewer` roles when absent, plus disabled `github-sandbox` and `stripe-sandbox` integrations when absent. It does not create users, secrets, destinations, routing rules, events, deliveries, retries, replay requests, audit recovery records, or AI records.

## PostgreSQL integration tests

Normal checks remain database-free. PostgreSQL integration tests use only the isolated test database on host port `5434`:

```bash
make db-test-up
make migrate-test
make seed-backend-test
make test-backend-integration
```

The integration test target leaves the isolated test database running.

## Make targets

- `make test` - run backend and frontend tests
- `make test-backend` - run backend pytest
- `make test-frontend` - run frontend Vitest (run mode)
- `make lint` - run Ruff lint and frontend ESLint
- `make format-check` - run Ruff format check and frontend Prettier check
- `make typecheck` - run backend mypy and frontend TypeScript checks
- `make check` - run lint, format-check, typecheck, test, then frontend build
- `make up` - start development Compose services
- `make down` - stop development Compose services
- `make db-test-up` - start only the isolated test PostgreSQL service and wait for health
- `make db-test-down` - stop only the isolated test PostgreSQL service
- `make db-test-reset` - remove only the isolated test PostgreSQL service and its named test volume
- `make migrate` - migrate the configured development database
- `make migrate-test` - migrate the isolated test database on host port `5434`
- `make seed-backend` - seed the configured development database
- `make seed-backend-test` - seed the isolated test database on host port `5434`
- `make test-backend-integration` - migrate and run only PostgreSQL integration tests
