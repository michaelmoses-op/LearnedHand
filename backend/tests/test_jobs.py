"""Job queue: enqueue, SKIP LOCKED claim, RLS context, retries."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.deps import AuthContext, set_rls_user
from app.jobs.handlers import handle_noop, register_builtin_handlers
from app.jobs.queue import (
    backoff_seconds,
    claim_next,
    mark_failed,
    mark_succeeded,
    requeue_stale_running,
)
from app.jobs.worker import process_one
from app.models.document import Document
from app.models.job import Job
from app.repositories.jobs import JobRepository
from tests.conftest import _asyncpg_dsn


@pytest.fixture(autouse=True)
def _handlers() -> None:
    register_builtin_handlers()


@pytest.fixture(autouse=True)
async def _wipe_jobs(test_urls: tuple[str, str]) -> AsyncIterator[None]:
    """Jobs are global to the claim path; clear them so tests cannot steal each other's work."""
    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[1]))
    try:
        await conn.execute("truncate jobs")
    finally:
        await conn.close()
    yield


async def _user_id(client: AsyncClient) -> uuid.UUID:
    me = (await client.get("/api/v1/auth/me")).json()
    return uuid.UUID(me["id"])


@pytest.mark.usefixtures("user_a")
async def test_enqueue_and_process_noop(app: FastAPI, client: AsyncClient) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        repo = JobRepository(session, AuthContext(user_id))
        job = await repo.enqueue(kind="noop", stage="smoke", payload={"n": 1})
        await session.commit()
        job_id = job.id

    assert await process_one(app.state.sessionmaker, "test-worker-1")

    async with app.state.sessionmaker() as session:
        done = await session.get(Job, job_id)
        assert done is not None
        assert done.status == "succeeded"
        assert done.attempts == 1
        assert done.locked_by is None


@pytest.mark.usefixtures("user_a", "user_b")
async def test_claim_sets_rls_so_only_owner_documents_visible(
    app: FastAPI, client: AsyncClient, client_b: AsyncClient
) -> None:
    """After claim, set_rls_user(job.user_id) must scope document reads."""
    epub = b"PK\x03\x04" + b"jobs-rls-" * 20
    doc_a = (
        await client.post("/api/v1/documents", content=epub, headers={"X-Filename": "a.epub"})
    ).json()
    await client_b.post(
        "/api/v1/documents",
        content=epub + b"b",
        headers={"X-Filename": "b.epub"},
    )
    user_a = await _user_id(client)

    async with app.state.sessionmaker() as session:
        # Uploads enqueue ingest jobs; clear them so this test claims the noop we create.
        await session.execute(delete(Job))
        await session.commit()

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_a)
        job = await JobRepository(session, AuthContext(user_a)).enqueue(kind="noop")
        await session.commit()
        job_id = job.id

    async with app.state.sessionmaker() as session:
        claimed = await claim_next(session, "rls-worker")
        await session.commit()
    assert claimed is not None and claimed.id == job_id and claimed.user_id == user_a

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, claimed.user_id)
        # Deliberately no user_id filter — only RLS should hide B's docs.
        rows = (await session.execute(select(Document))).scalars().all()
        assert [str(r.id) for r in rows] == [doc_a["id"]]
        await handle_noop(session, AuthContext(claimed.user_id), claimed)
        await mark_succeeded(session, claimed)
        await session.commit()


@pytest.mark.usefixtures("user_a")
async def test_concurrent_claim_skips_locked_row(app: FastAPI, client: AsyncClient) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        repo = JobRepository(session, AuthContext(user_id))
        await repo.enqueue(kind="noop")
        await repo.enqueue(kind="noop")
        await session.commit()

    async with app.state.sessionmaker() as s1, app.state.sessionmaker() as s2:
        # Hold the first claim transaction open so SKIP LOCKED matters for the second.
        j1 = await claim_next(s1, "w1")
        j2 = await claim_next(s2, "w2")
        await s1.commit()
        await s2.commit()

    assert j1 is not None and j2 is not None
    assert j1.id != j2.id


@pytest.mark.usefixtures("user_a")
async def test_failure_retries_then_marks_failed(app: FastAPI, client: AsyncClient) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        job = await JobRepository(session, AuthContext(user_id)).enqueue(
            kind="noop", max_attempts=2
        )
        await session.commit()
        job_id = job.id

    async with app.state.sessionmaker() as session:
        claimed = await claim_next(session, "w")
        assert claimed is not None
        await mark_failed(session, claimed, error="boom")
        await session.commit()
        mid = await session.get(Job, job_id)
        assert mid is not None
        assert mid.status == "pending"
        assert mid.attempts == 1
        assert mid.run_at > datetime.now(UTC)
        mid.run_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with app.state.sessionmaker() as session:
        claimed = await claim_next(session, "w")
        assert claimed is not None and claimed.attempts == 2
        await mark_failed(session, claimed, error="boom_again")
        await session.commit()
        done = await session.get(Job, job_id)
        assert done is not None
        assert done.status == "failed"
        assert done.error == "boom_again"


@pytest.mark.usefixtures("user_a")
async def test_stale_running_requeued(app: FastAPI, client: AsyncClient) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        await JobRepository(session, AuthContext(user_id)).enqueue(kind="noop")
        await session.commit()

    async with app.state.sessionmaker() as session:
        claimed = await claim_next(session, "dead-worker")
        assert claimed is not None
        claimed.locked_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()
        job_id = claimed.id

    async with app.state.sessionmaker() as session:
        n = await requeue_stale_running(session, older_than=timedelta(minutes=15))
        await session.commit()
        assert n == 1
        row = await session.get(Job, job_id)
        assert row is not None and row.status == "pending" and row.locked_by is None


@pytest.mark.usefixtures("user_a", "user_b")
async def test_repository_get_is_user_scoped(
    app: FastAPI, client: AsyncClient, client_b: AsyncClient
) -> None:
    user_a = await _user_id(client)
    user_b = await _user_id(client_b)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_a)
        job = await JobRepository(session, AuthContext(user_a)).enqueue(kind="noop")
        await session.commit()
        job_id = job.id

    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_b)
        assert await JobRepository(session, AuthContext(user_b)).get(job_id) is None


def test_backoff_caps() -> None:
    assert backoff_seconds(1) == 2
    assert backoff_seconds(12) == 3600  # 2**12 capped at 3600


@pytest.mark.usefixtures("user_a")
async def test_unknown_handler_fails_job(app: FastAPI, client: AsyncClient) -> None:
    user_id = await _user_id(client)
    async with app.state.sessionmaker() as session:
        await set_rls_user(session, user_id)
        # `ingest` is a valid kind; no handler registered yet → retryable failure.
        job = await JobRepository(session, AuthContext(user_id)).enqueue(kind="ingest")
        await session.commit()
        job_id = job.id

    assert await process_one(app.state.sessionmaker, "w")
    async with app.state.sessionmaker() as session:
        row = await session.get(Job, job_id)
        assert row is not None
        assert row.status == "pending"
        assert row.error is not None and "handler_failed" in row.error
