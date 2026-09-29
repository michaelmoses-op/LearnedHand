"""Enqueue and inspect jobs. Every method requires AuthContext (user_id stamped / filtered).

Cross-user claim lives in `app.jobs.queue` (worker-only); see ADR-0007.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.job import Job


class JobRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def enqueue(
        self,
        *,
        kind: str,
        stage: str = "pending",
        document_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 5,
    ) -> Job:
        job = Job(
            user_id=self.ctx.user_id,
            document_id=document_id,
            kind=kind,
            stage=stage,
            payload=payload or {},
            max_attempts=max_attempts,
            status="pending",
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        stmt = select(Job).where(Job.user_id == self.ctx.user_id, Job.id == job_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_document(self, document_id: uuid.UUID, *, limit: int = 50) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.user_id == self.ctx.user_id, Job.document_id == document_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())
