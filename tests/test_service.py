"""Unit tests for CostService (no network).

Covers caching, cross-project merging, exception isolation, and edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from robotsix_cost_monitor.config import Config, ProjectConfig, Settings
from robotsix_cost_monitor.service import CostService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _proj(name: str = "demo") -> ProjectConfig:
    """A ProjectConfig with dummy keys (base_url points nowhere — never called)."""
    return ProjectConfig(
        name=name,
        public_key=f"pk-{name}",
        secret_key=f"sk-{name}",
        base_url="http://localhost",
    )


def _config(*projects: ProjectConfig, ttl: int = 10) -> Config:
    return Config(projects=list(projects), settings=Settings(cache_ttl_seconds=ttl))


def _mock_client(**overrides: object) -> Mock:
    """A LangfuseClient mock whose async fetch methods return empty results."""
    client = Mock()
    client.fetch_traces_window = AsyncMock(return_value=[])
    client.fetch_model_usage_window = AsyncMock(return_value=[])
    client.fetch_backend_cost_window = AsyncMock(return_value={})
    client.fetch_trace_detail = AsyncMock(return_value={})
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


def _svc(*projects: ProjectConfig) -> CostService:
    """CostService whose LangfuseClient instances are all mocks."""
    cfg = _config(*projects)
    svc = CostService(cfg)
    for slug in list(svc._clients):
        svc._clients[slug] = _mock_client()
    return svc


def _trace(
    cost: float = 1.0,
    name: str = "implement",
    tid: str = "t1",
    session: str = "",
) -> dict:
    t: dict = {"id": tid, "name": name, "totalCost": cost}
    if session:
        t["sessionId"] = session
    return t


def _model_row(
    model: str = "opus",
    cost: float = 1.0,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
    observations: int = 1,
) -> dict:
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


async def test_empty_project_list_summary():
    svc = _svc()
    assert await svc.summary(None, 24) == {
        "window_hours": 24,
        "total_cost": 0.0,
        "projects": [],
    }


async def test_empty_project_list_by_agent():
    assert await _svc().by_agent(None, 24) == []


async def test_empty_project_list_by_model():
    assert await _svc().by_model(None, 24) == []


async def test_empty_project_list_backend_trend():
    assert await _svc().backend_trend(None, 24, "openrouter") == []


async def test_empty_project_list_trend():
    svc = _svc()
    trend = await svc.trend(None, 24, buckets=6)
    assert len(trend) == 6
    assert sum(b["cost"] for b in trend) == 0.0


async def test_empty_project_list_highlights():
    assert await _svc().highlights(None, 24) == {
        "most_expensive_trace": None,
        "most_expensive_session": None,
    }


async def test_empty_project_list_candidate_traces():
    assert await _svc().candidate_traces(None, 24, limit=5) == []


async def test_empty_project_list_trace_detail():
    assert await _svc().trace_detail("nope", "tr-1") == {}


async def test_hours_zero_does_not_crash():
    svc = _svc(_proj("a"))
    result = await svc.summary(None, 0)
    assert result["window_hours"] == 0
    assert result["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# Single project
# ---------------------------------------------------------------------------


async def test_single_project_summary():
    traces = [_trace(cost=2.5)]
    models = [_model_row(cost=2.5)]
    svc = _svc(_proj("demo"))
    svc._clients["demo"].fetch_traces_window = AsyncMock(return_value=traces)
    svc._clients["demo"].fetch_model_usage_window = AsyncMock(return_value=models)

    result = await svc.summary("demo", 24)
    assert result["total_cost"] == 2.5
    assert len(result["projects"]) == 1
    p = result["projects"][0]
    assert p["slug"] == "demo"
    assert p["cost"] == 2.5
    assert p["trace_count"] == 1


async def test_single_project_by_agent():
    traces = [_trace(1, "review"), _trace(3, "implement"), _trace(2, "implement")]
    svc = _svc(_proj("a"))
    svc._clients["a"].fetch_traces_window = AsyncMock(return_value=traces)

    rows = await svc.by_agent("a", 24)
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}


async def test_single_project_by_model():
    models = [
        _model_row("opus", cost=2.0, observations=3),
        _model_row("haiku", cost=0.5, observations=2),
    ]
    svc = _svc(_proj("a"))
    svc._clients["a"].fetch_model_usage_window = AsyncMock(return_value=models)

    rows = await svc.by_model("a", 24)
    assert rows[0]["model"] == "opus"
    assert rows[0]["cost"] == 2.0
    assert rows[1]["model"] == "haiku"
    assert rows[1]["cost"] == 0.5


async def test_single_project_highlights():
    traces = [_trace(1, session="a"), _trace(9, session="b")]
    svc = _svc(_proj("x"))
    svc._clients["x"].fetch_traces_window = AsyncMock(return_value=traces)

    result = await svc.highlights("x", 24)
    assert result["most_expensive_trace"]["cost"] == 9.0
    assert result["most_expensive_session"]["session_id"] == "b"


async def test_slug_all_returns_same_as_none():
    """slug='all' should be treated the same as slug=None (all projects)."""
    svc = _svc(_proj("demo"))
    traces = [_trace(cost=1.0)]
    svc._clients["demo"].fetch_traces_window = AsyncMock(return_value=traces)
    svc._clients["demo"].fetch_model_usage_window = AsyncMock(return_value=[])

    assert await svc.summary("all", 24) == await svc.summary(None, 24)


async def test_unknown_slug_returns_empty():
    """A slug that doesn't match any project returns empty results."""
    svc = _svc(_proj("demo"))
    assert await svc.summary("ghost", 24) == {
        "window_hours": 24,
        "total_cost": 0.0,
        "projects": [],
    }


