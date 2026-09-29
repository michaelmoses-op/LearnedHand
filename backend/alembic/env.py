import asyncio

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import get_settings
from app.models.base import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Tests/CI may override via `-x url=...`; otherwise use the owner-role URL.
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    settings = get_settings()
    return settings.migration_database_url or settings.database_url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_async())
