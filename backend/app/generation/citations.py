"""Citation extraction and verification against retrieved sources."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

# [1], [2], … map to 1-based source indices. Optional [chunk:<uuid>] form also accepted.
_INDEX_CITE = re.compile(r"\[(\d+)\]")
_CHUNK_CITE = re.compile(
    r"\[chunk:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]"
)


@dataclass(frozen=True, slots=True)
class SourceRef:
    index: int  # 1-based
    chunk_id: uuid.UUID
    section_id: uuid.UUID
    ordinal: int
    context_prefix: str


@dataclass(frozen=True, slots=True)
class Citation:
    index: int
    chunk_id: uuid.UUID
    section_id: uuid.UUID


def extract_citation_indices(answer: str) -> list[int]:
    """Unique 1-based indices in first-seen order."""
    seen: set[int] = set()
    out: list[int] = []
    for m in _INDEX_CITE.finditer(answer):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_chunk_ids(answer: str) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    out: list[uuid.UUID] = []
    for m in _CHUNK_CITE.finditer(answer):
        cid = uuid.UUID(m.group(1))
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def verify_citations(answer: str, sources: list[SourceRef]) -> list[Citation]:
    """Keep only citations that resolve to a retrieved source. Drops invented ids/indices."""
    by_index = {s.index: s for s in sources}
    by_id = {s.chunk_id: s for s in sources}
    out: list[Citation] = []
    seen: set[uuid.UUID] = set()

    for idx in extract_citation_indices(answer):
        src = by_index.get(idx)
        if src is None or src.chunk_id in seen:
            continue
        seen.add(src.chunk_id)
        out.append(Citation(index=src.index, chunk_id=src.chunk_id, section_id=src.section_id))

    for cid in extract_chunk_ids(answer):
        src = by_id.get(cid)
        if src is None or src.chunk_id in seen:
            continue
        seen.add(src.chunk_id)
        out.append(Citation(index=src.index, chunk_id=src.chunk_id, section_id=src.section_id))

    return out
