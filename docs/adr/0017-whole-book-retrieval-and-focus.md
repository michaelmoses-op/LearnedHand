# 17. Whole-book retrieval; focus on summaries and Q&A

Status: accepted

## Context

The product is a study companion for books people already own: summaries plus a chatbot that
helps them understand the material. Spoiler protection (reading position) and the Phase 5
flashcards/quizzes added complexity and UI the owner does not want at this stage.

## Decision

- **Removed**: flashcards, quizzes, the study LLM stage and prompts, the `document_progress` table,
  `PUT /documents/{id}/progress`, `max_ordinal` in status, the reading-position UI, and every
  `ordinal <= progress` filter (migrations 0011 and 0012, both reversible).
- **Kept**: notes/highlights (their `anchor_ordinal` is now optional), tutor mode, concepts,
  routing and the agentic loop; all now operate on the whole book.
- **Unchanged isolation guarantee**: every query is still scoped by `user_id` and `document_id`
  in SQL, with forced RLS and 404-not-403. This is the security boundary; the progress gate was a
  product feature on top of it, not a part of it.
- **Added**: `GET /documents/{id}/summaries` and a Summary tab exposing the summary tree that was
  already built for retrieval.
- Retrieval no longer needs "frontier" handling for partly read sections; the hierarchical pass
  still searches sections that lack a summary.
- Eval question files may still contain `progress` / `forbidden_snippets`; they are accepted and
  ignored, and the spoiler metric is gone.

## Consequences

- Answers, summaries and concept notes can reveal anything in the book. If spoiler protection
  returns, reintroduce it as a filter in `RetrievalPipeline` and the concept/summaries services
  (the ADR 0014/0016 design is a reference).
- Upload hardening (same change set): more tolerant EPUB parsing (percent-encoded and
  case-mismatched paths, missing spine files skipped, nav/NCX chapter titles, hardened XML parser
  with no entity expansion), explicit DRM detection, owner-password-only PDFs accepted, higher
  size/time limits, and the stored failure reason is surfaced to the user. OCR for scanned PDFs is
  still not performed.
