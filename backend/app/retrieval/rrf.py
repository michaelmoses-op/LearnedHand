"""Reciprocal Rank Fusion for combining ranked retrieval lists."""

from __future__ import annotations

import uuid
from collections import defaultdict


def reciprocal_rank_fusion(
    ranked_lists: list[list[uuid.UUID]],
    *,
    k: int = 60,
) -> list[tuple[uuid.UUID, float]]:
    """Fuse ranked ID lists. Higher score is better. Stable tie-break by UUID."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
