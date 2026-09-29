# 13. Eval harness

Status: accepted

## Context

Retrieval choices (flat vs hierarchical, prefixes, hybrid vs vector, rerank) need evidence, and
`make eval` must produce a comparison without paid API calls or a network.

## Decision

- Package `evals/` at the repo root; it calls the same `RetrievalPipeline` and prompt builder as
  the app, so a config is exactly what production would run. Configs are YAML validated by the
  `RetrievalConfig` schema (unknown keys are errors; `max_iterations` is 1–3, see ADR 0015).
- Questions identify gold passages by text snippet, not chunk id, so results survive re-chunking.
  `forbidden_snippets` gives a content-based spoiler check independent of the ordinal gate.
- Metrics: recall@k, MRR, per-stage recall (incl. broad→section), context and judged answer
  point coverage, citation validity, spoiler leaks, latency percentiles, tokens, cost.
- Results persist in `eval_runs` / `eval_results` (RLS; ids/metrics only, no text). A reserved
  eval user owns them. The demo corpus is a deterministic synthetic EPUB, so ingestion is reused
  across runs.
- The fake provider is made *lexical* (hashed bag-of-words embeddings, extractive summaries) so
  offline runs discriminate between strategies. Numbers from it validate plumbing only; the
  table says so.

## Consequences

- Real evaluation needs a real provider and human-written questions (human-owned files).
- Ingestion-side variants (chunk size, prefix mode) need separate ingests and are out of scope
  for a single run.
