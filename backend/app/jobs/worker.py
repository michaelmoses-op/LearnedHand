"""Worker entrypoint: claim jobs, set RLS from job.user_id, run handlers, ack/retry."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.db import make_engine, make_sessionmaker, ping
from app.core.deps import AuthContext, set_rls_user
from app.core.logging import configure_logging, get_logger
from app.jobs.handlers import get_handler, register_builtin_handlers
from app.jobs.queue import (
    claim_next,
    mark_failed,
    mark_succeeded,
    new_worker_id,
    requeue_stale_running,
)
from app.models.job import Job

POLL_IDLE_SECONDS = 1.0
HEARTBEAT_SECONDS = 30
STALE_RUNNING = timedelta(minutes=15)


async def process_one(sessionmaker: async_sessionmaker[AsyncSession], worker_id: str) -> bool:
    """Claim and run at most one job. Returns True if a job was claimed."""
    log = get_logger("worker")
    async with sessionmaker() as session:
        job = await claim_next(session, worker_id)
        if job is None:
            await session.commit()
            return False
        job_id = job.id
        await session.commit()  # release claim row lock before long work

    async with sessionmaker() as session:
        # Re-load under a fresh transaction with the job owner's RLS context.
        claimed = await session.get(Job, job_id)
        if claimed is None or claimed.status != "running":
            await session.commit()
            return True
        ctx = AuthContext(claimed.user_id)
        await set_rls_user(session, ctx.user_id)
        handler = get_handler(claimed.kind)
        try:
            if handler is None:
                raise RuntimeError(f"no_handler:{claimed.kind}")
            await handler(session, ctx, claimed)
            await mark_succeeded(session, claimed)
            await session.commit()
            log.info("job_succeeded", job_id=str(claimed.id), kind=claimed.kind)
        except Exception as exc:
            # Never log exception args that might contain passage text from future handlers.
            await mark_failed(session, claimed, error=f"{type(exc).__name__}: handler_failed")
            await session.commit()
            log.warning(
                "job_failed",
                job_id=str(claimed.id),
                kind=claimed.kind,
                error_type=type(exc).__name__,
                attempts=claimed.attempts,
                status=claimed.status,
            )
    return True


async def run(stop: asyncio.Event) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("worker")
    register_builtin_handlers()
    worker_id = new_worker_id()
    engine: AsyncEngine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    last_heartbeat = asyncio.get_running_loop().time()
    try:
        log.info("worker_started", worker_id=worker_id, database_ok=await ping(engine))
        async with sessionmaker() as session:
            n = await requeue_stale_running(session, older_than=STALE_RUNNING)
            await session.commit()
            if n:
                log.info("stale_jobs_requeued", count=n)
        while not stop.is_set():
            worked = await process_one(sessionmaker, worker_id)
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                log.info("worker_heartbeat", database_ok=await ping(engine), worker_id=worker_id)
                last_heartbeat = now
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=POLL_IDLE_SECONDS)
    finally:
        await engine.dispose()
        log.info("worker_stopped", worker_id=worker_id)


def main() -> None:
    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
