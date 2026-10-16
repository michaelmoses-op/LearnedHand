"""AuthContext-scoped section / chunk repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.chunk import Chunk
from app.models.section import Section


class SectionRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        rows: list[Section],
    ) -> list[Section]:
        """Idempotent: drop existing sections (chunks cascade) then insert."""
        await self.session.execute(
            delete(Section).where(
                Section.user_id == self.ctx.user_id, Section.document_id == document_id
            )
        )
        for row in rows:
            row.user_id = self.ctx.user_id
            row.document_id = document_id
            self.session.add(row)
        await self.session.flush()
        return rows

    async def list_for_document(self, document_id: uuid.UUID) -> list[Section]:
        stmt = (
            select(Section)
            .where(Section.user_id == self.ctx.user_id, Section.document_id == document_id)
            .order_by(Section.ordinal)
        )
        return list((await self.session.execute(stmt)).scalars())


class ChunkRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def replace_for_document(self, document_id: uuid.UUID, rows: list[Chunk]) -> list[Chunk]:
        await self.session.execute(
            delete(Chunk).where(Chunk.user_id == self.ctx.user_id, Chunk.document_id == document_id)
        )
        for row in rows:
            row.user_id = self.ctx.user_id
            row.document_id = document_id
            self.session.add(row)
        await self.session.flush()
        return rows

    async def list_for_document(self, document_id: uuid.UUID) -> list[Chunk]:
        stmt = (
            select(Chunk)
            .where(Chunk.user_id == self.ctx.user_id, Chunk.document_id == document_id)
            .order_by(Chunk.ordinal)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def max_ordinal(self, document_id: uuid.UUID) -> int | None:
        from sqlalchemy import func

        stmt = select(func.max(Chunk.ordinal)).where(
            Chunk.user_id == self.ctx.user_id, Chunk.document_id == document_id
        )
        return (await self.session.execute(stmt)).scalar_one()
