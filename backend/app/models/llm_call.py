"""LLM call accounting. FORCE RLS — see Phase 2 step 3."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = text("gen_random_uuid()")
_NOW = text("now()")


class LlmCall(Base):
    """Metadata-only accounting. Never stores prompts, completions, or embeddings."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint("kind in ('complete', 'stream', 'embed')", name="kind"),
        CheckConstraint("status in ('ok', 'error')", name="status"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonneg"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonneg"),
        CheckConstraint("latency_ms >= 0", name="latency_ms_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ok'"))
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
