"""Hierarchical summaries (section -> ... -> book), each embedded for the broad retrieval pass."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ingestion.constants import EMBEDDING_DIMENSION
from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class Summary(Base):
    """A section or whole-book summary; `first/last_ordinal` = the chunk range it covers."""

    __tablename__ = "summaries"
    __table_args__ = (
        CheckConstraint("kind in ('section', 'book')", name="kind"),
        CheckConstraint("first_ordinal >= 0", name="first_ordinal_nonneg"),
        CheckConstraint("last_ordinal >= first_ordinal", name="last_gte_first"),
        Index(
            "ix_summaries_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_summaries_document_kind", "document_id", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )  # null for the book-level summary
    kind: Mapped[str] = mapped_column(String(20))
    depth: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    first_ordinal: Mapped[int] = mapped_column(Integer)
    last_ordinal: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column("text", Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
