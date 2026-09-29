"""Build the configured LLM provider. Real HTTP providers are stubs until keys are wired."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import DomainError
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLM


class LLMConfigError(DomainError):
    code = "llm_config"
    title = "LLM configuration error"


def build_provider(settings: Settings) -> LLMProvider:
    """Return the provider named by `LLM_PROVIDER`. Default is fake (no API key)."""
    if settings.llm_provider == "fake":
        return FakeLLM()
    # Phase 2 ships fake only; names are reserved so env can switch later without schema churn.
    raise LLMConfigError(
        f"Provider {settings.llm_provider!r} is not enabled in this build; set LLM_PROVIDER=fake"
    )
