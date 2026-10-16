# LearnedHand: agent working agreement

Condensed from the project prompt (Humanities Reading Companion, RAG). Work one phase at a time.

## Working rules
1. Plan before code: per phase, output a short plan and wait for approval.
2. Small commits, conventional-commit messages; suite passing at each.
3. Tests ship with code. Do not invent library APIs; check docs. Justify any new dependency.
4. Never commit secrets (`.env.example` placeholders only). Record notable decisions as ADRs.
5. Human-owned files (`backend/app/prompts/*`, `evals/questions/*`): scaffold baselines only; do not tune.
6. Do not push to the remote unless asked.

## Architecture
routers -> services -> repositories. Routers validate/serialize only. Retrieval and generation live
outside routers so the eval CLI can call them without HTTP. Stack: Python 3.12, FastAPI, SQLAlchemy 2
async, Alembic, uv, ruff, mypy --strict, pytest; Postgres 16 + pgvector; Vite + React 18 + TS strict.
Native local dev (no Docker required). Runtime DB role is non-owner so RLS applies.

## Hard requirements (summary)
- Every resource owned by a user; repositories require an AuthContext; Postgres RLS forced; 404 not 403.
- Untrusted uploads parsed only in the worker with limits; local storage behind an interface.
- Book text is untrusted data in prompts; retrieval scoped by user_id + document_id in SQL (whole-book; no reading-position gate, see ADR 0017).
- No document text, prompts or tokens in logs. Sanitized Markdown only.
- RFC 7807 errors with stable `code`; API under /api/v1; generated TS client.

## Definition of done (each phase)
Tests + lint + types clean; new routes in the IDOR matrix; reversible migrations; docs/ADRs updated;
no secrets or document text in logs.

## Phases
0 Foundation. 1 Auth/authz/documents. 2 Ingestion v1 + basic Q&A. 3 Hierarchy, reranking, evals.
4 Concepts and routing. 5 Learning features. 6 Deploy-readiness and hardening.
