"""Build the configured LLM stack: provider -> resilience -> accounting/budget."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import DomainError
from app.llm.accounting import AccountingLLM
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLM
from app.llm.openai_provider import OpenAIProvider
from app.llm.resilient import ResilientLLM, breaker_for


class LLMConfigError(DomainError):
    code = "llm_config"
    title = "LLM configuration error"


def build_provider(settings: Settings) -> LLMProvider:
    """Return the provider named by `LLM_PROVIDER` (fake needs no key, and is not wrapped so
    tests stay deterministic and instant)."""
    if settings.llm_provider == "fake":
        return FakeLLM()
    if settings.llm_provider == "openai":
        if not settings.llm_api_key:
            raise LLMConfigError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        raw = OpenAIProvider(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        return ResilientLLM(
            raw,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            breaker=breaker_for(
                "openai", settings.llm_breaker_threshold, settings.llm_breaker_cooldown_seconds
            ),
        )
    raise LLMConfigError(f"Provider {settings.llm_provider!r} is not implemented")


def build_llm(
    settings: Settings,
    session: AsyncSession,
    ctx: AuthContext,
    *,
    document_id: uuid.UUID | None = None,
    stage: str | None = None,
) -> AccountingLLM:
    """The one way feature code should get an LLM: accounting + per-user budget included."""
    return AccountingLLM(
        build_provider(settings),
        session,
        ctx,
        document_id=document_id,
        stage=stage,
        daily_token_cap=settings.llm_daily_token_cap,
    )
