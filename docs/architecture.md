# RelayGuard Phase 1B Architecture

```mermaid
flowchart LR
  U[Developer Browser] --> F[Frontend\nReact + TypeScript + Vite + Tailwind]
  F -. API calls in later phases .-> B[Backend\nFastAPI + /api/v1/health]
  B --> C[Pure ASGI Correlation Middleware\nX-Correlation-ID]
  B --> L[structlog JSON Logs\ncontextvars correlation_id]
  B -. lazy engine only; no startup connection .-> D[(PostgreSQL\nNormalized persistence schema)]
  M[Alembic Async Migrations] --> D
  CI[GitHub Actions CI\nNode 24.x + Python 3.10/3.13] --> F
  CI --> B
```

PostgreSQL remains unconnected during startup and normal unit tests. Phase 1B adds SQLAlchemy ORM metadata and an initial Alembic migration for the normalized persistence foundation, validated against the isolated test database on host port `5434`.

The schema uses UUID primary keys, UTC-aware timestamp columns, string status columns with check constraints, JSONB only for payload/configuration/schema/audit documents, and PostgreSQL partial unique indexes where domain rules require them.

Phase 1B does not add idempotent seed data, PostgreSQL integration tests, Makefile database targets, a CI PostgreSQL integration job, or runtime reliability behavior. Webhook processing, retry execution, replay execution, and AI execution remain deferred to the next Phase 1 slice.
