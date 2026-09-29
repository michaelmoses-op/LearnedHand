"""Hierarchical summarisation: leaf sections -> parents -> book, bottom-up.

A summary covers a range of chunk ordinals and is only ever readable once the reader has passed
`last_ordinal` (spoiler gate; enforced in `retrieval.pipeline` and `SummaryRepository`).
Long inputs are map-reduced so no single LLM call exceeds SUMMARY_INPUT_TOKENS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext
from app.ingestion.chunking import count_tokens
from app.ingestion.constants import (
    EMBEDDING_DIMENSION,
    STAGE_VERSIONS,
    SUMMARY_INPUT_TOKENS,
)
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.section import Section
from app.models.summary import Summary
from app.prompts import load_prompt
from app.repositories.summaries import SummaryRepository


@dataclass
class _Node:
    section: Section
    children: list[_Node] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    summary: str = ""
    first: int | None = None
    last: int | None = None


@dataclass(frozen=True)
class _Part:
    kind: str  # "passage" | "part_summary"
    label: str
    text: str


def _render(parts: list[_Part]) -> str:
    return "\n\n".join(f'<{p.kind} title="{_attr(p.label)}">\n{p.text}\n</{p.kind}>' for p in parts)


def _attr(value: str) -> str:
    return value.replace('"', "'").replace("<", "(").replace(">", ")")[:200]


def _truncate_tokens(text: str, limit: int) -> str:
    if count_tokens(text) <= limit:
        return text
    return text[: limit * 3]  # ~3 chars/token is conservative for prose


def _pack(parts: list[_Part], budget: int) -> list[list[_Part]]:
    """Greedy grouping of parts into groups whose token total stays within budget."""
    groups: list[list[_Part]] = []
    cur: list[_Part] = []
    used = 0
    for part in parts:
        part = _Part(part.kind, part.label, _truncate_tokens(part.text, budget))
        n = count_tokens(part.text) + 20
        if cur and used + n > budget:
            groups.append(cur)
            cur, used = [], 0
        cur.append(part)
        used += n
    if cur:
        groups.append(cur)
    return groups


class Summarizer:
    def __init__(
        self,
        llm: AccountingLLM,
        settings: Settings,
        book_title: str,
        *,
        input_budget: int = SUMMARY_INPUT_TOKENS,
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._book_title = book_title
        self._budget = input_budget
        self._system = load_prompt("summarize")

    async def _one(self, label: str, parts: list[_Part]) -> str:
        user = (
            f"Book: {self._book_title}\nPart: {label}\n\n{_render(parts)}\n\n"
            "Write the summary of this part now."
        )
        out = await self._llm.complete(
            model=self._settings.ingest_model,
            messages=[ChatMessage("system", self._system), ChatMessage("user", user)],
        )
        return out.text.strip()

    async def summarize(self, label: str, parts: list[_Part]) -> str:
        """Map-reduce until a single call fits the token budget."""
        while True:
            groups = _pack(parts, self._budget)
            if len(groups) == 1:
                return await self._one(label, groups[0])
            partials = [
                _Part("part_summary", f"{label} (piece {i})", await self._one(label, g))
                for i, g in enumerate(groups, start=1)
            ]
            parts = partials


def _build_tree(sections: list[Section], chunks: list[Chunk]) -> list[_Node]:
    nodes = {s.id: _Node(section=s) for s in sections}
    roots: list[_Node] = []
    for s in sections:  # already in reading order
        node = nodes[s.id]
        parent = nodes.get(s.parent_id) if s.parent_id else None
        (parent.children if parent else roots).append(node)
    for c in chunks:
        owner = nodes.get(c.section_id)
        if owner is not None:
            owner.chunks.append(c)
    return roots


def _extend(node: _Node, lo: int | None, hi: int | None) -> None:
    if lo is not None:
        node.first = lo if node.first is None else min(node.first, lo)
    if hi is not None:
        node.last = hi if node.last is None else max(node.last, hi)


async def build_summaries(
    session: AsyncSession,
    ctx: AuthContext,
    settings: Settings,
    llm: AccountingLLM,
    doc: Document,
    sections: list[Section],
    chunks: list[Chunk],
) -> list[Summary]:
    """Summarise every section that has content, then the whole book; embed; persist."""
    roots = _build_tree(sections, chunks)
    summarizer = Summarizer(llm, settings, doc.title)
    rows: list[Summary] = []

    async def visit(node: _Node) -> None:
        for child in node.children:
            await visit(child)
            _extend(node, child.first, child.last)
        if node.chunks:
            _extend(node, node.chunks[0].ordinal, node.chunks[-1].ordinal)
        if node.first is None or node.last is None:
            return  # nothing to summarise
        parts: list[_Part] = []
        if node.chunks:
            body = "\n\n".join(c.body for c in node.chunks)
            parts.append(_Part("passage", node.section.title, body))
        parts.extend(
            _Part("part_summary", c.section.title, c.summary) for c in node.children if c.summary
        )
        node.summary = await summarizer.summarize(node.section.title, parts)
        rows.append(
            Summary(
                section_id=node.section.id,
                kind="section",
                depth=node.section.depth,
                first_ordinal=node.first,
                last_ordinal=node.last,
                body=node.summary,
                version=STAGE_VERSIONS["summaries"],
            )
        )

    for root in roots:
        await visit(root)

    covered = [r for r in roots if r.summary]
    if covered:
        book_text = await summarizer.summarize(
            doc.title,
            [_Part("part_summary", r.section.title, r.summary) for r in covered],
        )
        rows.append(
            Summary(
                section_id=None,
                kind="book",
                depth=0,
                first_ordinal=min(r.first for r in covered if r.first is not None),
                last_ordinal=max(r.last for r in covered if r.last is not None),
                body=book_text,
                version=STAGE_VERSIONS["summaries"],
            )
        )

    await _embed(llm, settings, rows)
    return await SummaryRepository(session, ctx).replace_for_document(doc.id, rows)


async def _embed(llm: AccountingLLM, settings: Settings, rows: list[Summary]) -> None:
    if settings.embedding_dim != EMBEDDING_DIMENSION:
        raise ValueError("embedding_dim mismatch")
    batch = 32
    for i in range(0, len(rows), batch):
        group = rows[i : i + batch]
        out = await llm.embed(
            model=settings.embedding_model,
            texts=[r.body for r in group],
            dimensions=settings.embedding_dim,
        )
        for row, vec in zip(group, out.vectors, strict=True):
            row.embedding = vec
            row.embedding_model = settings.embedding_model
            row.embedding_dim = settings.embedding_dim
