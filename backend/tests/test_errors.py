from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import DomainError, NotFoundError
from app.main import create_app


class Body(BaseModel):
    n: int


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("no such thing")

    @app.get("/domain")
    async def domain() -> None:
        raise DomainError()

    @app.post("/body")
    async def body(b: Body) -> Body:
        return b

    return app


async def _get(settings: Settings, method: str, path: str, **kw):  # type: ignore[no-untyped-def]
    app = _app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
        ) as c,
    ):
        return await c.request(method, path, **kw)


async def test_domain_error_is_problem_json(settings: Settings) -> None:
    r = await _get(settings, "GET", "/missing")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "not_found"


async def test_unknown_route_is_problem_json(settings: Settings) -> None:
    r = await _get(settings, "GET", "/nope")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_unhandled_error_hides_details(settings: Settings) -> None:
    r = await _get(settings, "GET", "/boom")
    assert r.status_code == 500
    assert "secret internals" not in r.text
    assert r.json()["code"] == "internal_error"


async def test_validation_error_does_not_echo_input(settings: Settings) -> None:
    r = await _get(settings, "POST", "/body", json={"n": "hunter2-not-an-int"})
    assert r.status_code == 422
    assert "hunter2" not in r.text
    assert r.json()["code"] == "validation_error"
