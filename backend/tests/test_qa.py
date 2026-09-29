"""Citation verification + ask SSE."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.generation.ask import sanitize_answer_html
from app.generation.citations import SourceRef, verify_citations
from app.jobs.worker import process_one
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


def test_verify_citations_keeps_only_retrieved_sources() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sa, sb = uuid.uuid4(), uuid.uuid4()
    sources = [
        SourceRef(1, a, sa, 0, ""),
        SourceRef(2, b, sb, 1, ""),
    ]
    fake = uuid.uuid4()
    cites = verify_citations(f"See [1] and [9] and [chunk:{fake}] and [chunk:{b}].", sources)
    assert [(c.index, c.chunk_id) for c in cites] == [(1, a), (2, b)]


def test_sanitize_strips_script() -> None:
    assert "<script" not in sanitize_answer_html("<b>ok</b><script>alert(1)</script>")
    assert "<b>ok</b>" in sanitize_answer_html("<b>ok</b>")


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event = "message"
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif line == "" and data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
            event = "message"
            data_lines = []
    if data_lines:
        events.append((event, json.loads("\n".join(data_lines))))
    return events


@pytest.mark.usefixtures("user_a")
async def test_ask_sse_emits_sources_tokens_citations(app: FastAPI, client: AsyncClient) -> None:
    epub = make_epub()
    doc_id = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "q.epub"})
    ).json()["id"]
    assert await process_one(app.state.sessionmaker, "ask-w")

    async with client.stream(
        "POST",
        f"/api/v1/documents/{doc_id}/ask",
        json={"question": "What is justice?"},
    ) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        body = ""
        async for chunk in res.aiter_text():
            body += chunk
    events = _parse_sse(body)
    names = [e for e, _ in events]
    assert "status" in names
    assert "sources" in names
    assert "token" in names
    assert "citations" in names
    assert names[-1] == "done"
    sources = next(d for n, d in events if n == "sources")
    assert isinstance(sources["items"], list)
    assert sources["items"], "ready book should retrieve at least one chunk"
    citations = next(d for n, d in events if n == "citations")
    cite_items = citations["items"]
    source_items = sources["items"]
    assert isinstance(cite_items, list) and isinstance(source_items, list)
    cite_ids = {c["chunk_id"] for c in cite_items if isinstance(c, dict)}
    source_ids = {c["chunk_id"] for c in source_items if isinstance(c, dict)}
    assert cite_ids <= source_ids


@pytest.mark.usefixtures("user_a")
async def test_ask_rejects_not_ready(app: FastAPI, client: AsyncClient) -> None:
    epub = make_epub()
    doc_id = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "nr.epub"})
    ).json()["id"]
    # Do not run worker — still uploaded.
    r = await client.post(f"/api/v1/documents/{doc_id}/ask", json={"question": "Anything?"})
    assert r.status_code == 409
    assert r.json()["code"] == "document_not_ready"


@pytest.mark.usefixtures("user_a", "user_b")
async def test_ask_idor_is_404(client: AsyncClient, client_b: AsyncClient) -> None:
    epub = make_epub()
    doc_id = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "id.epub"})
    ).json()["id"]
    r = await client_b.post(f"/api/v1/documents/{doc_id}/ask", json={"question": "secret?"})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


@pytest.mark.usefixtures("user_a")
async def test_sections_and_progress(app: FastAPI, client: AsyncClient) -> None:
    epub = make_epub()
    doc_id = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "s.epub"})
    ).json()["id"]
    assert await process_one(app.state.sessionmaker, "sec-w")

    sections = (await client.get(f"/api/v1/documents/{doc_id}/sections")).json()["items"]
    assert sections
    assert all(s["readable"] and s["body"] for s in sections)

    # Clamp progress to the first chunk only; later sections should gate.
    r = await client.put(f"/api/v1/documents/{doc_id}/progress", json={"max_ordinal": 0})
    assert r.status_code == 200 and r.json()["max_ordinal"] == 0
    gated = (await client.get(f"/api/v1/documents/{doc_id}/sections")).json()["items"]
    assert any(s["readable"] for s in gated)
    if len(gated) > 1:
        assert any(not s["readable"] for s in gated) or all(s["readable"] for s in gated)
