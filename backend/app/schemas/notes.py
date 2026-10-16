import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.schemas.common import StrictModel


class NoteIn(StrictModel):
    kind: Literal["note", "highlight"] = "note"
    body: str = Field(default="", max_length=10_000)
    quote: str | None = Field(default=None, max_length=4_000)
    # Optional passage the note is about.
    anchor_ordinal: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == "highlight" and not (self.quote and self.quote.strip()):
            raise ValueError("a highlight needs a quote")
        if self.kind == "note" and not self.body.strip():
            raise ValueError("a note needs text")
        return self


class NoteUpdate(StrictModel):
    body: str = Field(max_length=10_000)


class NoteOut(StrictModel):
    id: uuid.UUID
    kind: Literal["note", "highlight"]
    anchor_ordinal: int | None
    quote: str | None
    body: str
    created_at: datetime
    updated_at: datetime


class NoteListOut(StrictModel):
    items: list[NoteOut]
