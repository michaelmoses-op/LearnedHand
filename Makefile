.PHONY: setup dev test lint format typecheck migrate gen-api db-reset seed eval compare

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
	cd backend && uv run ruff check . ../evals && uv run ruff format --check . ../evals
	cd frontend && npm run lint

format:
	cd backend && uv run ruff format . ../evals && uv run ruff check --fix . ../evals
	cd frontend && npm run format

typecheck:
	cd backend && uv run mypy
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

# Runs every config in evals/configs/ over evals/questions/*.yaml and prints a comparison table.
# Works out of the box with the fake provider and the built-in demo book; needs `make migrate`.
eval:
	cd backend && PYTHONPATH=.. uv run python -m evals.run

# e.g. make compare ARGS="baseline_flat_hybrid hierarchical_hybrid"
compare:
	cd backend && PYTHONPATH=.. uv run python -m evals.compare $(ARGS)
