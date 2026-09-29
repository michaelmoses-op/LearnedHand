"""Structured output: JSON-schema request + Pydantic validation + one repair retry."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.llm.base import ChatMessage, Completion
from app.llm.errors import LLMInvalidOutputError


class _Completer(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        response_schema: dict[str, object] | None = None,
    ) -> Completion: ...


def _error_summary(exc: Exception) -> str:
    """Locations and messages only: input values may contain book text."""
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors()
        )[:500]
    return "output was not valid JSON"


def _parse[T: BaseModel](text: str, model_cls: type[T]) -> T:
    return model_cls.model_validate(json.loads(text))


async def complete_structured[T: BaseModel](
    llm: _Completer,
    *,
    model: str,
    messages: Sequence[ChatMessage],
    output: type[T],
) -> T:
    schema = output.model_json_schema()
    first = await llm.complete(model=model, messages=messages, response_schema=schema)
    try:
        return _parse(first.text, output)
    except (ValidationError, ValueError) as exc:
        problem = _error_summary(exc)
    repair = [
        *messages,
        ChatMessage(role="assistant", content=first.text),
        ChatMessage(
            role="user",
            content=(
                f"Your previous reply failed validation ({problem}). "
                "Reply again with ONLY valid JSON matching the schema."
            ),
        ),
    ]
    second = await llm.complete(model=model, messages=repair, response_schema=schema)
    try:
        return _parse(second.text, output)
    except (ValidationError, ValueError) as exc:
        raise LLMInvalidOutputError(_error_summary(exc)) from None
