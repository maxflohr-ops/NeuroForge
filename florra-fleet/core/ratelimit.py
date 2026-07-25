"""Per-user + per-channel sliding-window throttles (in-memory)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_user_per_minute: int, per_channel_per_minute: int):
        self.per_user = per_user_per_minute
        self.per_channel = per_channel_per_minute
        self._user_hits: dict[int, deque[float]] = defaultdict(deque)
        self._channel_hits: dict[int, deque[float]] = defaultdict(deque)

    @staticmethod
    def _prune(hits: deque[float], now: float) -> None:
        while hits and now - hits[0] > 60.0:
            hits.popleft()

    def allow(self, user_id: int, channel_id: int) -> bool:
        """Check both windows; only record the hit if allowed."""
        now = time.time()
        user_hits = self._user_hits[user_id]
        channel_hits = self._channel_hits[channel_id]
        self._prune(user_hits, now)
        self._prune(channel_hits, now)
        if len(user_hits) >= self.per_user or len(channel_hits) >= self.per_channel:
            return False
        user_hits.append(now)
        channel_hits.append(now)
        return True
