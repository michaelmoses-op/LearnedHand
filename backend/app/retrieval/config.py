"""Retrieval configuration: one immutable object describes a full retrieval strategy.

Used by the live ask path (built from settings) and by evals (loaded from YAML), so an eval
config is exactly what production would run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = "default"
    hierarchical: bool = False  # broad pass over summaries, then drill down
    use_context_prefix: bool = True  # False needs chunks.embedding_plain (STORE_PLAIN_EMBEDDINGS)
    mode: Literal["vector", "fts", "hybrid"] = "hybrid"
    rerank: bool = False
    candidate_k: int = Field(default=40, ge=1, le=500)
    rerank_pool: int = Field(default=30, ge=1, le=200)  # fused candidates sent to the reranker
    final_k: int = Field(default=8, ge=1, le=50)
    broad_k: int = Field(default=5, ge=1, le=50)  # summaries selected by the broad pass
    rrf_k: int = Field(default=60, ge=1)
    # >1 needs the agentic gap-check loop (Phase 4); rejected until then.
    max_iterations: int = Field(default=1, ge=1, le=1)

    @classmethod
    def from_settings(cls, settings: Settings) -> RetrievalConfig:
        return cls(
            hierarchical=settings.retrieval_hierarchical,
            rerank=settings.reranker != "none",
            broad_k=settings.retrieval_broad_k,
        )
