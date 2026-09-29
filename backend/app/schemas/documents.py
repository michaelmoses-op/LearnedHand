import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict

from app.schemas.common import StrictModel


class DocumentOut(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    original_filename: str
    format: str
    file_size: int
    status: str
    created_at: datetime


class DocumentPage(StrictModel):
    items: list[DocumentOut]
    next_cursor: str | None = None


class DocumentStatusOut(StrictModel):
    id: uuid.UUID
    status: str
    ingest_stage: str | None
    error: str | None
    max_ordinal: int | None
    updated_at: datetime


IngestStageName = Literal[
    "parse", "sections", "chunk", "context", "embed", "summaries", "concepts", "validate"
]


class ReingestIn(StrictModel):
    # Re-run this stage and every later one. Omit to resume from the first stale stage.
    from_stage: IngestStageName | None = None


class QualityReportOut(StrictModel):
    document_id: uuid.UUID
    report: dict[str, Any] | None  # null until the validate stage has run
