import math
import time
from collections import deque

from app.core.errors import RateLimitedError


class RateLimiter:
    """In-process sliding-window limiter. Sufficient for a single API process (no Redis by
    design, see ADR-0006); swap the implementation behind `check` if that changes."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, math.ceil(hits[0] + window_seconds - now))
            raise RateLimitedError(headers={"Retry-After": str(retry)})
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory
            self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - 3600}
