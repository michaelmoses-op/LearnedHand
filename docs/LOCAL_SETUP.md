# Local setup (native, no Docker)

Docker is never required locally. Dockerfiles exist for CI and later deployment only.

## Prerequisites

| Tool | Version | Ubuntu / WSL2 |
|---|---|---|
| Python + uv | 3.12 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node + npm | 20+ | via nvm |
| PostgreSQL + pgvector | 16+ | `sudo apt install postgresql-16 postgresql-16-pgvector` |
| make, git | | `sudo apt install make git` |

macOS: `brew install postgresql@16 pgvector uv node`. Windows: use WSL2 Ubuntu and follow the Ubuntu steps.

## First run

```bash
make setup
make dev
```

`make setup` runs `scripts/setup_db.sh`, which idempotently creates:

- role `app_owner` (runs migrations, owns tables)
- role `app_user` (runtime; non-owner, non-superuser, so Row-Level Security applies)
- databases `app_dev` and `app_test`, each with the `vector` and `pg_trgm` extensions

Admin access defaults to `sudo -u postgres psql`. To use an existing superuser instead:
`PGADMIN_URL=postgresql://user:pass@localhost:5432/postgres bash scripts/setup_db.sh`.
Dev passwords are throwaway defaults; override with `APP_OWNER_PASSWORD` / `APP_USER_PASSWORD`.

## Running processes individually

```bash
cd backend  && uv run uvicorn app.main:app --reload --port 8000
cd backend  && uv run python -m app.jobs.worker
cd frontend && npm run dev
```

## Other commands

`make test | lint | format | typecheck | migrate | gen-api | db-reset`.
After changing API routes or schemas, run `make gen-api` and commit the regenerated client
(`frontend/openapi.json`, `frontend/src/api/schema.d.ts`); CI fails if it is stale.

Tests use the fake LLM provider and the native `app_test` database.

## Troubleshooting

**`pgvector is not installed`** (from setup_db.sh): `sudo apt install postgresql-16-pgvector`, then re-run `make setup`.
**`extension "vector" is not available`** on a different Postgres major: install the matching `postgresql-NN-pgvector`.
**`Cannot connect to PostgreSQL as an admin`**: check `pg_lsclusters`; start with `sudo pg_ctlcluster 16 main start` (or `sudo service postgresql start` on WSL2).
**`Cannot reach the test database`** when running pytest: run `make setup`, and confirm `TEST_DATABASE_URL` and `TEST_MIGRATION_DATABASE_URL` in `.env`.
**`password authentication failed`**: the role passwords changed; re-run `scripts/setup_db.sh` and update `.env`.
