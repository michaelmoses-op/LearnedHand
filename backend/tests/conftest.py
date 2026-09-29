import os
import re
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
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

    async def wipe() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(mig))
        try:
            await conn.execute("truncate users cascade")
        finally:
            await conn.close()

    asyncio.run(wipe())
    yield


SECRET = "test-secret-key-0123456789abcdef0123456789"
PASSWORD = "correct horse battery"


class CapturingMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def token_for(self, to: str, subject_contains: str) -> str:
        for rcpt, subject, body in reversed(self.sent):
            if rcpt == to and subject_contains in subject:
                match = re.search(r"token=(\S+)", body)
                assert match
                return match.group(1)
        raise AssertionError(f"no mail to {to} matching {subject_contains}")


@pytest.fixture
def settings(test_urls: tuple[str, str], tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=test_urls[0],
        cors_origins=["http://localhost:5173"],
        secret_key=SECRET,
        storage_root=tmp_path / "storage",
        rate_limit_enabled=False,
        max_upload_bytes=4096,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    application.state.mailer = CapturingMailer()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
def mailer(app: FastAPI) -> CapturingMailer:
    m = app.state.mailer
    assert isinstance(m, CapturingMailer)
    return m


def build_client(app: FastAPI, auto_csrf: bool = True) -> AsyncClient:
    """A browser-like client (own cookie jar). auto_csrf mimics the frontend API client."""

    async def add_csrf(request: httpx.Request) -> None:
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and "x-csrf-token" not in request.headers
        ):
            token = http_client.cookies.get("csrf")
            if token:
                request.headers["x-csrf-token"] = token

    http_client = AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        event_hooks={"request": [add_csrf]} if auto_csrf else {},
    )
    return http_client


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with build_client(app) as c:
        yield c


@pytest.fixture
async def client_b(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with build_client(app) as c:
        yield c


async def register_and_login(c: AsyncClient, email: str | None = None) -> str:
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    r = await c.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD})
    assert r.status_code == 202, r.text
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 204, r.text
    return email


@pytest.fixture
async def user_a(client: AsyncClient) -> str:
    return await register_and_login(client)


@pytest.fixture
async def user_b(client_b: AsyncClient) -> str:
    return await register_and_login(client_b)
