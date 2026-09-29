import uuid
from datetime import datetime

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models import Document


class DocumentRepository:
    """Every method is scoped by the AuthContext (layer 1); Postgres RLS is layer 2.
    There is intentionally no method that fetches by a bare id."""

    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def add(self, doc: Document) -> Document:
        doc.user_id = self.ctx.user_id
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get(self, document_id: uuid.UUID) -> Document | None:
        stmt = select(Document).where(
            Document.user_id == self.ctx.user_id, Document.id == document_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_by_hash(self, file_hash: str) -> Document | None:
        stmt = select(Document).where(
            Document.user_id == self.ctx.user_id, Document.file_hash == file_hash
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self, limit: int, after: tuple[datetime, uuid.UUID] | None = None
    ) -> list[Document]:
        """Keyset pagination, newest first. Returns up to `limit` rows."""
        stmt = select(Document).where(Document.user_id == self.ctx.user_id)
        if after is not None:
            stmt = stmt.where(tuple_(Document.created_at, Document.id) < tuple_(*after))
        stmt = stmt.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def delete(self, document_id: uuid.UUID) -> Document | None:
        stmt = (
            delete(Document)
            .where(Document.user_id == self.ctx.user_id, Document.id == document_id)
            .returning(Document)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
