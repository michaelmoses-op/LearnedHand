"""AuthContext-scoped notes repository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.notes import Note


class NoteRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def add(self, note: Note) -> Note:
        note.user_id = self.ctx.user_id
        self.session.add(note)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def get(self, document_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        stmt = select(Note).where(
            Note.user_id == self.ctx.user_id, Note.document_id == document_id, Note.id == note_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search(
        self, document_id: uuid.UUID, *, q: str | None, kind: str | None, limit: int
    ) -> list[Note]:
        stmt = select(Note).where(Note.user_id == self.ctx.user_id, Note.document_id == document_id)
        if kind:
            stmt = stmt.where(Note.kind == kind)
        if q and q.strip():
            tsq = func.websearch_to_tsquery("english", q)  # safe for arbitrary user input
            stmt = stmt.where(Note.search_vector.op("@@")(tsq)).order_by(
                func.ts_rank(Note.search_vector, tsq).desc(), Note.created_at.desc()
            )
        else:
            stmt = stmt.order_by(Note.created_at.desc())
        return list((await self.session.execute(stmt.limit(limit))).scalars())

    async def delete(self, document_id: uuid.UUID, note_id: uuid.UUID) -> bool:
        res = await self.session.execute(
            delete(Note)
            .where(
                Note.user_id == self.ctx.user_id,
                Note.document_id == document_id,
                Note.id == note_id,
            )
            .returning(Note.id)
        )
        return res.first() is not None
