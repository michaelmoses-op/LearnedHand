"""Retrieval package (hybrid vector + FTS, whole-book)."""

from app.retrieval.hybrid import HybridRetriever, RetrievedChunk
from app.retrieval.rrf import reciprocal_rank_fusion

__all__ = ["HybridRetriever", "RetrievedChunk", "reciprocal_rank_fusion"]
