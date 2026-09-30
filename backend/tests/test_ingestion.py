"""Ingestion: EPUB parse limits, pipeline, status endpoint."""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.ingestion.parse_epub import EpubParseError, parse_epub
from app.ingestion.pipeline import run_ingest
from app.jobs.worker import process_one
from app.models.job import Job
from app.models.section import Section
from app.repositories.content import ChunkRepository, ProgressRepository
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


def test_parse_rejects_path_traversal() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("../evil.txt", "x")
    with pytest.raises(EpubParseError, match="traversal"):
        parse_epub(buf.getvalue())


def test_parse_rejects_oversized_entry() -> None:
    big = b"a" * (9 * 1024 * 1024)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("huge.bin", big)
    with pytest.raises(EpubParseError):
        parse_epub(buf.getvalue())


def test_parse_happy_path_extracts_sections() -> None:
    book = parse_epub(make_epub(title="Republic"))
    assert book.title == "Republic"
    assert len(book.sections) >= 2
    assert "Justice" in book.sections[0].text


@pytest.mark.usefixtures("user_a")
async def test_upload_enqueues_ingest_and_status(app: FastAPI, client: AsyncClient) -> None:
    epub = make_epub()
    r = await client.post(
        "/api/v1/documents", content=epub, headers={"X-Filename": "republic.epub"}
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    st = await client.get(f"/api/v1/documents/{doc_id}/status")
    assert st.status_code == 200
    body = st.json()
    assert body["status"] == "uploaded"
    assert body["ingest_stage"] is None

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        jobs = list(
            (
                await session.execute(
                    select(Job).where(Job.document_id == uuid.UUID(doc_id), Job.kind == "ingest")
                )
            ).scalars()
        )
        assert len(jobs) == 1 and jobs[0].status == "pending"


@pytest.mark.usefixtures("user_a")
async def test_ingest_pipeline_ready_with_progress_at_end(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    epub = make_epub()
    doc_id = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "book.epub"})
    ).json()["id"]

    assert await process_one(app.state.sessionmaker, "ingest-worker")

    st = (await client.get(f"/api/v1/documents/{doc_id}/status")).json()
    assert st["status"] == "ready"
    assert st["ingest_stage"] == "validate"
    assert st["error"] is None
    assert st["max_ordinal"] is not None and st["max_ordinal"] >= 0

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        sections = list(
            (
                await session.execute(
                    select(Section).where(Section.document_id == uuid.UUID(doc_id))
                )
            ).scalars()
        )
        chunks = await ChunkRepository(session, ctx).list_for_document(uuid.UUID(doc_id))
        assert len(sections) >= 2
        assert len(chunks) >= 1
        assert all(
            c.embedding is not None and len(c.embedding) == settings.embedding_dim for c in chunks
        )
        assert all(c.context_prefix for c in chunks)
        progress = await ProgressRepository(session, ctx).get(uuid.UUID(doc_id))
        assert progress is not None
        assert progress.max_ordinal == max(c.ordinal for c in chunks)


@pytest.mark.usefixtures("user_a")
async def test_ingest_idempotent_rerun(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    epub = make_epub()
    doc_id = uuid.UUID(
        (
            await client.post(
                "/api/v1/documents", content=epub, headers={"X-Filename": "idem.epub"}
            )
        ).json()["id"]
    )
    assert await process_one(app.state.sessionmaker, "w1")

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        first = len(await ChunkRepository(session, ctx).list_for_document(doc_id))
        job = Job(user_id=user_id, document_id=doc_id, kind="ingest", status="running")
        await run_ingest(session, ctx, job, settings, app.state.storage)
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        second = len(await ChunkRepository(session, AuthContext(user_id)).list_for_document(doc_id))
        assert first == second and first > 0


@pytest.mark.usefixtures("user_a")
async def test_pdf_ingest_fails_cleanly(app: FastAPI, client: AsyncClient) -> None:
    pdf = b"%PDF-1.4 " + b"x" * 100
    doc_id = (
        await client.post("/api/v1/documents", content=pdf, headers={"X-Filename": "a.pdf"})
    ).json()["id"]
    assert await process_one(app.state.sessionmaker, "w")
    st = (await client.get(f"/api/v1/documents/{doc_id}/status")).json()
    assert st["status"] == "failed"
    assert st["error"]


def test_epub_text_has_one_paragraph_per_block_and_no_duplicates() -> None:
    from app.ingestion.parse_epub import _xhtml_text

    html = (
        b"<html xmlns='http://www.w3.org/1999/xhtml'><body><div class='chapter'>"
        b"<h1>Chapter One</h1>"
        b"<p>First <em>paragraph</em> here.</p>"
        b"<blockquote><p>A quoted line.</p></blockquote>"
        b"loose words between blocks"
        b"<p>Verse one<br/>verse two<br/>verse three</p>"
        b"<ul><li>item a</li><li>item b</li></ul>"
        b"</div></body></html>"
    )
    text, heading = _xhtml_text(html)
    assert heading == "Chapter One"
    assert text.split("\n\n") == [
        "Chapter One",
        "First paragraph here.",
        "A quoted line.",
        "loose words between blocks",
        "Verse one\nverse two\nverse three",
        "item a",
        "item b",
    ]
