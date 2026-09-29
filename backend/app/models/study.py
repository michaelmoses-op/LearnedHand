"""Learning features: notes/highlights, flashcards and quiz questions.

All rows are user-owned (FORCE RLS). Everything anchored to the book carries an ordinal
(`anchor_ordinal` / `source_ordinal`) and is returned only when `ordinal <= progress`, so
lowering progress (or a reingest clamp) hides it again. Anchors are plain ordinals rather than
chunk foreign keys, so notes survive a re-ingest that rebuilds the chunks.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_UUID_DEFAULT = sql_text("gen_random_uuid()")
_NOW = sql_text("now()")


class _Owned:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class Note(_Owned, Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("kind in ('note', 'highlight')", name="kind_valid"),
        CheckConstraint("anchor_ordinal >= 0", name="anchor_nonneg"),
        CheckConstraint("kind <> 'highlight' or quote is not null", name="highlight_has_quote"),
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
    )

    kind: Mapped[str] = mapped_column(String(16))
    anchor_ordinal: Mapped[int] = mapped_column(Integer)
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


class Flashcard(_Owned, Base):
    __tablename__ = "flashcards"
    __table_args__ = (
        CheckConstraint("source_ordinal >= 0", name="source_nonneg"),
        CheckConstraint("reps >= 0 and lapses >= 0", name="counters_nonneg"),
        Index("ix_flashcards_document_due", "document_id", "due_at"),
    )

    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    front_key: Mapped[str] = mapped_column(String(200))  # normalised, de-duplicates generation
    source_ordinal: Mapped[int] = mapped_column(Integer)
    # SM-2-style scheduling state.
    ease: Mapped[float] = mapped_column(Float, server_default=sql_text("2.5"))
    interval_days: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    reps: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    lapses: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)


class QuizQuestion(_Owned, Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint("source_ordinal >= 0", name="source_nonneg"),
        CheckConstraint("answer_index >= 0", name="answer_nonneg"),
        CheckConstraint("times_correct <= times_answered", name="correct_le_answered"),
    )

    question: Mapped[str] = mapped_column(Text)
    question_key: Mapped[str] = mapped_column(String(200))
    choices: Mapped[list[str]] = mapped_column(JSONB)
    answer_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text, server_default=sql_text("''"))
    source_ordinal: Mapped[int] = mapped_column(Integer)
    times_answered: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    times_correct: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_NOW)
