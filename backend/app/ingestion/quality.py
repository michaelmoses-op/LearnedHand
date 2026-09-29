"""Parsing quality report. Numbers and flags only — never book text."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.constants import CHUNK_TOKEN_MAX, CHUNK_TOKEN_MIN
from app.models.chunk import Chunk
from app.models.section import Section

_GENERIC_TITLE = re.compile(r"^(section|untitled)?\s*\d*$|\.x?html?$", re.I)
_SUSPECT_CHARS = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")


def build_quality_report(
    sections: list[Section],
    chunks: list[Chunk],
    parse_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    total_chars = sum(len(s.body) for s in sections)
    suspect = sum(len(_SUSPECT_CHARS.findall(s.body)) for s in sections)
    tokens = [c.token_count for c in chunks]
    tiny = sum(1 for t in tokens if t < CHUNK_TOKEN_MIN // 3)
    oversize = sum(1 for t in tokens if t > CHUNK_TOKEN_MAX)
    bodies = [c.body for c in chunks]
    duplicates = len(bodies) - len(set(bodies))
    empty_sections = sum(1 for s in sections if not s.body.strip())
    generic_titles = sum(1 for s in sections if _GENERIC_TITLE.search(s.title.strip()))
    paged = sum(1 for c in chunks if c.page_start is not None)

    suspect_ratio = suspect / total_chars if total_chars else 0.0
    duplicate_ratio = duplicates / len(bodies) if bodies else 0.0
    tiny_ratio = tiny / len(chunks) if chunks else 0.0

    warnings: list[str] = []
    if not chunks:
        warnings.append("no_chunks")
    if suspect_ratio > 0.01:
        warnings.append("garbled_text")
    if duplicate_ratio > 0.05:
        warnings.append("many_duplicate_chunks")
    if tiny_ratio > 0.3:
        warnings.append("many_tiny_chunks")
    if sections and generic_titles / len(sections) > 0.5:
        warnings.append("section_titles_unrecognised")
    if empty_sections:
        warnings.append("empty_sections")
    if oversize:
        warnings.append("oversize_chunks")

    score = 1.0
    score -= min(0.4, suspect_ratio * 20)
    score -= min(0.2, duplicate_ratio * 2)
    score -= min(0.2, tiny_ratio * 0.5)
    if sections and generic_titles / len(sections) > 0.5:
        score -= 0.1
    if not chunks:
        score = 0.0
    return {
        "score": round(max(0.0, score), 3),
        "warnings": warnings,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "total_chars": total_chars,
        "total_tokens": sum(tokens),
        "avg_chunk_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
        "tiny_chunks": tiny,
        "oversize_chunks": oversize,
        "duplicate_chunks": duplicates,
        "empty_sections": empty_sections,
        "generic_section_titles": generic_titles,
        "suspect_char_ratio": round(suspect_ratio, 5),
        "chunks_with_pages": paged,
        "parse_stats": parse_stats or {},
    }
