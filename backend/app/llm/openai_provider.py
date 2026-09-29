"""OpenAI provider (official SDK). Transport retries are disabled here: retry/timeout/breaker
policy lives in `ResilientLLM` so it is uniform across providers. Never logs prompts,
completions, or embeddings."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from app.llm.base import ChatMessage, Completion, EmbeddingBatch, estimate_tokens
from app.llm.errors import PermanentLLMError, TransientLLMError

# Only the text-embedding-3 family accepts a `dimensions` argument.
_SUPPORTS_DIMENSIONS_PREFIX = "text-embedding-3"


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, openai.APITimeoutError):
        return TransientLLMError("timeout")
    if isinstance(exc, openai.APIConnectionError):
        return TransientLLMError("connection_error")
    if isinstance(exc, openai.RateLimitError):
        return TransientLLMError("rate_limited")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500 or exc.status_code == 408:
            return TransientLLMError(f"upstream_{exc.status_code}")
        return PermanentLLMError(f"rejected_{exc.status_code}")
    return exc


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        http_client: Any = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,  # ResilientLLM owns retries
            http_client=http_client,
        )

    @property
    def name(self) -> str:
        return "openai"

    async def complete(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        response_schema: dict[str, Any] | None = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {}
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": response_schema, "strict": False},
            }
        try:
            resp = await self._client.chat.completions.create(
                model=model, messages=_to_api(messages), **kwargs
            )
        except Exception as exc:
            raise _translate(exc) from None
        choice = resp.choices[0] if resp.choices else None
        text = (choice.message.content if choice else None) or ""
        usage = resp.usage
        cached = 0
        if usage is not None and usage.prompt_tokens_details is not None:
            cached = usage.prompt_tokens_details.cached_tokens or 0
        return Completion(
            text=text,
            input_tokens=usage.prompt_tokens
            if usage
            else sum(estimate_tokens(m.content) for m in messages),
            output_tokens=usage.completion_tokens if usage else estimate_tokens(text),
            model=resp.model or model,
            cached_tokens=cached,
        )

    async def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=model, messages=_to_api(messages), stream=True
            )
            async for event in stream:
                if not event.choices:
                    continue
                piece = event.choices[0].delta.content
                if piece:
                    yield piece
        except Exception as exc:
            raise _translate(exc) from None

    async def embed(self, *, model: str, texts: Sequence[str], dimensions: int) -> EmbeddingBatch:
        kwargs: dict[str, Any] = {}
        if model.startswith(_SUPPORTS_DIMENSIONS_PREFIX):
            kwargs["dimensions"] = dimensions
        try:
            resp = await self._client.embeddings.create(model=model, input=list(texts), **kwargs)
        except Exception as exc:
            raise _translate(exc) from None
        ordered = sorted(resp.data, key=lambda d: d.index)
        vectors = [list(d.embedding) for d in ordered]
        if len(vectors) != len(texts) or any(len(v) != dimensions for v in vectors):
            raise PermanentLLMError("embedding_shape_mismatch")
        return EmbeddingBatch(
            vectors=vectors,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            model=resp.model or model,
            dimensions=dimensions,
        )


def _to_api(messages: Sequence[ChatMessage]) -> list[Any]:
    return [{"role": m.role, "content": m.content} for m in messages]
