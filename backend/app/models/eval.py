"""Eval harness persistence. One `eval_runs` row per (batch, config); one result per question.

Stores ids, metrics and timings only — no book text, prompts, or answers.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    config_name: Mapped[str] = mapped_column(String(100))
    corpus: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(100))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
