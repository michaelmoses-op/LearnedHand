import uuid
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.core.deps import (
    AuthDbDep,
    AuthDep,
    LimiterDep,
    SettingsDep,
    StorageDep,
    csrf_protect,
)
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.repositories.content import ProgressRepository
from app.schemas.documents import DocumentOut, DocumentPage, DocumentStatusOut
from app.services.documents import DocumentService, decode_cursor, encode_cursor

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(csrf_protect)])


@router.post(
    "", response_model=DocumentOut, status_code=201, responses={200: {"model": DocumentOut}}
)
async def upload_document(
    request: Request,
    response: Response,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
    storage: StorageDep,
    limiter: LimiterDep,
    x_filename: Annotated[str | None, Header(max_length=255)] = None,
    idempotency_key: Annotated[str | None, Header(max_length=100)] = None,
) -> DocumentOut:
    """Raw-body streaming upload (body = file bytes, name in `X-Filename`).

    Re-uploading identical content returns the existing document with 200, so retries with
    an `Idempotency-Key` (or without) are safe.
    """
    limiter.check(f"upload:user:{auth.user_id}", 30, 3600)
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > settings.max_upload_bytes:
        raise PayloadTooLargeError()
    service = DocumentService(db, auth, storage)
    # Clients percent-encode the name so non-ASCII filenames survive HTTP headers.
    filename = unquote(x_filename) if x_filename else None
    doc, created = await service.upload(request.stream(), filename, settings.max_upload_bytes)
    await db.commit()
    if not created:
        response.status_code = 200
    return DocumentOut.model_validate(doc)


@router.get("", response_model=DocumentPage)
async def list_documents(
    auth: AuthDep,
    db: AuthDbDep,
    storage: StorageDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> DocumentPage:
    service = DocumentService(db, auth, storage)
    after = decode_cursor(cursor) if cursor else None
    rows = await service.repo.list(limit + 1, after)
    page, more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if more and page else None
    return DocumentPage(
        items=[DocumentOut.model_validate(r) for r in page], next_cursor=next_cursor
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID, auth: AuthDep, db: AuthDbDep, storage: StorageDep
) -> DocumentOut:
    doc = await DocumentService(db, auth, storage).repo.get(document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def get_document_status(
    document_id: uuid.UUID, auth: AuthDep, db: AuthDbDep, storage: StorageDep
) -> DocumentStatusOut:
    doc = await DocumentService(db, auth, storage).repo.get(document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    progress = await ProgressRepository(db, auth).get(document_id)
    return DocumentStatusOut(
        id=doc.id,
        status=doc.status,
        ingest_stage=doc.ingest_stage,
        error=doc.error,
        max_ordinal=progress.max_ordinal if progress else None,
        updated_at=doc.updated_at,
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, auth: AuthDep, db: AuthDbDep, storage: StorageDep
) -> Response:
    if not await DocumentService(db, auth, storage).delete(document_id):
        raise NotFoundError("Document not found")
    await db.commit()
    return Response(status_code=204)
