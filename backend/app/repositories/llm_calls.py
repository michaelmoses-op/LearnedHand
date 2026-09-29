"""AuthContext-scoped llm_calls writes. Never stores prompt/completion text."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models.llm_call import LlmCall


class LlmCallRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def add(
        self,
        *,
        provider: str,
        model: str,
        kind: str,
        status: str = "ok",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        latency_ms: int = 0,
        error_code: str | None = None,
        document_id: uuid.UUID | None = None,
        stage: str | None = None,
    ) -> LlmCall:
        row = LlmCall(
            user_id=self.ctx.user_id,
            document_id=document_id,
            provider=provider,
            model=model,
            kind=kind,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            error_code=error_code,
            stage=stage,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_recent(self, *, limit: int = 50) -> list[LlmCall]:
        stmt = (
            select(LlmCall)
            .where(LlmCall.user_id == self.ctx.user_id)
            .order_by(LlmCall.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def tokens_today(self) -> int:
        """Input + output tokens this user consumed since 00:00 UTC."""
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(
            func.coalesce(func.sum(LlmCall.input_tokens + LlmCall.output_tokens), 0)
        ).where(LlmCall.user_id == self.ctx.user_id, LlmCall.created_at >= start)
        return int((await self.session.execute(stmt)).scalar_one())
