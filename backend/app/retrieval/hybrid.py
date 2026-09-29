"""Hybrid retrieval: vector + full-text, fused with RRF. Always progress-gated."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.llm.factory import build_llm
from app.models.chunk import Chunk
from app.repositories.content import ProgressRepository
from app.retrieval.rrf import reciprocal_rank_fusion

log = get_logger("retrieval.hybrid")

DEFAULT_CANDIDATE_K = 40
DEFAULT_LIMIT = 8
RRF_K = 60


class RetrievalError(DomainError):
    code = "retrieval_failed"
    title = "Retrieval failed"


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    section_id: uuid.UUID
    ordinal: int
    text: str
    context_prefix: str
    score: float


def _scoped[T](
    stmt: Select[T],
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    progress: int,
) -> Select[T]:
    """Every retrieval query must include user, document, and ordinal <= progress."""
    return stmt.where(
        Chunk.user_id == user_id,
        Chunk.document_id == document_id,
        Chunk.ordinal <= progress,
    )


class HybridRetriever:
    """Vector + FTS hybrid search. Callers supply AuthContext; progress is required."""

    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        settings: Settings,
        *,
        document_id: uuid.UUID | None = None,
    ) -> None:
        self._session = session
        self._ctx = ctx
        self._settings = settings
        self._document_id = document_id
        self._llm = build_llm(settings, session, ctx, document_id=document_id, stage="retrieve")

    async def resolve_progress(self, document_id: uuid.UUID) -> int:
        row = await ProgressRepository(self._session, self._ctx).get(document_id)
        if row is None:
            # No progress row ⇒ nothing readable (safer than opening the whole book).
            return -1
        return row.max_ordinal

    async def retrieve(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        progress: int | None = None,
        limit: int = DEFAULT_LIMIT,
        candidate_k: int = DEFAULT_CANDIDATE_K,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise RetrievalError("empty_query")
        if limit < 1 or candidate_k < 1:
            raise RetrievalError("bad_limit")

        gate = progress if progress is not None else await self.resolve_progress(document_id)
        if gate < 0:
            return []

        query_vec = await self._embed_query(query)
        vector_ids = await self._vector_search(
            document_id=document_id, query_vec=query_vec, progress=gate, limit=candidate_k
        )
        fts_ids = await self._fts_search(
            document_id=document_id, query=query, progress=gate, limit=candidate_k
        )
        fused = reciprocal_rank_fusion([vector_ids, fts_ids], k=RRF_K)[:limit]
        if not fused:
            return []

        by_id = await self._load_chunks(
            document_id=document_id, progress=gate, chunk_ids=[cid for cid, _ in fused]
        )
        out: list[RetrievedChunk] = []
        for cid, score in fused:
            chunk = by_id.get(cid)
            if chunk is None:
                continue
            # Defense in depth: never return past the gate even if a bug bypassed SQL.
            if chunk.ordinal > gate:
                continue
            out.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    section_id=chunk.section_id,
                    ordinal=chunk.ordinal,
                    text=chunk.body,
                    context_prefix=chunk.context_prefix,
                    score=score,
                )
            )
        log.info(
            "retrieve_done",
            document_id=str(document_id),
            progress=gate,
            vector_hits=len(vector_ids),
            fts_hits=len(fts_ids),
            returned=len(out),
        )
        return out

    async def _embed_query(self, query: str) -> list[float]:
        batch = await self._llm.embed(
            model=self._settings.embedding_model,
            texts=[query],
            dimensions=self._settings.embedding_dim,
        )
        return batch.vectors[0]

    async def _vector_search(
        self,
        *,
        document_id: uuid.UUID,
        query_vec: list[float],
        progress: int,
        limit: int,
    ) -> list[uuid.UUID]:
        dist = Chunk.embedding.cosine_distance(query_vec)
        stmt = _scoped(
            select(Chunk.id).order_by(dist).limit(limit),
            user_id=self._ctx.user_id,
            document_id=document_id,
            progress=progress,
        ).where(Chunk.embedding.is_not(None))
        rows = (await self._session.execute(stmt)).all()
        return [row[0] for row in rows]

    async def _fts_search(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        progress: int,
        limit: int,
    ) -> list[uuid.UUID]:
        ts_query = func.plainto_tsquery("english", query)
        rank = func.ts_rank_cd(Chunk.search_vector, ts_query)
        stmt = (
            _scoped(
                select(Chunk.id),
                user_id=self._ctx.user_id,
                document_id=document_id,
                progress=progress,
            )
            .where(Chunk.search_vector.op("@@")(ts_query))
            .order_by(rank.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [row[0] for row in rows]

    async def _load_chunks(
        self,
        *,
        document_id: uuid.UUID,
        progress: int,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, Chunk]:
        if not chunk_ids:
            return {}
        stmt = _scoped(
            select(Chunk).where(Chunk.id.in_(chunk_ids)),
            user_id=self._ctx.user_id,
            document_id=document_id,
            progress=progress,
        )
        rows = list((await self._session.execute(stmt)).scalars())
        return {c.id: c for c in rows}
