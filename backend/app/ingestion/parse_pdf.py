"""PDF → ParsedBook. Extraction runs in a resource-limited child process (see pdf_worker)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from app.core.errors import DomainError
from app.ingestion import pdf_text
from app.ingestion.parse_epub import ParsedBook

PDF_TIMEOUT_SECONDS = 120.0
PDF_MEMORY_MB = 1024
PDF_MAX_PAGES = 3000
PDF_MAX_OUTPUT_BYTES = 200 * 1024 * 1024
MIN_TEXT_CHARS = 200  # below this a PDF is treated as image-only (no OCR support)


class PdfParseError(DomainError):
    code = "pdf_invalid"
    title = "Invalid or unsafe PDF"


async def parse_pdf(
    data: bytes,
    *,
    time_limit: float = PDF_TIMEOUT_SECONDS,
    memory_mb: int = PDF_MEMORY_MB,
    max_pages: int = PDF_MAX_PAGES,
) -> ParsedBook:
    payload = await _run_worker(
        data, time_limit=time_limit, memory_mb=memory_mb, max_pages=max_pages
    )
    return book_from_extraction(payload)


async def _run_worker(
    data: bytes, *, time_limit: float, memory_mb: int, max_pages: int
) -> dict[str, Any]:
    env = {  # minimal environment: no secrets leak into the parser process
        "PATH": os.environ.get("PATH", ""),
        "PDF_WORKER_MEMORY_MB": str(memory_mb),
        "PDF_WORKER_CPU_SECONDS": str(max(1, int(time_limit))),
        "PDF_MAX_PAGES": str(max_pages),
    }
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.ingestion.pdf_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=os.getcwd(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(data), timeout=time_limit)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise PdfParseError("pdf_timeout") from exc
    if proc.returncode != 0:
        reason = stderr.decode("utf-8", "replace").strip()[:60]
        known = {"pdf_encrypted", "pdf_too_many_pages", "pdf_memory_limit", "pdf_invalid"}
        raise PdfParseError(reason if reason in known else "pdf_invalid")
    if len(stdout) > PDF_MAX_OUTPUT_BYTES:
        raise PdfParseError("pdf_output_too_large")
    try:
        parsed = json.loads(stdout)
    except ValueError as exc:
        raise PdfParseError("pdf_invalid") from exc
    if not isinstance(parsed, dict):
        raise PdfParseError("pdf_invalid")
    return parsed


def book_from_extraction(payload: dict[str, Any]) -> ParsedBook:
    """Structure detection: outline first, then heading heuristics, then page windows."""
    raw_pages = payload.get("pages") or []
    pages, furniture = pdf_text.strip_page_furniture(pdf_text.blocks_from_worker(raw_pages))
    total_chars = sum(len(b.text) for page in pages for b in page)
    if total_chars < MIN_TEXT_CHARS:
        raise PdfParseError("pdf_no_text_layer")  # scanned/image PDF: OCR is not supported

    method = "outline"
    sections, repairs = pdf_text.sections_from_toc(pages, list(payload.get("toc") or []))
    if len(sections) < 2:
        method = "headings"
        sections, repairs = pdf_text.sections_from_headings(pages)
    if len(sections) < 2:
        method = "page_windows"
        sections, repairs = pdf_text.sections_from_page_windows(pages)
    if not sections:
        raise PdfParseError("pdf_no_text_layer")

    title = str(payload.get("title") or "").strip() or "Untitled"
    stats = {
        **furniture,
        "dehyphenated": repairs,
        "pages": int(payload.get("n_pages") or len(raw_pages)),
        "outline_entries": len(payload.get("toc") or []),
        "structure_method": {"outline": 1, "headings": 2, "page_windows": 3}[method],
    }
    return ParsedBook(title=title[:200], sections=sections, stats=stats)