async def test_candidate_traces_sorted_by_cost():
    traces = [
        _trace(1.0, "cheap", "t1"),
        _trace(9.0, "expensive", "t2"),
        _trace(3.0, "mid", "t3"),
    ]
    svc = _svc(_proj("a"))
    svc._clients["a"].fetch_traces_window = AsyncMock(return_value=traces)

    rows = await svc.candidate_traces(None, 24, limit=10)
    assert [r["cost"] for r in rows] == [9.0, 3.0, 1.0]
    assert rows[0]["project"] == "a"


async def test_candidate_traces_limit():
    traces = [_trace(float(i), f"t{i}", f"tr-{i}") for i in range(1, 6)]
    svc = _svc(_proj("a"))
    svc._clients["a"].fetch_traces_window = AsyncMock(return_value=traces)

    rows = await svc.candidate_traces(None, 24, limit=3)
    assert len(rows) == 3
    assert rows[0]["cost"] == 5.0  # most expensive first


async def test_trace_detail_unknown_project():
    svc = _svc(_proj("a"))
    assert await svc.trace_detail("ghost", "tr-1") == {}


async def test_trace_detail_delegates_to_client():
    svc = _svc(_proj("a"))
    detail = {"id": "tr-1", "observations": [{"name": "gpt-4"}]}
    svc._clients["a"].fetch_trace_detail = AsyncMock(return_value=detail)
    result = await svc.trace_detail("a", "tr-1")
    assert result == detail


# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------


