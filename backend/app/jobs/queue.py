"""Worker-only claim / complete / fail. User-scoped enqueue is JobRepository (AuthContext)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

# Cap backoff so a poisoned job is not silent for days.
_MAX_BACKOFF_SECONDS = 3600


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff after a failed attempt (`attempts` is post-increment)."""
    delay = 2 ** max(attempts, 0)
    return delay if delay < _MAX_BACKOFF_SECONDS else _MAX_BACKOFF_SECONDS


async def claim_next(session: AsyncSession, worker_id: str) -> Job | None:
    """Atomically claim the next due pending job (`FOR UPDATE SKIP LOCKED`).

    No AuthContext: claiming is cross-user by design (ADR-0007). Caller must set RLS
    from `job.user_id` before touching user-owned tables.
    """
    # Nested SELECT keeps SKIP LOCKED in the lock clause; UPDATE … RETURNING is the claim.
    stmt = text(
        """
        UPDATE jobs
        SET status = 'running',
            locked_at = now(),
            locked_by = :worker_id,
            attempts = attempts + 1,
            updated_at = now(),
            error = NULL
        WHERE id = (
            SELECT id FROM jobs
            WHERE status = 'pending' AND run_at <= now()
            ORDER BY run_at ASC, created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id
        """
    )
    result = await session.execute(stmt, {"worker_id": worker_id})
    row = result.first()
    if row is None:
        return None
    job = await session.get(Job, row[0])
    if job is None:  # pragma: no cover — RETURNING id must exist
        return None
    return job


async def mark_succeeded(session: AsyncSession, job: Job) -> None:
    job.status = "succeeded"
    job.locked_at = None
    job.locked_by = None
    job.error = None
    job.updated_at = datetime.now(UTC)
    await session.flush()


async def mark_failed(session: AsyncSession, job: Job, *, error: str, retry: bool = True) -> None:
    """Record failure. Retries re-queue as pending with backoff unless attempts exhausted.

    `error` must be a safe summary — never document text, prompts, or tokens.
    """
    safe = error[:500]
    now = datetime.now(UTC)
    if retry and job.attempts < job.max_attempts:
        job.status = "pending"
        job.run_at = now + timedelta(seconds=backoff_seconds(job.attempts))
        job.locked_at = None
        job.locked_by = None
        job.error = safe
    else:
        job.status = "failed"
        job.locked_at = None
        job.locked_by = None
        job.error = safe
    job.updated_at = now
    await session.flush()


async def requeue_stale_running(session: AsyncSession, *, older_than: timedelta) -> int:
    """Return stale `running` jobs to `pending` (worker crash recovery)."""
    cutoff = datetime.now(UTC) - older_than
    stmt = (
        update(Job)
        .where(Job.status == "running", Job.locked_at.is_not(None), Job.locked_at < cutoff)
        .values(
            status="pending",
            locked_at=None,
            locked_by=None,
            updated_at=datetime.now(UTC),
            error="requeued: stale lock",
        )
        .returning(Job.id)
    )
    result = await session.execute(stmt)
    return len(result.all())


def new_worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:12]}"
