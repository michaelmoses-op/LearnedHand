"""PDF ingestion: structure detection, cleanup, hostile-input containment, end-to-end."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.deps import AuthContext, set_rls_user
from app.ingestion import pdf_text
from app.ingestion.parse_pdf import PdfParseError, parse_pdf
from app.jobs.worker import process_one
from app.repositories.content import ChunkRepository, SectionRepository
from tests.conftest import _asyncpg_dsn
from tests.pdf_fixture import make_image_only_pdf, make_pdf


@pytest.fixture(autouse=True)
async def _wipe_jobs(test_urls: tuple[str, str]) -> AsyncIterator[None]:
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[1]))
    try:
        await conn.execute("truncate jobs")
    finally:
        await conn.close()
    yield


async def test_outline_sections_strip_furniture_and_map_pages() -> None:
    book = await parse_pdf(make_pdf())
    titles = [s.title for s in book.sections]
    assert titles == ["Chapter One", "Chapter Two", "Chapter Three"]
    assert book.stats["structure_method"] == 1
    assert book.stats["removed_headers_footers"] >= 5
    assert book.stats["removed_page_numbers"] >= 5
    for s in book.sections:
        assert "Running Header" not in s.text
        assert s.page_map and s.page_map[0][1] == s.page_start
    assert (book.sections[0].page_start, book.sections[0].page_end) == (1, 2)
    assert book.sections[2].page_start == 5


async def test_heading_detection_without_outline() -> None:
    book = await parse_pdf(make_pdf(outline=False))
    assert [s.title for s in book.sections] == ["Chapter One", "Chapter Two", "Chapter Three"]
    assert book.stats["structure_method"] == 2


async def test_page_window_fallback_when_no_structure() -> None:
    book = await parse_pdf(make_pdf(outline=False, big_headings=False))
    assert book.stats["structure_method"] == 3
    assert book.sections[0].title.startswith("Pages 1")


def test_dehyphenation_and_line_joining() -> None:
    text, repairs = pdf_text.clean_block_text("The informa-\ntion carried by institu-\ntions here")
    assert text == "The information carried by institutions here"
    assert repairs == 2
    # A real hyphenated compound before a capital is not merged.
    kept, none = pdf_text.clean_block_text("well-\nKnown")
    assert kept == "well- Known" and none == 0


def test_paragraph_split_across_pages_is_joined() -> None:
    b = pdf_text._SectionBuilder("S", 0, 1)
    b.add("The argument continues on", 1)
    b.add("the next page and ends here.", 2)
    b.add("A new paragraph.", 2)
    sec = b.build()
    assert sec.text.split("\n\n") == [
        "The argument continues on the next page and ends here.",
        "A new paragraph.",
    ]
    assert sec.page_map == [[0, 1], [len("The argument continues on") + 1, 2]]


async def test_hyphenated_pdf_text_repaired_end_to_end() -> None:
    book = await parse_pdf(make_pdf(hyphenate=True))
    assert "information carried by institutions" in book.sections[0].text


# ---- hostile / broken input: must fail closed with a clean domain error ----------------------


@pytest.mark.parametrize(
    "data",
    [b"%PDF-1.7\ngarbage garbage", b"%PDF-", b"\x00" * 2048, make_pdf()[:300]],
)
async def test_corrupt_pdfs_raise_domain_error(data: bytes) -> None:
    with pytest.raises(PdfParseError):
        await parse_pdf(data)


async def test_encrypted_pdf_rejected() -> None:
    with pytest.raises(PdfParseError, match="pdf_encrypted"):
        await parse_pdf(make_pdf(encrypt=True))


async def test_page_limit_enforced() -> None:
    with pytest.raises(PdfParseError, match="pdf_too_many_pages"):
        await parse_pdf(make_pdf(), max_pages=2)


async def test_image_only_pdf_reports_no_text_layer() -> None:
    with pytest.raises(PdfParseError, match="pdf_no_text_layer"):
        await parse_pdf(make_image_only_pdf())


async def test_worker_memory_limit_is_enforced() -> None:
    with pytest.raises(PdfParseError):
        await parse_pdf(make_pdf(), memory_mb=40)


async def test_worker_wall_clock_timeout_kills_child() -> None:
    with pytest.raises(PdfParseError, match="pdf_timeout"):
        await parse_pdf(make_pdf(), time_limit=0.05)


# ---- end to end through the API and job worker -----------------------------------------------


async def _uid(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])


@pytest.mark.usefixtures("user_a")
async def test_pdf_upload_ingests_with_pages_and_quality_report(
    app: FastAPI, client: AsyncClient
) -> None:
    r = await client.post(
        "/api/v1/documents", content=make_pdf(), headers={"X-Filename": "book.pdf"}
    )
    assert r.status_code == 201, r.text
    doc_id = uuid.UUID(r.json()["id"])
    assert await process_one(app.state.sessionmaker, "pdf-worker")

    st = (await client.get(f"/api/v1/documents/{doc_id}/status")).json()
    assert st["status"] == "ready", st

    user_id = await _uid(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        ctx = AuthContext(user_id)
        chunks = await ChunkRepository(session, ctx).list_for_document(doc_id)
        sections = await SectionRepository(session, ctx).list_for_document(doc_id)
    assert len(sections) == 3
    assert chunks and all(c.page_start is not None for c in chunks)
    assert all(
        c.page_start <= c.page_end
        for c in chunks
        if c.page_start is not None and c.page_end is not None
    )
    assert sections[0].first_chunk_ordinal == 0
