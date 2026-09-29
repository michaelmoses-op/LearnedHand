from typing import Literal

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_origins_parsed_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def _settings(environment: Literal["dev", "prod"]) -> Settings:
    return Settings(
        _env_file=None,
        environment=environment,
        cors_origins=["https://app.example"],
        database_url="postgresql+asyncpg://u:p@h/db",
        secret_key="x" * 40,
    )


def test_origin_allowlist_is_strict_outside_dev() -> None:
    prod = _settings("prod")
    assert prod.origin_allowed("https://app.example")
    assert not prod.origin_allowed("http://localhost:5174")
    assert not prod.origin_allowed("https://evil.example")

    dev = _settings("dev")
    assert dev.origin_allowed("http://localhost:5174")
    assert dev.origin_allowed("http://127.0.0.1:5999")
    assert not dev.origin_allowed("http://localhost.evil.example")
    assert not dev.origin_allowed("https://evil.example")
