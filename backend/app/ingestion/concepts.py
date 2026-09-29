"""Concept extraction: per-section concepts (from section summaries), merged across the book.

Working from the summaries keeps this to one small LLM call per section. Where a concept name
actually occurs in the chunks is found lexically, so its visibility follows where the reader has
really been, not where the model says it is.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.llm.structured import complete_structured
from app.models.chunk import Chunk
from app.models.concept import Concept, ConceptMention
from app.models.document import Document
from app.models.section import Section
from app.models.summary import Summary
from app.prompts import load_prompt
from app.repositories.concepts import ConceptRepository

MAX_PER_SECTION = 8
MAX_CONCEPTS = 400
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_ARTICLE = re.compile(r"^(the|a|an) ")


class ExtractedConcept(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    note: str = Field(default="", max_length=600)


class SectionConcepts(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list)


def concept_key(name: str) -> str:
    """Merge key: lowercase, punctuation-free, article-free, crudely singularised."""
    k = " ".join(_NON_ALNUM.sub(" ", name.lower()).split())
    k = _ARTICLE.sub("", k)
    words = k.split()
    if words and len(words[-1]) > 4 and words[-1].endswith("s") and not words[-1].endswith("ss"):
        words[-1] = words[-1][:-1]
    return " ".join(words)[:200]


def _locate(name: str, chunks: list[Chunk], fallback: int) -> tuple[int, int, int]:
    """(first_ordinal, last_ordinal, chunks_mentioning). Falls back to the section's last chunk,
    so an unlocated concept only becomes visible once the whole section has been read."""
    needle = name.lower()
    hits = [c.ordinal for c in chunks if needle in c.body.lower()]
    if not hits:
        return fallback, fallback, 0
    return min(hits), max(hits), len(hits)


async def build_concepts(
    session: AsyncSession,
    ctx: AuthContext,
    settings: Settings,
    llm: AccountingLLM,
    doc: Document,
    sections: list[Section],
    chunks: list[Chunk],
    summaries: list[Summary],
) -> tuple[int, int]:
    """Returns (concepts, mentions) written."""
    system = load_prompt("concepts")
    summary_by_section = {s.section_id: s for s in summaries if s.kind == "section"}
    chunks_by_section: dict[uuid.UUID, list[Chunk]] = {}
    for c in chunks:
        chunks_by_section.setdefault(c.section_id, []).append(c)

    concepts: dict[str, Concept] = {}
    mentions: list[ConceptMention] = []
    for sec in sections:
        summary = summary_by_section.get(sec.id)
        own = chunks_by_section.get(sec.id, [])
        if summary is None or not own or sec.last_chunk_ordinal is None:
            continue
        user = (
            f"Book: {doc.title}\nSection: {sec.title}\n\n"
            f'<part_summary title="{sec.title[:200]}">\n{summary.body}\n</part_summary>\n\n'
            "List the concepts now."
        )
        out = await complete_structured(
            llm,
            model=settings.ingest_model,
            messages=[ChatMessage("system", system), ChatMessage("user", user)],
            output=SectionConcepts,
        )
        seen: set[str] = set()
        for item in out.concepts[:MAX_PER_SECTION]:
            name = " ".join(item.name.split())
            key = concept_key(name)
            if len(key) < 2 or key in seen:
                continue
            seen.add(key)
            if key not in concepts and len(concepts) >= MAX_CONCEPTS:
                continue
            concept = concepts.get(key)
            if concept is None:
                concept = Concept(id=uuid.uuid4(), name=name[:200], key=key, first_ordinal=0)
                concepts[key] = concept
            first, last, count = _locate(name, own, sec.last_chunk_ordinal)
            mentions.append(
                ConceptMention(
                    concept_id=concept.id,
                    section_id=sec.id,
                    first_ordinal=first,
                    last_ordinal=last,
                    section_last_ordinal=sec.last_chunk_ordinal,
                    mention_chunks=count,
                    note=" ".join(item.note.split())[:600],
                )
            )

    earliest: dict[uuid.UUID, int] = {}
    for m in mentions:
        earliest[m.concept_id] = min(earliest.get(m.concept_id, m.first_ordinal), m.first_ordinal)
    for concept in concepts.values():
        concept.first_ordinal = earliest.get(concept.id, 0)
    await ConceptRepository(session, ctx).replace_for_document(
        doc.id, list(concepts.values()), mentions
    )
    return len(concepts), len(mentions)
