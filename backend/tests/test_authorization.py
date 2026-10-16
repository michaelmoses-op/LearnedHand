import re
import uuid
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import _asyncpg_dsn

EPUB = b"PK\x03\x04" + b"authz-" * 20

# Every /api/v1 route that takes an id belonging to a user, as (method, template).
# The completeness test below fails if a new ID-bearing route is added without an entry.
ID_ROUTES = [
    ("GET", "/api/v1/documents/{document_id}"),
    ("GET", "/api/v1/documents/{document_id}/status"),
    ("GET", "/api/v1/documents/{document_id}/sections"),
    ("GET", "/api/v1/documents/{document_id}/quality"),
    ("GET", "/api/v1/documents/{document_id}/summaries"),
    ("GET", "/api/v1/documents/{document_id}/concepts"),
    ("GET", "/api/v1/documents/{document_id}/concepts/{concept_id}/trajectory"),
    ("POST", "/api/v1/documents/{document_id}/reingest"),
    ("POST", "/api/v1/documents/{document_id}/ask"),
    ("DELETE", "/api/v1/documents/{document_id}"),
    ("POST", "/api/v1/documents/{document_id}/notes"),
    ("GET", "/api/v1/documents/{document_id}/notes"),
    ("PATCH", "/api/v1/documents/{document_id}/notes/{note_id}"),
    ("DELETE", "/api/v1/documents/{document_id}/notes/{note_id}"),
]
PUBLIC_ID_ROUTES: list[tuple[str, str]] = []


def _idor_kwargs(method: str, template: str = "") -> dict[str, Any]:
    bodies = {
        "/reingest": {},
        "/notes": {"body": "x"},
    }
    for suffix, body in bodies.items():
        if method in ("POST", "PATCH") and template.endswith(suffix):
            return {"json": body}
    if method == "PATCH":
        return {"json": {"body": "x"}}
    if method == "POST":
        return {"json": {"question": "x"}}
    return {}


def _fmt(template: str, document_id: object) -> str:
    return template.format(
        document_id=document_id,
        concept_id=uuid.uuid4(),
        note_id=uuid.uuid4(),
        card_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
    )


@pytest.fixture
def app_routes() -> list[tuple[str, str]]:
    from app.main import app

    found: list[tuple[str, str]] = []
    for path, ops in app.openapi()["paths"].items():
        if path.startswith("/api/v1") and re.search(r"\{\w+\}", path):
            found.extend((method.upper(), path) for method in ops)
    return found


def test_id_route_matrix_is_complete(app_routes: list[tuple[str, str]]) -> None:
    assert sorted(app_routes) == sorted(ID_ROUTES + PUBLIC_ID_ROUTES)


@pytest.mark.usefixtures("user_a", "user_b")
@pytest.mark.parametrize(("method", "template"), ID_ROUTES)
async def test_idor_other_users_resource_is_404(
    client: AsyncClient, client_b: AsyncClient, method: str, template: str
) -> None:
    doc = (
        await client.post("/api/v1/documents", content=EPUB, headers={"X-Filename": "a.epub"})
    ).json()
    url = _fmt(template, doc["id"])
    kwargs = _idor_kwargs(method, template)
    # B is refused with 404, identical to a resource that never existed.
    r_other = await client_b.request(method, url, **kwargs)
    r_missing = await client_b.request(method, _fmt(template, uuid.uuid4()), **kwargs)
    assert r_other.status_code == r_missing.status_code == 404
    assert r_other.json()["code"] == r_missing.json()["code"] == "not_found"
    # Owner's document untouched (delete by B did nothing).
    assert (await client.get(f"/api/v1/documents/{doc['id']}")).status_code == 200


@pytest.mark.usefixtures("user_a", "user_b")
async def test_list_only_shows_own_documents(client: AsyncClient, client_b: AsyncClient) -> None:
    await client.post("/api/v1/documents", content=EPUB, headers={"X-Filename": "a.epub"})
    assert (await client_b.get("/api/v1/documents")).json()["items"] == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/documents"),
        ("POST", "/api/v1/documents"),
        ("GET", f"/api/v1/documents/{uuid.uuid4()}"),
        ("GET", f"/api/v1/documents/{uuid.uuid4()}/status"),
        ("GET", f"/api/v1/documents/{uuid.uuid4()}/sections"),
        ("POST", f"/api/v1/documents/{uuid.uuid4()}/ask"),
        ("DELETE", f"/api/v1/documents/{uuid.uuid4()}"),
        ("GET", "/api/v1/auth/me"),
    ],
)
async def test_unauthenticated_is_401(client: AsyncClient, method: str, path: str) -> None:
    kwargs = _idor_kwargs(method, path)
    assert (await client.request(method, path, **kwargs)).status_code == 401


async def test_forged_token_rejected(client: AsyncClient) -> None:
    client.cookies.set("access", "not.a.jwt")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


# ---- Row-Level Security: must hold even when the repository filter is bypassed ----------


async def test_rls_blocks_cross_user_access_without_repository_filters(
    app: FastAPI,
    client: AsyncClient,
    client_b: AsyncClient,
    user_a: str,
    user_b: str,
    test_urls: tuple[str, str],
) -> None:
    doc_a = (
        await client.post("/api/v1/documents", content=EPUB, headers={"X-Filename": "a.epub"})
    ).json()
    me_a = (await client.get("/api/v1/auth/me")).json()["id"]
    me_b = (await client_b.get("/api/v1/auth/me")).json()["id"]

    conn = await asyncpg.connect(_asyncpg_dsn(test_urls[0]))  # runtime role: app_user
    try:
        role = await conn.fetchval("select current_user")
        assert role == "app_user"
        assert not await conn.fetchval(
            "select rolsuper or rolbypassrls from pg_roles where rolname = current_user"
        )

        async def visible(user_id: str | None) -> int:
            async with conn.transaction():
                if user_id:
                    await conn.execute(
                        "select set_config('app.current_user_id', $1, true)", user_id
                    )
                # Deliberately NO user_id filter: only RLS stands between us and the data.
                return int(
                    await conn.fetchval(
                        "select count(*) from documents where id = $1", uuid.UUID(doc_a["id"])
                    )
                )

        assert await visible(me_a) == 1
        assert await visible(me_b) == 0
        assert await visible(None) == 0  # no context => no rows

        async with conn.transaction():
            await conn.execute("select set_config('app.current_user_id', $1, true)", me_b)
            # B cannot delete or rewrite A's row, nor insert a row owned by A.
            assert await conn.execute("delete from documents") == "DELETE 0"
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await conn.execute(
                    "insert into documents (user_id, title, original_filename, format, "
                    "file_hash, file_size, storage_key) "
                    "values ($1, 't', 'f', 'pdf', 'h', 1, $2)",
                    uuid.UUID(me_a),
                    f"{me_a}/{uuid.uuid4().hex}",
                )
        async with conn.transaction():
            await conn.execute("select set_config('app.current_user_id', $1, true)", me_b)
            assert (
                await conn.fetchval(
                    "select count(*) from refresh_tokens where user_id = $1", uuid.UUID(me_a)
                )
                == 0
            )
    finally:
        await conn.close()
