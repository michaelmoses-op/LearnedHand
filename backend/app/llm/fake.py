"""Deterministic FAKE LLM provider. No network; safe default for tests and local Phase 2."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.llm.base import ChatMessage, Completion, EmbeddingBatch, estimate_tokens


class FakeLLM:
    """Stable outputs from SHA-256 of inputs so tests are repeatable."""

    @property
    def name(self) -> str:
        return "fake"

    async def complete(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        response_schema: dict[str, Any] | None = None,
    ) -> Completion:
        if response_schema is not None:
            text = json.dumps(_example_from_schema(response_schema, response_schema))
            inp = sum(estimate_tokens(m.content) for m in messages)
            return Completion(
                text=text, input_tokens=inp, output_tokens=estimate_tokens(text), model=model
            )
        extract = _extractive_summary(messages)
        if extract is not None:
            inp = sum(estimate_tokens(m.content) for m in messages)
            return Completion(
                text=extract, input_tokens=inp, output_tokens=estimate_tokens(extract), model=model
            )
        digest = _messages_digest(messages)
        # Q&A responses are synthetic metadata only (never echo untrusted book text). The one
        # exception is the extractive fake *summariser* above, whose output is stored as data.
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


_WORD = re.compile(r"[a-z0-9]+")
_BLOCK = re.compile(r"<(passage|part_summary)[^>]*>\n?(.*?)\n?</\1>", re.DOTALL)
_STOPWORDS = frozenset(
    {
        *("a", "an", "and", "are", "as", "at", "be", "but", "by", "did", "do", "does"),
        *("for", "from", "had", "has", "have", "how", "in", "is", "it", "its", "of"),
        *("on", "or", "that", "the", "their", "they", "this", "to", "was", "were"),
        *("what", "when", "where", "which", "who", "whom", "why", "with"),
    }
)
_SLOTS_PER_TOKEN = 3
_SUMMARY_WORDS_PER_BLOCK = 45
_SUMMARY_WORDS_MAX = 160


def _extractive_summary(messages: Sequence[ChatMessage]) -> str | None:
    """Fake summariser: the opening words of each <passage>/<part_summary> block. Deterministic,
    content-bearing (so hierarchical retrieval is testable offline), never used for Q&A."""
    user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    if '<source index="' in user:
        return None
    blocks = _BLOCK.findall(user)
    if not blocks:
        return None
    words: list[str] = []
    for _kind, body in blocks:
        words.extend(body.split()[:_SUMMARY_WORDS_PER_BLOCK])
    return " ".join(words[:_SUMMARY_WORDS_MAX])


def _fake_vector(text: str, dimensions: int) -> list[float]:
    """Deterministic *lexical* embedding: hashed bag of words, L2-normalised.

    Texts sharing words get high cosine similarity, so retrieval evals mean something offline.
    Text without word tokens falls back to a hash-derived random vector.
    """
    counts: dict[str, int] = {}
    for tok in _WORD.findall(text.lower()):
        if tok not in _STOPWORDS:
            counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return _hash_vector(text, dimensions)
    vec = [0.0] * dimensions
    for tok, n in counts.items():
        weight = 1.0 + math.log(n)  # sub-linear term frequency
        digest = hashlib.sha256(tok.encode()).digest()
        for k in range(_SLOTS_PER_TOKEN):
            idx = int.from_bytes(digest[k * 4 : k * 4 + 3], "big") % dimensions
            vec[idx] += weight if digest[k * 4 + 3] & 1 else -weight
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return _hash_vector(text, dimensions)
    return [x / norm for x in vec]


def _hash_vector(text: str, dimensions: int) -> list[float]:
    seed = hashlib.sha256(text.encode()).digest()
    out: list[float] = []
    block = seed
    while len(out) < dimensions:
        block = hashlib.sha256(block).digest()
        for i in range(0, len(block) - 3, 4):
            if len(out) >= dimensions:
                break
            (u,) = struct.unpack_from(">I", block, i)
            out.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def _example_from_schema(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    """Smallest valid instance of a (pydantic-style) JSON Schema. Deterministic."""
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _example_from_schema(root.get("$defs", {}).get(name, {}), root)
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return _example_from_schema(options[0], root)
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        return {k: _example_from_schema(v, root) for k, v in props.items()}
    if kind == "array":
        return []
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "number":
        return float(schema.get("minimum", 0))
    if kind == "boolean":
        return False
    return "fake"
