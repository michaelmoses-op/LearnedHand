# 16. Learning features and end-to-end progress enforcement

Status: accepted

## Context

Phase 5 adds notes/highlights, flashcards, quizzes and a tutor mode. Each is a new way for book
text (or text derived from it) to reach the reader, so each must respect reading progress.

## Decision

- New user-owned tables `notes`, `flashcards`, `quiz_questions` (FORCE RLS, migration 0010). Items
  are anchored by an **ordinal** (`anchor_ordinal` / `source_ordinal`), not a chunk foreign key,
  so they survive re-ingest. Every read filters `ordinal <= progress` in SQL; lowering progress
  hides items again and makes them 404 by id.
- Notes: `anchor_ordinal` defaults to the current progress and may not exceed it (422
  `beyond_progress`). Search uses Postgres full text (`websearch_to_tsquery`, safe for arbitrary
  input) over a generated `tsvector`.
- Generation reads only chunks with `ordinal <= progress` (the 8 most recent, optionally one
  reached section) and sends them as untrusted `<passage ordinal>` blocks. Drafts whose
  `source_ordinal` was not among the passages sent are discarded, duplicates are skipped, and
  quiz drafts are validated (answer index, distinct choices). Quiz answers are only returned by
  the answer endpoint, never in the list.
- Flashcard scheduling is a small SM-2 variant (`next_state`, pure and unit-tested).
- Tutor mode is `mode: "tutor"` on the ask endpoint: same retrieval and gate, different
  human-owned system prompt (`tutor.md`). No new leakage surface.
- `tests/test_progress_enforcement.py` exercises every route that can return book-derived content
  at several reading positions and fails if any response contains text from a later chapter. A
  completeness test fails when a new document route is not classified as content or no-book-text.
- Prompts `flashcards.md`, `quiz.md`, `tutor.md` are human-owned baselines.

## Consequences

Generated study items are static once created; regenerate after re-ingest if the source changed.
