"""Paragraph-aware chunking that never crosses section boundaries."""

from __future__ import annotations

from dataclasses import dataclass

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


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def chunk_sections(sections: list[ParsedSection]) -> list[DraftChunk]:
    """Split each section on paragraph boundaries into ~300–500 token chunks."""
    out: list[DraftChunk] = []
    for idx, section in enumerate(sections):
        out.extend(_chunk_section(idx, section.text))
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
