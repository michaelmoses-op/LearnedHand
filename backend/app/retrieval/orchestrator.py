"""One entry point for "answer-time retrieval": route → (scope) → single pass or agentic loop.

Used by the ask path and by the eval runner, so evals measure exactly what users get.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.llm.base import Reranker
from app.llm.factory import build_llm
from app.repositories.concepts import ConceptRepository
from app.retrieval.agentic import run_agentic
from app.retrieval.config import RetrievalConfig
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.routing import (
    classify_question,
    find_concept_sections,
    strategy_for,
)
from app.retrieval.types import RetrievalResult


class RetrievalOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        settings: Settings,
        *,
        document_id: uuid.UUID,
        reranker: Reranker | None = None,
    ) -> None:
        self._session, self._ctx, self._settings = session, ctx, settings
        self._document_id = document_id
        self.pipeline = RetrievalPipeline(
            session, ctx, settings, document_id=document_id, reranker=reranker
        )
        self._route_llm = build_llm(settings, session, ctx, document_id=document_id, stage="route")
        self._gap_llm = build_llm(settings, session, ctx, document_id=document_id, stage="gapcheck")

    async def run(
        self,
        *,
        query: str,
        config: RetrievalConfig | None = None,
        progress: int | None = None,
        route: bool = False,
    ) -> RetrievalResult:
        cfg = config or RetrievalConfig.from_settings(self._settings)
        gate = (
            progress
            if progress is not None
            else await self.pipeline.resolve_progress(self._document_id)
        )
        label: str | None = None
        scope: list[uuid.UUID] | None = None
        if route and gate >= 0:
            cls = await classify_question(self._route_llm, self._settings, query)
            label = cls.label
            if cls.label == "concept":
                sections = await find_concept_sections(
                    ConceptRepository(self._session, self._ctx),
                    self._document_id,
                    gate,
                    query,
                    cls.concept,
                )
                if sections:
                    scope = sections
                else:
                    label = "factual"  # concept not (yet) known to this reader: search normally
            cfg = strategy_for(cfg, label)
        result = await run_agentic(
            self.pipeline,
            self._gap_llm,
            self._settings,
            document_id=self._document_id,
            query=query,
            config=cfg,
            progress=gate,
            scope_sections=scope,
        )
        result.route = label
        return result
