import uuid

from app.schemas.common import StrictModel


class SectionSummaryOut(StrictModel):
    section_id: uuid.UUID
    title: str
    ordinal: int
    depth: int
    body: str


class SummariesOut(StrictModel):
    """The book-level summary (null until ingestion has produced it) and one per section."""

    book: str | None
    sections: list[SectionSummaryOut]
