"""AuthContext-scoped summaries repository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.summary import Summary


class SummaryRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def replace_for_document(
        self, document_id: uuid.UUID, rows: list[Summary]
    ) -> list[Summary]:
        """Idempotent: drop existing summaries for the document, then insert."""
        await self.session.execute(
            delete(Summary).where(
                Summary.user_id == self.ctx.user_id, Summary.document_id == document_id
            )
        )
        for row in rows:
            row.user_id = self.ctx.user_id
            row.document_id = document_id
            self.session.add(row)
        await self.session.flush()
        return rows

    async def list_for_document(self, document_id: uuid.UUID) -> list[Summary]:
        stmt = (
            select(Summary)
            .where(Summary.user_id == self.ctx.user_id, Summary.document_id == document_id)
            .order_by(Summary.first_ordinal, Summary.depth)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def list_visible(self, document_id: uuid.UUID, progress: int) -> list[Summary]:
        """Only summaries the reader has fully passed: last_ordinal <= progress."""
        stmt = (
            select(Summary)
            .where(
                Summary.user_id == self.ctx.user_id,
                Summary.document_id == document_id,
                Summary.last_ordinal <= progress,
            )
            .order_by(Summary.first_ordinal, Summary.depth)
        )
        return list((await self.session.execute(stmt)).scalars())
