"""A tiny, dependency-free TTL cache for within-session reuse (OPT-4).

Used to avoid repeating identical, deterministic work in a single Streamlit
session — chiefly query translation and structured-lane resolution for a query
the user asks (or re-asks) more than once. It is process-local and bounded:
entries expire after ``ttl_seconds`` and the oldest are evicted past
``max_entries``. It never persists anything to disk and stores only values the
caller passes in, so it introduces no new logging surface.

Time uses ``time.monotonic`` so it is immune to wall-clock changes. A ttl of 0
(or a max of 0) disables caching entirely — every ``get`` misses.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

__all__ = ["TTLCache"]


class TTLCache:
    """Bounded, monotonic-clock TTL cache. Not thread-safe (per-session use)."""

    def __init__(self, *, ttl_seconds: float = 300.0, max_entries: int = 256,
                 clock=time.monotonic) -> None:
        self._ttl = max(0.0, float(ttl_seconds))
        self._max = max(0, int(max_entries))
        self._clock = clock
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0 and self._max > 0

    def get(self, key: str) -> tuple[bool, Any]:
        """Return ``(hit, value)``. ``hit`` is False on miss or expiry."""
        if not self.enabled or key not in self._store:
            self.misses += 1
            return False, None
        expires_at, value = self._store[key]
        if self._clock() >= expires_at:
            del self._store[key]
            self.misses += 1
            return False, None
        self._store.move_to_end(key)  # LRU freshness
        self.hits += 1
        return True, value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._store[key] = (self._clock() + self._ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)  # evict oldest

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> dict[str, int]:
        """Safe counters for the inspector (no keys, no values)."""
        return {"entries": len(self._store), "hits": self.hits, "misses": self.misses}
