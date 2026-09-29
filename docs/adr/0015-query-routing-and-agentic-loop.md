# 15. Query routing and the agentic gap-check loop

Status: accepted

## Context

One retrieval strategy does not fit every question, and single-pass retrieval sometimes misses
needed context. Both features add LLM calls, and both must not widen what the reader can see.

## Decision

- `RetrievalOrchestrator` is the one entry point (live asks and evals). It classifies the question
  (structured output: factual / thematic / concept / other; any failure falls back to factual) and
  maps the label to a `RetrievalConfig` (thematic → hierarchical; factual → flat; concept → scoped
  to sections where the reader-visible concept appears, else normal search).
- The gap-check loop asks a model whether the retrieved passages suffice; if not it returns a
  follow-up query, used only as query text for another `RetrievalPipeline` pass. Iterations are
  capped at 3 (`max_iterations`, default 1 = off), results are merged and de-duplicated
  (capped at `2 * final_k`), and errors count as "sufficient".
- Safety: passages are marked untrusted in the prompt; the classifier never sees book text; every
  pass goes through the same SQL gate (user, document, ordinal <= progress), so a hijacked verdict
  can cost extra searches but not leak. Stage traces record decisions and token counts, never text.
- Evals: configs gain `route`, and the table reports average iterations. Prompts `classify.md` and
  `gap_check.md` are human-owned baselines.

## Consequences

Extra latency and tokens per ask when enabled; measure with `make eval` before turning
`RETRIEVAL_MAX_ITERATIONS` up.
