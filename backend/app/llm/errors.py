"""LLM layer errors. Messages never contain prompts, completions, or book text."""

from __future__ import annotations

from app.core.errors import DomainError


class LLMError(DomainError):
    status = 502
    code = "llm_error"
    title = "LLM provider error"


class TransientLLMError(LLMError):
    """Retryable: timeouts, connection failures, 429s, 5xx."""

    status = 503
    code = "llm_unavailable"
    title = "LLM temporarily unavailable"


class PermanentLLMError(LLMError):
    """Not retryable: bad request, auth failure, unknown model."""

    code = "llm_rejected"
    title = "LLM request rejected"


class LLMTimeoutError(TransientLLMError):
    status = 504
    code = "llm_timeout"
    title = "LLM call timed out"


class LLMCircuitOpenError(TransientLLMError):
    code = "llm_circuit_open"
    title = "LLM provider is failing; calls paused briefly"


class LLMBudgetExceededError(LLMError):
    status = 429
    code = "llm_budget_exceeded"
    title = "Daily LLM budget exceeded"


class LLMInvalidOutputError(LLMError):
    code = "llm_invalid_output"
    title = "LLM returned output that failed validation"
