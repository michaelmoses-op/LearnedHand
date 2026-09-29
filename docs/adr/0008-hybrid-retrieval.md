# 8. Hybrid retrieval (vector + FTS + RRF) with progress gate

Status: accepted

## Context

Phase 2 Q&A needs retrieval that the eval CLI can call without HTTP. Every hit
must respect the reading-progress spoiler gate (`ordinal <= max_ordinal`) in SQL,
scoped by `user_id` + `document_id`. Book text is untrusted and must not be logged.

## Options

### A. Vector-only (pgvector)

Simple. Misses exact lexical matches (names, rare terms) that embeddings blur.

### B. FTS-only (`tsvector`)

Strong on keywords; weak on paraphrase / conceptual questions common in
humanities reading.

### C. Hybrid + Reciprocal Rank Fusion

Run both candidate searches, fuse with RRF (`k=60`). No learned weights. Progress
filter on every SQL path; reload + ordinal check as defense in depth.

## Decision

Choose **C**. Keep retrieval in `app/retrieval` (not routers) so evals share the
same path. Callers pass `AuthContext`; missing progress row ⇒ empty results
(safer than opening the whole book).

## Consequences

- Embedding dimension must match ingest (`EMBEDDING_DIMENSION` / `embedding_dim`).
- Query embeddings go through `AccountingLLM` like chat (cost rows, no text in logs).
- HTTP SSE Q&A (next step) is a thin caller of `HybridRetriever`.
