"""Concepts extracted per section and merged across the book.

Spoiler rules (enforced in `repositories/concepts.py`):
- a concept is visible once any mention has `first_ordinal <= progress`;
- a mention's `note` (model-written from the whole section summary) is visible only when the
  reader has finished the section: `section_last_ordinal <= progress`.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        Index("uq_concepts_document_key", "document_id", "key", unique=True),
        CheckConstraint("first_ordinal >= 0", name="first_ordinal_nonneg"),
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
    name: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(200))  # normalised name used for merging
    first_ordinal: Mapped[int] = mapped_column(Integer)  # earliest visible appearance
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)


class ConceptMention(Base):
    __tablename__ = "concept_mentions"
    __table_args__ = (
        CheckConstraint("first_ordinal >= 0", name="first_ordinal_nonneg"),
        CheckConstraint("last_ordinal >= first_ordinal", name="last_gte_first"),
        CheckConstraint("mention_chunks >= 0", name="mention_chunks_nonneg"),
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
    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    # Where the name actually occurs in this section's chunks (section range if not found).
    first_ordinal: Mapped[int] = mapped_column(Integer)
    last_ordinal: Mapped[int] = mapped_column(Integer)
    section_last_ordinal: Mapped[int] = mapped_column(Integer)  # note gate
    mention_chunks: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
