"""Paragraph-aware chunking that never crosses section boundaries."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, replace

import tiktoken

from app.ingestion.constants import CHUNK_TOKEN_MAX, CHUNK_TOKEN_MIN, CHUNK_TOKEN_TARGET
from app.ingestion.parse_epub import ParsedSection

_ENC = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class DraftChunk:
    section_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    page_start: int | None = None
    page_end: int | None = None


def _page_at(page_map: list[list[int]] | None, offset: int) -> int | None:
    if not page_map:
        return None
    keys = [entry[0] for entry in page_map]
    idx = bisect.bisect_right(keys, offset) - 1
    return page_map[max(idx, 0)][1]


def _with_pages(chunks: list[DraftChunk], page_map: list[list[int]] | None) -> list[DraftChunk]:
    if not page_map:
        return chunks
    return [
        replace(
            c,
            page_start=_page_at(page_map, c.char_start),
            page_end=_page_at(page_map, max(c.char_end - 1, c.char_start)),
        )
        for c in chunks
    ]


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def chunk_sections(sections: list[ParsedSection]) -> list[DraftChunk]:
    """Split each section on paragraph boundaries into ~300–500 token chunks."""
    out: list[DraftChunk] = []
    for idx, section in enumerate(sections):
        out.extend(_with_pages(_chunk_section(idx, section.text), section.page_map))
    return out


def _chunk_section(section_index: int, text: str) -> list[DraftChunk]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    chunks: list[DraftChunk] = []
    buf: list[str] = []
    buf_tokens = 0
    # Track char offsets in the original section text.
    cursor = 0
    buf_start = 0

    def flush() -> None:
        nonlocal buf, buf_tokens, buf_start
        if not buf:
            return
        body = "\n\n".join(buf)
        end = buf_start + len(body)
        chunks.append(
            DraftChunk(
                section_index=section_index,
                text=body,
                char_start=buf_start,
                char_end=end,
                token_count=count_tokens(body),
            )
        )
        buf = []
        buf_tokens = 0

    for para in paragraphs:
        # Locate paragraph in text starting at cursor (best-effort).
        pos = text.find(para, cursor)
        if pos < 0:
            pos = cursor
        para_tokens = count_tokens(para)
        if para_tokens > CHUNK_TOKEN_MAX:
            # Hard-split oversized paragraph by tokens.
            flush()
            buf_start = pos
            for piece in _split_long(para):
                chunks.append(
                    DraftChunk(
                        section_index=section_index,
                        text=piece,
                        char_start=buf_start,
                        char_end=buf_start + len(piece),
                        token_count=count_tokens(piece),
                    )
                )
                buf_start += len(piece) + 2
            cursor = pos + len(para)
            continue
        if buf and buf_tokens + para_tokens > CHUNK_TOKEN_TARGET and buf_tokens >= CHUNK_TOKEN_MIN:
            flush()
            buf_start = pos
        if not buf:
            buf_start = pos
        buf.append(para)
        buf_tokens += para_tokens
        cursor = pos + len(para)
        if buf_tokens >= CHUNK_TOKEN_MAX:
            flush()
    flush()
    return chunks


def _split_long(para: str) -> list[str]:
    tokens = _ENC.encode(para)
    pieces: list[str] = []
    step = CHUNK_TOKEN_TARGET
    for i in range(0, len(tokens), step):
        pieces.append(_ENC.decode(tokens[i : i + step]))
    return pieces
