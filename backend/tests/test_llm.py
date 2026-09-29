"""Fake LLM provider + llm_calls accounting."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.factory import LLMConfigError, build_provider
from app.llm.fake import FakeLLM
from app.models.llm_call import LlmCall
from app.repositories.llm_calls import LlmCallRepository
from tests.conftest import _asyncpg_dsn


@pytest.fixture(autouse=True)
async def _wipe_llm_calls(test_urls: tuple[str, str]) -> AsyncIterator[None]:
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[1]))
    try:
        await conn.execute("truncate llm_calls")
    finally:
        await conn.close()
    yield


async def _user_id(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])


def test_build_provider_defaults_to_fake() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@h/db",
        secret_key="x" * 40,
        llm_provider="fake",
        llm_model="my-chat",
        embedding_model="my-embed",
        embedding_dim=16,
    )
    assert isinstance(build_provider(settings), FakeLLM)


def test_openai_provider_requires_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@h/db",
        secret_key="x" * 40,
        llm_provider="openai",
    )
    with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
        build_provider(settings)


def test_anthropic_provider_not_implemented() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@h/db",
        secret_key="x" * 40,
        llm_provider="anthropic",
    )
    with pytest.raises(LLMConfigError, match="not implemented"):
        build_provider(settings)


@pytest.mark.asyncio
async def test_fake_complete_and_stream_are_deterministic() -> None:
    llm = FakeLLM()
    msgs = [ChatMessage(role="user", content="What is justice?")]
    a = await llm.complete(model="fake-chat", messages=msgs)
    b = await llm.complete(model="fake-chat", messages=msgs)
    assert a.text == b.text
    assert "justice" not in a.text.lower()  # never echo untrusted passage text
    assert a.model == "fake-chat"

    streamed: list[str] = []
    async for part in llm.stream(model="fake-chat", messages=msgs):
        streamed.append(part)
    assert "".join(streamed).replace(" ", "") == a.text.replace(" ", "")


@pytest.mark.asyncio
async def test_fake_embed_dim_and_determinism() -> None:
    llm = FakeLLM()
    batch = await llm.embed(model="fake-embed", texts=["alpha", "beta"], dimensions=16)
    assert batch.dimensions == 16
    assert len(batch.vectors) == 2
    assert all(len(v) == 16 for v in batch.vectors)
    again = await llm.embed(model="fake-embed", texts=["alpha"], dimensions=16)
    assert again.vectors[0] == batch.vectors[0]
    # Different text => different vector
    other = await llm.embed(model="fake-embed", texts=["gamma"], dimensions=16)
    assert other.vectors[0] != batch.vectors[0]


@pytest.mark.usefixtures("user_a")
async def test_accounting_writes_metadata_only(
    app: FastAPI, client: AsyncClient, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    user_id = await _user_id(client)
    msgs = [ChatMessage(role="user", content="SECRET_PASSAGE_SHOULD_NOT_BE_STORED")]
    with caplog.at_level(logging.INFO):
        async with app.state.sessionmaker() as session:
            await set_rls_user(session, user_id)
            llm = AccountingLLM(build_provider(settings), session, AuthContext(user_id))
            result = await llm.complete(model=settings.llm_model, messages=msgs)
            await session.commit()

    assert "SECRET_PASSAGE" not in caplog.text
    assert result.text  # got a completion

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        rows = await LlmCallRepository(session, AuthContext(user_id)).list_recent()
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "complete" and row.status == "ok"
        assert row.provider == "fake" and row.model == settings.llm_model
        assert row.input_tokens > 0 and row.output_tokens > 0
        # ORM row has no text fields for prompts — only metadata columns.
        assert not hasattr(row, "prompt")
        assert set(LlmCall.__table__.columns.keys()) == {
            "id",
            "user_id",
            "document_id",
            "provider",
            "model",
            "kind",
            "status",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "stage",
            "latency_ms",
            "error_code",
            "created_at",
        }


@pytest.mark.usefixtures("user_a")
async def test_accounting_stream_and_embed(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        llm = AccountingLLM(build_provider(settings), session, AuthContext(user_id))
        parts = [
            p
            async for p in llm.stream(
                model=settings.llm_model, messages=[ChatMessage(role="user", content="hi")]
            )
        ]
        assert parts
        emb = await llm.embed(
            model=settings.embedding_model, texts=["a"], dimensions=settings.embedding_dim
        )
        assert len(emb.vectors[0]) == settings.embedding_dim
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        kinds = {
            r.kind for r in await LlmCallRepository(session, AuthContext(user_id)).list_recent()
        }
        assert kinds == {"stream", "embed"}


@pytest.mark.usefixtures("user_a", "user_b")
async def test_llm_calls_rls_hides_other_users_rows(
    app: FastAPI, client: AsyncClient, client_b: AsyncClient, test_urls: tuple[str, str]
) -> None:
    user_a = await _user_id(client)
    user_b = await _user_id(client_b)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_a)
        await AccountingLLM(FakeLLM(), session, AuthContext(user_a)).complete(
            model="fake-chat", messages=[ChatMessage(role="user", content="a")]
        )
        await session.commit()

    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[0]))
    try:
        async with conn.transaction():
            await conn.execute("select set_config('app.current_user_id', $1, true)", str(user_b))
            # No repository filter — RLS alone must hide A's rows.
            n = await conn.fetchval("select count(*) from llm_calls")
            assert n == 0
        async with conn.transaction():
            await conn.execute("select set_config('app.current_user_id', $1, true)", str(user_a))
            n = await conn.fetchval("select count(*) from llm_calls")
            assert n == 1
    finally:
        await conn.close()


@pytest.mark.usefixtures("user_a", "user_b")
async def test_repository_list_is_user_scoped(
    app: FastAPI, client: AsyncClient, client_b: AsyncClient
) -> None:
    user_a = await _user_id(client)
    user_b = await _user_id(client_b)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_a)
        await LlmCallRepository(session, AuthContext(user_a)).add(
            provider="fake", model="m", kind="complete"
        )
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_b)
        assert await LlmCallRepository(session, AuthContext(user_b)).list_recent() == []


@pytest.mark.usefixtures("user_a")
async def test_embed_error_is_accounted(
    app: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    user_id = await _user_id(client)

    class Boom(FakeLLM):
        async def embed(self, *, model: str, texts, dimensions: int):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        llm = AccountingLLM(Boom(), session, AuthContext(user_id))
        with pytest.raises(RuntimeError):
            await llm.embed(model=settings.embedding_model, texts=["x"], dimensions=8)
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        rows = await LlmCallRepository(session, AuthContext(user_id)).list_recent()
        assert len(rows) == 1
        assert rows[0].status == "error" and rows[0].error_code == "embed_failed"