async def test_traces_cache_hit_same_window():
    """Calling by_agent twice with the same (slug, hours) uses cache."""
    traces = [_trace(1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_traces_window = AsyncMock(return_value=traces)

    # Populate cache
    await svc.by_agent("demo", 24)
    assert client.fetch_traces_window.call_count == 1

    # Cache hit — no additional fetch
    await svc.by_agent("demo", 24)
    assert client.fetch_traces_window.call_count == 1


async def test_traces_cache_miss_different_hours():
    """Different (slug, hours) keys produce separate fetches."""
    traces = [_trace(1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_traces_window = AsyncMock(return_value=traces)

    await svc.by_agent("demo", 24)
    await svc.by_agent("demo", 48)
    assert client.fetch_traces_window.call_count == 2


async def test_traces_cache_expiry():
    """After TTL expires, a fresh fetch is made."""
    traces_v1 = [_trace(1.0, "old")]
    traces_v2 = [_trace(2.0, "new")]
    svc = _svc(_proj("demo"))  # default ttl=10
    client = svc._clients["demo"]
    client.fetch_traces_window = AsyncMock(side_effect=[traces_v1, traces_v2])

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        result1 = await svc.by_agent("demo", 24)
        assert result1[0]["name"] == "old"

        # Advance past TTL
        mono.return_value = 1020.0
        result2 = await svc.by_agent("demo", 24)
        assert result2[0]["name"] == "new"
        assert client.fetch_traces_window.call_count == 2


async def test_model_usage_cache_hit():
    """Repeated by_model calls within TTL use cached model data."""
    models = [_model_row("opus", cost=2.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_model_usage_window = AsyncMock(return_value=models)

    await svc.by_model("demo", 24)
    await svc.by_model("demo", 24)
    assert client.fetch_model_usage_window.call_count == 1


async def test_model_usage_cache_expiry():
    models_v1 = [_model_row("opus", cost=1.0)]
    models_v2 = [_model_row("opus", cost=2.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_model_usage_window = AsyncMock(side_effect=[models_v1, models_v2])

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.by_model("demo", 24)
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.by_model("demo", 24)
        assert r2[0]["cost"] == 2.0
        assert client.fetch_model_usage_window.call_count == 2


async def test_backend_cost_cache_hit():
    data = {"2026-01-01": {"claude-sdk": 5.0}}
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_backend_cost_window = AsyncMock(return_value=data)

    await svc.backend_trend("demo", 24, "claude-sdk")
    await svc.backend_trend("demo", 24, "claude-sdk")
    assert client.fetch_backend_cost_window.call_count == 1


async def test_backend_cost_cache_expiry():
    data1 = {"2026-01-01": {"claude-sdk": 1.0}}
    data2 = {"2026-01-01": {"claude-sdk": 2.0}}
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_backend_cost_window = AsyncMock(side_effect=[data1, data2])

    with patch("robotsix_cost_monitor.service.time.monotonic") as mono:
        mono.return_value = 1000.0
        r1 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r1[0]["cost"] == 1.0

        mono.return_value = 1020.0
        r2 = await svc.backend_trend("demo", 24, "claude-sdk")
        assert r2[0]["cost"] == 2.0
        assert client.fetch_backend_cost_window.call_count == 2


async def test_summary_uses_both_caches():
    """summary() hits _model_usage and _traces; each should cache independently."""
    traces = [_trace(1.0)]
    models = [_model_row("opus", cost=1.0)]
    svc = _svc(_proj("demo"))
    client = svc._clients["demo"]
    client.fetch_traces_window = AsyncMock(return_value=traces)
    client.fetch_model_usage_window = AsyncMock(return_value=models)

    # First call populates both caches
    await svc.summary("demo", 24)
    assert client.fetch_traces_window.call_count == 1
    assert client.fetch_model_usage_window.call_count == 1

    # Second call hits both caches
    await svc.summary("demo", 24)
    assert client.fetch_traces_window.call_count == 1
    assert client.fetch_model_usage_window.call_count == 1


# ---------------------------------------------------------------------------
# Cross-project merging
# ---------------------------------------------------------------------------


async def test_cross_project_summary_merges():
    svc = _svc(_proj("proj-a"), _proj("proj-b"))
    svc._clients["proj-a"].fetch_traces_window = AsyncMock(
        return_value=[_trace(1.5, tid="t1")]
    )
    svc._clients["proj-a"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row(cost=1.5)]
    )
    svc._clients["proj-b"].fetch_traces_window = AsyncMock(
        return_value=[_trace(2.5, tid="t2")]
    )
    svc._clients["proj-b"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row(cost=2.5)]
    )

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 4.0
    assert len(result["projects"]) == 2
    slugs = {p["slug"] for p in result["projects"]}
    assert slugs == {"proj-a", "proj-b"}


async def test_cross_project_by_model_merges_same_model():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row("opus", cost=1.0, input_tokens=100)]
    )
    svc._clients["b"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row("opus", cost=2.0, input_tokens=200)]
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 1
    assert rows[0]["model"] == "opus"
    assert rows[0]["cost"] == 3.0
    assert rows[0]["input_tokens"] == 300


async def test_cross_project_by_model_keeps_distinct_models():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row("opus", cost=1.0)]
    )
    svc._clients["b"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row("haiku", cost=2.0)]
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 2
    models = {r["model"] for r in rows}
    assert models == {"opus", "haiku"}


async def test_cross_project_by_agent_merges():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_traces_window = AsyncMock(
        return_value=[_trace(3.0, "implement"), _trace(1.0, "review")]
    )
    svc._clients["b"].fetch_traces_window = AsyncMock(
        return_value=[_trace(2.0, "implement")]
    )

    rows = await svc.by_agent(None, 24)
    by_name = {r["name"]: r for r in rows}
    assert by_name["implement"]["cost"] == 5.0
    assert by_name["implement"]["count"] == 2
    assert by_name["review"]["cost"] == 1.0


async def test_cross_project_backend_trend_merges():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_backend_cost_window = AsyncMock(
        return_value={"2026-06-17": {"claude-sdk": 3.0}}
    )
    svc._clients["b"].fetch_backend_cost_window = AsyncMock(
        return_value={"2026-06-17": {"claude-sdk": 2.0, "openrouter": 1.0}}
    )

    rows = await svc.backend_trend(None, 24, "claude-sdk")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 5.0}]


