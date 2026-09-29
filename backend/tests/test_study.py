"""Notes/highlights, flashcards, quizzes and tutor mode (with progress gating)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.generation.ask import build_messages
from app.retrieval.types import RetrievedChunk
from app.services.study import CardBatch, CardDraft, next_state
from tests.conftest import _asyncpg_dsn
from tests.test_hierarchical import _ingest, _sections, _uid, _wipe_jobs  # noqa: F401

# Words that occur only in the Foundry / Glacier chapters' bodies.
LATE_WORDS = ("furnace", "ironwork", "molten", "anvil", "hammer", "crevasse", "sledges")


async def _gate_after_chapter_two(app: FastAPI, client: AsyncClient) -> tuple[uuid.UUID, int]:
    doc_id = await _ingest(app, client)
    sections = await _sections(app, await _uid(client), doc_id)
    gate = sections[1].last_chunk_ordinal
    assert gate is not None
    r = await client.put(f"/api/v1/documents/{doc_id}/progress", json={"max_ordinal": gate})
    assert r.status_code == 200
    return doc_id, gate


def _url(doc_id: uuid.UUID, tail: str) -> str:
    return f"/api/v1/documents/{doc_id}/{tail}"


def test_scheduler_again_resets_and_good_grows_intervals() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    ease, iv, reps, lapses, due = next_state(
        ease=2.5, interval_days=6, reps=3, lapses=0, rating="again", now=now
    )
    assert (iv, reps, lapses) == (0, 0, 1) and ease < 2.5 and (due - now).total_seconds() == 600
    steps = []
    state = (2.5, 0, 0, 0)
    for _ in range(4):
        e, iv, r, la, due = next_state(
            ease=state[0],
            interval_days=state[1],
            reps=state[2],
            lapses=state[3],
            rating="good",
            now=now,
        )
        state = (e, iv, r, la)
        steps.append(iv)
    assert steps[:2] == [1, 3] and steps[2] > 3 and steps == sorted(steps)
    hard = next_state(ease=1.35, interval_days=10, reps=5, lapses=0, rating="hard", now=now)
    assert hard[0] == 1.3  # ease never drops below the floor
    easy = next_state(ease=2.5, interval_days=10, reps=5, lapses=0, rating="easy", now=now)
    assert easy[0] > 2.5


@pytest.mark.usefixtures("user_a")
async def test_notes_are_gated_searchable_and_editable(app: FastAPI, client: AsyncClient) -> None:
    doc_id = await _ingest(app, client)
    notes = _url(doc_id, "notes")
    # Ingest leaves progress at the end of the book, so the default anchor is the last chunk.
    first = await client.post(notes, json={"body": "at the end"})
    assert first.status_code == 201 and first.json()["anchor_ordinal"] > 4
    assert (await client.delete(f"{notes}/{first.json()['id']}")).status_code == 204

    await client.put(_url(doc_id, "progress"), json={"max_ordinal": 4})
    n1 = await client.post(notes, json={"body": "The lighthouse keeper is lonely"})
    assert n1.status_code == 201 and n1.json()["anchor_ordinal"] == 4  # defaults to progress
    hl = await client.post(
        notes, json={"kind": "highlight", "quote": "orchard blossom apples", "anchor_ordinal": 2}
    )
    assert hl.status_code == 201 and hl.json()["kind"] == "highlight"

    ahead = await client.post(notes, json={"body": "spoiler", "anchor_ordinal": 5})
    assert ahead.status_code == 422 and ahead.json()["code"] == "beyond_progress"
    assert (await client.post(notes, json={"kind": "highlight"})).status_code == 422
    assert (await client.post(notes, json={"body": "  "})).status_code == 422

    found = (await client.get(notes, params={"q": "lonely lighthouse"})).json()["items"]
    assert [i["id"] for i in found] == [n1.json()["id"]]
    assert [
        i["kind"] for i in (await client.get(notes, params={"kind": "highlight"})).json()["items"]
    ] == ["highlight"]
    assert (await client.get(notes, params={"q": "'\") OR ((("})).status_code == 200  # safe parsing
    listed = (await client.get(notes)).json()["items"]
    assert [i["anchor_ordinal"] for i in listed] == [2, 4]  # book order

    upd = await client.patch(f"{notes}/{n1.json()['id']}", json={"body": "keeper feels alone"})
    assert upd.status_code == 200 and upd.json()["body"] == "keeper feels alone"

    # Lowering progress hides notes anchored later — and makes them unreachable by id.
    await client.put(_url(doc_id, "progress"), json={"max_ordinal": 2})
    assert [i["id"] for i in (await client.get(notes)).json()["items"]] == [hl.json()["id"]]
    assert (await client.patch(f"{notes}/{n1.json()['id']}", json={"body": "x"})).status_code == 404
    assert (await client.delete(f"{notes}/{n1.json()['id']}")).status_code == 404

    assert (await client.delete(f"{notes}/{hl.json()['id']}")).status_code == 204
    assert (await client.get(notes)).json()["items"] == []


@pytest.mark.usefixtures("user_a")
async def test_flashcards_generate_only_from_read_material_and_schedule(
    app: FastAPI, client: AsyncClient
) -> None:
    doc_id, gate = await _gate_after_chapter_two(app, client)
    gen = await client.post(_url(doc_id, "study/generate"), json={"kind": "flashcards", "count": 6})
    assert gen.status_code == 200, gen.text
    assert gen.json()["created"] >= 1
    cards = (await client.get(_url(doc_id, "flashcards"))).json()["items"]
    assert cards and all(c["source_ordinal"] <= gate for c in cards)
    dump = str(cards).lower()
    assert not any(w in dump for w in LATE_WORDS)

    again = await client.post(
        _url(doc_id, "study/generate"), json={"kind": "flashcards", "count": 6}
    )
    assert again.json()["created"] == 0 and again.json()["skipped"] >= 1  # de-duplicated

    due = (await client.get(_url(doc_id, "flashcards"), params={"due": "true"})).json()["items"]
    assert len(due) == len(cards)
    first = cards[0]["id"]
    rev = await client.post(_url(doc_id, f"flashcards/{first}/review"), json={"rating": "good"})
    assert rev.status_code == 200 and rev.json()["reps"] == 1 and rev.json()["interval_days"] == 1
    due_after = (await client.get(_url(doc_id, "flashcards"), params={"due": "true"})).json()[
        "items"
    ]
    assert first not in [c["id"] for c in due_after]

    # Progress lowered below a card's source: the card disappears and cannot be reviewed.
    await client.put(_url(doc_id, "progress"), json={"max_ordinal": 0})
    left = (await client.get(_url(doc_id, "flashcards"))).json()["items"]
    assert all(c["source_ordinal"] <= 0 for c in left)
    hidden = next(c["id"] for c in cards if c["source_ordinal"] > 0)
    r = await client.post(_url(doc_id, f"flashcards/{hidden}/review"), json={"rating": "good"})
    assert r.status_code == 404


@pytest.mark.usefixtures("user_a")
async def test_quiz_generation_answering_and_no_answer_leak(
    app: FastAPI, client: AsyncClient
) -> None:
    doc_id, gate = await _gate_after_chapter_two(app, client)
    gen = await client.post(_url(doc_id, "study/generate"), json={"kind": "quiz", "count": 4})
    assert gen.status_code == 200 and gen.json()["created"] >= 1
    items = (await client.get(_url(doc_id, "quiz"))).json()["items"]
    assert items and all(q["source_ordinal"] <= gate for q in items)
    assert all("answer_index" not in q and "explanation" not in q for q in items)
    assert not any(w in str(items).lower() for w in LATE_WORDS)

    q = next(x for x in items if x["source_ordinal"] > 0)
    url = _url(doc_id, f"quiz/{q['id']}/answer")
    probe = (await client.post(url, json={"choice": 0})).json()
    right = probe["answer_index"]
    wrong = next(i for i in range(len(q["choices"])) if i != right)
    assert (await client.post(url, json={"choice": right})).json()["correct"] is True
    assert (await client.post(url, json={"choice": wrong})).json()["correct"] is False
    assert (await client.post(url, json={"choice": 9})).json()["code"] == "invalid_input"

    await client.put(_url(doc_id, "progress"), json={"max_ordinal": 0})
    assert (await client.post(url, json={"choice": 0})).status_code == 404


@pytest.mark.usefixtures("user_a")
async def test_generation_scope_rules(app: FastAPI, client: AsyncClient) -> None:
    doc_id, _gate = await _gate_after_chapter_two(app, client)
    sections = await _sections(app, await _uid(client), doc_id)
    body = {"kind": "flashcards", "count": 3}
    # Section the reader has not reached: 404, same as an unknown section.
    for sid in (sections[3].id, uuid.uuid4()):
        r = await client.post(_url(doc_id, "study/generate"), json={**body, "section_id": str(sid)})
        assert r.status_code == 404
    ok = await client.post(
        _url(doc_id, "study/generate"), json={**body, "section_id": str(sections[0].id)}
    )
    assert ok.status_code == 200 and ok.json()["created"] >= 1
    # No progress row => nothing to study.
    other = await client.post(
        "/api/v1/documents", content=b"PK\x03\x04" + b"x" * 40, headers={"X-Filename": "n.epub"}
    )
    r = await client.post(_url(other.json()["id"], "study/generate"), json=body)
    assert r.status_code in (409,)  # not ready


@pytest.mark.usefixtures("user_a")
async def test_hostile_model_output_cannot_smuggle_unread_ordinals(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_id, gate = await _gate_after_chapter_two(app, client)

    async def fake(*_a: Any, **_k: Any) -> CardBatch:
        return CardBatch(
            cards=[
                CardDraft(front="Who is at the harbor?", back="The keeper.", source_ordinal=0),
                CardDraft(
                    front="What burns in the furnace?", back="Iron.", source_ordinal=gate + 3
                ),
            ]
        )

    monkeypatch.setattr("app.services.study.complete_structured", fake)
    out = (await client.post(_url(doc_id, "study/generate"), json={"kind": "flashcards"})).json()
    assert (out["created"], out["skipped"]) == (1, 1)
    fronts = [c["front"] for c in (await client.get(_url(doc_id, "flashcards"))).json()["items"]]
    assert fronts == ["Who is at the harbor?"]


@pytest.mark.usefixtures("user_a")
async def test_tutor_mode_uses_socratic_prompt_and_same_gate(
    app: FastAPI, client: AsyncClient
) -> None:
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

    doc_id, gate = await _gate_after_chapter_two(app, client)
    r = await client.post(
        _url(doc_id, "ask"), json={"question": "Tell me about the furnace", "mode": "tutor"}
    )
    assert r.status_code == 200
    assert '"mode":"tutor"' in r.text.replace(" ", "")
    assert not any(w in r.text.lower() for w in LATE_WORDS)
    bad = await client.post(_url(doc_id, "ask"), json={"question": "x", "mode": "cheat"})
    assert bad.status_code == 422


@pytest.mark.usefixtures("user_a", "user_b")
async def test_rls_on_study_tables_for_the_runtime_role(
    app: FastAPI,
    client: AsyncClient,
    client_b: AsyncClient,
    test_urls: tuple[str, str],
) -> None:
    doc_id, _ = await _gate_after_chapter_two(app, client)
    await client.post(_url(doc_id, "notes"), json={"body": "mine"})
    await client.post(_url(doc_id, "study/generate"), json={"kind": "flashcards"})
    await client.post(_url(doc_id, "study/generate"), json={"kind": "quiz"})
    me_a = (await client.get("/api/v1/auth/me")).json()["id"]
    me_b = (await client_b.get("/api/v1/auth/me")).json()["id"]
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[0]))
    try:
        for table in ("notes", "flashcards", "quiz_questions"):
            forced = await conn.fetchval(
                "select relforcerowsecurity from pg_class where relname = $1", table
            )
            assert forced is True
            counts = {}
            for who in (me_a, me_b):
                async with conn.transaction():
                    await conn.execute("select set_config('app.current_user_id', $1, true)", who)
                    counts[who] = await conn.fetchval(f"select count(*) from {table}")  # noqa: S608
            assert counts[me_a] >= 1 and counts[me_b] == 0
    finally:
        await conn.close()
