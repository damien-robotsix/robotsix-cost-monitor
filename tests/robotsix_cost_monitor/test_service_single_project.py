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


async def test_unknown_slug_returns_empty() -> None:
    """A slug that doesn't match any project returns empty results."""
    svc = _svc(_proj("demo"))
    assert await svc.summary("ghost", 24) == {
        "window_hours": 24,
        "total_cost": 0.0,
        "projects": [],
    }


async def test_candidate_traces_sorted_by_cost() -> None:
    traces = [
        trace(1.0, "cheap", tid="t1"),
        trace(9.0, "expensive", tid="t2"),
        trace(3.0, "mid", tid="t3"),
    ]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )

    rows = await svc.candidate_traces(None, 24, limit=10)
    assert [r["cost"] for r in rows] == [9.0, 3.0, 1.0]
    assert rows[0]["project"] == "a"
    # Each candidate carries why the selector picked it.
    assert rows[0]["rank"] == 1
    assert rows[0]["pct_of_traced"] == 69.2  # 9.0 / 13.0
    assert "agent 'expensive'" in rows[0]["selection_reason"]


async def test_candidate_traces_per_agent_covers_cheaper_agent() -> None:
    # Agent A has the two priciest traces; agent B has only a cheap one. Global
    # top-2 would pick both A traces and ignore B — per-agent must surface B.
    traces = [
        trace(10.0, "agentA", tid="a1"),
        trace(8.0, "agentA", tid="a2"),
        trace(2.0, "agentB", tid="b1"),
    ]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )

    rows = await svc.candidate_traces(None, 24, limit=2, per_agent=1)
    names = {r["name"] for r in rows}
    assert names == {"agentA", "agentB"}  # both agents represented
    assert [r["cost"] for r in rows] == [10.0, 2.0]


async def test_candidate_traces_limit() -> None:
    traces = [trace(float(i), f"t{i}", tid=f"tr-{i}") for i in range(1, 6)]
    svc = _svc(_proj("a"))
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )

    rows = await svc.candidate_traces(None, 24, limit=3)
    assert len(rows) == 3
    assert rows[0]["cost"] == 5.0  # most expensive first


async def test_trace_detail_unknown_project() -> None:
    svc = _svc(_proj("a"))
    assert await svc.trace_detail("ghost", "tr-1") == {}


async def test_trace_detail_delegates_to_client() -> None:
    svc = _svc(_proj("a"))
    trace_model = trace(cost=1.0, tid="tr-1")
    object.__setattr__(
        svc._clients["a"], "fetch_trace_detail", AsyncMock(return_value=trace_model)
    )
    result = await svc.trace_detail("a", "tr-1")
    assert result["id"] == "tr-1"
    assert result["totalCost"] == 1.0
