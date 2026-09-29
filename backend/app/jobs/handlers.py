"""In-process job handlers keyed by `Job.kind`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import AuthContext
from app.core.logging import get_logger
from app.models.job import Job
from app.storage.local import LocalFileStorage

type Handler = Callable[[AsyncSession, AuthContext, Job], Awaitable[None]]

_HANDLERS: dict[str, Handler] = {}
log = get_logger("jobs.handlers")


def register(kind: str, handler: Handler) -> None:
    _HANDLERS[kind] = handler


def get_handler(kind: str) -> Handler | None:
    return _HANDLERS.get(kind)


async def handle_noop(session: AsyncSession, ctx: AuthContext, job: Job) -> None:
    """Phase-2 smoke handler: proves claim → RLS context → success path."""
    log.info("noop_job", job_id=str(job.id), user_id=str(ctx.user_id), stage=job.stage)
    _ = session


async def handle_ingest(session: AsyncSession, ctx: AuthContext, job: Job) -> None:
    from app.ingestion.pipeline import run_ingest

    settings = get_settings()
    storage = LocalFileStorage(settings.storage_root)
    await run_ingest(session, ctx, job, settings, storage)


def register_builtin_handlers() -> None:
    register("noop", handle_noop)
    register("ingest", handle_ingest)
