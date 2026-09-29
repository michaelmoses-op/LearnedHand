import uuid

from pydantic import Field

from app.schemas.common import StrictModel


class AskIn(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=20)


class ProgressIn(StrictModel):
    max_ordinal: int = Field(ge=0)


class ProgressOut(StrictModel):
    document_id: uuid.UUID
    max_ordinal: int


class SectionOut(StrictModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    ordinal: int
    depth: int
    title: str
    body: str | None
    readable: bool


class SectionListOut(StrictModel):
    items: list[SectionOut]
