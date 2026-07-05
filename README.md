# RelayGuard

RelayGuard Phase 1A provides a minimal frontend shell, a backend FastAPI app foundation, developer tooling, CI quality checks, process health routing, typed configuration, structured logging, request correlation IDs, and lazy PostgreSQL async session infrastructure.

Phase 1A intentionally includes **no database schema, ORM models, startup database connection, webhook handling, retry worker, replay worker, authentication, or AI execution**.

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

## Docker database commands (Phase 0 skeleton only)

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
