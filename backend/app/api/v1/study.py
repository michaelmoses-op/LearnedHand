"""Learning features: notes/highlights, flashcards, quizzes. Routers validate/serialise only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.deps import AuthDbDep, AuthDep, LimiterDep, SettingsDep, csrf_protect
from app.schemas.study import (
    AnswerIn,
    AnswerOut,
    FlashcardListOut,
    FlashcardOut,
    GenerateIn,
    GenerateOut,
    NoteIn,
    NoteListOut,
    NoteOut,
    NoteUpdate,
    QuizListOut,
    QuizQuestionOut,
    ReviewIn,
)
from app.services.study import NoteService, StudyService

router = APIRouter(prefix="/documents", tags=["study"], dependencies=[Depends(csrf_protect)])


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
    """Notes and highlights up to your reading progress; `q` is a full-text search."""
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


@router.post("/{document_id}/study/generate", response_model=GenerateOut)
async def generate_study_material(
    document_id: uuid.UUID,
    body: GenerateIn,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
) -> GenerateOut:
    """Flashcards or quiz questions from what you have already read (most recent passages)."""
    limiter.check(f"study_generate:user:{auth.user_id}", 30, 3600)
    out = await StudyService(db, auth, settings).generate(document_id, body)
    await db.commit()
    return out


@router.get("/{document_id}/flashcards", response_model=FlashcardListOut)
async def list_flashcards(
    document_id: uuid.UUID,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
    due: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FlashcardListOut:
    rows = await StudyService(db, auth, settings).list_cards(document_id, due_only=due, limit=limit)
    return FlashcardListOut(
        items=[FlashcardOut.model_validate(r, from_attributes=True) for r in rows]
    )


@router.post("/{document_id}/flashcards/{card_id}/review", response_model=FlashcardOut)
async def review_flashcard(
    document_id: uuid.UUID,
    card_id: uuid.UUID,
    body: ReviewIn,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
) -> FlashcardOut:
    card = await StudyService(db, auth, settings).review(document_id, card_id, body.rating)
    out = FlashcardOut.model_validate(card, from_attributes=True)
    await db.commit()
    return out


@router.get("/{document_id}/quiz", response_model=QuizListOut)
async def list_quiz(
    document_id: uuid.UUID,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> QuizListOut:
    rows = await StudyService(db, auth, settings).list_quiz(document_id, limit)
    return QuizListOut(
        items=[QuizQuestionOut.model_validate(r, from_attributes=True) for r in rows]
    )


@router.post("/{document_id}/quiz/{question_id}/answer", response_model=AnswerOut)
async def answer_quiz(
    document_id: uuid.UUID,
    question_id: uuid.UUID,
    body: AnswerIn,
    auth: AuthDep,
    db: AuthDbDep,
    settings: SettingsDep,
) -> AnswerOut:
    correct, q = await StudyService(db, auth, settings).answer(
        document_id, question_id, body.choice
    )
    out = AnswerOut(correct=correct, answer_index=q.answer_index, explanation=q.explanation)
    await db.commit()
    return out
