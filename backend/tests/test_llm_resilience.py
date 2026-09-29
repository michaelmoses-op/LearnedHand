"""Timeouts, retries, circuit breaker, structured output repair, reranker, budget."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict

from app.core.deps import AuthContext, set_rls_user
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage, Completion, EmbeddingBatch
from app.llm.errors import (
    LLMBudgetExceededError,
    LLMCircuitOpenError,
    LLMInvalidOutputError,
    LLMTimeoutError,
    TransientLLMError,
)
from app.llm.fake import FakeLLM
from app.llm.rerank import FakeReranker
from app.llm.resilient import CircuitBreaker, ResilientLLM
from app.llm.structured import complete_structured

MSGS = [ChatMessage(role="user", content="x")]


class Flaky:
    """Fails `fail_times` with a transient error, then succeeds."""

    name = "flaky"

    def __init__(self, fail_times: int, delay: float = 0.0) -> None:
        self.fail_times, self.delay, self.calls = fail_times, delay, 0

    async def complete(
        self, *, model: str, messages: Sequence[ChatMessage], response_schema: Any = None
    ) -> Completion:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.calls <= self.fail_times:
            raise TransientLLMError("boom")
        return Completion(text="ok", input_tokens=1, output_tokens=1, model=model)

    async def embed(self, *, model: str, texts: Sequence[str], dimensions: int) -> EmbeddingBatch:
        raise NotImplementedError

    async def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TransientLLMError("boom")
        yield "a"
        yield "b"


def resilient(
    p: Any,
    *,
    retries: int = 3,
    timeout: float = 1.0,
    breaker: CircuitBreaker | None = None,
    sleeps: list[float] | None = None,
) -> ResilientLLM:
    log = sleeps if sleeps is not None else []

    async def sleep(d: float) -> None:
        log.append(d)

    return ResilientLLM(
        p,
        timeout=timeout,
        max_retries=retries,
        breaker=breaker or CircuitBreaker(100, 1.0),
        sleep=sleep,
        rand=lambda: 1.0,
    )


async def test_retries_with_backoff_then_succeeds() -> None:
    sleeps: list[float] = []
    p = Flaky(fail_times=2)
    out = await resilient(p, sleeps=sleeps).complete(model="m", messages=MSGS)
    assert out.text == "ok" and p.calls == 3
    assert sleeps == [0.5, 1.0]  # rand=1.0 => full window: base * 2**attempt


async def test_gives_up_after_max_retries() -> None:
    p = Flaky(fail_times=99)
    with pytest.raises(TransientLLMError):
        await resilient(p, retries=2).complete(model="m", messages=MSGS)
    assert p.calls == 3


async def test_timeout_is_enforced_and_retried() -> None:
    p = Flaky(fail_times=0, delay=0.2)
    with pytest.raises(LLMTimeoutError):
        await resilient(p, retries=1, timeout=0.02).complete(model="m", messages=MSGS)
    assert p.calls == 2


def test_breaker_opens_then_half_opens() -> None:
    now = [0.0]
    b = CircuitBreaker(2, 10.0, clock=lambda: now[0])
    b.before_call()
    b.failure()
    b.before_call()
    b.failure()  # threshold reached
    with pytest.raises(LLMCircuitOpenError):
        b.before_call()
    now[0] = 11.0
    b.before_call()  # half-open: one trial allowed
    b.failure()  # trial fails => reopens immediately
    with pytest.raises(LLMCircuitOpenError):
        b.before_call()
    now[0] = 30.0
    b.before_call()
    b.success()
    b.before_call()  # closed again


async def test_open_breaker_short_circuits_without_calling_provider() -> None:
    p = Flaky(fail_times=99)
    b = CircuitBreaker(1, 60.0)
    llm = resilient(p, retries=0, breaker=b)
    with pytest.raises(TransientLLMError):
        await llm.complete(model="m", messages=MSGS)
    with pytest.raises(LLMCircuitOpenError):
        await llm.complete(model="m", messages=MSGS)
    assert p.calls == 1


async def test_stream_retries_only_before_first_token() -> None:
    p = Flaky(fail_times=1)
    pieces = [x async for x in resilient(p).stream(model="m", messages=MSGS)]
    assert pieces == ["a", "b"] and p.calls == 2

    class DiesMidStream(Flaky):
        async def stream(
            self, *, model: str, messages: Sequence[ChatMessage]
        ) -> AsyncIterator[str]:
            self.calls += 1
            yield "a"
            raise TransientLLMError("mid")

    q = DiesMidStream(fail_times=0)
    got: list[str] = []
    with pytest.raises(TransientLLMError):
        async for x in resilient(q).stream(model="m", messages=MSGS):
            got.append(x)
    assert got == ["a"] and q.calls == 1  # no replay of already-shown text


# ---- structured output ----------------------------------------------------------------


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    score: int


class Scripted:
    """Returns scripted texts in order."""

    name = "scripted"

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.seen: list[list[ChatMessage]] = []

    async def complete(
        self, *, model: str, messages: Sequence[ChatMessage], response_schema: Any = None
    ) -> Completion:
        self.seen.append(list(messages))
        return Completion(text=self.texts.pop(0), input_tokens=1, output_tokens=1, model=model)


async def test_structured_happy_path_with_fake_provider() -> None:
    out = await complete_structured(FakeLLM(), model="m", messages=MSGS, output=Summary)
    assert isinstance(out, Summary)


async def test_structured_repairs_once() -> None:
    s = Scripted('{"title": "x"}', '{"title": "x", "score": 3}')
    out = await complete_structured(s, model="m", messages=MSGS, output=Summary)
    assert out.score == 3 and len(s.seen) == 2
    repair_prompt = s.seen[1][-1].content
    assert "score" in repair_prompt and "valid JSON" in repair_prompt


async def test_structured_fails_after_one_repair_without_leaking_values() -> None:
    s = Scripted("not json SECRET_BOOK_TEXT", '{"title": 5, "score": "SECRET_BOOK_TEXT"}')
    with pytest.raises(LLMInvalidOutputError) as info:
        await complete_structured(s, model="m", messages=MSGS, output=Summary)
    assert "SECRET_BOOK_TEXT" not in str(info.value)
    assert len(s.seen) == 2


# ---- reranker --------------------------------------------------------------------------


async def test_fake_reranker_prefers_lexical_overlap() -> None:
    scores = await FakeReranker().rerank(
        query="nature of justice", passages=["the cat sat", "justice is the nature of the soul", ""]
    )
    assert scores[1] > scores[0] >= scores[2] == 0.0


# ---- budget ----------------------------------------------------------------------------


@pytest.mark.usefixtures("user_a")
async def test_daily_token_cap_blocks_further_calls(app: FastAPI, client: AsyncClient) -> None:
    user_id = uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        llm = AccountingLLM(FakeLLM(), session, AuthContext(user_id), daily_token_cap=50)
        big = [ChatMessage(role="user", content="word " * 200)]  # ~250 estimated tokens
        await llm.complete(model="m", messages=big)  # first call is under the cap when checked
        with pytest.raises(LLMBudgetExceededError):
            await llm.complete(model="m", messages=MSGS)
        with pytest.raises(LLMBudgetExceededError):
            await llm.embed(model="m", texts=["x"], dimensions=8)
        await session.rollback()


@pytest.mark.usefixtures("user_a")
async def test_zero_cap_means_unlimited(app: FastAPI, client: AsyncClient) -> None:
    user_id = uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        llm = AccountingLLM(FakeLLM(), session, AuthContext(user_id), daily_token_cap=0)
        for _ in range(3):
            await llm.complete(model="m", messages=[ChatMessage(role="user", content="w " * 500)])
        await session.rollback()
