"""Unit tests for CostService (no network).

Covers caching, cross-project merging, exception isolation, and edge cases.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from helpers import _config, _mock_client, _proj, trace

from robotsix_cost_monitor.config import ProjectConfig
from robotsix_cost_monitor.service import CostService

# ---------------------------------------------------------------------------
# Helpers (file-local — not shared across test modules)
# ---------------------------------------------------------------------------


def _svc(*projects: ProjectConfig, **config_kwargs: Any) -> CostService:
    """CostService whose LangfuseClient instances are all mocks.

    ``config_kwargs`` are forwarded to ``_config`` (e.g. ``subscription_call_cap``).
    """
    cfg = _config(*projects, **config_kwargs)
    svc = CostService(cfg)
    for slug in list(svc._clients):
        svc._clients[slug] = _mock_client()
    return svc


def _model_row(
    model: str = "opus",
    cost: float = 1.0,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
    observations: int = 1,
) -> dict[str, Any]:
    return {
        "model": model,
        "backend": "claude-sdk",
        "cost": cost,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_empty_project_list_summary() -> None:
    svc = _svc()
    assert await svc.summary(None, 24) == {
        "window_hours": 24,
        "total_cost": 0.0,
        "projects": [],
    }


async def test_empty_project_list_by_agent() -> None:
    assert await _svc().by_agent(None, 24) == []


async def test_empty_project_list_by_model() -> None:
    assert await _svc().by_model(None, 24) == []


async def test_empty_project_list_backend_trend() -> None:
    assert await _svc().backend_trend(None, 24, "openrouter") == []


async def test_empty_project_list_trend() -> None:
    svc = _svc()
    trend = await svc.trend(None, 24, buckets=6)
    assert len(trend) == 6
    assert sum(b["cost"] for b in trend) == 0.0


async def test_empty_project_list_highlights() -> None:
    assert await _svc().highlights(None, 24) == {
        "most_expensive_trace": None,
        "most_expensive_session": None,
    }


async def test_empty_project_list_candidate_traces() -> None:
    assert await _svc().candidate_traces(None, 24, limit=5) == []


async def test_empty_project_list_trace_detail() -> None:
    assert await _svc().trace_detail("nope", "tr-1") == {}


async def test_hours_zero_does_not_crash() -> None:
    svc = _svc(_proj("a"))
    result = await svc.summary(None, 0)
    assert result["window_hours"] == 0
    assert result["total_cost"] == 0.0


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
    """After TTL expires, a fresh fetch is made."""
    traces_v1 = [trace(1.0, "old")]
    traces_v2 = [trace(2.0, "new")]
    svc = _svc(_proj("demo"))  # default ttl=10
    client = svc._clients["demo"]
    object.__setattr__(
        client, "fetch_traces_window", AsyncMock(side_effect=[traces_v1, traces_v2])
    )

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        result1 = await svc.by_agent("demo", 24)
        assert result1[0]["name"] == "old"

        # Advance past TTL
        mono.return_value = 1020.0
        result2 = await svc.by_agent("demo", 24)
        assert result2[0]["name"] == "new"
        assert client.fetch_traces_window.call_count == 2  # type: ignore[attr-defined]


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

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_model("demo", 24)
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_model("demo", 24)
        assert r2[0]["cost"] == 2.0
        assert client.fetch_model_usage_window.call_count == 2  # type: ignore[attr-defined]


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

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r2[0]["cost"] == 2.0
        assert client.fetch_backend_cost_window.call_count == 2  # type: ignore[attr-defined]


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


async def test_top_ticket_picks_priciest_session() -> None:
    svc = _svc(_proj("a"))
    traces = [
        trace(5.0, "refine", session="robotsix-mill · T1", tid="r1"),
        trace(3.0, "implement", session="robotsix-mill · T1", tid="i1"),
        trace(2.0, "refine", session="robotsix-mill · T2", tid="r2"),
    ]
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    top = await svc.top_ticket(None, 24)
    assert top is not None
    assert top["session_id"] == "robotsix-mill · T1"  # 5+3=8 beats 2
    assert top["cost"] == 8.0
    assert top["count"] == 2
    stages = {s["name"]: s["cost"] for s in top["by_stage"]}
    assert stages == {"refine": 5.0, "implement": 3.0}


async def test_top_stage_picks_priciest_stage() -> None:
    svc = _svc(_proj("a"))
    traces = [
        trace(5.0, "refine", tid="r1"),
        trace(4.0, "refine", tid="r2"),
        trace(2.0, "audit", tid="a1"),
    ]
    object.__setattr__(
        svc._clients["a"], "fetch_traces_window", AsyncMock(return_value=traces)
    )
    top = await svc.top_stage(None, 24, sample=5)
    assert top is not None
    assert top["stage"] == "refine"  # 9 beats 2
    assert top["cost"] == 9.0
    assert top["count"] == 2
    assert top["pct_of_traced"] == 81.8  # 9 / 11
    assert [t["trace_id"] for t in top["traces"]] == ["r1", "r2"]


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
    # Should match the trace-level aggregation exactly
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}
    # fetch_agent_usage_window must NOT have been called
    assert svc._clients["a"].fetch_agent_usage_window.call_count == 0  # type: ignore[attr-defined]


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
    """After TTL expires, a fresh agent usage fetch is made."""
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

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_agent("demo", 24, backend="claude-sdk")
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_agent("demo", 24, backend="claude-sdk")
        assert r2[0]["cost"] == 2.0
        assert client.fetch_agent_usage_window.call_count == 2  # type: ignore[attr-defined]


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
    """After TTL expires, a fresh agent usage fetch is made."""
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
        assert r2["rows"][0]["openrouter_cost"] == 2.0
        assert client.fetch_agent_usage_window.call_count == 2  # type: ignore[attr-defined]


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
