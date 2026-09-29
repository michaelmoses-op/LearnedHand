"""Shared retrieval types (kept import-cycle free)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.core.errors import DomainError


class RetrievalError(DomainError):
    code = "retrieval_failed"
    title = "Retrieval failed"


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    section_id: uuid.UUID
    ordinal: int
    text: str
    context_prefix: str
    score: float


@dataclass(slots=True)
class StageTrace:
    """One pipeline stage: how long it took and what it produced.

    `ids` are chunk ids for chunk stages and section ids for the broad stage, so evals can
    compute recall@k per stage. Never contains text.
    """

    name: str
    duration_ms: float
    count: int
    tokens: int = 0
    ids: list[uuid.UUID] = field(default_factory=list)
    note: str = ""


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    stages: list[StageTrace]
    progress: int
    iterations: int = 1  # retrieval passes (agentic loop)
    route: str | None = None  # query class chosen by the router, if routing was on

    @property
    def total_ms(self) -> float:
        return sum(s.duration_ms for s in self.stages)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.stages)
