import base64
import hashlib
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext
from app.core.errors import (
    ConflictError,
    DomainError,
    PayloadTooLargeError,
    UnsupportedFileError,
)
from app.models import Document
from app.repositories.documents import DocumentRepository
from app.repositories.jobs import JobRepository
from app.storage.base import Storage
from app.storage.local import new_key

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # EPUB is a ZIP; full EPUB validation happens in the worker.
_MAGIC_BYTES_NEEDED = 5


def sanitize_filename(name: str | None) -> str:
    """Display-only. The filename never influences storage paths."""
    base = PurePath((name or "").replace("\\", "/")).name
    base = "".join(c for c in unicodedata.normalize("NFC", base) if c.isprintable())
    return base[:255] or "untitled"


def detect_format(filename: str, head: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext == ".pdf" and head.startswith(_PDF_MAGIC):
        return "pdf"
    if ext == ".epub" and head.startswith(_ZIP_MAGIC):
        return "epub"
    raise UnsupportedFileError("Only .epub and .pdf files with matching content are accepted")


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename).stem
    return re.sub(r"[_\s]+", " ", stem).strip()[:200] or "Untitled"


def encode_cursor(created_at: datetime, doc_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{doc_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, _, raw_id = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        return datetime.fromisoformat(ts), uuid.UUID(raw_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise DomainError("Invalid cursor") from exc


@dataclass
class _Progress:
    size: int = 0
    format: str = ""


class DocumentService:
    def __init__(self, session: AsyncSession, ctx: AuthContext, storage: Storage) -> None:
        self.session, self.ctx, self.storage = session, ctx, storage
        self.repo = DocumentRepository(session, ctx)

    async def upload(
        self, stream: AsyncIterator[bytes], filename: str | None, max_bytes: int
    ) -> tuple[Document, bool]:
        """Stream to storage, enforcing the size cap while streaming and checking magic bytes on
        the first bytes. Returns (document, created). Duplicate content returns the existing
        document (created=False), which also makes retries idempotent."""
        name = sanitize_filename(filename)
        key = new_key(self.ctx.user_id)
        sha = hashlib.sha256()
        progress = _Progress()

        async def guarded() -> AsyncIterator[bytes]:
            head = bytearray()
            async for chunk in stream:
                if not chunk:
                    continue
                progress.size += len(chunk)
                if progress.size > max_bytes:
                    raise PayloadTooLargeError(f"File exceeds {max_bytes} bytes")
                sha.update(chunk)
                if progress.format:
                    yield chunk
                    continue
                head += chunk
                if len(head) >= _MAGIC_BYTES_NEEDED:
                    progress.format = detect_format(name, bytes(head))
                    yield bytes(head)
            if not progress.format:
                if not head:
                    raise DomainError("Empty upload")
                progress.format = detect_format(name, bytes(head))  # raises: too short
                yield bytes(head)

        try:
            await self.storage.put_stream(key, guarded())
        except BaseException:
            await self.storage.delete(key)
            raise

        file_hash = sha.hexdigest()
        existing = await self.repo.find_by_hash(file_hash)
        if existing is not None:
            await self.storage.delete(key)
            return existing, False
        doc = Document(
            title=title_from_filename(name),
            original_filename=name,
            format=progress.format,
            file_hash=file_hash,
            file_size=progress.size,
            storage_key=key,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(doc)
        except IntegrityError as exc:
            await self.storage.delete(key)
            raise ConflictError("Concurrent upload of the same file") from exc
        # Kick off ingest (idempotent stages). Duplicate content returns early above.
        await JobRepository(self.session, self.ctx).enqueue(
            kind="ingest", document_id=doc.id, stage="pending"
        )
        return doc, True

    async def status(self, document_id: uuid.UUID) -> Document | None:
        return await self.repo.get(document_id)

    async def delete(self, document_id: uuid.UUID) -> bool:
        doc = await self.repo.delete(document_id)
        if doc is None:
            return False
        await self.storage.delete(doc.storage_key)
        return True
