"""Concept map and trajectories, filtered to the reader's progress."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.core.errors import NotFoundError
from app.repositories.concepts import ConceptRepository
from app.repositories.content import ProgressRepository, SectionRepository
from app.repositories.documents import DocumentRepository
from app.schemas.concepts import (
    ConceptCellOut,
    ConceptMapOut,
    ConceptRowOut,
    SectionAxisOut,
    TrajectoryOut,
    TrajectoryPointOut,
)


class ConceptService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def _progress(self, document_id: uuid.UUID) -> int:
        if await DocumentRepository(self.session, self.ctx).get(document_id) is None:
            raise NotFoundError("Document not found")
        row = await ProgressRepository(self.session, self.ctx).get(document_id)
        return row.max_ordinal if row else -1  # no progress row ⇒ nothing readable

    async def concept_map(self, document_id: uuid.UUID, limit: int) -> ConceptMapOut:
        progress = await self._progress(document_id)
        if progress < 0:
            return ConceptMapOut(progress=None, sections=[], concepts=[])
        sections = [
            s
            for s in await SectionRepository(self.session, self.ctx).list_for_document(document_id)
            if s.first_chunk_ordinal is not None
            and s.last_chunk_ordinal is not None
            and s.first_chunk_ordinal <= progress
        ]
        size = {
            s.id: (s.last_chunk_ordinal or 0) - (s.first_chunk_ordinal or 0) + 1 for s in sections
        }
        repo = ConceptRepository(self.session, self.ctx)
        stats = await repo.list_visible(document_id, progress)
        stats = sorted(stats, key=lambda st: (-st.chunks, -st.sections, st.concept.name))[:limit]
        by_concept: dict[uuid.UUID, list[ConceptCellOut]] = defaultdict(list)
        for m in await repo.mentions_visible(document_id, progress):
            if m.section_id in size:
                by_concept[m.concept_id].append(
                    ConceptCellOut(
                        section_id=m.section_id,
                        chunks=m.mention_chunks,
                        intensity=min(1.0, m.mention_chunks / size[m.section_id]),
                    )
                )
        return ConceptMapOut(
            progress=progress,
            sections=[
                SectionAxisOut(
                    id=s.id,
                    title=s.title,
                    ordinal=s.ordinal,
                    chunks=size[s.id],
                    fully_read=(s.last_chunk_ordinal or 0) <= progress,
                )
                for s in sections
            ],
            concepts=[
                ConceptRowOut(
                    id=st.concept.id,
                    name=st.concept.name,
                    sections=st.sections,
                    chunks=st.chunks,
                    cells=by_concept.get(st.concept.id, []),
                )
                for st in stats
            ],
        )

    async def trajectory(self, document_id: uuid.UUID, concept_id: uuid.UUID) -> TrajectoryOut:
        progress = await self._progress(document_id)
        repo = ConceptRepository(self.session, self.ctx)
        concept = await repo.get_visible(document_id, concept_id, progress)
        if concept is None:  # unknown, other user's, or not yet reached: all indistinguishable
            raise NotFoundError("Concept not found")
        titles = {
            s.id: s
            for s in await SectionRepository(self.session, self.ctx).list_for_document(document_id)
        }
        points: list[TrajectoryPointOut] = []
        for m in await repo.mentions_visible(document_id, progress, concept_id):
            sec = titles.get(m.section_id)
            if sec is None:
                continue
            finished = m.section_last_ordinal <= progress  # the note summarises the whole section
            points.append(
                TrajectoryPointOut(
                    section_id=sec.id,
                    section_title=sec.title,
                    section_ordinal=sec.ordinal,
                    first_ordinal=m.first_ordinal,
                    chunks=m.mention_chunks,
                    note=m.note if finished and m.note else None,
                )
            )
        points.sort(key=lambda p: p.section_ordinal)
        return TrajectoryOut(concept_id=concept.id, name=concept.name, points=points)
