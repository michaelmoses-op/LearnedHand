"""AuthContext-scoped concept repository. Visibility (spoiler) rules live here, in SQL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.concept import Concept, ConceptMention


@dataclass(frozen=True, slots=True)
class ConceptStat:
    concept: Concept
    sections: int  # visible mentions (sections where it appears, up to progress)
    chunks: int  # chunks mentioning it, up to progress


class ConceptRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        concepts: list[Concept],
        mentions: list[ConceptMention],
    ) -> None:
        """Idempotent: mentions cascade with their concepts."""
        await self.session.execute(
            delete(Concept).where(
                Concept.user_id == self.ctx.user_id, Concept.document_id == document_id
            )
        )
        for concept in concepts:
            concept.user_id, concept.document_id = self.ctx.user_id, document_id
            self.session.add(concept)
        await self.session.flush()  # concepts first: mentions reference them
        for mention in mentions:
            mention.user_id, mention.document_id = self.ctx.user_id, document_id
            self.session.add(mention)
        await self.session.flush()

    async def list_visible(self, document_id: uuid.UUID, progress: int) -> list[ConceptStat]:
        """Concepts with at least one appearance at or before `progress`."""
        m = ConceptMention
        stmt = (
            select(Concept, func.count(m.id), func.coalesce(func.sum(m.mention_chunks), 0))
            .join(m, m.concept_id == Concept.id)
            .where(
                Concept.user_id == self.ctx.user_id,
                Concept.document_id == document_id,
                m.user_id == self.ctx.user_id,
                m.first_ordinal <= progress,
            )
            .group_by(Concept.id)
            .order_by(Concept.first_ordinal, Concept.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [ConceptStat(c, int(n), int(k)) for c, n, k in rows]

    async def get_visible(
        self, document_id: uuid.UUID, concept_id: uuid.UUID, progress: int
    ) -> Concept | None:
        stmt = select(Concept).where(
            Concept.user_id == self.ctx.user_id,
            Concept.document_id == document_id,
            Concept.id == concept_id,
            Concept.first_ordinal <= progress,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def mentions_visible(
        self, document_id: uuid.UUID, progress: int, concept_id: uuid.UUID | None = None
    ) -> list[ConceptMention]:
        """Mentions whose first appearance is at or before `progress`, in book order.
        Callers must blank `note` when `section_last_ordinal > progress`."""
        stmt = select(ConceptMention).where(
            ConceptMention.user_id == self.ctx.user_id,
            ConceptMention.document_id == document_id,
            ConceptMention.first_ordinal <= progress,
        )
        if concept_id is not None:
            stmt = stmt.where(ConceptMention.concept_id == concept_id)
        stmt = stmt.order_by(ConceptMention.first_ordinal)
        return list((await self.session.execute(stmt)).scalars())
