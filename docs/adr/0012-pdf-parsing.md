# 12. PDF parsing with PyMuPDF in a sandboxed child process

Status: accepted

## Context

Users upload PDFs they own. PDF parsers are a frequent source of memory-safety bugs and
resource-exhaustion attacks. Pure-Python options (pypdf) are safer but give worse text order,
no font information (needed for heading detection) and weaker outline support.

## Decision

- Use **PyMuPDF** for extraction, but never in the API/worker process: `app.ingestion.pdf_worker`
  runs as a short-lived child (`python -m ...`) with `RLIMIT_AS` (memory), `RLIMIT_CPU`,
  no core dumps, no file writes, a minimal environment (no secrets), a wall-clock timeout that
  kills it, page-count and output-size limits. It returns JSON blocks; all structure logic
  (`pdf_text.py`) is pure Python in the parent and unit-tested without a PDF library.
- Structure: PDF outline first; else font-size/keyword heading heuristics; else fixed page
  windows. Running headers/footers and page numbers are stripped, hyphenation repaired,
  paragraphs split across pages joined. Chunks and sections keep page numbers (`page_map`).
- Encrypted and image-only PDFs are rejected with a clear code (no OCR in scope).
- **Licence:** PyMuPDF is AGPL-3.0 (commercial licence from Artifex otherwise). Fine for a
  personal/self-hosted app; if LearnedHand is ever offered as a network service to others, the
  AGPL source-availability terms apply to the service, so re-evaluate (swap to pypdf/pdfminer or
  buy a licence) before that deployment.

## Consequences

- One subprocess per PDF ingest (~100 ms overhead), acceptable for a background job.
- Outline-based sections are page-granular (a chapter starting mid-page shares that page with
  its predecessor).
