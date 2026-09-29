"""End-to-end spoiler enforcement: every route that can return book-derived content is exercised
at several reading positions and must never contain text from beyond the reader's progress.

A completeness test fails when a new document route is added without being classified here.
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.section import Section
from tests.test_hierarchical import _ingest, _sections, _uid, _wipe_jobs  # noqa: F401

# Words found only in a chapter's *body* (titles are visible in the table of contents).
CHAPTER_WORDS = [
    ("blossom", "apples", "pruning", "beehives"),  # ch2 (section index 1)
    ("furnace", "ironwork", "molten", "anvil", "hammer"),  # ch3
    ("expedition", "crevasse", "sledges"),  # ch4
]

# Routes returning book-derived text: exercised below. Others carry no book text.
CONTENT_ROUTES = {
    ("GET", "/api/v1/documents/{document_id}/sections"),
    ("GET", "/api/v1/documents/{document_id}/concepts"),
    ("GET", "/api/v1/documents/{document_id}/concepts/{concept_id}/trajectory"),
    ("POST", "/api/v1/documents/{document_id}/ask"),
    ("GET", "/api/v1/documents/{document_id}/notes"),
    ("POST", "/api/v1/documents/{document_id}/study/generate"),
    ("GET", "/api/v1/documents/{document_id}/flashcards"),
    ("GET", "/api/v1/documents/{document_id}/quiz"),
    ("POST", "/api/v1/documents/{document_id}/quiz/{question_id}/answer"),  # explanation
}
NO_BOOK_TEXT = {
    ("GET", "/api/v1/documents/{document_id}"),
    ("GET", "/api/v1/documents/{document_id}/status"),
    ("GET", "/api/v1/documents/{document_id}/quality"),
    ("POST", "/api/v1/documents/{document_id}/reingest"),
    ("PUT", "/api/v1/documents/{document_id}/progress"),
    ("DELETE", "/api/v1/documents/{document_id}"),
    ("POST", "/api/v1/documents/{document_id}/notes"),  # echoes the reader's own text
    ("PATCH", "/api/v1/documents/{document_id}/notes/{note_id}"),
    ("DELETE", "/api/v1/documents/{document_id}/notes/{note_id}"),
    ("POST", "/api/v1/documents/{document_id}/flashcards/{card_id}/review"),  # card fields only
}


def test_every_document_route_is_classified() -> None:
    from app.main import app

    found = {
        (m.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/api/v1/documents/")
        for m in ops
    }
    assert found == CONTENT_ROUTES | NO_BOOK_TEXT, (
        "classify new document routes as CONTENT_ROUTES (and exercise them) or NO_BOOK_TEXT"
    )


def _forbidden(gate: int, sections: list[Section]) -> list[str]:
    """Body words of every chapter that starts after `gate`."""
    words: list[str] = []
    for idx, group in enumerate(CHAPTER_WORDS, start=1):
        first = sections[idx].first_chunk_ordinal
        if first is not None and first > gate:
            words.extend(group)
    return words


@pytest.mark.usefixtures("user_a")
async def test_no_route_returns_text_from_beyond_the_reading_position(
    app: FastAPI, client: AsyncClient
) -> None:
    doc_id = await _ingest(app, client)
    sections = await _sections(app, await _uid(client), doc_id)
    base = f"/api/v1/documents/{doc_id}"
    gates = [
        sections[0].last_chunk_ordinal,
        sections[1].last_chunk_ordinal,
        sections[2].first_chunk_ordinal,
    ]
    assert all(g is not None for g in gates)

    for gate in gates:
        assert gate is not None
        await client.put(f"{base}/progress", json={"max_ordinal": gate})
        bad = _forbidden(gate, sections)
        assert bad  # each position has unread chapters to leak from
        seen: list[tuple[str, str]] = []

        def record(label: str, text: str, seen: list[tuple[str, str]] = seen) -> None:
            seen.append((label, text.lower()))

        r = await client.get(f"{base}/sections")
        record("sections", " ".join(s["body"] or "" for s in r.json()["items"]))

        cmap = (await client.get(f"{base}/concepts")).json()
        record("concepts", str(cmap))
        for row in cmap["concepts"]:
            t = await client.get(f"{base}/concepts/{row['id']}/trajectory")
            assert t.status_code == 200
            record("trajectory", t.text)

        for mode in ("answer", "tutor"):
            for q in ("What happens at the furnace?", "Tell me about the glacier expedition"):
                a = await client.post(f"{base}/ask", json={"question": q, "mode": mode})
                assert a.status_code == 200
                record(f"ask-{mode}", a.text)

        for term in (None, "furnace", "glacier crevasse"):
            n = await client.get(f"{base}/notes", params={"q": term} if term else {})
            record("notes", n.text)

        for kind in ("flashcards", "quiz"):
            g = await client.post(f"{base}/study/generate", json={"kind": kind, "count": 10})
            assert g.status_code == 200
            record(f"generate-{kind}", g.text)
        record("flashcards", (await client.get(f"{base}/flashcards")).text)
        quiz = await client.get(f"{base}/quiz")
        record("quiz", quiz.text)
        for item in quiz.json()["items"]:
            ans = await client.post(f"{base}/quiz/{item['id']}/answer", json={"choice": 0})
            assert ans.status_code == 200
            record("quiz-answer", ans.text)

        for label, text in seen:
            for word in bad:
                assert not re.search(rf"\b{word}\b", text), f"{label} leaked '{word}' at {gate}"

    # Something was actually produced (the test is not vacuous).
    assert (await client.get(f"{base}/flashcards")).json()["items"]


@pytest.mark.usefixtures("user_a")
async def test_forbidden_word_sets_are_real(app: FastAPI, client: AsyncClient) -> None:
    """Guard the guard: at full progress those words do appear in returned content."""
    doc_id = await _ingest(app, client)
    r = await client.get(f"/api/v1/documents/{doc_id}/sections")
    text = " ".join(s["body"] or "" for s in r.json()["items"]).lower()
    for group in CHAPTER_WORDS:
        assert all(w in text for w in group)
    assert uuid.UUID(str(doc_id))
