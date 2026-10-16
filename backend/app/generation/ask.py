"""Ask / generate: retrieve → prompt → stream. Callable without HTTP (evals)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import nh3
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import DomainError, NotFoundError
from app.core.logging import get_logger
from app.generation.citations import SourceRef, verify_citations
from app.llm.base import ChatMessage
from app.llm.factory import build_llm
from app.prompts import load_prompt
from app.repositories.content import SectionRepository
from app.repositories.documents import DocumentRepository
from app.retrieval.config import RetrievalConfig
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.retrieval.types import RetrievalResult, RetrievedChunk

log = get_logger("generation.ask")

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "qa.md"

# Allow a small Markdown-ish HTML subset after nh3; strip scripts/handlers.
_ALLOWED_TAGS = {
    "p",
    "br",
    "em",
    "strong",
    "b",
    "i",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "a",
}
_ALLOWED_ATTRS = {"a": {"href", "title"}}


class DocumentNotReadyError(DomainError):
    status = 409
    code = "document_not_ready"
    title = "Document not ready"


class AskError(DomainError):
    code = "ask_failed"
    title = "Ask failed"


EventName = Literal["status", "sources", "token", "citations", "done", "error"]


@dataclass(frozen=True, slots=True)
class AskEvent:
    event: EventName
    data: dict[str, Any]


def load_qa_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def sanitize_answer_html(text: str) -> str:
    """Strip unsafe markup from model output. Never log `text`."""
    return nh3.clean(text, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def _sources_from_chunks(chunks: list[RetrievedChunk]) -> list[SourceRef]:
    return [
        SourceRef(
            index=i,
            chunk_id=c.chunk_id,
            section_id=c.section_id,
            ordinal=c.ordinal,
            context_prefix=c.context_prefix,
        )
        for i, c in enumerate(chunks, start=1)
    ]


def build_messages(
    *, question: str, chunks: list[RetrievedChunk], mode: str = "answer"
) -> list[ChatMessage]:
    system = load_prompt("tutor") if mode == "tutor" else load_qa_system_prompt()
    parts: list[str] = ["Sources (cite with [n]):"]
    for i, c in enumerate(chunks, start=1):
        prefix = f"{c.context_prefix}\n" if c.context_prefix else ""
        parts.append(
            f'<source index="{i}" chunk_id="{c.chunk_id}" ordinal="{c.ordinal}">\n'
            f"<passage>\n{prefix}{c.text}\n</passage>\n</source>"
        )
    parts.append(f"<question>\n{question.strip()}\n</question>")
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content="\n\n".join(parts)),
    ]


class AskService:
    """Cited Q&A over the whole document. Yields SSE-oriented events; no book text in logs."""

    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        settings: Settings,
        *,
        config: RetrievalConfig | None = None,
    ) -> None:
        self._session = session
        self._ctx = ctx
        self._settings = settings
        self._config = config  # evals inject a config; the live path derives it from settings
        self.last_retrieval: RetrievalResult | None = None  # stage trace of the last ask

    async def ask_stream(
        self,
        *,
        document_id: uuid.UUID,
        question: str,
        limit: int = 8,
        mode: str = "answer",
    ) -> AsyncIterator[AskEvent]:
        q = question.strip()
        if not q:
            yield AskEvent("error", {"code": "empty_question", "detail": "Question is required"})
            return
        if len(q) > 4000:
            yield AskEvent("error", {"code": "question_too_long", "detail": "Question is too long"})
            return

        doc = await DocumentRepository(self._session, self._ctx).get(document_id)
        if doc is None:
            raise NotFoundError("Document not found")
        if doc.status != "ready":
            raise DocumentNotReadyError("Document is not ready for questions")

        yield AskEvent("status", {"stage": "retrieving"})
        orchestrator = RetrievalOrchestrator(
            self._session, self._ctx, self._settings, document_id=document_id
        )
        config = self._config or RetrievalConfig.from_settings(self._settings)
        config = config.model_copy(update={"final_k": limit})
        # Evals inject a config and get exactly that strategy; live asks are routed.
        result = await orchestrator.run(
            query=q, config=config, route=self._settings.routing_enabled and self._config is None
        )
        self.last_retrieval = result
        if result.route is not None:
            yield AskEvent("status", {"stage": "routed", "route": result.route})
        chunks = result.chunks
        sources = _sources_from_chunks(chunks)
        yield AskEvent(
            "sources",
            {
                "items": [
                    {
                        "index": s.index,
                        "chunk_id": str(s.chunk_id),
                        "section_id": str(s.section_id),
                        "ordinal": s.ordinal,
                        "context_prefix": s.context_prefix,
                    }
                    for s in sources
                ]
            },
        )

        yield AskEvent("status", {"stage": "generating", "mode": mode})
        messages = build_messages(question=q, chunks=chunks, mode=mode)
        llm = build_llm(
            self._settings, self._session, self._ctx, document_id=document_id, stage="generate"
        )
        pieces: list[str] = []
        try:
            async for piece in llm.stream(model=self._settings.llm_model, messages=messages):
                clean = sanitize_answer_html(piece)
                if not clean:
                    continue
                pieces.append(clean)
                yield AskEvent("token", {"text": clean})
        except Exception:
            log.warning("ask_stream_failed", document_id=str(document_id))
            yield AskEvent("error", {"code": "stream_failed", "detail": "Generation failed"})
            return

        answer = "".join(pieces)
        citations = verify_citations(answer, sources)
        yield AskEvent(
            "citations",
            {
                "items": [
                    {
                        "index": c.index,
                        "chunk_id": str(c.chunk_id),
                        "section_id": str(c.section_id),
                    }
                    for c in citations
                ]
            },
        )
        log.info(
            "ask_done",
            document_id=str(document_id),
            source_count=len(sources),
            citation_count=len(citations),
            answer_chars=len(answer),
        )
        yield AskEvent("done", {"ok": True})


async def list_sections(
    session: AsyncSession,
    ctx: AuthContext,
    document_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Sections of the document with their full text, in reading order."""
    if await DocumentRepository(session, ctx).get(document_id) is None:
        raise NotFoundError("Document not found")
    return [
        {
            "id": s.id,
            "parent_id": s.parent_id,
            "ordinal": s.ordinal,
            "depth": s.depth,
            "title": s.title,
            "body": s.body,
        }
        for s in await SectionRepository(session, ctx).list_for_document(document_id)
    ]
