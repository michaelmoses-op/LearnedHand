"""Notes/highlights and tutor mode."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.generation.ask import build_messages
from app.retrieval.types import RetrievedChunk
from tests.conftest import _asyncpg_dsn
from tests.test_hierarchical import _ingest, _uid, _wipe_jobs  # noqa: F401


def _url(doc_id: uuid.UUID, tail: str) -> str:
    return f"/api/v1/documents/{doc_id}/{tail}"


@pytest.mark.usefixtures("user_a")
async def test_notes_are_searchable_and_editable(app: FastAPI, client: AsyncClient) -> None:
    doc_id = await _ingest(app, client)
    notes = _url(doc_id, "notes")
    n1 = await client.post(notes, json={"body": "The lighthouse keeper is lonely"})
    assert n1.status_code == 201 and n1.json()["anchor_ordinal"] is None
    hl = await client.post(
        notes, json={"kind": "highlight", "quote": "orchard blossom apples", "anchor_ordinal": 2}
    )
    assert hl.status_code == 201 and hl.json()["kind"] == "highlight"
    assert (await client.post(notes, json={"kind": "highlight"})).status_code == 422
    assert (await client.post(notes, json={"body": "  "})).status_code == 422

    found = (await client.get(notes, params={"q": "lonely lighthouse"})).json()["items"]
    assert [i["id"] for i in found] == [n1.json()["id"]]
    assert [
        i["kind"] for i in (await client.get(notes, params={"kind": "highlight"})).json()["items"]
    ] == ["highlight"]
    assert (await client.get(notes, params={"q": "'\") OR ((("})).status_code == 200  # safe parsing
    assert len((await client.get(notes)).json()["items"]) == 2

    upd = await client.patch(f"{notes}/{n1.json()['id']}", json={"body": "keeper feels alone"})
    assert upd.status_code == 200 and upd.json()["body"] == "keeper feels alone"
    assert (await client.delete(f"{notes}/{n1.json()['id']}")).status_code == 204
    assert (await client.delete(f"{notes}/{n1.json()['id']}")).status_code == 404
    assert (await client.delete(f"{notes}/{hl.json()['id']}")).status_code == 204
    assert (await client.get(notes)).json()["items"] == []


@pytest.mark.usefixtures("user_a")
async def test_tutor_mode_uses_socratic_prompt(app: FastAPI, client: AsyncClient) -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        ordinal=1,
        text="t",
        context_prefix="",
        score=1.0,
    )
    tutor = build_messages(question="q", chunks=[chunk], mode="tutor")
    plain = build_messages(question="q", chunks=[chunk])
    assert "Socratic" in tutor[0].content and "Socratic" not in plain[0].content
    assert "<question>" in tutor[1].content

    doc_id = await _ingest(app, client)
    r = await client.post(
        _url(doc_id, "ask"), json={"question": "Tell me about the furnace", "mode": "tutor"}
    )
    assert r.status_code == 200
    assert '"mode":"tutor"' in r.text.replace(" ", "")
    bad = await client.post(_url(doc_id, "ask"), json={"question": "x", "mode": "cheat"})
    assert bad.status_code == 422


@pytest.mark.usefixtures("user_a", "user_b")
async def test_rls_on_notes_for_the_runtime_role(
    app: FastAPI,
    client: AsyncClient,
    client_b: AsyncClient,
    test_urls: tuple[str, str],
) -> None:
    doc_id = await _ingest(app, client)
    await client.post(_url(doc_id, "notes"), json={"body": "mine"})
    me_a = (await client.get("/api/v1/auth/me")).json()["id"]
    me_b = (await client_b.get("/api/v1/auth/me")).json()["id"]
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[0]))
    try:
        forced = await conn.fetchval(
            "select relforcerowsecurity from pg_class where relname = 'notes'"
        )
        assert forced is True
        counts = {}
        for who in (me_a, me_b):
            async with conn.transaction():
                await conn.execute("select set_config('app.current_user_id', $1, true)", who)
                counts[who] = await conn.fetchval("select count(*) from notes")
        assert counts[me_a] >= 1 and counts[me_b] == 0
    finally:
        await conn.close()
