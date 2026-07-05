# Decisions

## Entry 1
- **Decision:** Pin Node runtime to `24.18.0` via root `.nvmrc`, use npm with lockfile, and use `npm ci` in CI.
- **Rationale:** Ensures consistent local/CI behavior and deterministic dependency installation.
- **Sources consulted:** Node.js downloads/releases, npm documentation for `npm ci`, GitHub Actions setup-node cache documentation.
- **Date:** 2026-07-04
- **Alternatives:** Floating Node major/minor versions and `npm install` in CI were rejected due to drift risk.

## Entry 2
- **Decision:** Scaffold frontend with Vite React TypeScript and configure Tailwind through Vite plugin (`@tailwindcss/vite`) plus `@import "tailwindcss";`.
- **Rationale:** Matches current official setup and keeps CSS pipeline minimal for Phase 0.
- **Sources consulted:** Vite React template guidance, Tailwind v4 setup guidance for Vite.
- **Date:** 2026-07-04
- **Alternatives:** CRA and manual PostCSS-based Tailwind setup were not selected.

## Entry 3
- **Decision:** Use standard `venv` + pip workflow with backend packaging in `pyproject.toml` and a `dev` optional dependency group installable via `python -m pip install -e ".[dev]"`.
- **Rationale:** Provides reproducible local and CI installs without Poetry/PDM/uv and keeps tooling centralized.
- **Sources consulted:** Python packaging (`pyproject.toml`) documentation and pip editable install guidance.
- **Date:** 2026-07-04
- **Alternatives:** Poetry, PDM, uv were explicitly out of scope.

## Entry 4
- **Decision:** Adopt frontend quality tooling (ESLint, Prettier, Vitest, jsdom, Testing Library, jest-dom, user-event) and backend quality tooling (pytest, Ruff, mypy, httpx in dev group).
- **Rationale:** Provides baseline linting, formatting, type checking, and unit testing coverage for Phase 0 foundations.
- **Sources consulted:** Tooling official docs for Vitest, Testing Library, ESLint flat config, Ruff, mypy, and pytest.
- **Date:** 2026-07-04

## Entry 5
- **Decision:** Add unconnected PostgreSQL Compose skeletons for development and test using `postgres:17.10-alpine`, named volumes, root `.env` variables, and health checks.
- **Rationale:** Enables early environment readiness without introducing schema, ORM, or backend DB integration before Phase 1.
- **Sources consulted:** Docker Compose specification and official PostgreSQL container documentation.
- **Date:** 2026-07-04
- **Alternatives:** Connecting backend to DB in Phase 0 was rejected to preserve phase boundaries.

## Entry 6
- **Decision:** Configure CI with GitHub Actions using `actions/checkout@v6`, `actions/setup-node@v6`, and `actions/setup-python@v6`; apply workflow-level `permissions: contents: read`; run frontend and backend quality jobs separately with dependency caching.
- **Rationale:** Aligns with approved action versions and keeps feedback targeted while avoiding premature Docker integration tests.
- **Sources consulted:** GitHub Actions documentation for checkout, setup-node, setup-python, and caching behavior.
- **Date:** 2026-07-04
- **Alternatives:** Single combined job and Docker-based integration test execution were deferred.

## Entry 7
- **Decision:** Start Phase 1A with database-free backend infrastructure: pydantic-settings configuration, structlog JSON logging with contextvars, pure ASGI correlation-ID middleware, a process-only `GET /api/v1/health` route, and lazy SQLAlchemy 2 async engine/sessionmaker setup using asyncpg.
- **Rationale:** Establishes backend cross-cutting foundations while keeping `make check` fast and avoiding premature database coupling, ORM models, migrations, or integration jobs.
- **Sources consulted:** SQLAlchemy asyncio documentation, Alembic asyncio cookbook, Pydantic settings documentation, and structlog contextvars documentation.
- **Date:** 2026-07-05
- **Alternatives:** Database readiness in health checks, BaseHTTPMiddleware, SQLite test fallbacks, ORM models, and migration creation were rejected to preserve Phase 1A boundaries.

## Entry 8
- **Decision:** Change tracked test PostgreSQL host port defaults from `5433` to `5434`.
- **Rationale:** The local environment already reserves host ports `5432` and `5433`; aligning the tracked example and Compose fallback avoids conflicts for RelayGuard test PostgreSQL.
- **Sources consulted:** Local tracked `.env.example`, `docker-compose.test.yml`, and sanitized local `.env` values.
- **Date:** 2026-07-05
