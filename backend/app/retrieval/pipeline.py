"""Configurable retrieval pipeline with per-stage tracing.

Stages (each optional per `RetrievalConfig`):
  embed_query → [broad (summaries)] → vector / fts → fuse (RRF) → [rerank] → final

Spoiler gate: every chunk query is scoped to `ordinal <= progress`; summaries are only eligible
when `last_ordinal <= progress`. Hierarchical drill-down additionally covers the "frontier" —
sections whose summary is not yet visible (unfinished or unsummarised) — so partially read
sections are never skipped, and nothing beyond `progress` is ever reachable.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.logging import get_logger
from app.llm.base import Reranker
from app.llm.factory import build_llm
from app.llm.rerank import build_reranker
from app.models.chunk import Chunk
from app.models.summary import Summary
from app.repositories.content import ProgressRepository
from app.retrieval.config import RetrievalConfig
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.types import (
    RetrievalError,
    RetrievalResult,
    RetrievedChunk,
    StageTrace,
)

log = get_logger("retrieval.pipeline")


def _scoped[T](
    stmt: Select[T],
    *,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    progress: int,
) -> Select[T]:
    """Every chunk query must include user, document, and ordinal <= progress."""
    return stmt.where(
        Chunk.user_id == user_id,
        Chunk.document_id == document_id,
        Chunk.ordinal <= progress,
    )


_TS_TOKEN = re.compile(r"\w+", re.UNICODE)


def _ts_query(query: str, operator: str) -> ColumnElement[Any] | None:
    """Build a tsquery. OR-mode passes only `\\w+` tokens to `to_tsquery` (no operators from
    user text can reach it); stop words are dropped by the `english` config."""
    if operator == "and":
        return func.plainto_tsquery("english", query)
    tokens = list(dict.fromkeys(t.lower() for t in _TS_TOKEN.findall(query)))[:64]
    if not tokens:
        return None
    return func.to_tsquery("english", " | ".join(tokens))


class _Timer:
    def __init__(self) -> None:
        self._t = time.perf_counter()

    def ms(self) -> float:
        return (time.perf_counter() - self._t) * 1000.0


class RetrievalPipeline:
    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        settings: Settings,
        *,
        document_id: uuid.UUID | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._session = session
        self._ctx = ctx
        self._settings = settings
        self._llm = build_llm(settings, session, ctx, document_id=document_id, stage="retrieve")
        self._reranker = reranker if reranker is not None else build_reranker(settings)

    async def resolve_progress(self, document_id: uuid.UUID) -> int:
        row = await ProgressRepository(self._session, self._ctx).get(document_id)
        if row is None:
            # No progress row ⇒ nothing readable (safer than opening the whole book).
            return -1
        return row.max_ordinal

    async def run(
        self,
        *,
        document_id: uuid.UUID,
        query: str,
        config: RetrievalConfig | None = None,
        progress: int | None = None,
        scope_sections: Sequence[uuid.UUID] | None = None,
    ) -> RetrievalResult:
        """`scope_sections` restricts candidates to those sections (e.g. where a concept appears);
        it narrows the search but can never widen it past the progress gate."""
        cfg = config or RetrievalConfig.from_settings(self._settings)
        if not query.strip():
            raise RetrievalError("empty_query")
        if cfg.rerank and self._reranker is None:
            raise RetrievalError("reranker_not_configured")

        gate = progress if progress is not None else await self.resolve_progress(document_id)
        stages: list[StageTrace] = []
        if gate < 0:
            return RetrievalResult(chunks=[], stages=stages, progress=gate)

        if not cfg.use_context_prefix and not await self._has_plain_embeddings(document_id):
            raise RetrievalError("plain_embeddings_missing")

        # -- embed query --
        timer = _Timer()
        batch = await self._llm.embed(
            model=self._settings.embedding_model,
            texts=[query],
            dimensions=self._settings.embedding_dim,
        )
        qvec = batch.vectors[0]
        stages.append(StageTrace("embed_query", timer.ms(), 1, tokens=batch.input_tokens, ids=[]))

        # -- broad pass over summaries --
        scope: ColumnElement[bool] | None = None
        if cfg.hierarchical:
            timer = _Timer()
            picked, has_visible = await self._broad(document_id, qvec, gate, cfg.broad_k)
            if has_visible:
                scope = await self._drill_scope(document_id, gate, picked)
                note = ""
            else:
                note = "no_visible_summaries_fallback_flat"
            stages.append(
                StageTrace(
                    "broad",
                    timer.ms(),
                    len(picked),
                    ids=[section_id for section_id, _, _ in picked if section_id is not None],
                    note=note,
                )
            )

        if scope_sections is not None:
            only = Chunk.section_id.in_(list(scope_sections))
            scope = only if scope is None else and_(scope, only)

        # -- candidate generation --
        ranked: list[list[uuid.UUID]] = []
        if cfg.mode in ("vector", "hybrid"):
            timer = _Timer()
            ids = await self._vector_search(document_id, qvec, gate, cfg, scope)
            stages.append(StageTrace("vector", timer.ms(), len(ids), ids=ids))
            ranked.append(ids)
        if cfg.mode in ("fts", "hybrid"):
            timer = _Timer()
            ids = await self._fts_search(document_id, query, gate, cfg, scope)
            stages.append(StageTrace("fts", timer.ms(), len(ids), ids=ids))
            ranked.append(ids)

        timer = _Timer()
        fused = reciprocal_rank_fusion(ranked, k=cfg.rrf_k)
        if cfg.mode == "hybrid":
            stages.append(StageTrace("fuse", timer.ms(), len(fused), ids=[cid for cid, _ in fused]))

        # -- rerank --
        pool_n = cfg.rerank_pool if cfg.rerank else cfg.final_k
        pool = fused[: max(pool_n, cfg.final_k)]
        by_id = await self._load_chunks(document_id, gate, [cid for cid, _ in pool])
        ordered: list[tuple[uuid.UUID, float]] = [(cid, s) for cid, s in pool if cid in by_id]
        if cfg.rerank and self._reranker is not None and ordered:
            timer = _Timer()
            scores = await self._reranker.rerank(
                query=query, passages=[by_id[cid].body for cid, _ in ordered]
            )
            order = sorted(range(len(ordered)), key=lambda i: (-scores[i], i))
            ordered = [(ordered[i][0], float(scores[i])) for i in order]
            stages.append(
                StageTrace("rerank", timer.ms(), len(ordered), ids=[cid for cid, _ in ordered])
            )

        final = ordered[: cfg.final_k]
        out: list[RetrievedChunk] = []
        for cid, score in final:
            chunk = by_id[cid]
            if chunk.ordinal > gate:  # defense in depth: never return past the gate
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
        stages.append(StageTrace("final", 0.0, len(out), ids=[c.chunk_id for c in out]))
        log.info(
            "retrieve_done",
            document_id=str(document_id),
            config=cfg.name,
            progress=gate,
            returned=len(out),
            stages={s.name: round(s.duration_ms, 1) for s in stages},
        )
        return RetrievalResult(chunks=out, stages=stages, progress=gate)

    # ---- stages ------------------------------------------------------------------------------

    async def _has_plain_embeddings(self, document_id: uuid.UUID) -> bool:
        stmt = select(
            exists().where(
                Chunk.user_id == self._ctx.user_id,
                Chunk.document_id == document_id,
                Chunk.embedding_plain.is_not(None),
            )
        )
        return bool((await self._session.execute(stmt)).scalar_one())

    async def _broad(
        self, document_id: uuid.UUID, qvec: list[float], progress: int, k: int
    ) -> tuple[list[tuple[uuid.UUID | None, int, int]], bool]:
        """Nearest visible section summaries → (section_id, first_ordinal, last_ordinal)."""
        visible = (
            Summary.user_id == self._ctx.user_id,
            Summary.document_id == document_id,
            Summary.kind == "section",
            Summary.last_ordinal <= progress,  # spoiler gate for summaries
        )
        has_visible = bool(
            (await self._session.execute(select(exists().where(*visible)))).scalar_one()
        )
        if not has_visible:
            return [], False
        stmt = (
            select(Summary.section_id, Summary.first_ordinal, Summary.last_ordinal)
            .where(*visible, Summary.embedding.is_not(None))
            .order_by(Summary.embedding.cosine_distance(qvec))
            .limit(k)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(r[0], int(r[1]), int(r[2])) for r in rows], True

    async def _drill_scope(
        self,
        document_id: uuid.UUID,
        progress: int,
        picked: Sequence[tuple[uuid.UUID | None, int, int]],
    ) -> ColumnElement[bool]:
        """Chunks inside picked ranges, plus every chunk of sections with no visible summary."""
        summarised = select(Summary.section_id).where(
            Summary.user_id == self._ctx.user_id,
            Summary.document_id == document_id,
            Summary.kind == "section",
            Summary.last_ordinal <= progress,
            Summary.section_id.is_not(None),
        )
        frontier = Chunk.section_id.not_in(summarised)
        ranges = [and_(Chunk.ordinal >= lo, Chunk.ordinal <= hi) for _, lo, hi in picked]
        return or_(frontier, *ranges)

    async def _vector_search(
        self,
        document_id: uuid.UUID,
        qvec: list[float],
        progress: int,
        cfg: RetrievalConfig,
        scope: ColumnElement[bool] | None,
    ) -> list[uuid.UUID]:
        col = Chunk.embedding if cfg.use_context_prefix else Chunk.embedding_plain
        stmt = _scoped(
            select(Chunk.id).order_by(col.cosine_distance(qvec)).limit(cfg.candidate_k),
            user_id=self._ctx.user_id,
            document_id=document_id,
            progress=progress,
        ).where(col.is_not(None))
        if scope is not None:
            stmt = stmt.where(scope)
        return [row[0] for row in (await self._session.execute(stmt)).all()]

    async def _fts_search(
        self,
        document_id: uuid.UUID,
        query: str,
        progress: int,
        cfg: RetrievalConfig,
        scope: ColumnElement[bool] | None,
    ) -> list[uuid.UUID]:
        ts_query = _ts_query(query, cfg.fts_operator)
        if ts_query is None:
            return []
        vector: Any = (
            Chunk.search_vector
            if cfg.use_context_prefix
            else func.to_tsvector("english", Chunk.body)
        )
        stmt = (
            _scoped(
                select(Chunk.id),
                user_id=self._ctx.user_id,
                document_id=document_id,
                progress=progress,
            )
            .where(vector.op("@@")(ts_query))
            .order_by(func.ts_rank_cd(vector, ts_query).desc())
            .limit(cfg.candidate_k)
        )
        if scope is not None:
            stmt = stmt.where(scope)
        return [row[0] for row in (await self._session.execute(stmt)).all()]

    async def _load_chunks(
        self, document_id: uuid.UUID, progress: int, chunk_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Chunk]:
        if not chunk_ids:
            return {}
        stmt = _scoped(
            select(Chunk).where(Chunk.id.in_(chunk_ids)),
            user_id=self._ctx.user_id,
            document_id=document_id,
            progress=progress,
        )
        return {c.id: c for c in (await self._session.execute(stmt)).scalars()}
