"""Record llm_calls after each provider invocation (metadata only)."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.core.logging import get_logger
from app.llm.base import ChatMessage, Completion, EmbeddingBatch, LLMProvider
from app.repositories.llm_calls import LlmCallRepository

log = get_logger("llm.accounting")


class AccountingLLM:
    """Wraps a provider; every call writes an `llm_calls` row under the AuthContext."""

    def __init__(
        self,
        provider: LLMProvider,
        session: AsyncSession,
        ctx: AuthContext,
        *,
        document_id: uuid.UUID | None = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._ctx = ctx
        self._document_id = document_id
        self._repo = LlmCallRepository(session, ctx)

    @property
    def name(self) -> str:
        return self._provider.name

    async def complete(self, *, model: str, messages: Sequence[ChatMessage]) -> Completion:
        started = time.perf_counter()
        try:
            result = await self._provider.complete(model=model, messages=messages)
        except Exception:
            await self._record(
                kind="complete",
                model=model,
                status="error",
                error_code="complete_failed",
                latency_ms=_ms(started),
            )
            raise
        await self._record(
            kind="complete",
            model=result.model,
            status="ok",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=_ms(started),
        )
        return result

    async def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        started = time.perf_counter()
        chunks: list[str] = []
        try:
            async for piece in self._provider.stream(model=model, messages=messages):
                chunks.append(piece)
                yield piece
        except Exception:
            await self._record(
                kind="stream",
                model=model,
                status="error",
                error_code="stream_failed",
                latency_ms=_ms(started),
            )
            raise
        text = "".join(chunks)
        # Token counts estimated from streamed text only — never log the text.
        from app.llm.base import estimate_tokens

        await self._record(
            kind="stream",
            model=model,
            status="ok",
            input_tokens=sum(estimate_tokens(m.content) for m in messages),
            output_tokens=estimate_tokens(text),
            latency_ms=_ms(started),
        )

    async def embed(self, *, model: str, texts: Sequence[str], dimensions: int) -> EmbeddingBatch:
        started = time.perf_counter()
        try:
            result = await self._provider.embed(model=model, texts=texts, dimensions=dimensions)
        except Exception:
            await self._record(
                kind="embed",
                model=model,
                status="error",
                error_code="embed_failed",
                latency_ms=_ms(started),
            )
            raise
        await self._record(
            kind="embed",
            model=result.model,
            status="ok",
            input_tokens=result.input_tokens,
            output_tokens=0,
            latency_ms=_ms(started),
        )
        return result

    async def _record(
        self,
        *,
        kind: str,
        model: str,
        status: str,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
    ) -> None:
        await self._repo.add(
            provider=self._provider.name,
            model=model,
            kind=kind,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error_code=error_code,
            document_id=self._document_id,
        )
        # Structured log: ids and counts only — never prompts/completions.
        log.info(
            "llm_call",
            provider=self._provider.name,
            model=model,
            kind=kind,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error_code=error_code,
        )


def _ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
