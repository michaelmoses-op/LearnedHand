.PHONY: setup dev test lint format typecheck migrate gen-api db-reset seed eval

setup:
	@test -f .env || cp .env.example .env
	bash scripts/setup_db.sh
	cd backend && uv sync
	cd frontend && npm install
	uv tool install honcho >/dev/null 2>&1 || true
	$(MAKE) migrate

dev:
	honcho -f Procfile.dev start

test:
	cd backend && uv run pytest
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

typecheck:
	cd backend && uv run mypy app tests
	cd frontend && npm run typecheck

migrate:
	cd backend && uv run alembic upgrade head

gen-api:
	cd backend && uv run python -m app.core.openapi_dump > ../frontend/openapi.json
	cd frontend && npm run gen-api

db-reset:
	cd backend && uv run alembic downgrade base && uv run alembic upgrade head

seed:
	@echo "seed: not implemented until Phase 2"

eval:
	@echo "eval: not implemented until Phase 3"
