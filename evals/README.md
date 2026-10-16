# Evals

Compare retrieval/generation strategies on the same questions, with the same pipeline production uses.

```bash
make eval                                   # every config × every question file, prints a table
make compare ARGS="baseline_flat_hybrid hierarchical_hybrid"   # re-print chosen configs
cd backend && PYTHONPATH=.. uv run python -m evals.run --config ../evals/configs/flat_vector.yaml
```

Requires `make migrate` (tables `eval_runs`, `eval_results`). Runs as a reserved eval user
(`eval@learnedhand.invalid`, cannot log in); results are under RLS like any user data and contain
ids, metrics and timings only — no book text, prompts or answers.

## What is measured

| Metric | Meaning |
|---|---|
| recall@5 / @10, MRR | Gold passages found in the final ranked chunks |
| per-stage recall | Gold present in each stage's pool: `broad→section`, vector, FTS, fused, rerank |
| ctx points | Expected facts present (lexically) in the retrieved context — retrieval sufficiency |
| answer points (judge) | LLM-as-judge: expected facts stated in the answer (real provider only) |
| citation ok | Share of `[n]` markers that point at an existing source |
| p50/p95 ms, tokens, cost | Latency, token use, cost from `PRICE_*_PER_MTOK` settings |

With `LLM_PROVIDER=fake` (default) the vectors are a lexical stand-in, summaries are extractive and
answer quality is *not* measured: the numbers validate the plumbing and relative effects of
retrieval settings, not real-world quality.

## Files

- `questions/*.yaml` — **human-owned**. `demo.yaml` targets the synthetic demo book
  (`corpus.py`); copy `questions/example.yaml.template` to add questions about an EPUB you own.
  Gold passages are identified by a text snippet, so they survive re-chunking.
- `configs/*.yaml` — one retrieval strategy each (`schema.py`: `RetrievalConfig` fields +
  `reranker`). Add a file to add a row to the table. `retrieval.max_iterations` (1–3) enables the agentic gap-check loop and `route: true` classifies each question and picks a strategy, exactly like live asks (ADR 0015); the table reports average iterations.
- `prompts/judge.md` — **human-owned** judge prompt baseline.

## Limits

- One ingestion per corpus: configs vary retrieval, not ingestion (chunking, summaries,
  `CONTEXT_PREFIX_MODE`). The "context prefix off" config uses body-only vectors stored by
  `STORE_PLAIN_EMBEDDINGS` (the runner enables it).
- The `fake` reranker is lexical; use `reranker: cross_encoder` for a real one.
