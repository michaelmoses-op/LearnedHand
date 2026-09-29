# LearnedHand

Humanities reading companion (RAG): upload a book you own, then ask questions as if talking to a professor.
Structure-aware, spoiler-safe, cited. See `AGENTS.md` for the working agreement and phase plan.

## Quick start (native, no Docker)

```bash
make setup   # deps, DB roles/databases/extensions, .env, migrations
make dev     # api :8000, worker, frontend :5173
make test
make lint typecheck
```

Details and troubleshooting: [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).
