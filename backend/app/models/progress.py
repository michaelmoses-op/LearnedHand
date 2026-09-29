"""Per-document reading progress (spoiler gate). Default = end of book after ingest."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = text("gen_random_uuid()")
_NOW = text("now()")


class DocumentProgress(Base):
    __tablename__ = "document_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_document_progress_user_document"),
        CheckConstraint("max_ordinal >= 0", name="max_ordinal_nonneg"),
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
    max_ordinal: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
