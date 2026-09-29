"""Query classification and routing to a retrieval strategy.

The classifier is an LLM call with a small structured output. It only *chooses among strategies
we define*; it never sees book text and cannot widen access: every strategy is still gated by
user, document and reading progress in SQL. Any failure falls back to the default strategy.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.logging import get_logger
from app.ingestion.concepts import concept_key
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.errors import LLMError
from app.llm.structured import complete_structured
from app.prompts import load_prompt
from app.repositories.concepts import ConceptRepository
from app.retrieval.config import RetrievalConfig

log = get_logger("retrieval.routing")

QueryLabel = Literal["factual", "thematic", "concept", "other"]
DEFAULT_LABEL: QueryLabel = "factual"


class Classification(BaseModel):
    label: QueryLabel = DEFAULT_LABEL
    concept: str | None = Field(default=None, max_length=200)


async def classify_question(
    llm: AccountingLLM, settings: Settings, question: str
) -> Classification:
    """Structured classification; degrades to `factual` if the model misbehaves."""
    try:
        return await complete_structured(
            llm,
            model=settings.ingest_model,  # cheap model: this is a tiny task
            messages=[
                ChatMessage("system", load_prompt("classify")),
                ChatMessage("user", f"<question>\n{question.strip()[:2000]}\n</question>"),
            ],
            output=Classification,
        )
    except LLMError:
        log.warning("classify_failed_using_default")
        return Classification()


def strategy_for(base: RetrievalConfig, label: str) -> RetrievalConfig:
    """The strategy table. Thematic questions benefit from summaries first; factual ones from
    precise flat search; concept questions are scoped by the caller (`find_concept_sections`)."""
    if label == "thematic":
        return base.model_copy(
            update={
                "name": f"{base.name}+thematic",
                "hierarchical": True,
                "broad_k": max(base.broad_k, 5),
            }
        )
    if label == "factual":
        return base.model_copy(update={"name": f"{base.name}+factual", "hierarchical": False})
    return base


async def find_concept_sections(
    repo: ConceptRepository, document_id: uuid.UUID, progress: int, question: str, hint: str | None
) -> list[uuid.UUID]:
    """Sections where the concept named in the question appears — among concepts the reader has
    already reached (progress-gated), so an unread concept cannot be inferred from this."""
    haystack = f" {concept_key(question)} "
    hint_key = concept_key(hint) if hint else ""
    best: tuple[int, uuid.UUID] | None = None
    for stat in await repo.list_visible(document_id, progress):
        key = stat.concept.key
        matches = f" {key} " in haystack or (hint_key and key == hint_key)
        if matches and (best is None or len(key) > best[0]):
            best = (len(key), stat.concept.id)
    if best is None:
        return []
    mentions = await repo.mentions_visible(document_id, progress, best[1])
    return list(dict.fromkeys(m.section_id for m in mentions))
