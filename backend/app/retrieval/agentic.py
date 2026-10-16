"""Agentic gap-check loop: retrieve, ask the model whether the context is enough, and if not run
another retrieval with its follow-up query, up to `max_iterations` passes.

Safety: passages are untrusted data. The follow-up query is used *only* as retrieval query text;
every pass goes through `RetrievalPipeline`, so it is bounded by the same SQL gate (user,
document). Iterations are hard-capped, so a hijacked verdict costs at most
a couple of extra searches.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import replace

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.errors import LLMError
from app.llm.structured import complete_structured
from app.prompts import load_prompt
from app.retrieval.config import RetrievalConfig
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.types import RetrievalResult, RetrievedChunk, StageTrace

MAX_PASSAGE_CHARS = 1200
MAX_FOLLOW_UP_CHARS = 300


class GapVerdict(BaseModel):
    sufficient: bool = True
    missing: str = Field(default="", max_length=500)
    follow_up_query: str | None = Field(default=None, max_length=MAX_FOLLOW_UP_CHARS)


async def gap_check(
    llm: AccountingLLM, settings: Settings, question: str, chunks: Sequence[RetrievedChunk]
) -> tuple[GapVerdict, int]:
    """Returns (verdict, tokens used). Errors count as 'sufficient' (never block answering)."""
    passages = "\n".join(
        f'<passage ordinal="{c.ordinal}">\n{c.text[:MAX_PASSAGE_CHARS]}\n</passage>' for c in chunks
    )
    user = f"<question>\n{question}\n</question>\n\n{passages}\n\nAre these passages sufficient?"
    try:
        verdict = await complete_structured(
            llm,
            model=settings.ingest_model,
            messages=[ChatMessage("system", load_prompt("gap_check")), ChatMessage("user", user)],
            output=GapVerdict,
        )
    except LLMError:
        return GapVerdict(), 0
    tokens = len(user) // 4  # accounting rows hold exact counts; this is only for the trace
    return verdict, tokens


def _merge(
    base: list[RetrievedChunk], extra: list[RetrievedChunk], cap: int
) -> list[RetrievedChunk]:
    seen = {c.chunk_id for c in base}
    merged = list(base)
    for c in extra:
        if c.chunk_id not in seen and len(merged) < cap:
            merged.append(c)
            seen.add(c.chunk_id)
    return merged


def _tag(stages: list[StageTrace], suffix: str) -> list[StageTrace]:
    return [replace(s, name=f"{s.name}{suffix}") for s in stages]


async def run_agentic(
    pipeline: RetrievalPipeline,
    llm: AccountingLLM,
    settings: Settings,
    *,
    document_id: uuid.UUID,
    query: str,
    config: RetrievalConfig,
    scope_sections: Sequence[uuid.UUID] | None = None,
) -> RetrievalResult:
    first = await pipeline.run(
        document_id=document_id,
        query=query,
        config=config,
        scope_sections=scope_sections,
    )
    if config.max_iterations <= 1 or not first.chunks:
        return first

    stages = _tag(first.stages, "@1")
    chunks = first.chunks
    cap = config.final_k * 2
    iterations = 1
    while iterations < config.max_iterations:
        t0 = time.perf_counter()
        verdict, tokens = await gap_check(llm, settings, query, chunks)
        follow_up = (verdict.follow_up_query or "").strip()[:MAX_FOLLOW_UP_CHARS]
        stages.append(
            StageTrace(
                f"gap_check@{iterations}",
                (time.perf_counter() - t0) * 1000.0,
                0,
                tokens=tokens,
                note="sufficient" if verdict.sufficient or not follow_up else "follow_up",
            )
        )
        if verdict.sufficient or not follow_up:
            break
        iterations += 1
        nxt = await pipeline.run(
            document_id=document_id,
            query=follow_up,
            config=config,
            scope_sections=scope_sections,
        )
        stages.extend(_tag(nxt.stages, f"@{iterations}"))
        chunks = _merge(chunks, nxt.chunks, cap)

    stages.append(StageTrace("final", 0.0, len(chunks), ids=[c.chunk_id for c in chunks]))
    return RetrievalResult(chunks=chunks, stages=stages, iterations=iterations)
