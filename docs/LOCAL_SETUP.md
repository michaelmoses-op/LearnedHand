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

`make test | lint | format | typecheck | migrate | gen-api | db-reset | eval | compare`.
After changing API routes or schemas, run `make gen-api` and commit the regenerated client
(`frontend/openapi.json`, `frontend/src/api/schema.d.ts`); CI fails if it is stale.

Tests use the fake LLM provider and the native `app_test` database.

## Using a real LLM provider (OpenAI)

Nothing is billed until you opt in. In `.env` set `LLM_PROVIDER=openai`, `LLM_API_KEY=...`,
`LLM_MODEL=...` and `EMBEDDING_MODEL=text-embedding-3-small` (see `.env.example`), then restart
`make dev` (honcho reads `.env` once at start). `LLM_DAILY_TOKEN_CAP` (default 5M tokens/user/day)
stops runaway spend. Embeddings are 1536-d; documents ingested with the fake provider must be
re-ingested after switching (`POST /api/v1/documents/{id}/reingest`).

## Re-ingesting and the parsing quality report

`POST /api/v1/documents/{id}/reingest` re-runs ingestion from a stage (`{"from_stage": "summaries"}`)
or, with an empty body, from the first stage whose recorded version is stale. Reading progress is
kept. `GET /api/v1/documents/{id}/quality` returns the parse quality report (score, warnings,
counts). PDFs are extracted in a memory/CPU-limited child process; scanned (image-only) PDFs are
rejected because OCR is not supported.

## Concepts, routing and the agentic loop (Phase 4)

Run `make migrate` (adds migration 0009), then `POST /api/v1/documents/{id}/reingest` with an
empty body for existing books: it resumes at the stale `concepts` stage. The book page then links
to **Concepts**, an interactive concept × section heat map with a per-concept trajectory; only
concepts and sections up to your reading progress appear, and a section's note appears once you
finish it. Live asks classify the question (factual / thematic / concept / other) and choose a
retrieval strategy (`ROUTING_ENABLED`, default on). `RETRIEVAL_MAX_ITERATIONS` (1–3, default 1)
turns on the gap-check loop that may run follow-up searches, each still limited to what you have
read. Both cost extra small LLM calls (stages `route`, `gapcheck` in `llm_calls`).

## Notes, study and tutor mode (Phase 5)

Run `make migrate` (migration 0010). The book page links to **Notes** (notes and highlights with
full-text search), **Study** (spaced-repetition flashcards and multiple-choice quizzes generated
from what you have read so far) and has a **Tutor mode** checkbox next to the question box (the
tutor guides you with hints instead of answering directly). Everything is limited to your current
reading position: set your progress with `PUT /api/v1/documents/{id}/progress`, and material from
later chapters disappears again if you move it back. Generation uses the `study` LLM stage.

## Evals

`make eval` ingests the built-in synthetic demo book, runs every config in `evals/configs/` over
`evals/questions/*.yaml`, and prints a comparison table (`make compare` re-prints the latest).
It works with the fake provider, so it is free and offline; for real numbers point it at OpenAI
(`LLM_PROVIDER=openai`) and, for the cross-encoder reranker, `uv sync --extra rerank`.
See `evals/README.md` for adding your own questions and configs.

## Troubleshooting

**`pgvector is not installed`** (from setup_db.sh): `sudo apt install postgresql-16-pgvector`, then re-run `make setup`.
**`extension "vector" is not available`** on a different Postgres major: install the matching `postgresql-NN-pgvector`.
**`Cannot connect to PostgreSQL as an admin`**: check `pg_lsclusters`; start with `sudo pg_ctlcluster 16 main start` (or `sudo service postgresql start` on WSL2).
**`relation "summaries" / "eval_runs" does not exist`**: run `make migrate` (migrations 0006–0008 change the embedding column to 1536-d; existing dev documents are marked for re-ingest).
**`Cannot reach the test database`** when running pytest: run `make setup`, and confirm `TEST_DATABASE_URL` and `TEST_MIGRATION_DATABASE_URL` in `.env`.
**`password authentication failed`**: the role passwords changed; re-run `scripts/setup_db.sh` and update `.env`.