async def test_cross_project_highlights_finds_best_across_projects():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_traces_window = AsyncMock(
        return_value=[_trace(2.0, session="s1")]
    )
    svc._clients["b"].fetch_traces_window = AsyncMock(
        return_value=[_trace(8.0, session="s2")]
    )

    result = await svc.highlights(None, 24)
    assert result["most_expensive_trace"]["cost"] == 8.0
    assert result["most_expensive_session"]["session_id"] == "s2"


async def test_cross_project_candidate_traces_merges_and_sorts():
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_traces_window = AsyncMock(
        return_value=[_trace(5.0, tid="expensive-a")]
    )
    svc._clients["b"].fetch_traces_window = AsyncMock(
        return_value=[_trace(3.0, tid="mid-b"), _trace(8.0, tid="top-b")]
    )

    rows = await svc.candidate_traces(None, 24, limit=5)
    assert [r["trace_id"] for r in rows] == ["top-b", "expensive-a", "mid-b"]
    assert rows[0]["project"] == "b"


# ---------------------------------------------------------------------------
# Exception isolation
# ---------------------------------------------------------------------------


async def test_exception_isolation_by_agent():
    """One project raising should not prevent the other from appearing."""
    svc = _svc(_proj("good"), _proj("bad"))
    svc._clients["good"].fetch_traces_window = AsyncMock(
        return_value=[_trace(3.0, "implement")]
    )
    svc._clients["bad"].fetch_traces_window = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    rows = await svc.by_agent(None, 24)
    assert len(rows) > 0
    assert rows[0]["cost"] == 3.0


async def test_exception_isolation_summary():
    """summary catches per-project exceptions; dead project appears with zeros."""
    svc = _svc(_proj("good"), _proj("bad"))
    svc._clients["good"].fetch_traces_window = AsyncMock(return_value=[_trace(5.0)])
    svc._clients["good"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row(cost=5.0)]
    )
    svc._clients["bad"].fetch_traces_window = AsyncMock(
        side_effect=ConnectionError("unreachable")
    )
    svc._clients["bad"].fetch_model_usage_window = AsyncMock(
        side_effect=ConnectionError("unreachable")
    )

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 5.0
    assert len(result["projects"]) == 2
    bad = next(p for p in result["projects"] if p["slug"] == "bad")
    assert bad["cost"] == 0.0
    assert bad["trace_count"] == 0


async def test_exception_isolation_by_model():
    svc = _svc(_proj("good"), _proj("bad"))
    svc._clients["good"].fetch_model_usage_window = AsyncMock(
        return_value=[_model_row("opus", cost=3.0)]
    )
    svc._clients["bad"].fetch_model_usage_window = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    rows = await svc.by_model(None, 24)
    assert len(rows) == 1
    assert rows[0]["cost"] == 3.0


async def test_exception_isolation_backend_trend():
    svc = _svc(_proj("good"), _proj("bad"))
    svc._clients["good"].fetch_backend_cost_window = AsyncMock(
        return_value={"2026-06-17": {"claude-sdk": 4.0}}
    )
    svc._clients["bad"].fetch_backend_cost_window = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    rows = await svc.backend_trend(None, 24, "claude-sdk")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 4.0}]


async def test_exception_isolation_all_projects_dead():
    """When all projects raise, we still get empty results — no 500."""
    svc = _svc(_proj("a"), _proj("b"))
    svc._clients["a"].fetch_traces_window = AsyncMock(side_effect=RuntimeError)
    svc._clients["a"].fetch_model_usage_window = AsyncMock(side_effect=RuntimeError)
    svc._clients["b"].fetch_traces_window = AsyncMock(side_effect=RuntimeError)
    svc._clients["b"].fetch_model_usage_window = AsyncMock(side_effect=RuntimeError)

    result = await svc.summary(None, 24)
    assert result["total_cost"] == 0.0
    assert len(result["projects"]) == 2
    assert await svc.by_agent(None, 24) == []
    assert await svc.by_model(None, 24) == []


async def test_exception_isolation_mixed_in_backend_trend():
    """backend_trend with 'all' still works when one project is dead."""
    svc = _svc(_proj("good"), _proj("bad"))
    svc._clients["good"].fetch_backend_cost_window = AsyncMock(
        return_value={"2026-06-17": {"claude-sdk": 5.0}}
    )
    svc._clients["bad"].fetch_backend_cost_window = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    rows = await svc.backend_trend(None, 24, "all")
    assert rows == [{"bucket_start": "2026-06-17", "cost": 5.0}]
