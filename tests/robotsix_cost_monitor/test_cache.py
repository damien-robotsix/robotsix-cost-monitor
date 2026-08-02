"""Unit tests for TTLCache — cache hit / miss behaviour through CostService."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from robotsix_cost_monitor.cache import TTLCache
from tests.robotsix_cost_monitor.helpers import _model_row, _proj, _svc, trace

# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------


async def test_traces_cache_hit_same_window() -> None:
    """Calling by_agent twice with the same (slug, hours) uses cache."""
    traces = [trace(1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(client, "fetch_traces_window", AsyncMock(return_value=traces))

    # Populate cache
    await svc.by_agent("demo", 24)
    assert client.fetch_traces_window.call_count == 1  # type: ignore[attr-defined]

    # Cache hit — no additional fetch
    await svc.by_agent("demo", 24)
    assert client.fetch_traces_window.call_count == 1  # type: ignore[attr-defined]


async def test_traces_cache_miss_different_hours() -> None:
    """Different (slug, hours) keys produce separate fetches."""
    traces = [trace(1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(client, "fetch_traces_window", AsyncMock(return_value=traces))

    await svc.by_agent("demo", 24)
    await svc.by_agent("demo", 48)
    assert client.fetch_traces_window.call_count == 2  # type: ignore[attr-defined]


async def test_traces_cache_expiry() -> None:
    """After TTL expires the stale value is served immediately while a background
    refresh is scheduled; a subsequent call after the refresh completes gets
    the new value."""
    traces_v1 = [trace(1.0, "old")]
    traces_v2 = [trace(2.0, "new")]
    svc = _svc(_proj("demo"))  # default ttl=10
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_traces_window", AsyncMock(side_effect=[traces_v1, traces_v2])
    )

    with patch("robotsix_cost_monitor.cache.time.monotonic") as mono:
        mono.return_value = 1000.0
        result1 = await svc.by_agent("demo", 24)
        assert result1[0]["name"] == "old"
        assert client.fetch_traces_window.call_count == 1  # type: ignore[attr-defined]

        # Advance past TTL — stale, serve old value, background refresh scheduled
        mono.return_value = 1020.0
        result2 = await svc.by_agent("demo", 24)
        assert result2[0]["name"] == "old"  # stale served immediately

        # Let the background refresh run (unified cache's asyncio.gather needs
        # multiple event-loop iterations to complete).
        for _ in range(8):
            await asyncio.sleep(0)
        assert client.fetch_traces_window.call_count == 2  # type: ignore[attr-defined]

        # Third call — now fresh from background refresh
        result3 = await svc.by_agent("demo", 24)
        assert result3[0]["name"] == "new"


async def test_model_usage_cache_hit() -> None:
    """Repeated by_model calls within TTL use cached model data."""
    models = [_model_row("opus", cost=2.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_model_usage_window", AsyncMock(return_value=models)
    )

    await svc.by_model("demo", 24)
    await svc.by_model("demo", 24)
    assert client.fetch_model_usage_window.call_count == 1  # type: ignore[attr-defined]


async def test_model_usage_cache_expiry() -> None:
    models_v1 = [_model_row("opus", cost=1.0)]
    models_v2 = [_model_row("opus", cost=2.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client,
        "fetch_model_usage_window",
        AsyncMock(side_effect=[models_v1, models_v2]),
    )

    with patch("robotsix_cost_monitor.cache.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_model("demo", 24)
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_model("demo", 24)
        assert r2[0]["cost"] == 1.0  # stale served immediately

        # Let the background refresh run (unified cache's asyncio.gather needs
        # multiple event-loop iterations to complete).
        for _ in range(8):
            await asyncio.sleep(0)
        assert client.fetch_model_usage_window.call_count == 2  # type: ignore[attr-defined]

        r3 = await svc.by_model("demo", 24)
        assert r3[0]["cost"] == 2.0


async def test_backend_cost_cache_hit() -> None:
    data = {"2026-01-01": {"claude-sdk": 5.0}}
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_backend_cost_window", AsyncMock(return_value=data)
    )

    await svc.backend_trend("demo", 24, "claude-sdk")
    await svc.backend_trend("demo", 24, "claude-sdk")
    assert client.fetch_backend_cost_window.call_count == 1  # type: ignore[attr-defined]


async def test_backend_cost_cache_expiry() -> None:
    data1 = {"2026-01-01": {"claude-sdk": 1.0}}
    data2 = {"2026-01-01": {"claude-sdk": 2.0}}
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_backend_cost_window", AsyncMock(side_effect=[data1, data2])
    )

    with patch("robotsix_cost_monitor.cache.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r2[0]["cost"] == 1.0  # stale served immediately

        # Let the background refresh run (unified cache's asyncio.gather needs
        # multiple event-loop iterations to complete).
        for _ in range(8):
            await asyncio.sleep(0)
        assert client.fetch_backend_cost_window.call_count == 2  # type: ignore[attr-defined]

        r3 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r3[0]["cost"] == 2.0


async def test_summary_uses_both_caches() -> None:
    """summary() hits _model_usage and _trace_count; each should cache independently."""
    models = [_model_row("opus", cost=1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(client, "fetch_trace_count_window", AsyncMock(return_value=1))
    object.__setattr__(
        client, "fetch_model_usage_window", AsyncMock(return_value=models)
    )

    # First call populates both caches
    await svc.summary("demo", 24)
    assert client.fetch_trace_count_window.call_count == 1  # type: ignore[attr-defined]
    assert client.fetch_model_usage_window.call_count == 1  # type: ignore[attr-defined]

    # Second call hits both caches
    await svc.summary("demo", 24)
    assert client.fetch_trace_count_window.call_count == 1  # type: ignore[attr-defined]
    assert client.fetch_model_usage_window.call_count == 1  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LRU bound
# ---------------------------------------------------------------------------


async def test_cache_evicts_least_recently_used_beyond_max_entries() -> None:
    """The store never exceeds max_entries; the LRU key is the one dropped."""
    cache: TTLCache[int, int] = TTLCache(ttl=60.0, max_entries=3)

    async def _fetch(v: int) -> int:
        return v

    for k in (1, 2, 3):
        await cache.get_or_fetch(k, lambda k=k: _fetch(k))  # type: ignore[misc]
    assert set(cache._store) == {1, 2, 3}

    # Touch key 1 so key 2 becomes the least-recently-used.
    await cache.get_or_fetch(1, lambda: _fetch(1))
    await cache.get_or_fetch(4, lambda: _fetch(4))

    assert len(cache._store) == 3
    assert set(cache._store) == {1, 3, 4}


async def test_cache_unbounded_key_space_stays_bounded() -> None:
    """A caller walking distinct keys cannot grow the cache without limit.

    ``hours`` reaches the cache key straight from a query parameter, so this
    is the property that stops a crawler from pinning arbitrary windows in
    memory.
    """
    cache: TTLCache[int, str] = TTLCache(ttl=60.0, max_entries=8)

    async def _fetch(v: int) -> str:
        return f"value-{v}"

    for k in range(500):
        await cache.get_or_fetch(k, lambda k=k: _fetch(k))  # type: ignore[misc]

    assert len(cache._store) == 8
    # The most recent keys survive.
    assert set(cache._store) == set(range(492, 500))


async def test_background_refresh_respects_max_entries() -> None:
    """A stale-triggered background refresh re-inserts without breaking the bound."""
    cache: TTLCache[int, int] = TTLCache(ttl=0.0, max_entries=2)

    async def _fetch(v: int) -> int:
        return v

    for k in (1, 2):
        await cache.get_or_fetch(k, lambda k=k: _fetch(k))  # type: ignore[misc]
    # ttl=0 → both entries are already stale; serving them schedules refreshes.
    await cache.get_or_fetch(1, lambda: _fetch(1))
    await cache.get_or_fetch(2, lambda: _fetch(2))
    for _ in range(8):
        await asyncio.sleep(0)

    assert len(cache._store) <= 2
