"""LLM provider contract. Implementations must not log prompts, completions, or tokens."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    input_tokens: int
    model: str
    dimensions: int


class LLMProvider(Protocol):
    """Low-level provider. Model names and embedding dim come from the caller (settings)."""

    @property
    def name(self) -> str: ...

    async def complete(self, *, model: str, messages: Sequence[ChatMessage]) -> Completion: ...

    def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]: ...

    async def embed(
        self, *, model: str, texts: Sequence[str], dimensions: int
    ) -> EmbeddingBatch: ...


def estimate_tokens(text: str) -> int:
    """Rough token estimate for fake/accounting when the provider has no real tokenizer."""
    # ~4 chars/token; at least 1 for non-empty input.
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, (len(stripped) + 3) // 4)
