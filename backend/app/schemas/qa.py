import uuid
from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel


class AskIn(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=20)
    # `tutor`: Socratic guidance instead of a direct answer (same sources).
    mode: Literal["answer", "tutor"] = "answer"


class SectionOut(StrictModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    ordinal: int
    depth: int
    title: str
    body: str | None


class SectionListOut(StrictModel):
    items: list[SectionOut]
