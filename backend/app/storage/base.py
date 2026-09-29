from collections.abc import AsyncIterator
from typing import Protocol


class Storage(Protocol):
    """Blob storage interface. A future S3 implementation (presigned uploads) is a drop-in."""

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> int:
        """Write chunks under `key`; returns bytes written. Must not leave partial files."""
        ...

    def open(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...
