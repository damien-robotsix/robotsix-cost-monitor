"""Unit tests for CostService — by_agent with backend filtering."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from tests.robotsix_cost_monitor.helpers import _proj, _svc, trace

# ---------------------------------------------------------------------------
# by_agent with backend
# ---------------------------------------------------------------------------


async def test_by_agent_backend_all_unchanged() -> None:
    """backend='all' uses trace-level aggregation (aggregate_by_name) unchanged."""
    traces = [trace(1.0, "review"), trace(3.0, "implement"), trace(2.0, "implement")]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    # Even if fetch_agent_usage_window returns something different,
    # backend='all' must ignore it and use traces.
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "ghost", "backend": "claude-sdk", "cost": 99.0, "count": 1}
            ]
        ),
    )

    rows = await svc.by_agent("a", 24, backend="all")
    # Should match the trace-level aggregation exactly — agent_usage is
    # fetched by the unified cache but ignored for the 'all' path.
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}


async def test_by_agent_backend_specific_filters() -> None:
    """With a specific backend, only stages using that backend appear."""
    svc = _svc(_proj("a"))
    agent_rows = [
        {"name": "implement", "backend": "claude-sdk", "cost": 5.0, "count": 2},
        {"name": "implement", "backend": "openrouter", "cost": 3.0, "count": 1},
        {"name": "review", "backend": "claude-sdk", "cost": 1.0, "count": 3},
        {"name": "audit", "backend": "openrouter", "cost": 7.0, "count": 1},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    rows = await svc.by_agent("a", 24, backend="claude-sdk")
    # Only claude-sdk stages: implement (5.0) + review (1.0); audit omitted
    assert len(rows) == 2
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 3}


async def test_by_agent_backend_cross_project_merge() -> None:
    """Per-(stage, backend) rows are merged across projects."""
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "claude-sdk", "cost": 3.0, "count": 2},
            ]
        ),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "claude-sdk", "cost": 2.0, "count": 1},
                {"name": "review", "backend": "claude-sdk", "cost": 0.5, "count": 1},
            ]
        ),
    )

    rows = await svc.by_agent(None, 24, backend="claude-sdk")
    assert len(rows) == 2
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 3}
    assert rows[1] == {"name": "review", "cost": 0.5, "count": 1}


async def test_by_agent_backend_dead_project_isolation() -> None:
    """One dead project doesn't prevent other projects' stages from appearing."""
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "claude-sdk", "cost": 5.0, "count": 2},
            ]
        ),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_agent_usage_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    rows = await svc.by_agent(None, 24, backend="claude-sdk")
    assert len(rows) == 1
    assert rows[0]["name"] == "implement"
    assert rows[0]["cost"] == 5.0


async def test_by_agent_backend_all_dead_returns_empty() -> None:
    """When all projects fail, we get an empty list — no 500."""
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(side_effect=RuntimeError),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_agent_usage_window",
        AsyncMock(side_effect=RuntimeError),
    )

    assert await svc.by_agent(None, 24, backend="claude-sdk") == []


async def test_by_agent_backend_no_match_returns_empty() -> None:
    """When no stages used the requested backend, return empty."""
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 1},
            ]
        ),
    )

    rows = await svc.by_agent("a", 24, backend="claude-sdk")
    assert rows == []


async def test_by_agent_backend_agent_usage_cache_hit() -> None:
    """Repeated calls within TTL use cached agent usage data."""
    rows_data = [
        {"name": "implement", "backend": "claude-sdk", "cost": 3.0, "count": 2},
    ]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_agent_usage_window", AsyncMock(return_value=rows_data)
    )

    await svc.by_agent("demo", 24, backend="claude-sdk")
    await svc.by_agent("demo", 24, backend="claude-sdk")
    assert client.fetch_agent_usage_window.call_count == 1  # type: ignore[attr-defined]


async def test_by_agent_backend_agent_usage_cache_expiry() -> None:
    """After TTL expires, the stale value is served while a background refresh
    is scheduled; a subsequent call gets the new value."""
    rows_v1 = [
        {"name": "implement", "backend": "claude-sdk", "cost": 1.0, "count": 1},
    ]
    rows_v2 = [
        {"name": "implement", "backend": "claude-sdk", "cost": 2.0, "count": 1},
    ]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client,
        "fetch_agent_usage_window",
        AsyncMock(side_effect=[rows_v1, rows_v2]),
    )

    with patch("robotsix_cost_monitor.cache.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_agent("demo", 24, backend="claude-sdk")
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_agent("demo", 24, backend="claude-sdk")
        assert r2[0]["cost"] == 1.0  # stale served immediately

        # Let the background refresh run (unified cache's asyncio.gather needs
        # multiple event-loop iterations to complete).
        for _ in range(8):
            await asyncio.sleep(0)
        assert client.fetch_agent_usage_window.call_count == 2  # type: ignore[attr-defined]

        r3 = await svc.by_agent("demo", 24, backend="claude-sdk")
        assert r3[0]["cost"] == 2.0
