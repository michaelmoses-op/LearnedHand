# 10. OpenAI provider with a uniform resilience layer

Status: accepted

## Context

Phases 0–2 ran on a deterministic fake provider. Phase 3 needs a real provider for generation and
embeddings (chosen: OpenAI for both) without coupling app code to one vendor, and without a slow
or failing upstream taking the API or worker down or running up an unbounded bill.

## Decision

- `LLMProvider` (complete/stream/embed) stays the only interface; `OpenAIProvider` implements it
  with the official SDK, `max_retries=0` so policy lives in one place.
- `ResilientLLM` wraps any real provider: per-call timeout, bounded retries with full-jitter
  backoff for transient errors only, and a process-wide circuit breaker per provider. Streams
  retry only before the first token (no duplicated output).
- `AccountingLLM` (unchanged role) records metadata-only `llm_calls` rows (tokens, cached tokens,
  latency, stage) and enforces a per-user daily token cap before each call.
- Structured output: JSON-schema request, Pydantic validation, one repair attempt; error
  summaries contain locations/messages only, never values (which may be book text).
- Embeddings are fixed at **1536 dims** (`text-embedding-3-small`; pgvector HNSW caps at 2000).
  `chunks.embedding_model/embedding_dim` record what produced each vector. Changing dimension
  needs a migration and re-ingest; ingestion refuses a mismatching `EMBEDDING_DIM`.
- Anthropic is not implemented (factory raises `LLMConfigError`); the seam exists.

## Consequences

- Switching provider/model = env change + `reingest`. Migration 0006 marked dev documents for it.
- Costs are visible (`llm_calls`, `PRICE_*` settings in evals) and capped per user per day.
- Errors are translated to `TransientLLMError`/`PermanentLLMError` → 503/502-class problem+json.
