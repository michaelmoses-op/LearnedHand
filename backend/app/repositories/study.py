"""AuthContext-scoped repositories for notes, flashcards and quiz questions.

Every read that can carry book-derived content filters on `ordinal <= progress` in SQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.study import Flashcard, Note, QuizQuestion


class NoteRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    def _visible(self, document_id: uuid.UUID, progress: int) -> tuple[ColumnElement[bool], ...]:
        return (
            Note.user_id == self.ctx.user_id,
            Note.document_id == document_id,
            Note.anchor_ordinal <= progress,
        )

    async def add(self, note: Note) -> Note:
        note.user_id = self.ctx.user_id
        self.session.add(note)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def get(self, document_id: uuid.UUID, note_id: uuid.UUID, progress: int) -> Note | None:
        stmt = select(Note).where(*self._visible(document_id, progress), Note.id == note_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search(
        self,
        document_id: uuid.UUID,
        progress: int,
        *,
        q: str | None,
        kind: str | None,
        limit: int,
    ) -> list[Note]:
        stmt = select(Note).where(*self._visible(document_id, progress))
        if kind:
            stmt = stmt.where(Note.kind == kind)
        if q and q.strip():
            tsq = func.websearch_to_tsquery("english", q)  # safe for arbitrary user input
            stmt = stmt.where(Note.search_vector.op("@@")(tsq)).order_by(
                func.ts_rank(Note.search_vector, tsq).desc(), Note.created_at.desc()
            )
        else:
            stmt = stmt.order_by(Note.anchor_ordinal, Note.created_at)
        return list((await self.session.execute(stmt.limit(limit))).scalars())

    async def delete(self, document_id: uuid.UUID, note_id: uuid.UUID, progress: int) -> bool:
        res = await self.session.execute(
            delete(Note)
            .where(*self._visible(document_id, progress), Note.id == note_id)
            .returning(Note.id)
        )
        return res.first() is not None


class FlashcardRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def existing_keys(self, document_id: uuid.UUID) -> set[str]:
        rows = await self.session.execute(
            select(Flashcard.front_key).where(
                Flashcard.user_id == self.ctx.user_id, Flashcard.document_id == document_id
            )
        )
        return set(rows.scalars())

    async def add_many(self, document_id: uuid.UUID, cards: list[Flashcard]) -> None:
        for c in cards:
            c.user_id, c.document_id = self.ctx.user_id, document_id
            self.session.add(c)
        await self.session.flush()

    async def list_visible(
        self, document_id: uuid.UUID, progress: int, *, due_before: datetime | None, limit: int
    ) -> list[Flashcard]:
        stmt = select(Flashcard).where(
            Flashcard.user_id == self.ctx.user_id,
            Flashcard.document_id == document_id,
            Flashcard.source_ordinal <= progress,
        )
        if due_before is not None:
            stmt = stmt.where(Flashcard.due_at <= due_before)
        stmt = stmt.order_by(Flashcard.due_at, Flashcard.source_ordinal).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def get_visible(
        self, document_id: uuid.UUID, card_id: uuid.UUID, progress: int
    ) -> Flashcard | None:
        stmt = select(Flashcard).where(
            Flashcard.user_id == self.ctx.user_id,
            Flashcard.document_id == document_id,
            Flashcard.id == card_id,
            Flashcard.source_ordinal <= progress,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class QuizRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def existing_keys(self, document_id: uuid.UUID) -> set[str]:
        rows = await self.session.execute(
            select(QuizQuestion.question_key).where(
                QuizQuestion.user_id == self.ctx.user_id,
                QuizQuestion.document_id == document_id,
            )
        )
        return set(rows.scalars())

    async def add_many(self, document_id: uuid.UUID, rows: list[QuizQuestion]) -> None:
        for r in rows:
            r.user_id, r.document_id = self.ctx.user_id, document_id
            self.session.add(r)
        await self.session.flush()

    async def list_visible(
        self, document_id: uuid.UUID, progress: int, limit: int
    ) -> list[QuizQuestion]:
        stmt = (
            select(QuizQuestion)
            .where(
                QuizQuestion.user_id == self.ctx.user_id,
                QuizQuestion.document_id == document_id,
                QuizQuestion.source_ordinal <= progress,
            )
            .order_by(QuizQuestion.times_answered, QuizQuestion.source_ordinal)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def get_visible(
        self, document_id: uuid.UUID, question_id: uuid.UUID, progress: int
    ) -> QuizQuestion | None:
        stmt = select(QuizQuestion).where(
            QuizQuestion.user_id == self.ctx.user_id,
            QuizQuestion.document_id == document_id,
            QuizQuestion.id == question_id,
            QuizQuestion.source_ordinal <= progress,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
