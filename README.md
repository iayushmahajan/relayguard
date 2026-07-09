# RelayGuard

RelayGuard Phase 2 provides a minimal frontend shell, a backend FastAPI app foundation, developer tooling, CI quality checks, process health routing, typed configuration, structured logging, request correlation IDs, lazy PostgreSQL async session infrastructure, a normalized PostgreSQL persistence foundation, idempotent baseline seeding, PostgreSQL integration validation, deterministic known-integration webhook intake, canonical accepted-event creation, duplicate detection, rejected receipt recording, and safe event metadata retrieval.

Phase 2 intentionally includes **no startup database connection, retry worker, replay worker, authentication behavior, signature verification, delivery execution, retry execution, replay execution, or AI execution**.

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
- `POST /api/v1/integrations/{integration_slug}/webhooks` - deterministic known-integration webhook intake
- `GET /api/v1/events/{event_id}` - safe canonical event metadata lookup
- `X-Correlation-ID` response header - valid inbound UUIDs are reused; otherwise the backend generates a UUID4

The health endpoint does not check PostgreSQL readiness.

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

## Backend migrations

The backend uses SQLAlchemy 2 async metadata with Alembic's async migration bridge.
Phase 1C adds `0002_replay_statuses`, a forward migration that expands replay-request terminal statuses for integration-test compatibility while leaving the committed Phase 1B initial migration immutable. Phase 2 adds `0003_webhook_intake_support`, a forward migration that adds webhook receipt request metadata, permits duplicate receipt status, widens stored event types to the API contract, and records accepted event timestamps.

Use the isolated test database on host port `5434` for migration validation:

```bash
cd backend
POSTGRES_PORT=5434 .venv/bin/python -m alembic upgrade head
POSTGRES_PORT=5434 .venv/bin/python -m alembic downgrade base
```

Phase 2 completes deterministic webhook intake and canonical event lifecycle creation. Delivery records, retry execution, replay execution, authentication behavior, signature verification, and AI execution remain deferred.

## Backend seed command

The backend seed command is idempotent and creates only baseline roles plus disabled sandbox integration stubs:

```bash
cd backend
.venv/bin/python -m app.commands.seed
```

It creates `admin`, `operator`, and `viewer` roles when absent, plus disabled `github-sandbox` and `stripe-sandbox` integrations when absent. It does not create users, secrets, destinations, routing rules, events, deliveries, retries, replay requests, or AI records.

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
