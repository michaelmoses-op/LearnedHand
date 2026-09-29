import uuid
from datetime import datetime

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
