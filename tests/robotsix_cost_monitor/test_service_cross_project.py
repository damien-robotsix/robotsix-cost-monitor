"""Unit tests for CostService — cross-project merging."""

from __future__ import annotations

from unittest.mock import AsyncMock

from tests.robotsix_cost_monitor.helpers import _model_row, _proj, _svc, trace

# ---------------------------------------------------------------------------
# Cross-project merging
# ---------------------------------------------------------------------------


async def test_cross_project_summary_merges() -> None:
    svc = _svc(_proj("proj-a"), _proj("proj-b"))
    object.__setattr__(
        svc._clients["proj-a"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(1.5, tid="t1")]),
    )
    object.__setattr__(
        svc._clients["proj-a"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row(cost=1.5)]),
    )
    object.__setattr__(
        svc._clients["proj-b"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(2.5, tid="t2")]),
    )
    object.__setattr__(
        svc._clients["proj-b"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row(cost=2.5)]),
    )

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 4.0
    assert len(result["projects"]) == 2
    slugs = {p["slug"] for p in result["projects"]}
    assert slugs == {"proj-a", "proj-b"}


async def test_cross_project_by_model_merges_same_model() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row("opus", cost=1.0, input_tokens=100)]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row("opus", cost=2.0, input_tokens=200)]),
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 1
    assert rows[0]["model"] == "opus"
    assert rows[0]["cost"] == 3.0
    assert rows[0]["input_tokens"] == 300


async def test_cross_project_by_model_keeps_distinct_models() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row("opus", cost=1.0)]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_model_usage_window",
        AsyncMock(return_value=[_model_row("haiku", cost=2.0)]),
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 2
    models = {r["model"] for r in rows}
    assert models == {"opus", "haiku"}


async def test_cross_project_by_agent_merges() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(3.0, "implement"), trace(1.0, "review")]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(2.0, "implement")]),
    )

    rows = await svc.by_agent(None, 24)
    by_name = {r["name"]: r for r in rows}
    assert by_name["implement"]["cost"] == 5.0
    assert by_name["implement"]["count"] == 2
    assert by_name["review"]["cost"] == 1.0


async def test_cross_project_backend_trend_merges() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_backend_cost_window",
        AsyncMock(return_value={"2026-06-17": {"claude-sdk": 3.0}}),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_backend_cost_window",
        AsyncMock(return_value={"2026-06-17": {"claude-sdk": 2.0, "openrouter": 1.0}}),
    )

    rows = await svc.backend_trend(None, 24, "claude-sdk")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 5.0}]


async def test_cross_project_highlights_finds_best_across_projects() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    object.__setattr__(
        svc._clients["a"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(2.0, session="s1")]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(8.0, session="s2")]),
    )

    result = await svc.highlights(None, 24)
    assert result["most_expensive_trace"]["cost"] == 8.0
    assert result["most_expensive_session"]["session_id"] == "s2"


async def test_highlights_backend_all_unchanged() -> None:
    """backend='all' returns the most expensive trace/session from all traces."""
    traces = [trace(1.0, "review", session="a"), trace(9.0, "implement", session="b")]
    svc = _svc(_proj("x"))
    object.__setattr__(
        svc._clients["x"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    # fetch_agent_usage_window must NOT be called when backend='all'
    object.__setattr__(
        svc._clients["x"], "fetch_agent_usage_window", AsyncMock(return_value=[])
    )

    result = await svc.highlights("x", 24, backend="all")
    assert result["most_expensive_trace"]["cost"] == 9.0
    assert result["most_expensive_session"]["session_id"] == "b"
    assert svc._clients["x"].fetch_agent_usage_window.call_count == 0  # type: ignore[attr-defined]


async def test_highlights_backend_specific_filters() -> None:
    """With a specific backend, only traces whose name appears in that backend
    are considered for the highlights."""
    traces = [
        trace(1.0, "review", session="a"),
        trace(9.0, "implement", session="b"),
        trace(3.0, "audit", session="c"),
    ]
    svc = _svc(_proj("x"))
    object.__setattr__(
        svc._clients["x"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    object.__setattr__(
        svc._clients["x"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "claude-sdk", "cost": 9.0, "count": 1},
                {"name": "review", "backend": "openrouter", "cost": 1.0, "count": 1},
            ]
        ),
    )

    # Only "implement" is in claude-sdk → the 9.0 trace should be the top
    result = await svc.highlights("x", 24, backend="claude-sdk")
    assert result["most_expensive_trace"] is not None
    assert result["most_expensive_trace"]["cost"] == 9.0
    assert result["most_expensive_session"]["session_id"] == "b"

    # Only "review" is in openrouter → the 1.0 trace should be the top
    result = await svc.highlights("x", 24, backend="openrouter")
    assert result["most_expensive_trace"] is not None
    assert result["most_expensive_trace"]["cost"] == 1.0
    assert result["most_expensive_session"]["session_id"] == "a"


async def test_highlights_backend_no_match_returns_none() -> None:
    """When no traces match the requested backend, both highlights are None."""
    traces = [trace(5.0, "implement", session="a")]
    svc = _svc(_proj("x"))
    object.__setattr__(
        svc._clients["x"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    object.__setattr__(
        svc._clients["x"],
        "fetch_agent_usage_window",
        AsyncMock(
            return_value=[
                {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 1},
            ]
        ),
    )

    result = await svc.highlights("x", 24, backend="claude-sdk")
    assert result["most_expensive_trace"] is None
    assert result["most_expensive_session"] is None


async def test_cross_project_candidate_traces_merges_and_sorts() -> None:
    svc = _svc(_proj("a"), _proj("b"))
    # Distinct agent names so per-agent selection keeps all three (this test
    # checks the cross-project merge + global cost sort).
    object.__setattr__(
        svc._clients["a"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(5.0, "agentA", tid="expensive-a")]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_traces_window",
        AsyncMock(
            return_value=[
                trace(3.0, "agentB", tid="mid-b"),
                trace(8.0, "agentC", tid="top-b"),
            ]
        ),
    )

    rows = await svc.candidate_traces(None, 24, limit=5)
    assert [r["trace_id"] for r in rows] == ["top-b", "expensive-a", "mid-b"]
    assert rows[0]["project"] == "b"
