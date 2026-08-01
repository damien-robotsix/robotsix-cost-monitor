"""Generic TTL cache with stale-while-revalidate (SWR) semantics.

Each value is paired with a freshness deadline and a last-updated
monotonic timestamp.  ``get_or_fetch`` returns the cached value while
fresh; when stale it still returns the cached value but triggers a
background refresh (non-blocking).  On a cold miss it blocks on the
fetch.

The ``on_refresh`` callback (if set) is called after each successful
background refresh so the owning service can update its global
``last_updated`` timestamp.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

logger = structlog.get_logger(__name__)
K = TypeVar("K")
V = TypeVar("V")


class TTLCache[K, V]:
    """Generic TTL cache with stale-while-revalidate (SWR) semantics.

    Each value is paired with a freshness deadline and a last-updated
    monotonic timestamp.  ``get_or_fetch`` returns the cached value while
    fresh; when stale it still returns the cached value but triggers a
    background refresh (non-blocking).  On a cold miss it blocks on the
    fetch.

    The ``on_refresh`` callback (if set) is called after each successful
    background refresh so the owning service can update its global
    ``last_updated`` timestamp.
    """

    def __init__(
        self,
        ttl: float,
        *,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        """Create a cache where every entry is fresh for *ttl* seconds.

        After *ttl* seconds the entry becomes stale but is still served;
        a background refresh is scheduled when the first caller hits the
        stale entry.
        """
        self._ttl = ttl
        self._on_refresh = on_refresh
        # (value, freshness_deadline, last_updated_monotonic)
        self._store: dict[K, tuple[V, float, float]] = {}
        self._pending: set[K] = set()

    @property
    def last_updated(self) -> float | None:
        """Most recent ``time.monotonic()`` when any entry was refreshed.

        ``None`` when the cache has never been populated.
        """
        if not self._store:
            return None
        return max(entry[2] for entry in self._store.values())

    async def get_or_fetch(self, key: K, fetch_fn: Callable[[], Awaitable[V]]) -> V:
        """Fresh → serve, stale → serve + bg refresh, cold → block."""
        now = time.monotonic()
        hit = self._store.get(key)
        if hit is not None:
            _value, deadline, _updated = hit
            if deadline > now:
                return _value  # fresh — serve immediately
            # Stale — serve immediately, refresh in background
            if key not in self._pending:
                self._pending.add(key)
                asyncio.create_task(self._background_refresh(key, fetch_fn))
            return _value
        # Cold miss — block on fetch
        result = await fetch_fn()
        now = time.monotonic()
        self._store[key] = (result, now + self._ttl, now)
        if self._on_refresh is not None:
            self._on_refresh()
        return result

    async def _background_refresh(
        self, key: K, fetch_fn: Callable[[], Awaitable[V]]
    ) -> None:
        """Fetch a fresh value for *key* in the background, updating the store."""
        try:
            result = await fetch_fn()
            now = time.monotonic()
            self._store[key] = (result, now + self._ttl, now)
            if self._on_refresh is not None:
                self._on_refresh()
        except Exception:
            logger.debug("background refresh failed for key %s", key, exc_info=True)
        finally:
            self._pending.discard(key)

    def invalidate(self, key: K | None = None) -> None:
        """Remove *key* from the cache; when *key* is ``None`` clear all entries."""
        if key is None:
            self._store.clear()
            self._pending.clear()
        else:
            self._store.pop(key, None)
            self._pending.discard(key)
