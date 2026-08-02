"""Unit tests for CostService — single project queries."""

from __future__ import annotations

from unittest.mock import AsyncMock

from tests.robotsix_cost_monitor.helpers import _model_row, _proj, _svc, trace

# ---------------------------------------------------------------------------
# Single project
# ---------------------------------------------------------------------------


async def test_single_project_summary() -> None:
    traces = [trace(cost=2.5)]
    models = [_model_row(cost=2.5)]
    svc = _svc(_proj("demo"))
    object.__setattr__(
        svc._clients["demo"],
        "fetch_trace_count_window",
        AsyncMock(return_value=len(traces)),
    )
    object.__setattr__(
        svc._clients["demo"], "fetch_model_usage_window", AsyncMock(return_value=models)
    )

    result = await svc.summary("demo", 24)
    assert result["total_cost"] == 2.5
    assert len(result["projects"]) == 1
    p = result["projects"][0]
    assert p["slug"] == "demo"
    assert p["cost"] == 2.5
    assert p["trace_count"] == 1


async def test_single_project_by_agent() -> None:
    traces = [trace(1, "review"), trace(3, "implement"), trace(2, "implement")]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )

    rows = await svc.by_agent("a", 24)
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}


async def test_single_project_by_model() -> None:
    models = [
        _model_row("opus", cost=2.0, observations=3),
        _model_row("haiku", cost=0.5, observations=2),
    ]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_model_usage_window", AsyncMock(return_value=models)
    )

    rows = await svc.by_model("a", 24)
    assert rows[0]["model"] == "opus"
    assert rows[0]["cost"] == 2.0
    assert rows[1]["model"] == "haiku"
    assert rows[1]["cost"] == 0.5


async def test_single_project_highlights() -> None:
    traces = [trace(1, session="a"), trace(9, session="b")]
    svc = _svc(_proj("x"))
    object.__setattr__(
        svc._clients["x"], "fetch_traces_window", AsyncMock(return_value=traces)
    )

    result = await svc.highlights("x", 24)
    assert result["most_expensive_trace"]["cost"] == 9.0
    assert result["most_expensive_session"]["session_id"] == "b"


async def test_slug_all_returns_same_as_none() -> None:
    """slug='all' should be treated the same as slug=None (all projects)."""
    svc = _svc(_proj("demo"))
    traces = [trace(cost=1.0)]
    object.__setattr__(
        svc._clients["demo"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    object.__setattr__(
        svc._clients["demo"], "fetch_model_usage_window", AsyncMock(return_value=[])
    )

    assert await svc.summary("all", 24) == await svc.summary(None, 24)


async def test_unknown_slug_raises_project_not_found() -> None:
    """A slug that doesn't match any project raises ProjectNotFoundError."""
    import pytest

    from robotsix_cost_monitor.exceptions import ProjectNotFoundError

    svc = _svc(_proj("demo"))
    with pytest.raises(ProjectNotFoundError, match="ghost"):
        await svc.summary("ghost", 24)
