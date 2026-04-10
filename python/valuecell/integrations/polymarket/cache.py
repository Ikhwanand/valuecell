"""TTL-based in-memory cache for news analysis results.

Avoids hammering the news search APIs when the same market is analyzed
repeatedly within a short window.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger


class TTLCache:
    """Generic in-memory cache with per-key TTL expiration.

    Thread-safety is *not* guaranteed — this is intended for use within
    a single asyncio event loop.
    """

    def __init__(self, ttl_seconds: int = 900) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if present and not expired, else ``None``."""
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        """Store a value with the current timestamp."""
        self._store[key] = (time.time(), value)

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Flush the entire cache."""
        self._store.clear()

    def prune_expired(self) -> int:
        """Remove all expired entries. Returns the count of removed items."""
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_news_cache: TTLCache | None = None


def get_news_cache(ttl_seconds: int = 900) -> TTLCache:
    """Return (and lazily create) the module-level news cache (15-min TTL)."""
    global _news_cache
    if _news_cache is None:
        _news_cache = TTLCache(ttl_seconds=ttl_seconds)
    return _news_cache
