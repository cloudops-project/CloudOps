from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.exceptions.errors import AppError


class InMemoryRateLimiter:
    """Single-process Stage 1 limiter; production distributed limiting is deferred."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                raise AppError(
                    "rate_limited", "Too many authentication attempts. Try again later.", 429
                )
            events.append(now)
