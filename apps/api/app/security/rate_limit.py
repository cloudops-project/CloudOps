from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from math import ceil

from app.exceptions.errors import RateLimitError


class InMemoryRateLimiter:
    """Single-process Stage 1 limiter; production distributed limiting is deferred."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        message: str = "Too many authentication attempts. Try again later.",
    ) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, ceil(events[0] + self.window_seconds - now))
                raise RateLimitError(
                    "rate_limited",
                    message,
                    retry_after_seconds=retry_after,
                    limit=self.limit,
                    current_usage=len(events),
                )
            events.append(now)
