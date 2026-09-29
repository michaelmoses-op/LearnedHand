"""Document sections (structure tree with a global reading ordinal)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_sections_document_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonneg"),
        CheckConstraint("depth >= 0", name="depth_nonneg"),
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
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)  # global section order
    depth: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    title: Mapped[str] = mapped_column(String(500))
    spine_href: Mapped[str] = mapped_column(String(1000))
    body: Mapped[str] = mapped_column("text", Text, server_default=sql_text("''"))
    # Range of global chunk ordinals inside this section (null if it has no chunks).
    first_chunk_ordinal: Mapped[int | None] = mapped_column(Integer)
    last_chunk_ordinal: Mapped[int | None] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    # [[char_offset, page_number], ...] sorted by offset (PDF only); maps chunks to pages.
    page_map: Mapped[list[list[int]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
