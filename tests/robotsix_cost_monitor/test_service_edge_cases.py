"""Unit tests for CostService — edge cases (empty projects, zero hours)."""

from __future__ import annotations

from tests.robotsix_cost_monitor.helpers import _proj, _svc

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
