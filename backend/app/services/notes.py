"""Notes and highlights."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.core.errors import DomainError, NotFoundError
from app.models.notes import Note
from app.repositories.documents import DocumentRepository
from app.repositories.notes import NoteRepository
from app.schemas.notes import NoteIn


class InvalidInputError(DomainError):
    status = 422
    code = "invalid_input"
    title = "Invalid input"


class NoteService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx
        self.repo = NoteRepository(session, ctx)

    async def _require_document(self, document_id: uuid.UUID) -> None:
        if await DocumentRepository(self.session, self.ctx).get(document_id) is None:
            raise NotFoundError("Document not found")

    async def create(self, document_id: uuid.UUID, data: NoteIn) -> Note:
        await self._require_document(document_id)
        return await self.repo.add(
            Note(
                document_id=document_id,
                kind=data.kind,
                anchor_ordinal=data.anchor_ordinal,
                quote=data.quote.strip() if data.quote else None,
                body=data.body.strip(),
            )
        )

    async def list(
        self, document_id: uuid.UUID, *, q: str | None, kind: str | None, limit: int
    ) -> list[Note]:
        await self._require_document(document_id)
        return await self.repo.search(document_id, q=q, kind=kind, limit=limit)

    async def update(self, document_id: uuid.UUID, note_id: uuid.UUID, body: str) -> Note:
        await self._require_document(document_id)
        note = await self.repo.get(document_id, note_id)
        if note is None:
            raise NotFoundError("Note not found")
        if note.kind == "note" and not body.strip():
            raise InvalidInputError("A note needs text")
        note.body = body.strip()
        note.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def delete(self, document_id: uuid.UUID, note_id: uuid.UUID) -> None:
        await self._require_document(document_id)
        if not await self.repo.delete(document_id, note_id):
            raise NotFoundError("Note not found")
