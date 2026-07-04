SHELL := /bin/bash

.PHONY: test test-backend test-frontend lint format-check typecheck check up down

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest

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
