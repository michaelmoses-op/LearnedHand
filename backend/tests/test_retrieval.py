"""Hybrid retrieval + progress ordinal gate."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.jobs.worker import process_one
from app.models.chunk import Chunk
from app.repositories.content import ProgressRepository
from app.retrieval.config import RetrievalConfig
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.rrf import reciprocal_rank_fusion
from tests.conftest import _asyncpg_dsn
from tests.epub_fixture import make_epub


@pytest.fixture(autouse=True)
async def _wipe_jobs(test_urls: tuple[str, str]) -> AsyncIterator[None]:
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[1]))
    try:
        await conn.execute("truncate jobs")
    finally:
        await conn.close()
    yield


async def _uid(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])


def test_rrf_prefers_items_high_in_both_lists() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = reciprocal_rank_fusion([[a, b, c], [b, a, c]], k=60)
    assert fused[0][0] == b or fused[0][0] == a
    ids = [i for i, _ in fused]
    assert set(ids) == {a, b, c}


@pytest.mark.usefixtures("user_a")
async def test_progress_gate_excludes_later_ordinals(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    """Nothing with ordinal > progress may appear — SQL gate + defense in depth."""
    epub = make_epub(
        title="Gate Book",
        chapters=[
            ("Early", ("Alpha marker appears here. " * 80).strip()),
            ("Late", ("Omega spoiler appears here. " * 80).strip()),
        ],
    )
    doc_id = uuid.UUID(
        (
            await client.post(
                "/api/v1/documents", content=epub, headers={"X-Filename": "gate.epub"}
            )
        ).json()["id"]
    )
    assert await process_one(app.state.sessionmaker, "ret-worker")

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        chunks = list(
            (await session.execute(select(Chunk).where(Chunk.document_id == doc_id))).scalars()
        )
        assert len(chunks) >= 2
        # Gate mid-book: allow only the first half of ordinals.
        mid = sorted(c.ordinal for c in chunks)[len(chunks) // 2 - 1]
        await ProgressRepository(session, ctx).upsert(doc_id, mid)
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        chunks = list(
            (await session.execute(select(Chunk).where(Chunk.document_id == doc_id))).scalars()
        )
        allowed = {c.id for c in chunks if c.ordinal <= mid}
        forbidden = {c.id for c in chunks if c.ordinal > mid}
        assert forbidden, "need later chunks to prove the gate"

        retriever = HybridRetriever(session, ctx, settings, document_id=doc_id)
        # Broad query that would match both halves without a gate.
        hits = await retriever.retrieve(
            document_id=doc_id, query="marker spoiler appears here", progress=mid, limit=20
        )
        hit_ids = {h.chunk_id for h in hits}
        assert hit_ids <= allowed
        assert hit_ids.isdisjoint(forbidden)
        assert all(h.ordinal <= mid for h in hits)

        # Explicit progress=0 still must not leak later ordinals.
        only_first = await retriever.retrieve(
            document_id=doc_id, query="Omega spoiler", progress=0, limit=20
        )
        assert all(h.ordinal <= 0 for h in only_first)


@pytest.mark.usefixtures("user_a")
async def test_vector_and_fts_sql_both_apply_progress_filter(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    """Unit-level: each candidate SQL path filters ordinal <= progress."""
    epub = make_epub()
    doc_id = uuid.UUID(
        (
            await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "sql.epub"})
        ).json()["id"]
    )
    assert await process_one(app.state.sessionmaker, "ret-worker")

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        max_ord = (
            await session.execute(
                select(func.max(Chunk.ordinal)).where(Chunk.document_id == doc_id)
            )
        ).scalar_one()
        assert max_ord is not None and max_ord >= 1
        gate = 0
        await ProgressRepository(session, ctx).upsert(doc_id, gate)
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        retriever = HybridRetriever(session, ctx, settings, document_id=doc_id)
        pipeline = retriever._pipeline
        cfg = RetrievalConfig(candidate_k=50)
        emb = await pipeline._llm.embed(
            model=settings.embedding_model,
            texts=["justice virtue institutions"],
            dimensions=settings.embedding_dim,
        )
        vector_ids = await pipeline._vector_search(doc_id, emb.vectors[0], gate, cfg, None)
        fts_ids = await pipeline._fts_search(doc_id, "justice virtue", gate, cfg, None)

        if vector_ids:
            rows = (await session.execute(select(Chunk).where(Chunk.id.in_(vector_ids)))).scalars()
            assert all(c.ordinal <= gate for c in rows)
        if fts_ids:
            rows = (await session.execute(select(Chunk).where(Chunk.id.in_(fts_ids)))).scalars()
            assert all(c.ordinal <= gate for c in rows)

        # Past-gate query against full corpus would find later chunks; gated search must not.
        ungated = list(
            (
                await session.execute(
                    select(Chunk).where(Chunk.document_id == doc_id, Chunk.ordinal > gate)
                )
            ).scalars()
        )
        assert ungated
        hits = await retriever.retrieve(
            document_id=doc_id, query="justice", progress=gate, limit=20
        )
        assert all(h.ordinal <= gate for h in hits)
        assert {h.chunk_id for h in hits}.isdisjoint({c.id for c in ungated})


@pytest.mark.usefixtures("user_a", "user_b")
async def test_retrieval_cannot_see_other_users_chunks(
    app: FastAPI, client: AsyncClient, client_b: AsyncClient, settings: Settings
) -> None:
    epub = make_epub(title="Private")
    doc_a = uuid.UUID(
        (
            await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "a.epub"})
        ).json()["id"]
    )
    assert await process_one(app.state.sessionmaker, "w")

    user_b = await _uid(client_b)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_b)
        hits = await HybridRetriever(session, AuthContext(user_b), settings).retrieve(
            document_id=doc_a, query="justice", progress=10_000, limit=10
        )
        assert hits == []
