# RelayGuard Phase 1A Architecture

```mermaid
flowchart LR
  U[Developer Browser] --> F[Frontend\nReact + TypeScript + Vite + Tailwind]
  F -. API calls in later phases .-> B[Backend\nFastAPI + /api/v1/health]
  B --> C[Pure ASGI Correlation Middleware\nX-Correlation-ID]
  B --> L[structlog JSON Logs\ncontextvars correlation_id]
  B -. lazy engine only; no startup connection .-> D[(PostgreSQL Container\npostgres:17.10-alpine)]
  CI[GitHub Actions CI\nNode 24.x + Python 3.10/3.13] --> F
  CI --> B
```

PostgreSQL remains unconnected during startup and normal unit tests. Phase 1A adds SQLAlchemy 2 async engine/sessionmaker infrastructure for future integration work, but it does not add ORM models, migrations, or database readiness checks.
