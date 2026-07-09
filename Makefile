SHELL := /bin/bash

.PHONY: test test-backend test-frontend test-backend-integration lint format-check typecheck check up down db-test-up db-test-down db-test-reset migrate migrate-test seed-backend seed-backend-test

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest -m "not integration"

test-frontend:
	cd frontend && npm run test:run

lint:
	cd backend && .venv/bin/python -m ruff check .
	cd frontend && npm run lint

format-check:
	cd backend && .venv/bin/python -m ruff format --check .
	cd frontend && npm run format:check

typecheck:
	cd backend && .venv/bin/python -m mypy app
	cd frontend && npm run typecheck

check: lint format-check typecheck test
	cd frontend && npm run build

up:
	docker compose up -d

down:
	docker compose down

db-test-up:
	docker compose -f docker-compose.test.yml up -d --wait

db-test-down:
	docker compose -f docker-compose.test.yml down

db-test-reset:
	docker compose -f docker-compose.test.yml down -v

migrate:
	cd backend && .venv/bin/python -m alembic upgrade head

migrate-test:
	cd backend && POSTGRES_PORT=5434 .venv/bin/python -m alembic upgrade head

seed-backend:
	cd backend && .venv/bin/python -m app.commands.seed

seed-backend-test:
	cd backend && POSTGRES_PORT=5434 .venv/bin/python -m app.commands.seed

test-backend-integration: db-test-up migrate-test
	cd backend && POSTGRES_PORT=5434 .venv/bin/python -m pytest -m integration
