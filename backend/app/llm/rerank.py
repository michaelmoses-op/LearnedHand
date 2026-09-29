"""Rerankers: fake (tests/offline) and local cross-encoder (sentence-transformers)."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.llm.base import Reranker
from app.llm.errors import PermanentLLMError

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class FakeReranker:
    """Deterministic lexical-overlap score in [0, 1]. Not semantic; for tests and dry runs."""

    @property
    def name(self) -> str:
        return "fake"

    async def rerank(self, *, query: str, passages: Sequence[str]) -> list[float]:
        q = _tokens(query)
        if not q:
            return [0.0] * len(passages)
        return [len(q & _tokens(p)) / len(q) for p in passages]


class CrossEncoderReranker:
    """Local cross-encoder (default `BAAI/bge-reranker-base`). Requires the optional
    `rerank` extra (`uv sync --extra rerank`); imported lazily so the base install stays light."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None

    @property
    def name(self) -> str:
        return "cross_encoder"

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise PermanentLLMError(
                    "cross_encoder reranker needs the 'rerank' extra: uv sync --extra rerank"
                ) from exc
            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(self, *, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []

        def run() -> list[float]:
            model = self._load()
            scores = model.predict([(query, p) for p in passages])
            return [float(s) for s in scores]

        return await asyncio.to_thread(run)


def build_reranker(settings: Settings) -> Reranker | None:
    if settings.reranker == "none":
        return None
    if settings.reranker == "fake":
        return FakeReranker()
    return CrossEncoderReranker(settings.reranker_model)
