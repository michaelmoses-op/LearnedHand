"""Timeouts, retries with jittered backoff, and a circuit breaker around any provider."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

from app.llm.base import ChatMessage, Completion, EmbeddingBatch, LLMProvider
from app.llm.errors import LLMCircuitOpenError, LLMTimeoutError, TransientLLMError


class CircuitBreaker:
    """Opens after `threshold` consecutive transient failures; half-opens after `cooldown`."""

    def __init__(
        self,
        threshold: int,
        cooldown: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold, self.cooldown, self._clock = threshold, cooldown, clock
        self._failures = 0
        self._opened_at: float | None = None

    def before_call(self) -> None:
        if self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self.cooldown:
            self._opened_at = None  # half-open: let one attempt through
            self._failures = self.threshold - 1
            return
        raise LLMCircuitOpenError()

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = self._clock()


_BREAKERS: dict[str, CircuitBreaker] = {}


def breaker_for(name: str, threshold: int, cooldown: float) -> CircuitBreaker:
    """Process-wide breaker per provider so failures are shared across requests."""
    if name not in _BREAKERS:
        _BREAKERS[name] = CircuitBreaker(threshold, cooldown)
    return _BREAKERS[name]


class ResilientLLM:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        timeout: float,
        max_retries: int,
        breaker: CircuitBreaker,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._p = provider
        self._timeout = timeout
        self._max_retries = max_retries
        self._breaker = breaker
        self._base, self._max = base_delay, max_delay
        self._sleep, self._rand = sleep, rand

    @property
    def name(self) -> str:
        return self._p.name

    def _delay(self, attempt: int) -> float:
        # Full jitter: uniform(0, min(cap, base * 2^attempt)).
        return float(self._rand() * min(self._max, self._base * (2**attempt)))

    async def _call[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            self._breaker.before_call()
            try:
                async with asyncio.timeout(self._timeout):
                    result = await fn()
            except TimeoutError:
                err: TransientLLMError = LLMTimeoutError()
            except TransientLLMError as exc:
                err = exc
            else:
                self._breaker.success()
                return result
            self._breaker.failure()
            if attempt >= self._max_retries:
                raise err
            await self._sleep(self._delay(attempt))
            attempt += 1

    async def complete(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        response_schema: dict[str, Any] | None = None,
    ) -> Completion:
        return await self._call(
            lambda: self._p.complete(
                model=model, messages=messages, response_schema=response_schema
            )
        )

    async def embed(self, *, model: str, texts: Sequence[str], dimensions: int) -> EmbeddingBatch:
        return await self._call(
            lambda: self._p.embed(model=model, texts=texts, dimensions=dimensions)
        )

    async def stream(self, *, model: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Retries only until the first token; once tokens flow, a failure surfaces as-is
        (re-sending would duplicate text already shown to the user)."""
        attempt = 0
        while True:
            self._breaker.before_call()
            it = self._p.stream(model=model, messages=messages).__aiter__()
            try:
                async with asyncio.timeout(self._timeout):
                    first = await it.__anext__()
            except StopAsyncIteration:
                self._breaker.success()
                return
            except TimeoutError:
                err: TransientLLMError = LLMTimeoutError()
            except TransientLLMError as exc:
                err = exc
            else:
                self._breaker.success()
                yield first
                while True:
                    try:
                        async with asyncio.timeout(self._timeout):
                            piece = await it.__anext__()
                    except StopAsyncIteration:
                        return
                    except TimeoutError:
                        raise LLMTimeoutError() from None
                    yield piece
            await it.aclose()  # type: ignore[attr-defined]
            self._breaker.failure()
            if attempt >= self._max_retries:
                raise err
            await self._sleep(self._delay(attempt))
            attempt += 1
