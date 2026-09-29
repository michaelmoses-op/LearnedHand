# 14. Concept modelling and spoiler visibility

Status: accepted

## Context

Readers want to see how ideas develop across a book without learning what comes later.

## Decision

- Ingest stage `concepts` (after `summaries`): one structured LLM call per section, working from
  the section summary, extracts up to 8 concepts. Names are located lexically in the section's
  chunks to get real chunk ordinals (fallback: the section's last chunk). Stored in `concepts`
  (unique per document by normalised `key`) and `concept_mentions`, both user-owned with FORCE RLS.
- Visibility rules, enforced in SQL/repositories: a concept exists for the reader only if a mention
  has `first_ordinal <= progress`; a mention's model-written `note` (derived from the whole-section
  summary) is returned only when `section_last_ordinal <= progress`, otherwise null. Sections the
  reader has not started are absent from the concept map. Unreached concepts are 404, like missing.
- The prompt `app/prompts/concepts.md` is human-owned; the fake provider gives deterministic output.
- The UI uses plain SVG (no charting dependency): heat map plus a trajectory line and notes.

## Consequences

Concept quality depends on the summary quality. Stage version bumps trigger re-extraction on reingest.
