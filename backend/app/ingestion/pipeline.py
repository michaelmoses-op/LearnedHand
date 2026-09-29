"""Idempotent ingest pipeline: parse → sections → chunk → context → embed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.ingestion.chunking import DraftChunk, chunk_sections
from app.ingestion.constants import EMBEDDING_DIMENSION, INGEST_STAGES
from app.ingestion.parse_epub import ParsedBook, parse_epub
from app.llm.factory import build_llm
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.job import Job
from app.models.section import Section
from app.repositories.content import ChunkRepository, ProgressRepository, SectionRepository
from app.repositories.documents import DocumentRepository
from app.storage.base import Storage

log = get_logger("ingestion.pipeline")


class IngestError(DomainError):
    code = "ingest_failed"
    title = "Document ingestion failed"


async def run_ingest(
    session: AsyncSession,
    ctx: AuthContext,
    job: Job,
    settings: Settings,
    storage: Storage,
) -> None:
    if job.document_id is None:
        raise IngestError("ingest job missing document_id")
    docs = DocumentRepository(session, ctx)
    doc = await docs.get(job.document_id)
    if doc is None:
        raise IngestError("document_not_found")

    doc.status = "processing"
    doc.error = None
    doc.updated_at = datetime.now(UTC)
    await session.flush()

    try:
        if doc.format != "epub":
            raise IngestError("Only EPUB ingestion is supported in Phase 2")
        if settings.embedding_dim != EMBEDDING_DIMENSION:
            raise IngestError(
                f"EMBEDDING_DIM={settings.embedding_dim} must equal "
                f"column width {EMBEDDING_DIMENSION}"
            )

        await _set_stage(doc, "parse")
        raw = await _read_all(storage, doc.storage_key)
        book = parse_epub(raw)
        if book.title and book.title != "Untitled":
            doc.title = book.title[:200]

        await _set_stage(doc, "sections")
        sections = await _write_sections(session, ctx, doc.id, book)

        await _set_stage(doc, "chunk")
        drafts = chunk_sections(book.sections)
        if not drafts:
            raise IngestError("No chunks produced")

        await _set_stage(doc, "context")
        chunks = _build_chunks(doc.id, sections, drafts)

        await _set_stage(doc, "embed")
        llm = build_llm(settings, session, ctx, document_id=doc.id, stage="embed")
        texts = [f"{c.context_prefix}\n\n{c.body}" if c.context_prefix else c.body for c in chunks]
        # Batch embed (fake handles any size; keep batches modest for future real providers).
        vectors: list[list[float]] = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = await llm.embed(
                model=settings.embedding_model,
                texts=texts[i : i + batch_size],
                dimensions=settings.embedding_dim,
            )
            vectors.extend(batch.vectors)
        for chunk, vec in zip(chunks, vectors, strict=True):
            chunk.embedding = vec
            chunk.embedding_model = settings.embedding_model
            chunk.embedding_dim = settings.embedding_dim

        await ChunkRepository(session, ctx).replace_for_document(doc.id, chunks)
        max_ord = max(c.ordinal for c in chunks)
        # Phase 2 default: progress at end of book (spoiler gate opt-in later).
        await ProgressRepository(session, ctx).upsert(doc.id, max_ord)

        doc.status = "ready"
        doc.ingest_stage = "embed"
        doc.error = None
        doc.updated_at = datetime.now(UTC)
        await session.flush()
        log.info(
            "ingest_ready",
            document_id=str(doc.id),
            section_count=len(sections),
            chunk_count=len(chunks),
            max_ordinal=max_ord,
        )
    except Exception as exc:
        doc.status = "failed"
        # Safe summary only — never include passage text.
        doc.error = f"{type(exc).__name__}: ingest_failed"[:500]
        doc.updated_at = datetime.now(UTC)
        await session.flush()
        log.warning(
            "ingest_failed",
            document_id=str(doc.id),
            error_type=type(exc).__name__,
            stage=doc.ingest_stage,
        )
        raise


async def _set_stage(doc: Document, stage: str) -> None:
    if stage not in INGEST_STAGES:
        raise IngestError("bad_stage")
    doc.ingest_stage = stage
    doc.updated_at = datetime.now(UTC)


async def _read_all(storage: Storage, key: str) -> bytes:
    parts: list[bytes] = []
    async for chunk in storage.open(key):
        parts.append(chunk)
    return b"".join(parts)


async def _write_sections(
    session: AsyncSession, ctx: AuthContext, document_id: uuid.UUID, book: ParsedBook
) -> list[Section]:
    rows = [
        Section(
            ordinal=i,
            depth=sec.depth,
            title=sec.title[:500],
            spine_href=sec.spine_href[:1000],
            body=sec.text,
        )
        for i, sec in enumerate(book.sections)
    ]
    return await SectionRepository(session, ctx).replace_for_document(document_id, rows)


def _build_chunks(
    document_id: uuid.UUID,
    sections: list[Section],
    drafts: list[DraftChunk],
) -> list[Chunk]:
    by_index = {i: s for i, s in enumerate(sections)}
    chunks: list[Chunk] = []
    for ordinal, draft in enumerate(drafts):
        section = by_index[draft.section_index]
        prefix = section.title
        chunks.append(
            Chunk(
                section_id=section.id,
                ordinal=ordinal,
                body=draft.text,
                context_prefix=prefix,
                char_start=draft.char_start,
                char_end=draft.char_end,
                token_count=draft.token_count,
            )
        )
    _ = document_id  # stamped by repository.replace_for_document
    return chunks
