import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    """Identity store used by the auth flows. Deliberately not user-scoped: login and signup
    must resolve a user from an email before any AuthContext exists. Never used by feature
    code (documents, etc.), which go through AuthContext-scoped repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def create(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user
