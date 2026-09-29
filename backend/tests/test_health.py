from httpx import AsyncClient

from app.core.config import Settings


async def test_healthz(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz_checks_database(client: AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


async def test_readyz_unavailable_when_db_down(settings: Settings) -> None:
    from httpx import ASGITransport

    from app.main import create_app

    bad = settings.model_copy(update={"database_url": "postgresql+asyncpg://x:y@127.0.0.1:1/none"})
    app = create_app(bad)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/readyz")
    assert r.status_code == 503


async def test_security_headers_and_request_id(client: AsyncClient) -> None:
    r = await client.get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
