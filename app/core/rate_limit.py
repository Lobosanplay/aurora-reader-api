import math
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Per-process, per-peer window. A gateway must enforce distributed production limits."""

    def __init__(self, count: int, window: int) -> None:
        self.count = count
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, peer: str) -> int | None:
        now = time.monotonic()
        with self._lock:
            # Remove idle peers as well as old timestamps to avoid retaining arbitrary IPs forever.
            for address, hits in list(self._hits.items()):
                while hits and hits[0] <= now - self.window:
                    hits.popleft()
                if not hits:
                    del self._hits[address]
            hits = self._hits[peer]
            if len(hits) >= self.count:
                return max(1, math.ceil(self.window - (now - hits[0])))
            hits.append(now)
        return None
