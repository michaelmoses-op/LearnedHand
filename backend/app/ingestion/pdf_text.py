"""Pure PDF text logic (no PDF library): clean blocks, detect structure, build sections.

Input is the worker's JSON: pages → blocks {t, s (font size), b (bold)}.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.ingestion.parse_epub import ParsedSection

_DIGITS = re.compile(r"\d+")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?(?:\d{1,5}|[ivxlcdm]{1,8})\s*$", re.I)
_HEADING_WORDS = re.compile(
    r"^(chapter|part|book|section|prologue|epilogue|preface|introduction|conclusion|"
    r"appendix|foreword|afterword|contents)\b",
    re.I,
)
_SOFT_HYPHEN = "\u00ad"
_TERMINAL = tuple(".!?:;\"'”’)]")
FRONT_MATTER_TITLE = "Front matter"


@dataclass
class Block:
    text: str
    size: float
    bold: bool
    page: int  # 1-based


def blocks_from_worker(pages: list[list[dict[str, Any]]]) -> list[list[Block]]:
    return [
        [Block(str(b["t"]), float(b.get("s", 0.0)), bool(b.get("b")), i) for b in page]
        for i, page in enumerate(pages, start=1)
    ]


def _norm_repeat(text: str) -> str:
    """Normalise so 'Page 12' / 'Page 13' and 'Title — 4' / 'Title — 5' compare equal."""
    return _DIGITS.sub("#", " ".join(text.lower().split()))


def strip_page_furniture(pages: list[list[Block]]) -> tuple[list[list[Block]], dict[str, int]]:
    """Remove running headers/footers (repeated first/last blocks) and bare page numbers."""
    n = len(pages)
    edge = Counter[str]()
    for page in pages:
        seen = {_norm_repeat(b.text) for b in (page[:2] + page[-2:])}
        edge.update(seen)
    threshold = max(3, int(n * 0.3)) if n >= 3 else n + 1  # tiny docs: only page numbers
    repeated = {k for k, c in edge.items() if c >= threshold and len(k) <= 120}

    removed_repeat = removed_numbers = 0
    out: list[list[Block]] = []
    for page in pages:
        keep: list[Block] = []
        last = len(page) - 1
        for i, b in enumerate(page):
            on_edge = i < 2 or i > last - 2
            if _PAGE_NUMBER.match(b.text) and on_edge:
                removed_numbers += 1
            elif on_edge and _norm_repeat(b.text) in repeated:
                removed_repeat += 1
            else:
                keep.append(b)
        out.append(keep)
    return out, {"removed_headers_footers": removed_repeat, "removed_page_numbers": removed_numbers}


def clean_block_text(text: str) -> tuple[str, int]:
    """Join wrapped lines into one paragraph, repairing hyphenation. Returns (text, repairs)."""
    lines = [ln.strip() for ln in text.replace(_SOFT_HYPHEN, "").split("\n") if ln.strip()]
    repairs = 0
    out = ""
    for ln in lines:
        if not out:
            out = ln
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha() and ln[:1].islower():
            out = out[:-1] + ln  # "informa-" + "tion" → "information"
            repairs += 1
        else:
            out = f"{out} {ln}"
    return out, repairs


def _body_size(pages: list[list[Block]]) -> float:
    weight = Counter[float]()
    for page in pages:
        for b in page:
            if b.size > 0:
                weight[b.size] += len(b.text)
    return weight.most_common(1)[0][0] if weight else 0.0


def _is_heading(b: Block, body: float, levels: dict[float, int]) -> int | None:
    text = " ".join(b.text.split())
    if not text or len(text) > 100 or "\n" in b.text.strip() and b.text.count("\n") > 2:
        return None
    if text.endswith(",") or (text.endswith(".") and not _HEADING_WORDS.match(text)):
        return None
    larger = body > 0 and b.size >= body * 1.2
    if larger and b.size in levels:
        return levels[b.size]
    if _HEADING_WORDS.match(text) and (b.bold or larger):
        return 0
    return None


def _heading_levels(pages: list[list[Block]], body: float) -> dict[float, int]:
    """Map distinct larger-than-body font sizes of short blocks to depth 0,1,2 (largest first)."""
    sizes = Counter[float]()
    for page in pages:
        for b in page:
            t = " ".join(b.text.split())
            if body > 0 and b.size >= body * 1.2 and 0 < len(t) <= 100:
                sizes[b.size] += 1
    # A heading size must occur a handful of times, not once (a title page, a pull quote).
    ranked = sorted((s for s, c in sizes.items() if c >= 2), reverse=True)[:3]
    return {s: depth for depth, s in enumerate(ranked)}


class _SectionBuilder:
    def __init__(self, title: str, depth: int, start_page: int) -> None:
        self.title, self.depth = title, depth
        self.start_page = self.end_page = start_page
        self.parts: list[str] = []
        self.page_map: list[list[int]] = []
        self._len = 0  # length of "\n\n".join(parts)
        self._last_page = -1

    def add(self, text: str, page: int) -> None:
        if self.parts and page != self._last_page and _continues(self.parts[-1], text):
            # A paragraph running across a page break: join instead of splitting it in two.
            offset = self._len + 1
            self.parts[-1] += " " + text
            self._len = offset + len(text)
        else:
            offset = self._len + (2 if self.parts else 0)
            self.parts.append(text)
            self._len = offset + len(text)
        if page != self._last_page:
            self.page_map.append([offset, page])
            self._last_page = page
        self.end_page = page

    def build(self) -> ParsedSection:
        text = "\n\n".join(self.parts)
        return ParsedSection(
            title=self.title[:500],
            spine_href=f"pdf:p{self.start_page}",
            text=text,
            depth=self.depth,
            page_map=self.page_map or None,
            page_start=self.start_page,
            page_end=self.end_page,
        )


def _continues(prev: str, nxt: str) -> bool:
    """Does `nxt` (first block of a new page) continue the paragraph `prev` was in the middle of?"""
    prev = prev.rstrip()
    return bool(prev) and not prev.endswith(_TERMINAL) and nxt[:1].islower()


def sections_from_toc(
    pages: list[list[Block]], toc: list[list[Any]]
) -> tuple[list[ParsedSection], int]:
    """Sections from the PDF outline. Pages are assigned wholesale to the last entry starting at or
    before them (a chapter starting mid-page shares that page with its predecessor's tail — a known
    page-granularity limit of outline-based splitting)."""
    n = len(pages)
    entries = [
        (max(0, min(lv - 1, 5)), title.strip() or "Untitled", max(1, min(pg, n)))
        for lv, title, pg in toc
        if pg >= 1
    ]
    entries.sort(key=lambda e: e[2])  # outline is usually ordered; be safe
    if not entries:
        return [], 0
    builders: list[_SectionBuilder] = []
    if entries[0][2] > 1:
        builders.append(_SectionBuilder(FRONT_MATTER_TITLE, 0, 1))
    for depth, title, start in entries:
        builders.append(_SectionBuilder(title, depth, start))
    repairs = 0
    starts = [b.start_page for b in builders]
    for pno, page in enumerate(pages, start=1):
        # last builder whose start page <= pno
        owner = 0
        for i, s in enumerate(starts):
            if s <= pno:
                owner = i
        for b in page:
            text, r = clean_block_text(b.text)
            repairs += r
            if text:
                builders[owner].add(text, pno)
    return _finish(builders), repairs


def sections_from_headings(pages: list[list[Block]]) -> tuple[list[ParsedSection], int]:
    body = _body_size(pages)
    levels = _heading_levels(pages, body)
    builders: list[_SectionBuilder] = []
    current = _SectionBuilder(FRONT_MATTER_TITLE, 0, 1)
    repairs = 0
    for pno, page in enumerate(pages, start=1):
        for b in page:
            depth = _is_heading(b, body, levels)
            if depth is not None:
                if current.parts or builders:
                    builders.append(current)
                current = _SectionBuilder(" ".join(b.text.split()), depth, pno)
                continue
            text, r = clean_block_text(b.text)
            repairs += r
            if text:
                current.add(text, pno)
    builders.append(current)
    return _finish(builders), repairs


def sections_from_page_windows(
    pages: list[list[Block]], window: int = 15
) -> tuple[list[ParsedSection], int]:
    """Last resort when no structure is detectable: fixed page windows."""
    builders: list[_SectionBuilder] = []
    repairs = 0
    for pno, page in enumerate(pages, start=1):
        if (pno - 1) % window == 0:
            builders.append(
                _SectionBuilder(f"Pages {pno}–{min(pno + window - 1, len(pages))}", 0, pno)
            )
        for b in page:
            text, r = clean_block_text(b.text)
            repairs += r
            if text:
                builders[-1].add(text, pno)
    return _finish(builders), repairs


def _finish(builders: list[_SectionBuilder]) -> list[ParsedSection]:
    """Drop empty leaf sections but keep empty parents (a Part with chapters underneath)."""
    out: list[ParsedSection] = []
    for i, b in enumerate(builders):
        has_child = i + 1 < len(builders) and builders[i + 1].depth > b.depth
        if b.parts or has_child:
            out.append(b.build())
    return out
