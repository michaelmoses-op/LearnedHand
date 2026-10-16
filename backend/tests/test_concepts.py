"""Concept extraction, concept map and trajectory (with spoiler gating)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.deps import AuthContext, set_rls_user
from app.ingestion.concepts import concept_key
from app.repositories.concepts import ConceptRepository
from tests.test_hierarchical import _ingest, _sections, _uid, _wipe_jobs  # noqa: F401


def test_concept_key_merges_variants() -> None:
    assert concept_key("The Harbor") == concept_key("harbors") == "harbor"
    assert concept_key("Self-Reference!") == "self reference"
    assert concept_key("class") == "class"  # 'ss' endings are not plurals


@pytest.mark.usefixtures("user_a")
async def test_extraction_writes_concepts_with_located_mentions(
    app: FastAPI, client: AsyncClient
) -> None:
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    sections = await _sections(app, user, doc_id)
    async with app.state.sessionmaker() as s:
        await set_rls_user(s, user)
        repo = ConceptRepository(s, AuthContext(user))
        stats = await repo.list_concepts(doc_id)
        mentions = await repo.mentions(doc_id)
    names = {st.concept.name for st in stats}
    assert {"lighthouse", "glacier"} <= names
    by_section = {sec.id: sec for sec in sections}
    for m in mentions:
        sec = by_section[m.section_id]
        assert sec.first_chunk_ordinal is not None and sec.last_chunk_ordinal is not None
        assert (
            sec.first_chunk_ordinal <= m.first_ordinal <= m.last_ordinal <= sec.last_chunk_ordinal
        )
        assert m.section_last_ordinal == sec.last_chunk_ordinal
        assert m.mention_chunks >= 1  # the fake extracts words that really occur
    first = {st.concept.name: st.concept.first_ordinal for st in stats}
    assert first["lighthouse"] < first["glacier"]  # book order


@pytest.mark.usefixtures("user_a")
async def test_concept_map_and_trajectory_cover_the_whole_book(
    app: FastAPI, client: AsyncClient
) -> None:
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    sections = await _sections(app, user, doc_id)

    r = await client.get(f"/api/v1/documents/{doc_id}/concepts", params={"limit": 200})
    assert r.status_code == 200
    body = r.json()
    assert [s["id"] for s in body["sections"]] == [str(s.id) for s in sections]
    names = {c["name"] for c in body["concepts"]}
    assert {"lighthouse", "orchard", "furnace", "glacier"} <= names
    for row in body["concepts"]:
        assert row["cells"] and all(0 < c["intensity"] <= 1 for c in row["cells"])

    foundry = next(c for c in body["concepts"] if c["name"] == "foundry")
    tr = (
        await client.get(f"/api/v1/documents/{doc_id}/concepts/{foundry['id']}/trajectory")
    ).json()
    assert [p["section_title"] for p in tr["points"]] == ["Foundry"]
    assert tr["points"][0]["note"] == "This section discusses foundry."
    ords = [p["section_ordinal"] for p in tr["points"]]
    assert ords == sorted(ords)

    missing = await client.get(f"/api/v1/documents/{doc_id}/concepts/{uuid.uuid4()}/trajectory")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


@pytest.mark.usefixtures("user_a")
async def test_concept_map_limit_applies(app: FastAPI, client: AsyncClient) -> None:
    doc_id = await _ingest(app, client)
    r = await client.get(f"/api/v1/documents/{doc_id}/concepts", params={"limit": 3})
    assert len(r.json()["concepts"]) == 3
    bad = await client.get(f"/api/v1/documents/{doc_id}/concepts", params={"limit": 0})
    assert bad.status_code == 422
    missing = await client.get(f"/api/v1/documents/{uuid.uuid4()}/concepts")
    assert missing.status_code == 404
