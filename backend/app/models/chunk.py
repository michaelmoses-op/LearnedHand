"""Embedded text chunks (vector + full-text)."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ingestion.constants import EMBEDDING_DIMENSION
from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonneg"),
        CheckConstraint("char_start >= 0", name="char_start_nonneg"),
        CheckConstraint("char_end >= char_start", name="char_end_gte_start"),
        CheckConstraint("token_count >= 0", name="token_count_nonneg"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
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
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)  # global chunk ordinal (spoiler gate)
    body: Mapped[str] = mapped_column("text", Text)
    context_prefix: Mapped[str] = mapped_column(Text, server_default=sql_text("''"))
    char_start: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    char_end: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    token_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(context_prefix, '') || ' ' || coalesce(text, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
