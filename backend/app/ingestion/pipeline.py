"""Idempotent, resumable ingest pipeline.

Stages: parse → sections → chunk → context → embed → summaries → validate.

`job.payload["from_stage"]` re-runs one stage and everything after it, reusing stored output of
earlier stages (sections keep their full text, so chunking never needs the original file again).
`chunk`, `context` and `embed` are rebuilt together because a chunk row carries all three.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.ingestion.chunking import DraftChunk, chunk_sections
from app.ingestion.constants import EMBEDDING_DIMENSION, INGEST_STAGES, STAGE_VERSIONS
from app.ingestion.context import build_context_prefixes
from app.ingestion.parse_epub import ParsedBook, ParsedSection, parse_epub
from app.ingestion.quality import build_quality_report
from app.ingestion.summaries import build_summaries
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


def stages_from(from_stage: str) -> tuple[str, ...]:
    if from_stage not in INGEST_STAGES:
        raise IngestError("bad_stage")
    return INGEST_STAGES[INGEST_STAGES.index(from_stage) :]


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

    from_stage = str((job.payload or {}).get("from_stage") or "parse")
    run = set(stages_from(from_stage))

    doc.status = "processing"
    doc.error = None
    doc.updated_at = datetime.now(UTC)
    await session.flush()

    try:
        if settings.embedding_dim != EMBEDDING_DIMENSION:
            raise IngestError(
                f"EMBEDDING_DIM={settings.embedding_dim} must equal "
                f"column width {EMBEDDING_DIMENSION}"
            )
        versions = dict(doc.stage_versions or {})
        parse_stats: dict[str, int] = {}
        section_repo = SectionRepository(session, ctx)
        chunk_repo = ChunkRepository(session, ctx)

        # ---- parse + sections -------------------------------------------------------------
        if "parse" in run:
            await _set_stage(doc, "parse")
            raw = await _read_all(storage, doc.storage_key)
            book = await _parse(doc.format, raw)
            parse_stats = book.stats
            if book.title and book.title != "Untitled":
                doc.title = book.title[:200]
            versions["parse"] = STAGE_VERSIONS["parse"]
        if "sections" in run:
            await _set_stage(doc, "sections")
            sections = await _write_sections(session, ctx, doc.id, book)
            versions["sections"] = STAGE_VERSIONS["sections"]
        else:
            sections = await section_repo.list_for_document(doc.id)
            if not sections:
                raise IngestError("nothing_to_resume")
        if "parse" not in run:
            parse_stats = dict((doc.quality_report or {}).get("parse_stats") or {})

        # ---- chunk + context + embed ------------------------------------------------------
        if "chunk" in run or "context" in run or "embed" in run:
            await _set_stage(doc, "chunk")
            drafts = chunk_sections([_to_parsed(s) for s in sections])
            if not drafts:
                raise IngestError("No chunks produced")
            chunks = _build_chunks(sections, drafts)
            _set_section_ranges(sections, chunks)

            await _set_stage(doc, "context")
            ctx_llm = (
                build_llm(settings, session, ctx, document_id=doc.id, stage="context")
                if settings.context_prefix_mode == "llm"
                else None
            )
            await build_context_prefixes(
                ctx_llm, settings, book_title=doc.title, sections=sections, chunks=chunks
            )

            await _set_stage(doc, "embed")
            await _embed_chunks(session, ctx, settings, doc, chunks)
            chunks = await chunk_repo.replace_for_document(doc.id, chunks)
            for stage in ("chunk", "context", "embed"):
                versions[stage] = STAGE_VERSIONS[stage]
            # First ingest: progress at end of book (the reader lowers it; gate is opt-in).
            # Re-ingest must never reset the reader's progress, only clamp it to the new range.
            progress_repo = ProgressRepository(session, ctx)
            last_ordinal = max(c.ordinal for c in chunks)
            existing = await progress_repo.get(doc.id)
            await progress_repo.upsert(
                doc.id,
                last_ordinal if existing is None else min(existing.max_ordinal, last_ordinal),
            )
        else:
            chunks = await chunk_repo.list_for_document(doc.id)
            if not chunks:
                raise IngestError("nothing_to_resume")

        # ---- summaries --------------------------------------------------------------------
        if "summaries" in run:
            await _set_stage(doc, "summaries")
            sum_llm = build_llm(settings, session, ctx, document_id=doc.id, stage="summaries")
            summaries = await build_summaries(
                session, ctx, settings, sum_llm, doc, sections, chunks
            )
            versions["summaries"] = STAGE_VERSIONS["summaries"]
            summary_count = len(summaries)
        else:
            summary_count = 0

        # ---- validate ---------------------------------------------------------------------
        await _set_stage(doc, "validate")
        doc.quality_report = build_quality_report(sections, chunks, parse_stats)
        versions["validate"] = STAGE_VERSIONS["validate"]

        doc.stage_versions = versions
        doc.status = "ready"
        doc.ingest_stage = "validate"
        doc.error = None
        doc.updated_at = datetime.now(UTC)
        await session.flush()
        log.info(
            "ingest_ready",
            document_id=str(doc.id),
            from_stage=from_stage,
            section_count=len(sections),
            chunk_count=len(chunks),
            summary_count=summary_count,
            quality_score=doc.quality_report["score"],
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


async def _parse(fmt: str, raw: bytes) -> ParsedBook:
    if fmt == "epub":
        return parse_epub(raw)
    if fmt == "pdf":
        from app.ingestion.parse_pdf import parse_pdf

        return await parse_pdf(raw)
    raise IngestError("unsupported_format")


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
    rows: list[Section] = []
    stack: list[Section] = []  # ancestors of the section being added
    for i, sec in enumerate(book.sections):
        while stack and stack[-1].depth >= sec.depth:
            stack.pop()
        row = Section(
            id=uuid.uuid4(),
            parent_id=stack[-1].id if stack else None,
            ordinal=i,
            depth=sec.depth,
            title=sec.title[:500],
            spine_href=sec.spine_href[:1000],
            body=sec.text,
            page_start=sec.page_start,
            page_end=sec.page_end,
            page_map=sec.page_map,
        )
        rows.append(row)
        stack.append(row)
    return await SectionRepository(session, ctx).replace_for_document(document_id, rows)


def _to_parsed(s: Section) -> ParsedSection:
    return ParsedSection(
        title=s.title,
        spine_href=s.spine_href,
        text=s.body,
        depth=s.depth,
        page_map=s.page_map,
        page_start=s.page_start,
        page_end=s.page_end,
    )


def _build_chunks(sections: list[Section], drafts: list[DraftChunk]) -> list[Chunk]:
    return [
        Chunk(
            id=uuid.uuid4(),
            section_id=sections[d.section_index].id,
            ordinal=ordinal,
            body=d.text,
            context_prefix=sections[d.section_index].title,
            char_start=d.char_start,
            char_end=d.char_end,
            token_count=d.token_count,
            page_start=d.page_start,
            page_end=d.page_end,
        )
        for ordinal, d in enumerate(drafts)
    ]


def _set_section_ranges(sections: list[Section], chunks: list[Chunk]) -> None:
    by_section: dict[uuid.UUID, list[int]] = {}
    for c in chunks:
        by_section.setdefault(c.section_id, []).append(c.ordinal)
    for s in sections:
        ords = by_section.get(s.id)
        s.first_chunk_ordinal = min(ords) if ords else None
        s.last_chunk_ordinal = max(ords) if ords else None


async def _embed_chunks(
    session: AsyncSession,
    ctx: AuthContext,
    settings: Settings,
    doc: Document,
    chunks: list[Chunk],
) -> None:
    llm = build_llm(settings, session, ctx, document_id=doc.id, stage="embed")
    texts = [f"{c.context_prefix}\n\n{c.body}" if c.context_prefix else c.body for c in chunks]

    async def embed_all(items: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = 32  # modest batches for real providers
        for i in range(0, len(items), batch_size):
            batch = await llm.embed(
                model=settings.embedding_model,
                texts=items[i : i + batch_size],
                dimensions=settings.embedding_dim,
            )
            vectors.extend(batch.vectors)
        return vectors

    for chunk, vec in zip(chunks, await embed_all(texts), strict=True):
        chunk.embedding = vec
        chunk.embedding_model = settings.embedding_model
        chunk.embedding_dim = settings.embedding_dim
    if settings.store_plain_embeddings:
        plain = await embed_all([c.body for c in chunks])
        for chunk, vec in zip(chunks, plain, strict=True):
            chunk.embedding_plain = vec
