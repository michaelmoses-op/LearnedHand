import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.schemas.common import StrictModel


class NoteIn(StrictModel):
    kind: Literal["note", "highlight"] = "note"
    body: str = Field(default="", max_length=10_000)
    quote: str | None = Field(default=None, max_length=4_000)
    # Defaults to the reader's current position; may not be beyond it.
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
    anchor_ordinal: int
    quote: str | None
    body: str
    created_at: datetime
    updated_at: datetime


class NoteListOut(StrictModel):
    items: list[NoteOut]


class GenerateIn(StrictModel):
    kind: Literal["flashcards", "quiz"]
    count: int = Field(default=5, ge=1, le=10)
    section_id: uuid.UUID | None = None


class GenerateOut(StrictModel):
    kind: Literal["flashcards", "quiz"]
    created: int
    skipped: int  # duplicates or drafts that failed validation


class FlashcardOut(StrictModel):
    id: uuid.UUID
    front: str
    back: str
    source_ordinal: int
    due_at: datetime
    reps: int
    interval_days: int


class FlashcardListOut(StrictModel):
    items: list[FlashcardOut]


class ReviewIn(StrictModel):
    rating: Literal["again", "hard", "good", "easy"]


class QuizQuestionOut(StrictModel):
    id: uuid.UUID
    question: str
    choices: list[str]
    source_ordinal: int
    times_answered: int


class QuizListOut(StrictModel):
    items: list[QuizQuestionOut]


class AnswerIn(StrictModel):
    choice: int = Field(ge=0, le=9)


class AnswerOut(StrictModel):
    correct: bool
    answer_index: int
    explanation: str
