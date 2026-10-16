"""Hybrid retrieval: whole-book coverage, per-document and per-user scoping."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.jobs.worker import process_one
from app.models.chunk import Chunk
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
async def test_retrieval_covers_the_whole_book_but_only_that_document(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    async def upload(title: str, late_word: str) -> uuid.UUID:
        epub = make_epub(
            title=title,
            chapters=[
                ("Early", ("Alpha marker appears here. " * 80).strip()),
                ("Late", (f"{late_word} appears here. " * 80).strip()),
            ],
        )
        r = await client.post(
            "/api/v1/documents", content=epub, headers={"X-Filename": f"{title}.epub"}
        )
        assert await process_one(app.state.sessionmaker, "ret-worker")
        return uuid.UUID(r.json()["id"])

    doc_id = await upload("One", "Omegaword")
    other = await upload("Two", "Zetaword")

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        chunks = list(
            (await session.execute(select(Chunk).where(Chunk.document_id == doc_id))).scalars()
        )
        first_ordinal = min(c.ordinal for c in chunks)
        retriever = HybridRetriever(session, ctx, settings, document_id=doc_id)
        hits = await retriever.retrieve(document_id=doc_id, query="Omegaword appears", limit=10)
        assert hits and any(h.ordinal > first_ordinal for h in hits)  # late text is reachable
        assert {h.document_id for h in hits} == {doc_id}  # never the user's other book
        zeta = await retriever.retrieve(document_id=doc_id, query="Zetaword", limit=10)
        assert all(h.document_id == doc_id for h in zeta)
        assert other not in {h.document_id for h in zeta}


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
            document_id=doc_a, query="justice", limit=10
        )
        assert hits == []
