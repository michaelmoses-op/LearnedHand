"""Hybrid retrieval (vector + FTS, RRF) — a thin adapter over `RetrievalPipeline`.

Kept for callers that only want chunks; new code should use the pipeline for stage traces.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.retrieval.config import RetrievalConfig
from app.retrieval.pipeline import RetrievalPipeline, _scoped
from app.retrieval.types import RetrievalError, RetrievedChunk

DEFAULT_CANDIDATE_K = 40
DEFAULT_LIMIT = 8
RRF_K = 60

__all__ = [
    "DEFAULT_CANDIDATE_K",
    "DEFAULT_LIMIT",
    "RRF_K",
    "HybridRetriever",
    "RetrievalError",
    "RetrievedChunk",
    "_scoped",
]


class HybridRetriever:
    """Flat hybrid search. Callers supply AuthContext."""

    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        settings: Settings,
        *,
        document_id: uuid.UUID | None = None,
    ) -> None:
        self._pipeline = RetrievalPipeline(
            session, ctx, settings, document_id=document_id, reranker=None
        )

    async def retrieve(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        limit: int = DEFAULT_LIMIT,
        candidate_k: int = DEFAULT_CANDIDATE_K,
    ) -> list[RetrievedChunk]:
        if limit < 1 or candidate_k < 1:
            raise RetrievalError("bad_limit")
        config = RetrievalConfig(name="hybrid", final_k=limit, candidate_k=candidate_k)
        result = await self._pipeline.run(document_id=document_id, query=query, config=config)
        return result.chunks
