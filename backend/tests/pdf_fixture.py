"""Generate PDFs with PyMuPDF from our own text (no copyrighted material)."""

from __future__ import annotations

import importlib
from typing import Any

pymupdf: Any = importlib.import_module("pymupdf")

_PARA = (
    "Justice is the first virtue of social institutions, as truth is of systems of thought. "
    "A theory however elegant must be rejected if it is untrue. "
) * 6


def make_pdf(
    *,
    chapters: list[tuple[str, int]] | None = None,  # (title, pages)
    outline: bool = True,
    big_headings: bool = True,
    header: str | None = "The Test Book — Running Header",
    page_numbers: bool = True,
    hyphenate: bool = False,
    encrypt: bool = False,
) -> bytes:
    chapters = chapters or [("Chapter One", 2), ("Chapter Two", 2), ("Chapter Three", 1)]
    doc: Any = pymupdf.open()
    toc: list[list[Any]] = []
    number = 0
    for title, n_pages in chapters:
        for i in range(n_pages):
            number += 1
            page: Any = doc.new_page()
            y = 90.0
            if header:
                page.insert_text((72, 40), header, fontsize=9)
            if i == 0:
                page.insert_text((72, y), title, fontsize=22 if big_headings else 11)
                y += 40
                toc.append([1, title, number])
            body = _PARA
            if hyphenate and i == 0:
                body = "The informa-\ntion carried by institu-\ntions matters. " + _PARA
            page.insert_textbox(pymupdf.Rect(72, y, 520, 740), body, fontsize=11)
            if page_numbers:
                page.insert_text((300, 800), str(number), fontsize=9)
    if outline:
        doc.set_toc(toc)
    if encrypt:
        return bytes(doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"))
    return bytes(doc.tobytes(garbage=4, deflate=True))


def make_image_only_pdf() -> bytes:
    doc: Any = pymupdf.open()
    page: Any = doc.new_page()
    page.draw_rect(pymupdf.Rect(100, 100, 300, 300), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    return bytes(doc.tobytes())
