"""Reader notes and highlights (user-owned, FORCE RLS)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("kind in ('note', 'highlight')", name="kind_valid"),
        CheckConstraint("anchor_ordinal >= 0", name="anchor_nonneg"),
        CheckConstraint("kind <> 'highlight' or quote is not null", name="highlight_has_quote"),
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
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
    kind: Mapped[str] = mapped_column(String(16))
    # Optional passage the note is about (informational only; a plain ordinal, not a chunk FK,
    # so notes survive a re-ingest).
    anchor_ordinal: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str | None] = mapped_column(Text)  # the reader's own selection
    body: Mapped[str] = mapped_column(Text, server_default=sql_text("''"))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(body, '') || ' ' || coalesce(quote, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
