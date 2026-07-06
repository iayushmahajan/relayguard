# RelayGuard

RelayGuard Phase 1B provides a minimal frontend shell, a backend FastAPI app foundation, developer tooling, CI quality checks, process health routing, typed configuration, structured logging, request correlation IDs, lazy PostgreSQL async session infrastructure, and a normalized PostgreSQL persistence foundation.

Phase 1B intentionally includes **no startup database connection, webhook handling, retry worker, replay worker, authentication behavior, signature verification, replay execution, or AI execution**.

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
- `X-Correlation-ID` response header - valid inbound UUIDs are reused; otherwise the backend generates a UUID4

The health endpoint does not check PostgreSQL readiness.

## Backend migrations

The backend uses SQLAlchemy 2 async metadata with Alembic's async migration bridge.

Use the isolated test database on host port `5434` for migration validation:

```bash
cd backend
POSTGRES_PORT=5434 .venv/bin/python -m alembic upgrade head
POSTGRES_PORT=5434 .venv/bin/python -m alembic downgrade base
```

Phase 1B defines persistence tables and migration structure only. Idempotent seed data, PostgreSQL integration tests, Makefile database targets, a CI PostgreSQL integration job, webhook/reliability runtime behavior, retry execution, replay execution, and AI execution are deferred to the next Phase 1 slice.

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
