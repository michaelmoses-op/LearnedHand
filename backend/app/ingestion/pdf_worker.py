"""PDF extraction worker. Runs in a separate, resource-limited process (never in the API/worker
process): untrusted PDFs are a common parser-exploit vector, so the blast radius is one
short-lived child with a memory cap, a CPU cap and a wall-clock timeout enforced by the parent.

Protocol: raw PDF bytes on stdin → one JSON document on stdout:
  {"title": str, "toc": [[level, title, page], ...], "pages": [[block, ...], ...], "n_pages": int}
  block = {"t": text, "s": max_font_size, "b": bold(bool)}
Errors: exit code != 0 with a short machine-readable reason on stderr (never document text).
"""

from __future__ import annotations

import importlib
import json
import resource
import sys
from typing import Any

MAX_PAGES_ENV = "PDF_MAX_PAGES"
MAX_BLOCKS_PER_PAGE = 2000


def _limit(memory_bytes: int, cpu_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # cannot write files


def _fail(reason: str) -> int:
    sys.stderr.write(reason)
    return 2


def extract(data: bytes, max_pages: int) -> dict[str, Any]:
    pymupdf: Any = importlib.import_module("pymupdf")
    doc: Any = pymupdf.open(stream=data, filetype="pdf")
    if doc.needs_pass or doc.is_encrypted:
        raise ValueError("pdf_encrypted")
    if doc.page_count > max_pages:
        raise ValueError("pdf_too_many_pages")
    pages: list[list[dict[str, Any]]] = []
    for page in doc:
        blocks: list[dict[str, Any]] = []
        raw = page.get_text("dict", sort=True)
        for block in raw.get("blocks", [])[:MAX_BLOCKS_PER_PAGE]:
            if block.get("type") != 0:
                continue
            lines: list[str] = []
            size = 0.0
            bold = False
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(str(sp.get("text", "")) for sp in spans).strip()
                if not text:
                    continue
                lines.append(text)
                for sp in spans:
                    if str(sp.get("text", "")).strip():
                        size = max(size, float(sp.get("size", 0.0)))
                        bold = bold or bool(int(sp.get("flags", 0)) & 16)
            if lines:
                blocks.append({"t": "\n".join(lines), "s": round(size, 1), "b": bold})
        pages.append(blocks)
    toc = [[int(lv), str(t), int(p)] for lv, t, p in doc.get_toc(simple=True)]
    meta_title = str((doc.metadata or {}).get("title") or "")
    return {"title": meta_title, "toc": toc, "pages": pages, "n_pages": doc.page_count}


def main() -> int:
    import os

    mem_mb = int(os.environ.get("PDF_WORKER_MEMORY_MB", "1024"))
    cpu_s = int(os.environ.get("PDF_WORKER_CPU_SECONDS", "60"))
    max_pages = int(os.environ.get(MAX_PAGES_ENV, "3000"))
    data = sys.stdin.buffer.read()
    _limit(mem_mb * 1024 * 1024, cpu_s)
    try:
        out = extract(data, max_pages)
    except MemoryError:
        return _fail("pdf_memory_limit")
    except ValueError as exc:
        return _fail(str(exc))
    except Exception:  # corrupt / hostile input: report a class, never content
        return _fail("pdf_invalid")
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
