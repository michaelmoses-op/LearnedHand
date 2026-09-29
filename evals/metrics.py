"""Pure metric functions. No I/O; unit-tested."""

from __future__ import annotations

import re
import statistics
from collections.abc import Hashable, Iterable, Sequence
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")
_CITE = re.compile(r"\[(\d+)\]")


def recall_at_k[T: Hashable](
    gold: set[T], ranked: Sequence[T], k: int | None = None
) -> float | None:
    """Fraction of gold items in the top-k of `ranked` (None: all). None if there is no gold."""
    if not gold:
        return None
    top = ranked if k is None else ranked[:k]
    return len(gold & set(top)) / len(gold)


def reciprocal_rank[T: Hashable](gold: set[T], ranked: Sequence[T]) -> float | None:
    """1 / rank of the first gold item; 0 if none retrieved; None if there is no gold."""
    if not gold:
        return None
    for i, item in enumerate(ranked, start=1):
        if item in gold:
            return 1.0 / i
    return 0.0


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def point_coverage(points: Sequence[str], text: str) -> float | None:
    """Share of expected points whose words all occur in `text` (lexical, order-free)."""
    if not points:
        return None
    have = tokens(text)
    hit = sum(1 for p in points if (want := tokens(p)) and want <= have)
    return hit / len(points)


def citation_validity(answer: str, n_sources: int) -> float | None:
    """Share of [n] markers that point at an existing source. None if the answer cites nothing."""
    marks = [int(m) for m in _CITE.findall(answer)]
    if not marks:
        return None
    return sum(1 for m in marks if 1 <= m <= n_sources) / len(marks)


def contains_any(haystacks: Iterable[str], needles: Sequence[str]) -> int:
    """How many haystacks contain any needle (case-insensitive)."""
    low = [n.lower() for n in needles]
    return sum(1 for h in haystacks if any(n in h.lower() for n in low))


def cost_usd(
    input_tokens: int, output_tokens: int, price_in_per_mtok: float, price_out_per_mtok: float
) -> float:
    return (input_tokens * price_in_per_mtok + output_tokens * price_out_per_mtok) / 1_000_000


def mean(values: Iterable[float | None]) -> float | None:
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    return statistics.quantiles(xs, n=100, method="inclusive")[max(0, min(98, round(q) - 1))]


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-question metric dicts into one summary per config."""
    keys = {k for r in rows for k in r if isinstance(r[k], int | float) or r[k] is None}
    out: dict[str, Any] = {"questions": len(rows)}
    for key in sorted(keys):
        vals = [r.get(key) for r in rows]
        if key in ("spoiler_leaks", "input_tokens", "output_tokens", "cost_usd"):
            out[key] = sum(v or 0 for v in vals)
        elif key.endswith("_ms"):
            nums = [v for v in vals if v is not None]
            out[f"{key}_p50"] = percentile(nums, 50)
            out[f"{key}_p95"] = percentile(nums, 95)
        else:
            out[key] = mean(vals)
    return out
