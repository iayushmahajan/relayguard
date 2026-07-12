# Project Status

## Phase 0 - Foundation
- [x] Repository structure scaffolded
- [x] Node runtime pinned with `.nvmrc`
- [x] Frontend scaffolded with Vite React TypeScript
- [x] Tailwind configured via Vite plugin and CSS import
- [x] Frontend quality tooling configured
- [x] Backend FastAPI foundation created with no routes
- [x] Backend quality tooling configured in `backend/pyproject.toml`
- [x] Docker Compose development/test PostgreSQL skeletons created (unconnected)
- [x] GitHub Actions quality workflow created
- [x] Required validation sequence completed

## Phase 1 - Initial API and wiring
- [x] Phase 1A backend process health route added
- [x] Phase 1A typed settings added with pydantic-settings
- [x] Phase 1A JSON structured logging added with structlog contextvars
- [x] Phase 1A pure ASGI correlation-ID middleware added
- [x] Phase 1A lazy SQLAlchemy 2 async engine/sessionmaker infrastructure added
- [x] Phase 1A tracked test PostgreSQL host port default aligned to `5434`
- [x] Phase 1B normalized SQLAlchemy ORM metadata added
- [x] Phase 1B async Alembic environment added
- [x] Phase 1B initial schema migration added
- [x] Phase 1B database-free metadata tests added
- [x] Phase 1B migration round-trip validated against isolated test PostgreSQL
- [x] Phase 1C idempotent baseline seed command added
- [x] Phase 1C PostgreSQL integration tests added
- [x] Phase 1C Makefile database targets added
- [x] Phase 1C backend PostgreSQL integration CI job added
- [x] Phase 1C replay-request terminal status compatibility migration added
- [ ] Replay, authentication, signature verification, and AI execution behavior not started

## Phase 2 - Deterministic webhook intake and canonical event lifecycle
- [x] Added `0003_webhook_intake_support` forward migration with downgrade
- [x] Added manual known-integration webhook intake route
- [x] Added service-layer orchestration for accepted, duplicate, and rejected attempts
- [x] Added Pydantic webhook and event metadata schemas
- [x] Added safe event metadata lookup route
- [x] Added PostgreSQL integration tests for accepted, duplicate, rejected, invalid, unknown, and lookup behavior
- [x] Preserved database-free `make check` behavior
- [x] Validated PostgreSQL integration checks against isolated host port `5434`
- [ ] Replay execution, authentication behavior, signature verification, and AI execution not started

## Phase 3 - Deterministic routing and delivery scheduling
- [x] Added destination management endpoints
- [x] Added deterministic event-type routing rule endpoints
- [x] Added `0004_routing_schedule` idempotency migration
- [x] Added durable delivery scheduling endpoint
- [x] Added safe delivery metadata listing endpoint
- [x] Added service-layer routing and scheduling orchestration
- [x] Added PostgreSQL integration tests for destination, routing, scheduling, idempotency, matching, and delivery listing behavior
- [x] Preserved database-free `make check` behavior
- [ ] Replay execution, authentication behavior, signature verification, and AI execution not started

## Phase 4 - HTTP delivery execution and retry attempt recording
- [x] Added `0005_delivery_execution` forward migration with downgrade
- [x] Added explicit delivery execution endpoint
- [x] Added retry job execution endpoint
- [x] Added safe delivery attempt, retry job, and dead-letter metadata endpoints
- [x] Added deterministic retry policy and retryable/non-retryable classification
- [x] Added service-layer HTTP execution, retry, and dead-letter orchestration
- [x] Added injectable HTTP client pattern for integration tests without external internet
- [x] Added PostgreSQL integration tests for success, retryable failure, terminal failure, timeout, retry execution, retry exhaustion, and safe metadata behavior
- [x] Preserved database-free `make check` behavior
- [x] Validated PostgreSQL integration checks against isolated host port `5434`
- [x] Fixed stale pending retry job cleanup after terminal delivery outcomes
- [ ] Background workers, authentication behavior, signature verification, and AI execution not started

## Phase 5 - Replay and recovery workflow
- [x] Added `0006_replay_workflow` forward migration with downgrade
- [x] Added replay request creation, listing, and lookup endpoints
- [x] Added replay approval, rejection, and explicit execution endpoints
- [x] Added service-layer replay workflow and safe audit logging
- [x] Reused deterministic Phase 4 delivery execution for replay attempts
- [x] Preserved previous delivery attempt history during replay
- [x] Added PostgreSQL integration tests for replay creation, approval, rejection, execution, invalid transitions, idempotency, metadata safety, and audit logging
- [x] Preserved database-free `make check` behavior
- [x] Validated PostgreSQL integration checks against isolated host port `5434`
- [ ] Background workers, authentication behavior, signature verification, and AI execution not started

## Phase 6 - Frontend operator dashboard MVP
- [x] Replaced the frontend shell with a substantial operator dashboard
- [x] Added typed frontend API client and dashboard data models
- [x] Added Vite dev proxy for relative `/api` calls to the local backend
- [x] Added backend support endpoints for safe integration listing, integration activation/disablement, and recent event listing
- [x] Added dashboard sections for overview, integrations, routing setup, webhook testing, events, deliveries, attempts, retry jobs, dead letters, and replay requests
- [x] Added frontend tests for dashboard rendering, backend unavailable state, status badges, and webhook tester behavior
- [x] Added PostgreSQL integration tests for dashboard support endpoints
- [x] Preserved database-free `make check` behavior
- [x] Validated PostgreSQL integration checks against isolated host port `5434`
- [ ] Authentication behavior, signature verification, background workers, frontend auth/session management, and AI execution not started

## Phase 7 - Local demo receiver and sample environment
- [x] Added standalone local downstream demo receiver on port `9000`
- [x] Added receiver endpoints for success, retryable failure, non-retryable rejection, slow response, and health
- [x] Added dashboard quick-fill guidance for local receiver destination URLs
- [x] Updated Webhook Tester with richer sample invoice event defaults
- [x] Documented the full local browser demo flow without external internet services
- [x] Preserved database-free `make check` behavior
- [ ] AI execution, authentication behavior, signature verification, background workers, external queues, Make.com, and n8n integrations not started
