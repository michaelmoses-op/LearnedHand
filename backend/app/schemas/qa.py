import uuid
from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class AskIn(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=20)
    # `tutor`: Socratic guidance instead of a direct answer (same sources, same progress gate).
    mode: Literal["answer", "tutor"] = "answer"


class ProgressIn(StrictModel):
    max_ordinal: int = Field(ge=0)


class ProgressOut(StrictModel):
    document_id: uuid.UUID
    max_ordinal: int


class ChunkSpanOut(StrictModel):
    """Where one chunk (the unit progress is tracked in) sits inside its section's text."""

    ordinal: int
    char_start: int
    char_end: int


class SectionOut(StrictModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    ordinal: int
    depth: int
    title: str
    body: str | None
    readable: bool
    # Last chunk ordinal of the section: what "I have finished this section" sets progress to.
    last_chunk_ordinal: int | None
    # Offsets only (never text); present when the section body is, so a paragraph can be mapped
    # to the chunk boundary the reader has fully passed.
    chunks: list[ChunkSpanOut]


class SectionListOut(StrictModel):
    items: list[SectionOut]
