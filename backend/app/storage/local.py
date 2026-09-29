import asyncio
import contextlib
import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

_KEY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{32}$")


def new_key(user_id: uuid.UUID) -> str:
    """Server-generated storage key. Never derived from user-supplied names."""
    return f"{user_id}/{uuid.uuid4().hex}"


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # defense in depth against traversal
            raise ValueError("invalid storage key")
        return path

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> int:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True, mode=0o700)
        tmp = path.with_name(path.name + ".part")
        written = 0
        fd = await asyncio.to_thread(os.open, tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in chunks:
                    await asyncio.to_thread(f.write, chunk)
                    written += len(chunk)
            await asyncio.to_thread(os.replace, tmp, path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(os.unlink, tmp)
            raise
        return written

    async def open(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        with path.open("rb") as f:
            while chunk := await asyncio.to_thread(f.read, 1024 * 1024):
                yield chunk

    async def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            await asyncio.to_thread(os.unlink, self._path(key))

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)
