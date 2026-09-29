import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.models import EmailToken, RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def add(
        self, family_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        row = RefreshToken(
            user_id=self.ctx.user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == self.ctx.user_id, RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == self.ctx.user_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all(self) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == self.ctx.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )


class EmailTokenRepository:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx

    async def add(self, purpose: str, token_hash: str, expires_at: datetime) -> None:
        self.session.add(
            EmailToken(
                user_id=self.ctx.user_id,
                purpose=purpose,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await self.session.flush()

    async def consume(self, purpose: str, token_hash: str) -> bool:
        """Atomically mark a valid, unused, unexpired token as used."""
        result = await self.session.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == self.ctx.user_id,
                EmailToken.purpose == purpose,
                EmailToken.token_hash == token_hash,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > datetime.now(UTC),
            )
            .values(used_at=datetime.now(UTC))
            .returning(EmailToken.id)
        )
        return result.first() is not None
