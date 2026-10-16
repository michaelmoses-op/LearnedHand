"""Query routing, concept scoping and the agentic gap-check loop."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.llm.errors import LLMError
from app.llm.factory import build_llm
from app.models.chunk import Chunk
from app.retrieval.config import RetrievalConfig
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.retrieval.routing import Classification, classify_question, strategy_for
from tests.test_hierarchical import _ingest, _sections, _uid, _wipe_jobs  # noqa: F401


async def _orch_run(
    app: FastAPI,
    settings: Settings,
    user: uuid.UUID,
    doc_id: uuid.UUID,
    query: str,
    *,
    route: bool,
    cfg: RetrievalConfig | None = None,
) -> tuple[Any, list[Chunk]]:
    async with app.state.sessionmaker() as s:
        await set_rls_user(s, user)
        orch = RetrievalOrchestrator(s, AuthContext(user), settings, document_id=doc_id)
        result = await orch.run(query=query, config=cfg, route=route)
        rows = (
            await s.execute(select(Chunk).where(Chunk.id.in_([c.chunk_id for c in result.chunks])))
        ).scalars()
        by_id = {c.id: c for c in rows}
    return result, [by_id[c.chunk_id] for c in result.chunks]


@pytest.mark.usefixtures("user_a")
async def test_fake_classifier_labels(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    async with app.state.sessionmaker() as s:
        await set_rls_user(s, user)
        llm = build_llm(settings, s, AuthContext(user), document_id=doc_id, stage="route")
        got = {
            q: await classify_question(llm, settings, q)
            for q in (
                "Who tends the lighthouse?",
                "What is the main argument of the book?",
                "How does the concept of foundry develop?",
            )
        }
    assert [c.label for c in got.values()] == ["factual", "thematic", "concept"]
    assert list(got.values())[2].concept == "foundry"


@pytest.mark.usefixtures("user_a")
async def test_classifier_failure_falls_back_to_factual(
    app: FastAPI, client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_a: Any, **_k: Any) -> Any:
        raise LLMError("nope")

    monkeypatch.setattr("app.retrieval.routing.complete_structured", boom)
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    async with app.state.sessionmaker() as s:
        await set_rls_user(s, user)
        llm = build_llm(settings, s, AuthContext(user), document_id=doc_id, stage="route")
        assert await classify_question(llm, settings, "anything") == Classification()


def test_strategy_table() -> None:
    base = RetrievalConfig(name="b", hierarchical=True, broad_k=2)
    assert strategy_for(base, "factual").hierarchical is False
    thematic = strategy_for(base.model_copy(update={"hierarchical": False}), "thematic")
    assert thematic.hierarchical is True and thematic.broad_k >= 5
    assert strategy_for(base, "other") == base


@pytest.mark.usefixtures("user_a")
async def test_concept_route_scopes_to_the_concept_sections(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    sections = await _sections(app, user, doc_id)
    foundry = sections[2]
    q = "How does the concept of foundry develop?"

    result, chunks = await _orch_run(app, settings, user, doc_id, q, route=True)
    assert result.route == "concept"
    assert chunks and {c.section_id for c in chunks} == {foundry.id}


@pytest.mark.usefixtures("user_a")
async def test_agentic_loop_iterates_within_cap(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    doc_id = await _ingest(app, client)
    user = await _uid(client)
    # The question mixes topics from chapters that one small first pass cannot all cover.
    q = "orchard blossom apples glacier crevasse expedition sledges furnace anvil lighthouse"

    base = RetrievalConfig(name="a", mode="hybrid", final_k=1)
    single, _ = await _orch_run(app, settings, user, doc_id, q, route=False, cfg=base)
    assert single.iterations == 1

    agentic = base.model_copy(update={"max_iterations": 3})
    result, chunks = await _orch_run(app, settings, user, doc_id, q, route=False, cfg=agentic)
    assert 2 <= result.iterations <= 3
    assert chunks
    assert len(chunks) <= agentic.final_k * 2
    assert len({c.id for c in chunks}) == len(chunks)  # merged without duplicates
    names = [s.name for s in result.stages]
    assert "gap_check@1" in names and "final" in names and "final@1" in names
    notes = " ".join(s.note or "" for s in result.stages if s.name.startswith("gap_check"))
    assert "glacier" not in notes  # traces carry decisions, never text

    # A question fully covered by the first pass stops immediately.
    covered, _ = await _orch_run(
        app,
        settings,
        user,
        doc_id,
        "orchard blossom apples",
        route=False,
        cfg=agentic,
    )
    assert covered.iterations == 1


@pytest.mark.usefixtures("user_a")
async def test_live_ask_emits_route_status(app: FastAPI, client: AsyncClient) -> None:
    doc_id = await _ingest(app, client)
    r = await client.post(
        f"/api/v1/documents/{doc_id}/ask", json={"question": "What is the main argument overall?"}
    )
    assert r.status_code == 200
    assert '"route": "thematic"' in r.text or '"route":"thematic"' in r.text
