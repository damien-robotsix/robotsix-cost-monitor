"""Unit tests for CostService (no network).

Covers caching, cross-project merging, exception isolation, and edge cases.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from conftest import _config, _mock_client, _proj
from helpers import trace

from robotsix_cost_monitor.config import ProjectConfig
from robotsix_cost_monitor.service import CostService

# ---------------------------------------------------------------------------
# Helpers (file-local — not shared across test modules)
# ---------------------------------------------------------------------------


def _svc(*projects: ProjectConfig) -> CostService:
    """CostService whose LangfuseClient instances are all mocks."""
    cfg = _config(*projects)
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
        svc._clients["demo"], "fetch_traces_window", AsyncMock(return_value=traces)
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
    detail = {"id": "tr-1", "observations": [{"name": "gpt-4"}]}
    object.__setattr__(
        svc._clients["a"], "fetch_trace_detail", AsyncMock(return_value=detail)
    )
    result = await svc.trace_detail("a", "tr-1")
    assert result == detail


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
    """summary() hits _model_usage and _traces; each should cache independently."""
    traces = [trace(1.0)]
    models = [_model_row("opus", cost=1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    object.__setattr__(client, "fetch_traces_window", AsyncMock(return_value=traces))
    object.__setattr__(
        client, "fetch_model_usage_window", AsyncMock(return_value=models)
    )

    # First call populates both caches
    await svc.summary("demo", 24)
    assert client.fetch_traces_window.call_count == 1  # type: ignore[attr-defined]
    assert client.fetch_model_usage_window.call_count == 1  # type: ignore[attr-defined]

    # Second call hits both caches
    await svc.summary("demo", 24)
    assert client.fetch_traces_window.call_count == 1  # type: ignore[attr-defined]
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
    object.__setattr__(
        svc._clients["a"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(5.0, tid="expensive-a")]),
    )
    object.__setattr__(
        svc._clients["b"],
        "fetch_traces_window",
        AsyncMock(return_value=[trace(3.0, tid="mid-b"), trace(8.0, tid="top-b")]),
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
    """summary catches per-project exceptions; dead project appears with zeros."""
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
