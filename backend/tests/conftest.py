import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _test_urls() -> tuple[str, str]:
    s = get_settings()
    url = os.environ.get("TEST_DATABASE_URL") or s.test_database_url
    mig = os.environ.get("TEST_MIGRATION_DATABASE_URL") or s.test_migration_database_url
    if not url or not mig:
        pytest.exit(
            "TEST_DATABASE_URL / TEST_MIGRATION_DATABASE_URL not set. See docs/LOCAL_SETUP.md.",
            returncode=2,
        )
    return url, mig


def alembic(mig_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-x", f"url={mig_url}", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def test_urls() -> tuple[str, str]:
    return _test_urls()


@pytest.fixture(scope="session", autouse=True)
def migrated_db(test_urls: tuple[str, str]) -> Iterator[None]:
    import asyncio

    url, mig = test_urls

    async def check() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(url), timeout=5)
        await conn.close()

    try:
        asyncio.run(check())
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"Cannot reach the test database ({type(exc).__name__}). "
            "Run scripts/setup_db.sh and see docs/LOCAL_SETUP.md.",
            returncode=2,
        )
    result = alembic(mig, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    yield


@pytest.fixture
def settings(test_urls: tuple[str, str]) -> Settings:
    return Settings(
        environment="test",
        database_url=test_urls[0],
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
