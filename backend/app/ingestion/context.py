"""Context prefixes: text prepended to each chunk before embedding (contextual retrieval).

Modes: `title` (free: the section title) or `llm` (a short situating note per chunk, written by
the ingest model). LLM calls are sequential because they share one DB session for accounting.
"""

from __future__ import annotations

from app.core.config import Settings
from app.llm.accounting import AccountingLLM
from app.llm.base import ChatMessage
from app.models.chunk import Chunk
from app.models.section import Section
from app.prompts import load_prompt

_MAX_NOTE_CHARS = 300


def _clean(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line[:_MAX_NOTE_CHARS]


async def build_context_prefixes(
    llm: AccountingLLM | None,
    settings: Settings,
    *,
    book_title: str,
    sections: list[Section],
    chunks: list[Chunk],
) -> None:
    """Fill `chunk.context_prefix` in place."""
    by_id = {s.id: s for s in sections}
    if settings.context_prefix_mode == "title" or llm is None:
        for c in chunks:
            c.context_prefix = by_id[c.section_id].title
        return
    system = load_prompt("context_prefix")
    for c in chunks:
        title = by_id[c.section_id].title
        user = (
            f"Book: {book_title}\nSection: {title}\n\n<passage>\n{c.body}\n</passage>\n\n"
            "Write the situating note now."
        )
        out = await llm.complete(
            model=settings.ingest_model,
            messages=[ChatMessage("system", system), ChatMessage("user", user)],
        )
        note = _clean(out.text)
        c.context_prefix = f"{title}: {note}" if note else title
