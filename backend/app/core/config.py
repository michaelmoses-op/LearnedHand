import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_ORIGIN_PATTERN = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
_DEV_ORIGIN = re.compile(DEV_ORIGIN_PATTERN)
_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """All configuration comes from the environment. Missing required values fail at startup."""

    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str
    migration_database_url: str | None = None
    test_database_url: str | None = None
    test_migration_database_url: str | None = None
    db_pool_size: int = Field(default=5, ge=1, le=100)

    secret_key: str = Field(min_length=32)
    access_token_ttl_minutes: int = Field(default=15, ge=1)
    refresh_token_ttl_days: int = Field(default=30, ge=1)
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    rate_limit_enabled: bool = True
    frontend_base_url: str = "http://localhost:5173"

    cookie_secure: bool = False
    # Comma-separated in the environment (honcho/dotenv-safe), e.g. http://a,http://b
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    llm_provider: Literal["fake", "openai", "anthropic"] = "fake"
    # Model IDs come from env — never hard-code provider model strings in call sites.
    llm_model: str = Field(default="fake-chat", min_length=1, max_length=100)
    embedding_model: str = Field(default="fake-embed", min_length=1, max_length=100)
    # Must equal the chunks.embedding column width (ingestion/constants.py). pgvector's HNSW
    # index supports at most 2000 dimensions for `vector`.
    embedding_dim: int = Field(default=1536, ge=8, le=2000)
    llm_api_key: str | None = None  # unused while LLM_PROVIDER=fake
    llm_base_url: str | None = None  # OpenAI-compatible gateways / test servers
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_breaker_threshold: int = Field(default=5, ge=1)
    llm_breaker_cooldown_seconds: float = Field(default=30.0, gt=0)
    # Per-user daily token budget (input + output, all calls). 0 disables the cap.
    llm_daily_token_cap: int = Field(default=5_000_000, ge=0)
    # Optional cheaper model for high-volume ingestion calls (prefixes, summaries).
    llm_ingest_model: str | None = None
    # USD per 1M tokens, used only for cost reporting (evals). 0 = unknown/free.
    price_input_per_mtok: float = Field(default=0.0, ge=0)
    price_output_per_mtok: float = Field(default=0.0, ge=0)

    reranker: Literal["none", "fake", "cross_encoder"] = "none"
    reranker_model: str = "BAAI/bge-reranker-base"
    storage_root: Path = Path("./var/storage")

    @property
    def ingest_model(self) -> str:
        return self.llm_ingest_model or self.llm_model

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def origin_allowed(self, origin: str) -> bool:
        """Explicit allowlist; in `dev` only, any localhost/127.0.0.1 port (Vite may pick a
        different port). Never relaxed outside dev."""
        if origin in self.cors_origins:
            return True
        return self.environment == "dev" and bool(_DEV_ORIGIN.match(origin))


@lru_cache
def get_settings() -> Settings:
    return Settings()
