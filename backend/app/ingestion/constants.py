"""Shared ingestion constants. EMBEDDING_DIMENSION must match the chunks.embedding column."""

# pgvector column width (migration 0006). Settings.embedding_dim must equal this at runtime.
EMBEDDING_DIMENSION = 1536

INGEST_STAGES = ("parse", "sections", "chunk", "context", "embed")

# Chunk sizing (tiktoken cl100k_base counts).
CHUNK_TOKEN_MIN = 300
CHUNK_TOKEN_TARGET = 400
CHUNK_TOKEN_MAX = 500

# EPUB safety limits (worker-only parsing).
EPUB_MAX_FILES = 2_000
EPUB_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
EPUB_MAX_FILE_BYTES = 8 * 1024 * 1024
EPUB_MAX_COMPRESSION_RATIO = 100
