"""Notes/highlights, flashcards and quizzes — all gated by the reader's progress."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.generation.ask import DocumentNotReadyError
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.factory import build_llm
from app.llm.structured import complete_structured
from app.models.chunk import Chunk
from app.models.study import Flashcard, Note, QuizQuestion
from app.prompts import load_prompt
from app.repositories.content import ProgressRepository, SectionRepository
from app.repositories.documents import DocumentRepository
from app.repositories.study import FlashcardRepository, NoteRepository, QuizRepository
from app.schemas.study import GenerateIn, GenerateOut, NoteIn

MAX_PASSAGES = 8  # most recent chunks read
MAX_PASSAGE_CHARS = 1500
MIN_EASE = 1.3
AGAIN_DELAY = timedelta(minutes=10)


class BeyondProgressError(DomainError):
    status = 422
    code = "beyond_progress"
    title = "Beyond your reading progress"


class InvalidInputError(DomainError):
    status = 422
    code = "invalid_input"
    title = "Invalid input"


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))[:200]


async def progress_for(session: AsyncSession, ctx: AuthContext, document_id: uuid.UUID) -> int:
    """404 for unknown/other users' documents; -1 (nothing readable) when no progress is set."""
    if await DocumentRepository(session, ctx).get(document_id) is None:
        raise NotFoundError("Document not found")
    row = await ProgressRepository(session, ctx).get(document_id)
    return row.max_ordinal if row else -1


# ---- notes --------------------------------------------------------------------------------


class NoteService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session, self.ctx = session, ctx
        self.repo = NoteRepository(session, ctx)

    async def create(self, document_id: uuid.UUID, data: NoteIn) -> Note:
        progress = await progress_for(self.session, self.ctx, document_id)
        if progress < 0:
            raise ConflictError("Set your reading progress before adding notes")
        anchor = progress if data.anchor_ordinal is None else data.anchor_ordinal
        if anchor > progress:
            raise BeyondProgressError("You can only annotate what you have read")
        return await self.repo.add(
            Note(
                document_id=document_id,
                kind=data.kind,
                anchor_ordinal=anchor,
                quote=data.quote.strip() if data.quote else None,
                body=data.body.strip(),
            )
        )

    async def list(
        self, document_id: uuid.UUID, *, q: str | None, kind: str | None, limit: int
    ) -> list[Note]:
        progress = await progress_for(self.session, self.ctx, document_id)
        return await self.repo.search(document_id, progress, q=q, kind=kind, limit=limit)

    async def update(self, document_id: uuid.UUID, note_id: uuid.UUID, body: str) -> Note:
        progress = await progress_for(self.session, self.ctx, document_id)
        note = await self.repo.get(document_id, note_id, progress)
        if note is None:
            raise NotFoundError("Note not found")
        if note.kind == "note" and not body.strip():
            raise InvalidInputError("A note needs text")
        note.body = body.strip()
        note.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def delete(self, document_id: uuid.UUID, note_id: uuid.UUID) -> None:
        progress = await progress_for(self.session, self.ctx, document_id)
        if not await self.repo.delete(document_id, note_id, progress):
            raise NotFoundError("Note not found")


# ---- scheduling (SM-2 style) --------------------------------------------------------------

_QUALITY = {"again": 0, "hard": 3, "good": 4, "easy": 5}


def next_state(
    *, ease: float, interval_days: int, reps: int, lapses: int, rating: str, now: datetime
) -> tuple[float, int, int, int, datetime]:
    """Returns (ease, interval_days, reps, lapses, due_at)."""
    q = _QUALITY[rating]
    if q < 3:
        return max(MIN_EASE, ease - 0.2), 0, 0, lapses + 1, now + AGAIN_DELAY
    reps += 1
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 3
    else:
        interval = max(interval_days + 1, round(interval_days * ease))
    if rating == "hard":
        ease = max(MIN_EASE, ease - 0.15)
        interval = max(1, round(interval * 0.8))
    elif rating == "easy":
        ease += 0.15
        interval = round(interval * 1.3)
    return ease, interval, reps, lapses, now + timedelta(days=interval)


# ---- generation, review, quiz -------------------------------------------------------------


class CardDraft(BaseModel):
    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=1500)
    source_ordinal: int


class CardBatch(BaseModel):
    cards: list[CardDraft] = Field(max_length=20)


