"""Deterministic FAKE LLM provider. No network; safe default for tests and local Phase 2."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import AsyncIterator, Sequence

from app.llm.base import ChatMessage, Completion, EmbeddingBatch, estimate_tokens


class FakeLLM:
    """Stable outputs from SHA-256 of inputs so tests are repeatable."""

    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, *, model: str, messages: Sequence[ChatMessage]) -> Completion:
        digest = _messages_digest(messages)
        # Response is synthetic metadata only — never echo message content (untrusted book text).
        text = f"[fake:{model}:{digest[:12]}] {len(messages)} messages."
        # If the prompt listed sources, cite the first index so citation wiring is testable.
        if any('<source index="' in m.content for m in messages):
            text = f"{text} [1]"
        inp = sum(estimate_tokens(m.content) for m in messages)
        out = estimate_tokens(text)
        return Completion(text=text, input_tokens=inp, output_tokens=out, model=model)

    async def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        result = await self.complete(model=model, messages=messages)
        for word in result.text.split(" "):
            yield word if word.endswith(".") else f"{word} "

    async def embed(self, *, model: str, texts: Sequence[str], dimensions: int) -> EmbeddingBatch:
        if dimensions < 1:
            raise ValueError("dimensions must be >= 1")
        vectors = [_fake_vector(t, dimensions) for t in texts]
        inp = sum(estimate_tokens(t) for t in texts)
        return EmbeddingBatch(vectors=vectors, input_tokens=inp, model=model, dimensions=dimensions)


def _messages_digest(messages: Sequence[ChatMessage]) -> str:
    h = hashlib.sha256()
    for m in messages:
        h.update(m.role.encode())
        h.update(b"\0")
        h.update(m.content.encode())
        h.update(b"\0")
    return h.hexdigest()


def _fake_vector(text: str, dimensions: int) -> list[float]:
    """Unit-ish vector derived from text hash; length == dimensions."""
    seed = hashlib.sha256(text.encode()).digest()
    out: list[float] = []
    block = seed
    while len(out) < dimensions:
        # Expand digest deterministically.
        block = hashlib.sha256(block).digest()
        for i in range(0, len(block) - 3, 4):
            if len(out) >= dimensions:
                break
            (u,) = struct.unpack_from(">I", block, i)
            # Map to (-1, 1)
            out.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
    # L2-normalize for stable cosine behavior in later retrieval tests.
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]
