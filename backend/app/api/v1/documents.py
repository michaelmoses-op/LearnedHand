import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.core.deps import (
    AuthDbDep,
    AuthDep,
    LimiterDep,
    SettingsDep,
    StorageDep,
    csrf_protect,
)
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.generation.ask import AskService, DocumentNotReadyError, list_readable_sections
from app.repositories.content import ProgressRepository
from app.schemas.concepts import ConceptMapOut, TrajectoryOut
from app.schemas.documents import (
    DocumentOut,
    DocumentPage,
    DocumentStatusOut,
    QualityReportOut,
    ReingestIn,
)
from app.schemas.qa import AskIn, ProgressIn, ProgressOut, SectionListOut, SectionOut
from app.services.concepts import ConceptService
from app.services.documents import DocumentService, decode_cursor, encode_cursor

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(csrf_protect)])


def _sse(event: str, data: dict[str, object]) -> bytes:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


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


@router.get("/{document_id}/concepts", response_model=ConceptMapOut)
async def get_concept_map(
    document_id: uuid.UUID,
    auth: AuthDep,
    db: AuthDbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> ConceptMapOut:
    """Concept × section heat map, restricted to what the reader has reached."""
    return await ConceptService(db, auth).concept_map(document_id, limit)


@router.get("/{document_id}/concepts/{concept_id}/trajectory", response_model=TrajectoryOut)
async def get_concept_trajectory(
    document_id: uuid.UUID, concept_id: uuid.UUID, auth: AuthDep, db: AuthDbDep
) -> TrajectoryOut:
    """How one concept develops through the sections read so far."""
    return await ConceptService(db, auth).trajectory(document_id, concept_id)


@router.get("/{document_id}/quality", response_model=QualityReportOut)
async def get_quality_report(
    document_id: uuid.UUID, auth: AuthDep, db: AuthDbDep, storage: StorageDep
) -> QualityReportOut:
    doc = await DocumentService(db, auth, storage).repo.get(document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    return QualityReportOut(document_id=doc.id, report=doc.quality_report)


@router.post("/{document_id}/reingest", response_model=DocumentStatusOut, status_code=202)
async def reingest_document(
    document_id: uuid.UUID,
    body: ReingestIn,
    auth: AuthDep,
    db: AuthDbDep,
    storage: StorageDep,
    limiter: LimiterDep,
) -> DocumentStatusOut:
    """Re-run ingestion from a stage (default: first stale stage). Keeps reading progress."""
    limiter.check(f"reingest:user:{auth.user_id}", 20, 3600)
    doc = await DocumentService(db, auth, storage).reingest(document_id, body.from_stage)
    if doc is None:
        raise NotFoundError("Document not found")
    await db.commit()
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


@router.get("/{document_id}/sections", response_model=SectionListOut)
async def list_sections(document_id: uuid.UUID, auth: AuthDep, db: AuthDbDep) -> SectionListOut:
    rows = await list_readable_sections(db, auth, document_id)
    return SectionListOut(items=[SectionOut.model_validate(r) for r in rows])


@router.put("/{document_id}/progress", response_model=ProgressOut)
async def put_progress(
    document_id: uuid.UUID, body: ProgressIn, auth: AuthDep, db: AuthDbDep, storage: StorageDep
) -> ProgressOut:
    doc = await DocumentService(db, auth, storage).repo.get(document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    row = await ProgressRepository(db, auth).upsert(document_id, body.max_ordinal)
    await db.commit()
    return ProgressOut(document_id=document_id, max_ordinal=row.max_ordinal)


@router.post(
    "/{document_id}/ask",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE stream (status, sources, token, citations, done, error)",
            "content": {"text/event-stream": {}},
        }
    },
)
async def ask_document(
    document_id: uuid.UUID,
    body: AskIn,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
    storage: StorageDep,
    limiter: LimiterDep,
) -> StreamingResponse:
    """Cited Q&A over POST+fetch SSE (not EventSource — CSRF requires a custom header)."""
    limiter.check(f"ask:user:{auth.user_id}", 60, 3600)
    # Resolve ownership / readiness before streaming so IDOR clients get JSON 404/409.
    doc = await DocumentService(db, auth, storage).repo.get(document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    if doc.status != "ready":
        raise DocumentNotReadyError("Document is not ready for questions")

    async def events() -> AsyncIterator[bytes]:
        try:
            async for ev in AskService(db, auth, settings).ask_stream(
                document_id=document_id, question=body.question, limit=body.limit
            ):
                yield _sse(ev.event, ev.data)
            await db.commit()
        except Exception:
            await db.rollback()
            yield _sse("error", {"code": "ask_failed", "detail": "Ask failed"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
