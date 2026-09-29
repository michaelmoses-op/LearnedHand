# 11. Hierarchical summaries and a configurable retrieval pipeline

Status: accepted

## Context

Flat chunk search struggles with broad or thematic questions and pays for irrelevant context.
Every retrieval path must still respect the spoiler gate: a summary of a chapter the reader has
not finished is itself a spoiler.

## Decision

- Ingest gains stages `summaries` (bottom-up: sections → parents → book, map-reduced to fit a
  token budget, then embedded) and `validate` (quality report). Order: parse, sections, chunk,
  context, embed, summaries, validate. `STAGE_VERSIONS` + `documents.stage_versions` decide what
  is stale; `job.payload.from_stage` re-runs one stage and everything after it. Re-ingest keeps
  reading progress (clamped to the new range).
- `summaries` rows carry the chunk-ordinal range they cover. **A summary is visible only when
  `last_ordinal <= progress`.** Enforced in SQL in `RetrievalPipeline._broad` and
  `SummaryRepository.list_visible`; tables are under FORCE RLS.
- `RetrievalConfig` (one immutable object; loaded from settings in the app and from YAML in
  evals) drives `RetrievalPipeline`: embed → [broad pass over visible summaries] → vector/FTS →
  RRF → [rerank] → final. Each stage records duration, tokens and candidate ids for per-stage
  recall. Hierarchical drill-down searches chunks inside the picked summaries' ranges **plus the
  frontier** (sections with no visible summary — the chapter being read), all still gated by
  `ordinal <= progress`. With no visible summaries it falls back to flat search.
- FTS uses OR semantics by default (`fts_operator`): natural-language questions rarely contain
  only words that all occur in one chunk; the AND behaviour stays available for comparison.
- Rerank is optional: local cross-encoder (`BAAI/bge-reranker-base`, `rerank` extra, lazy import)
  or a lexical fake for CI. No hosted reranker (no extra data leaves the machine).
- Summarisation and context-prefix prompts are human-owned baselines in `app/prompts/`.

## Consequences

- Summaries cost LLM calls at ingest (one per section plus map-reduce pieces); use
  `LLM_INGEST_MODEL` for a cheaper model. `CONTEXT_PREFIX_MODE=llm` is one call per chunk and off
  by default (`title`).
- Summary text is model output about the user's book: stored under RLS, never logged.
- EPUB sections are flat (spine files), so the tree is usually book → sections; PDFs with an
  outline produce deeper trees.
