from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient, Response

from app.core.config import Settings

D = "/api/v1/documents"
EPUB = b"PK\x03\x04" + b"epub-body-" * 20
PDF = b"%PDF-1.7\n" + b"pdf-body-" * 20


async def put(c: AsyncClient, data: bytes, name: str = "book.epub", **kw: str) -> Response:
    return await c.post(D, content=data, headers={"X-Filename": name, **kw})


def stored_files(settings: Settings) -> list[Path]:
    root = settings.storage_root
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


@pytest.mark.usefixtures("user_a")
async def test_upload_list_get_delete(client: AsyncClient, settings: Settings) -> None:
    r = await put(client, EPUB, "Godel_Escher  Bach.epub")
    assert r.status_code == 201
    doc = r.json()
    assert doc["format"] == "epub" and doc["status"] == "uploaded"
    assert doc["title"] == "Godel Escher Bach"
    assert len(stored_files(settings)) == 1

    assert (await client.get(f"{D}/{doc['id']}")).json()["id"] == doc["id"]
    assert [d["id"] for d in (await client.get(D)).json()["items"]] == [doc["id"]]

    assert (await client.delete(f"{D}/{doc['id']}")).status_code == 204
    assert (await client.get(f"{D}/{doc['id']}")).status_code == 404
    assert stored_files(settings) == []


@pytest.mark.usefixtures("user_a")
async def test_duplicate_upload_is_idempotent(client: AsyncClient, settings: Settings) -> None:
    first = await put(client, PDF, "a.pdf", **{"Idempotency-Key": "k1"})
    second = await put(client, PDF, "renamed.pdf", **{"Idempotency-Key": "k1"})
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(stored_files(settings)) == 1


@pytest.mark.usefixtures("user_a")
async def test_same_file_allowed_for_different_users(
    client: AsyncClient, client_b: AsyncClient, user_b: str
) -> None:
    a = await put(client, EPUB + b"shared")
    b = await put(client_b, EPUB + b"shared")
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


@pytest.mark.usefixtures("user_a")
@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"MZ\x90\x00 not a pdf", "evil.pdf"),  # wrong magic for extension
        (PDF, "book.epub"),  # magic doesn't match extension
        (EPUB, "book.exe"),  # extension not allowed
        (b"<html>", "book.epub"),
        (b"PK", "tiny.epub"),  # too short to verify
    ],
)
async def test_rejects_wrong_type(
    client: AsyncClient, settings: Settings, data: bytes, name: str
) -> None:
    r = await put(client, data, name)
    assert r.status_code == 415, r.text
    assert stored_files(settings) == []


@pytest.mark.usefixtures("user_a")
async def test_empty_upload_rejected(client: AsyncClient) -> None:
    assert (await put(client, b"")).status_code == 400


@pytest.mark.usefixtures("user_a")
async def test_oversize_aborted_and_nothing_left_behind(
    client: AsyncClient, settings: Settings
) -> None:
    big = b"PK\x03\x04" + b"x" * (settings.max_upload_bytes + 10)
    r = await put(client, big)
    assert r.status_code == 413
    assert stored_files(settings) == []


@pytest.mark.usefixtures("user_a")
async def test_oversize_without_content_length_is_capped_while_streaming(
    client: AsyncClient, settings: Settings
) -> None:
    async def gen() -> AsyncIterator[bytes]:
        yield b"PK\x03\x04"
        for _ in range(100):
            yield b"x" * 1024

    r = await client.post(D, content=gen(), headers={"X-Filename": "a.epub"})
    assert r.status_code == 413
    assert stored_files(settings) == []


@pytest.mark.usefixtures("user_a")
async def test_filename_cannot_influence_storage_path(
    client: AsyncClient, settings: Settings
) -> None:
    r = await put(client, EPUB, "../../etc/passwd.epub")
    assert r.status_code == 201
    assert r.json()["original_filename"] == "passwd.epub"
    for p in stored_files(settings):
        assert p.resolve().is_relative_to(settings.storage_root.resolve())


@pytest.mark.usefixtures("user_a")
async def test_pagination(client: AsyncClient) -> None:
    ids = []
    for i in range(5):
        ids.append((await put(client, EPUB + bytes([i]) * 10, f"b{i}.epub")).json()["id"])
    page1 = (await client.get(D, params={"limit": 2})).json()
    assert [d["id"] for d in page1["items"]] == ids[::-1][:2]
    assert page1["next_cursor"]
    page2 = (await client.get(D, params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    assert [d["id"] for d in page2["items"]] == ids[::-1][2:4]
    page3 = (await client.get(D, params={"limit": 2, "cursor": page2["next_cursor"]})).json()
    assert len(page3["items"]) == 1 and page3["next_cursor"] is None
    bad = await client.get(D, params={"cursor": "garbage"})
    assert bad.status_code == 400


@pytest.mark.usefixtures("user_a")
async def test_percent_encoded_filename_is_decoded(client: AsyncClient) -> None:
    r = await put(client, EPUB, "Caf%C3%A9%20Society.epub")
    assert r.status_code == 201
    assert r.json()["original_filename"] == "Café Society.epub"
