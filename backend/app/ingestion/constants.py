"""Shared ingestion constants. EMBEDDING_DIMENSION must match the chunks.embedding column."""

# pgvector column width (migration 0006). Settings.embedding_dim must equal this at runtime.
EMBEDDING_DIMENSION = 1536

INGEST_STAGES = (
    "parse",
    "sections",
    "chunk",
    "context",
    "embed",
    "summaries",
    "concepts",
    "validate",
)

# Bump a stage's version to force it (and every later stage) to re-run on re-ingest.
STAGE_VERSIONS: dict[str, int] = {
    "parse": 1,
    "sections": 1,
    "chunk": 1,
    "context": 1,
    "embed": 1,
    "summaries": 1,
    "concepts": 1,
    "validate": 1,
}

# Summaries: max input tokens per LLM call before map-reduce kicks in.
SUMMARY_INPUT_TOKENS = 6000
SUMMARY_MAX_OUTPUT_HINT = "150-250 words"

# Chunk sizing (tiktoken cl100k_base counts).
CHUNK_TOKEN_MIN = 300
CHUNK_TOKEN_TARGET = 400
CHUNK_TOKEN_MAX = 500

# EPUB safety limits (worker-only parsing).
EPUB_MAX_FILES = 2_000
EPUB_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
EPUB_MAX_FILE_BYTES = 8 * 1024 * 1024
EPUB_MAX_COMPRESSION_RATIO = 100
