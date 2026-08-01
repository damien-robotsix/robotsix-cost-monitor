"""Unit tests for CostService — by_agent_segmented (openrouter vs subscription split)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from tests.robotsix_cost_monitor.helpers import _proj, _svc

# ---------------------------------------------------------------------------
# by_agent_segmented
# ---------------------------------------------------------------------------


async def test_by_agent_segmented_empty() -> None:
    """Empty project list returns empty rows."""
    result = await _svc().by_agent_segmented(None, 24)
    assert result["rows"] == []
    assert result["openrouter_marginal_total"] == 0.0
    assert result["subscription_estimate_total"] == 0.0
    assert result["subscription_count_total"] == 0
    assert result["window_hours"] == 24
    assert result["subscription_cap"] == 0
    assert result["subscription_cap_pct"] is None


async def test_by_agent_segmented_openrouter_only() -> None:
    """Only openrouter-backed stages; subscription cost is zero."""
    svc = _svc(_proj("a"))
    agent_rows = [
        {"name": "implement", "backend": "openrouter", "cost": 15.0, "count": 7},
        {"name": "review", "backend": "openrouter", "cost": 3.0, "count": 2},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 2
    # implement (higher openrouter cost) first
    assert rows[0]["name"] == "implement"
    assert rows[0]["openrouter_cost"] == 15.0
    assert rows[0]["subscription_cost"] == 0.0
    assert rows[0]["total_cost"] == 15.0
    assert rows[0]["openrouter_count"] == 7
    assert rows[0]["subscription_count"] == 0
    assert rows[0]["marginal_reducible"] is True
    # review second
    assert rows[1]["name"] == "review"
    assert rows[1]["openrouter_cost"] == 3.0
    assert rows[1]["subscription_cost"] == 0.0
    assert rows[1]["marginal_reducible"] is True
    # totals
    assert result["openrouter_marginal_total"] == 18.0
    assert result["subscription_estimate_total"] == 0.0
    assert result["subscription_count_total"] == 0


async def test_by_agent_segmented_subscription_only() -> None:
    """Only claude-sdk stages; openrouter cost is zero."""
    svc = _svc(_proj("a"))
    agent_rows = [
        {"name": "refine", "backend": "claude-sdk", "cost": 51.15, "count": 183},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 1
    assert rows[0]["name"] == "refine"
    assert rows[0]["openrouter_cost"] == 0.0
    assert rows[0]["subscription_cost"] == 51.15
    assert rows[0]["total_cost"] == 51.15
    assert rows[0]["openrouter_count"] == 0
    assert rows[0]["subscription_count"] == 183
    assert rows[0]["marginal_reducible"] is False
    assert result["openrouter_marginal_total"] == 0.0
    assert result["subscription_estimate_total"] == 51.15
    assert result["subscription_count_total"] == 183


async def test_by_agent_segmented_both_backends() -> None:
    """Stage with both openrouter and claude-sdk rows splits correctly."""
    svc = _svc(_proj("a"))
    agent_rows = [
        {"name": "implement", "backend": "openrouter", "cost": 10.0, "count": 5},
        {"name": "implement", "backend": "claude-sdk", "cost": 40.0, "count": 20},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "implement"
    assert r["openrouter_cost"] == 10.0
    assert r["subscription_cost"] == 40.0
    assert r["total_cost"] == 50.0
    assert r["openrouter_count"] == 5
    assert r["subscription_count"] == 20
    assert r["marginal_reducible"] is True
    assert result["openrouter_marginal_total"] == 10.0
    assert result["subscription_estimate_total"] == 40.0
    assert result["subscription_count_total"] == 20


async def test_by_agent_segmented_cross_project_merge() -> None:
    """Same-stage rows from different projects are summed within each pool."""
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "openrouter", "cost": 1.5, "count": 2},
                {"name": "implement", "backend": "claude-sdk", "cost": 0.5, "count": 1},
            ]
        ),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "openrouter", "cost": 2.5, "count": 3},
                {"name": "review", "backend": "openrouter", "cost": 1.0, "count": 1},
            ]
        ),
    )

    result = await svc.by_agent_segmented(None, 24)
    rows = result["rows"]
    assert len(rows) == 2
    # implement: 1.5 + 2.5 = 4.0 openrouter; 0.5 subscription
    impl = next(r for r in rows if r["name"] == "implement")
    assert impl["openrouter_cost"] == 4.0
    assert impl["subscription_cost"] == 0.5
    assert impl["total_cost"] == 4.5
    assert impl["openrouter_count"] == 5
    assert impl["subscription_count"] == 1
    # review: only from proj-b
    rev = next(r for r in rows if r["name"] == "review")
    assert rev["openrouter_cost"] == 1.0
    assert rev["subscription_cost"] == 0.0
    # totals
    assert result["openrouter_marginal_total"] == 5.0  # 4.0 + 1.0
    assert result["subscription_estimate_total"] == 0.5
    assert result["subscription_count_total"] == 1


async def test_by_agent_segmented_sort_order() -> None:
    """Sorted by openrouter_cost desc, then total_cost desc.

    A high-subscription/low-marginal stage ranks BELOW a high-marginal stage.
    """
    svc = _svc(_proj("a"))
    agent_rows = [
        # refine: heavy Claude-SDK, trivial OpenRouter
        {"name": "refine", "backend": "claude-sdk", "cost": 51.15, "count": 183},
        {"name": "refine", "backend": "openrouter", "cost": 0.0002, "count": 1},
        # implement: moderate both
        {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 10},
        {"name": "implement", "backend": "claude-sdk", "cost": 12.0, "count": 20},
        # review: only moderate openrouter
        {"name": "review", "backend": "openrouter", "cost": 3.0, "count": 5},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 3
    assert rows[0]["name"] == "implement"  # highest openrouter (5.0)
    assert rows[1]["name"] == "review"  # second (3.0)
    assert (
        rows[2]["name"] == "refine"
    )  # lowest openrouter (0.0002) despite highest total


async def test_by_agent_segmented_exception_isolation() -> None:
    """One dead project doesn't prevent other projects' stages from appearing."""
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 2},
            ]
        ),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_agent_usage_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await svc.by_agent_segmented(None, 24)
    rows = result["rows"]
    assert len(rows) == 1
    assert rows[0]["name"] == "implement"
    assert rows[0]["openrouter_cost"] == 5.0


async def test_by_agent_segmented_all_dead() -> None:
    """When all projects fail, return empty rows — no 500."""
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

    result = await svc.by_agent_segmented(None, 24)
    assert result["rows"] == []


async def test_by_agent_segmented_cache_hit() -> None:
    """Repeated calls within TTL use cached agent usage data."""
    rows_data = [
        {"name": "implement", "backend": "openrouter", "cost": 3.0, "count": 2},
    ]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_agent_usage_window", AsyncMock(return_value=rows_data)
    )

    await svc.by_agent_segmented("demo", 24)
    await svc.by_agent_segmented("demo", 24)
    assert client.fetch_agent_usage_window.call_count == 1  # type: ignore[attr-defined]


async def test_by_agent_segmented_cache_expiry() -> None:
    """After TTL expires, the stale value is served while a background refresh
    is scheduled; a subsequent call gets the new value."""
    rows_v1 = [
        {"name": "implement", "backend": "openrouter", "cost": 1.0, "count": 1},
    ]
    rows_v2 = [
        {"name": "implement", "backend": "openrouter", "cost": 2.0, "count": 1},
    ]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(
        client,
        "fetch_agent_usage_window",
        AsyncMock(side_effect=[rows_v1, rows_v2]),
    )

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_agent_segmented("demo", 24)
        assert r1["rows"][0]["openrouter_cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_agent_segmented("demo", 24)
        assert r2["rows"][0]["openrouter_cost"] == 1.0  # stale served immediately

        # Let the background refresh run
        await asyncio.sleep(0)
        assert client.fetch_agent_usage_window.call_count == 2  # type: ignore[attr-defined]

        r3 = await svc.by_agent_segmented("demo", 24)
        assert r3["rows"][0]["openrouter_cost"] == 2.0


async def test_by_agent_segmented_null_cost() -> None:
    """Null/None cost is treated as 0.0."""
    svc = _svc(_proj("a"))
    agent_rows = [
        {"name": "review", "backend": "openrouter", "cost": None, "count": 1},
        {"name": "review", "backend": "claude-sdk", "cost": None, "count": 2},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "review"
    assert r["openrouter_cost"] == 0.0
    assert r["subscription_cost"] == 0.0
    assert r["total_cost"] == 0.0
    assert r["openrouter_count"] == 1
    assert r["subscription_count"] == 2


async def test_by_agent_segmented_unknown_slug() -> None:
    """A slug not matching any project returns empty rows."""
    svc = _svc(_proj("demo"))
    result = await svc.by_agent_segmented("ghost", 24)
    assert result["rows"] == []


async def test_by_agent_segmented_slug_all() -> None:
    """slug='all' includes all projects (same as None)."""
    svc = _svc(_proj("demo"))
    agent_rows = [
        {"name": "implement", "backend": "openrouter", "cost": 7.0, "count": 3},
    ]
    object.__setattr__(
        svc._clients["demo"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    none_result = await svc.by_agent_segmented(None, 24)
    all_result = await svc.by_agent_segmented("all", 24)
    assert all_result == none_result
    assert len(all_result["rows"]) == 1
    assert all_result["rows"][0]["openrouter_cost"] == 7.0


async def test_by_agent_segmented_subscription_cap_zero() -> None:
    """With subscription_call_cap=0 (disabled), cap_pct is None."""
    svc = _svc(_proj("a"), subscription_call_cap=0)
    agent_rows = [
        {"name": "implement", "backend": "claude-sdk", "cost": 10.0, "count": 50},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    assert result["subscription_cap"] == 0
    assert result["subscription_cap_pct"] is None
    assert result["subscription_count_total"] == 50


async def test_by_agent_segmented_subscription_cap_nonzero() -> None:
    """With subscription_call_cap > 0, cap_pct = count_total / cap."""
    svc = _svc(_proj("a"), subscription_call_cap=1000)
    agent_rows = [
        {"name": "refine", "backend": "claude-sdk", "cost": 51.15, "count": 250},
        {"name": "implement", "backend": "claude-sdk", "cost": 5.0, "count": 100},
        {"name": "review", "backend": "openrouter", "cost": 3.0, "count": 50},
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    assert result["subscription_cap"] == 1000
    assert result["subscription_count_total"] == 350  # 250 + 100
    assert result["subscription_cap_pct"] == 0.35  # 350 / 1000


async def test_by_agent_segmented_refine_attribution() -> None:
    """A refine trace with rows on both claude-sdk and vendor/model OpenRouter
    produces a refine row with both subscription_cost > 0 and openrouter_cost > 0.
    """
    svc = _svc(_proj("a"))
    agent_rows = [
        # refine: uses BOTH claude-sdk (opus) and openrouter (deepseek/deepseek-v4-pro)
        {"name": "refine", "backend": "claude-sdk", "cost": 51.15, "count": 183},
        {
            "name": "refine",
            "backend": "openrouter",
            "cost": 0.45,
            "count": 1,
        },
    ]
    object.__setattr__(
        svc._clients["a"],
        "fetch_agent_usage_window",
        AsyncMock(return_value=agent_rows),
    )

    result = await svc.by_agent_segmented("a", 24)
    rows = result["rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "refine"
    assert r["subscription_cost"] > 0
    assert r["openrouter_cost"] > 0
    assert r["marginal_reducible"] is True
    assert result["openrouter_marginal_total"] == 0.45
    assert result["subscription_estimate_total"] == 51.15
