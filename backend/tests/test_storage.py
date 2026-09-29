import stat
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.storage.local import LocalFileStorage, new_key


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for p in parts:
        yield p


async def test_roundtrip_permissions_and_delete(tmp_path: Path) -> None:
    s = LocalFileStorage(tmp_path)
    key = new_key(uuid.uuid4())
    assert await s.put_stream(key, _chunks(b"ab", b"cd")) == 4
    assert await s.exists(key)
    assert b"".join([c async for c in s.open(key)]) == b"abcd"
    mode = stat.S_IMODE((tmp_path / key).stat().st_mode)
    assert mode == 0o600
    await s.delete(key)
    assert not await s.exists(key)
    await s.delete(key)  # idempotent


@pytest.mark.parametrize(
    "key", ["../evil", "/etc/passwd", "a/b", "x" * 10, f"{uuid.uuid4()}/../../x"]
)
async def test_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    s = LocalFileStorage(tmp_path)
    with pytest.raises(ValueError, match="invalid storage key"):
        await s.exists(key)


async def test_failed_write_leaves_no_partial_file(tmp_path: Path) -> None:
    s = LocalFileStorage(tmp_path)
    key = new_key(uuid.uuid4())

    async def boom() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("client went away")

    with pytest.raises(RuntimeError):
        await s.put_stream(key, boom())
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []  # noqa: ASYNC240
