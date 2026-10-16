"""Read access to the summaries produced at ingestion."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.core.errors import NotFoundError
from app.repositories.content import SectionRepository
from app.repositories.documents import DocumentRepository
from app.repositories.summaries import SummaryRepository
from app.schemas.summaries import SectionSummaryOut, SummariesOut


async def get_summaries(
    session: AsyncSession, ctx: AuthContext, document_id: uuid.UUID
) -> SummariesOut:
    if await DocumentRepository(session, ctx).get(document_id) is None:
        raise NotFoundError("Document not found")
    rows = await SummaryRepository(session, ctx).list_for_document(document_id)
    sections = {
        s.id: s for s in await SectionRepository(session, ctx).list_for_document(document_id)
    }
    book = next((r.body for r in rows if r.kind == "book"), None)
    items = [
        SectionSummaryOut(
            section_id=sec.id, title=sec.title, ordinal=sec.ordinal, depth=sec.depth, body=r.body
        )
        for r in rows
        if r.kind == "section" and r.section_id is not None and (sec := sections.get(r.section_id))
    ]
    items.sort(key=lambda i: i.ordinal)
    return SummariesOut(book=book, sections=items)
