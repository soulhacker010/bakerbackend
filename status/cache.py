"""
Simple in-memory cache for health check results.

Caches results for a configurable TTL (default 30 seconds) to avoid
hammering external services on every request.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()

DEFAULT_TTL_SECONDS = 30


def get_cached(key: str) -> Any | None:
    """Return cached value if still valid, else None."""
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del _cache[key]
            return None
        return value


def set_cached(key: str, value: Any, ttl: float = DEFAULT_TTL_SECONDS) -> None:
    """Store value in cache with TTL."""
    with _lock:
        _cache[key] = (time.time() + ttl, value)


def clear_cache() -> None:
    """Clear all cached entries."""
    with _lock:
        _cache.clear()
