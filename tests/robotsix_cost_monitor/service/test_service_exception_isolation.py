"""Unit tests for CostService — exception isolation across projects."""

from __future__ import annotations

from unittest.mock import AsyncMock

from tests.robotsix_cost_monitor.helpers import _model_row, _proj, _svc, trace

# ---------------------------------------------------------------------------
# Exception isolation
# ---------------------------------------------------------------------------


async def test_exception_isolation_by_agent() -> None:
    """One project raising should not prevent the other from appearing."""
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(3.0, "implement")]),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_traces_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    rows = await svc.by_agent(None, 24)
    assert len(rows) > 0
    assert rows[0]["cost"] == 3.0


async def test_exception_isolation_summary() -> None:
    """Summary catches per-project exceptions; dead project appears with zeros."""
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(5.0)]),
    )
    object.__setattr__(
        svc._clients["good"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row(cost=5.0)]),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_traces_window",
        AsyncMock(side_effect=ConnectionError("unreachable")),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_model_usage_window",
        AsyncMock(side_effect=ConnectionError("unreachable")),
    )

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 5.0
    assert len(result["projects"]) == 2
    bad = next(p for p in result["projects"] if p["slug"] == "bad")
    assert bad["cost"] == 0.0
    assert bad["trace_count"] == 0


async def test_exception_isolation_by_model() -> None:
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row("opus", cost=3.0)]),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_model_usage_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 1
    assert rows[0]["cost"] == 3.0


async def test_exception_isolation_backend_trend() -> None:
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_backend_cost_window",
        AsyncMock(return_value={"2026-06-17": {"claude-sdk": 4.0}}),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_backend_cost_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    rows = await svc.backend_trend(None, 24, "claude-sdk")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 4.0}]


async def test_exception_isolation_all_projects_dead() -> None:
    """When all projects raise, we still get empty results — no 500."""
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(side_effect=RuntimeError)
    )
    object.__setattr__(
        svc._clients["a"],
        "fetch_model_usage_window",
        AsyncMock(side_effect=RuntimeError),
    )
    object.__setattr__(
        svc._clients["b"], "fetch_traces_window", AsyncMock(side_effect=RuntimeError)
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_model_usage_window",
        AsyncMock(side_effect=RuntimeError),
    )

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 0.0
    assert len(result["projects"]) == 2
    assert await svc.by_agent(None, 24) == []
    assert await svc.by_model(None, 24) == []


async def test_exception_isolation_mixed_in_backend_trend() -> None:
    """backend_trend with 'all' still works when one project is dead."""
    svc = _svc(_proj("good"), _proj("bad"))
    object.__setattr__(
        svc._clients["good"],
        "fetch_backend_cost_window",
        AsyncMock(return_value={"2026-06-17": {"claude-sdk": 5.0}}),
    )
    object.__setattr__(
        svc._clients["bad"],
        "fetch_backend_cost_window",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    rows = await svc.backend_trend(None, 24, "all")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 5.0}]