class QuizDraft(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    choices: list[str] = Field(min_length=2, max_length=5)
    answer_index: int = Field(ge=0)
    explanation: str = Field(default="", max_length=800)
    source_ordinal: int


class QuizBatch(BaseModel):
    questions: list[QuizDraft] = Field(max_length=20)


class StudyService:
    def __init__(self, session: AsyncSession, ctx: AuthContext, settings: Settings) -> None:
        self.session, self.ctx, self.settings = session, ctx, settings
        self.cards = FlashcardRepository(session, ctx)
        self.quiz = QuizRepository(session, ctx)

    async def _read_passages(
        self, document_id: uuid.UUID, progress: int, section_id: uuid.UUID | None
    ) -> list[Chunk]:
        stmt = select(Chunk).where(
            Chunk.user_id == self.ctx.user_id,
            Chunk.document_id == document_id,
            Chunk.ordinal <= progress,  # the spoiler gate
        )
        if section_id is not None:
            sections = await SectionRepository(self.session, self.ctx).list_for_document(
                document_id
            )
            sec = next((s for s in sections if s.id == section_id), None)
            if sec is None or sec.first_chunk_ordinal is None or sec.first_chunk_ordinal > progress:
                raise NotFoundError("Section not found")  # unknown or not yet reached
            stmt = stmt.where(Chunk.section_id == section_id)
        stmt = stmt.order_by(Chunk.ordinal.desc()).limit(MAX_PASSAGES)
        return sorted((await self.session.execute(stmt)).scalars(), key=lambda c: c.ordinal)

    async def generate(self, document_id: uuid.UUID, data: GenerateIn) -> GenerateOut:
        doc = await DocumentRepository(self.session, self.ctx).get(document_id)
        if doc is None:
            raise NotFoundError("Document not found")
        if doc.status != "ready":
            raise DocumentNotReadyError("Document is not ready")
        progress = await progress_for(self.session, self.ctx, document_id)
        if progress < 0:
            raise ConflictError("Set your reading progress before generating study material")
        chunks = await self._read_passages(document_id, progress, data.section_id)
        if not chunks:
            raise ConflictError("Nothing to study yet")
        allowed = {c.ordinal for c in chunks}
        passages = "\n".join(
            f'<passage ordinal="{c.ordinal}">\n{c.body[:MAX_PASSAGE_CHARS]}\n</passage>'
            for c in chunks
        )
        llm = build_llm(
            self.settings, self.session, self.ctx, document_id=document_id, stage="study"
        )
        if data.kind == "flashcards":
            return await self._make_cards(llm, document_id, passages, allowed, data.count)
        return await self._make_quiz(llm, document_id, passages, allowed, data.count)

    async def _make_cards(
        self,
        llm: AccountingLLM,
        document_id: uuid.UUID,
        passages: str,
        allowed: set[int],
        count: int,
    ) -> GenerateOut:
        batch = await complete_structured(
            llm,
            model=self.settings.llm_model,
            messages=[
                ChatMessage("system", load_prompt("flashcards")),
                ChatMessage("user", f"{passages}\n\nCreate up to {count} flashcards."),
            ],
            output=CardBatch,
        )
        seen = await self.cards.existing_keys(document_id)
        new: list[Flashcard] = []
        for d in batch.cards:
            key = _key(d.front)
            # A draft citing a passage we did not send (or a duplicate) is discarded.
            if d.source_ordinal not in allowed or not key or key in seen or len(new) >= count:
                continue
            seen.add(key)
            new.append(
                Flashcard(
                    front=d.front.strip(),
                    back=d.back.strip(),
                    front_key=key,
                    source_ordinal=d.source_ordinal,
                )
            )
        await self.cards.add_many(document_id, new)
        return GenerateOut(kind="flashcards", created=len(new), skipped=len(batch.cards) - len(new))

    async def _make_quiz(
        self,
        llm: AccountingLLM,
        document_id: uuid.UUID,
        passages: str,
        allowed: set[int],
        count: int,
    ) -> GenerateOut:
        batch = await complete_structured(
            llm,
            model=self.settings.llm_model,
            messages=[
                ChatMessage("system", load_prompt("quiz")),
                ChatMessage("user", f"{passages}\n\nCreate up to {count} questions."),
            ],
            output=QuizBatch,
        )
        seen = await self.quiz.existing_keys(document_id)
        new: list[QuizQuestion] = []
        for d in batch.questions:
            key = _key(d.question)
            choices = [c.strip() for c in d.choices]
            valid = (
                d.source_ordinal in allowed
                and key
                and key not in seen
                and d.answer_index < len(choices)
                and all(choices)
                and len({c.lower() for c in choices}) == len(choices)
                and len(new) < count
            )
            if not valid:
                continue
            seen.add(key)
            new.append(
                QuizQuestion(
                    question=d.question.strip(),
                    question_key=key,
                    choices=choices,
                    answer_index=d.answer_index,
                    explanation=d.explanation.strip(),
                    source_ordinal=d.source_ordinal,
                )
            )
        await self.quiz.add_many(document_id, new)
        return GenerateOut(kind="quiz", created=len(new), skipped=len(batch.questions) - len(new))

    async def list_cards(
        self, document_id: uuid.UUID, *, due_only: bool, limit: int
    ) -> list[Flashcard]:
        progress = await progress_for(self.session, self.ctx, document_id)
        return await self.cards.list_visible(
            document_id, progress, due_before=datetime.now(UTC) if due_only else None, limit=limit
        )

    async def review(self, document_id: uuid.UUID, card_id: uuid.UUID, rating: str) -> Flashcard:
        progress = await progress_for(self.session, self.ctx, document_id)
        card = await self.cards.get_visible(document_id, card_id, progress)
        if card is None:
            raise NotFoundError("Flashcard not found")
        now = datetime.now(UTC)
        card.ease, card.interval_days, card.reps, card.lapses, card.due_at = next_state(
            ease=card.ease,
            interval_days=card.interval_days,
            reps=card.reps,
            lapses=card.lapses,
            rating=rating,
            now=now,
        )
        card.last_reviewed_at = now
        await self.session.flush()
        return card

    async def list_quiz(self, document_id: uuid.UUID, limit: int) -> list[QuizQuestion]:
        progress = await progress_for(self.session, self.ctx, document_id)
        return await self.quiz.list_visible(document_id, progress, limit)

    async def answer(
        self, document_id: uuid.UUID, question_id: uuid.UUID, choice: int
    ) -> tuple[bool, QuizQuestion]:
        progress = await progress_for(self.session, self.ctx, document_id)
        q = await self.quiz.get_visible(document_id, question_id, progress)
        if q is None:
            raise NotFoundError("Question not found")
        if choice >= len(q.choices):
            raise InvalidInputError("Unknown choice")
        correct = choice == q.answer_index
        q.times_answered += 1
        q.times_correct += int(correct)
        await self.session.flush()
        return correct, q
