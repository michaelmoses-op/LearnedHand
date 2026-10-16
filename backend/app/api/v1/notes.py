"""Notes and highlights. Routers validate/serialise only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.deps import AuthDbDep, AuthDep, LimiterDep, csrf_protect
from app.schemas.notes import NoteIn, NoteListOut, NoteOut, NoteUpdate
from app.services.notes import NoteService

router = APIRouter(prefix="/documents", tags=["notes"], dependencies=[Depends(csrf_protect)])


@router.post("/{document_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(
    document_id: uuid.UUID, body: NoteIn, auth: AuthDep, db: AuthDbDep, limiter: LimiterDep
) -> NoteOut:
    limiter.check(f"notes:user:{auth.user_id}", 600, 3600)
    note = await NoteService(db, auth).create(document_id, body)
    out = NoteOut.model_validate(note, from_attributes=True)
    await db.commit()
    return out


@router.get("/{document_id}/notes", response_model=NoteListOut)
async def list_notes(
    document_id: uuid.UUID,
    auth: AuthDep,
    db: AuthDbDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[str | None, Query(pattern="^(note|highlight)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> NoteListOut:
    """Notes and highlights for this book; `q` is a full-text search."""
    rows = await NoteService(db, auth).list(document_id, q=q, kind=kind, limit=limit)
    return NoteListOut(items=[NoteOut.model_validate(r, from_attributes=True) for r in rows])


@router.patch("/{document_id}/notes/{note_id}", response_model=NoteOut)
async def update_note(
    document_id: uuid.UUID, note_id: uuid.UUID, body: NoteUpdate, auth: AuthDep, db: AuthDbDep
) -> NoteOut:
    note = await NoteService(db, auth).update(document_id, note_id, body.body)
    out = NoteOut.model_validate(note, from_attributes=True)
    await db.commit()
    return out


@router.delete("/{document_id}/notes/{note_id}", status_code=204)
async def delete_note(
    document_id: uuid.UUID, note_id: uuid.UUID, auth: AuthDep, db: AuthDbDep
) -> Response:
    await NoteService(db, auth).delete(document_id, note_id)
    await db.commit()
    return Response(status_code=204)
