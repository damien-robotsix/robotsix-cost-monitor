"""Unit tests for the pure cost aggregations (no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from robotsix_cost_monitor import langfuse as lf


def _trace(cost, name="implement", session="t1", ago_h=1.0):
    ts = (datetime.now(UTC) - timedelta(hours=ago_h)).isoformat()
    return {
        "id": f"tr-{cost}-{name}",
        "name": name,
        "sessionId": session,
        "totalCost": cost,
        "timestamp": ts.replace("+00:00", "Z"),
    }


def test_total_cost():
    assert lf.total_cost([_trace(1.5), _trace(2.25)]) == 3.75


def test_total_cost_tolerates_field_variants():
    assert lf.total_cost([{"calculatedTotalCost": 2.0}, {"cost": 1.0}]) == 3.0


def test_aggregate_by_name_sorted_desc():
    rows = lf.aggregate_by_name(
        [_trace(1, "review"), _trace(3, "implement"), _trace(2, "implement")]
    )
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}


def test_merge_model_costs_sums_by_model_sorted_desc():
    project_a = [
        {
            "model": "opus",
            "cost": 2.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "observations": 3,
        },
        {
            "model": "haiku",
            "cost": 0.5,
            "input_tokens": 80,
            "output_tokens": 20,
            "total_tokens": 100,
            "observations": 2,
        },
    ]
    project_b = [
        {
            "model": "opus",
            "cost": 1.0,
            "input_tokens": 40,
            "output_tokens": 10,
            "total_tokens": 50,
            "observations": 1,
        },
    ]
    rows = lf.merge_model_costs([project_a, project_b])
    assert rows[0] == {
        "model": "opus",
        "backend": "claude-sdk",
        "cost": 3.0,
        "input_tokens": 140,
        "output_tokens": 60,
        "total_tokens": 200,
        "observations": 4,
    }
    assert rows[1]["model"] == "haiku"
    assert lf.merge_model_costs([]) == []


def test_backend_for_model():
    assert lf.backend_for_model("deepseek/deepseek-v4-pro-20260423") == "openrouter"
    assert lf.backend_for_model("anthropic/claude-x") == "openrouter"
    assert lf.backend_for_model("opus") == "claude-sdk"
    assert lf.backend_for_model("haiku") == "claude-sdk"


def test_backend_cost_series_merges_filters_and_sorts():
    project_a = {
        "2026-06-17": {"openrouter": 1.0, "claude-sdk": 4.0},
        "2026-06-18": {"openrouter": 2.0},
    }
    project_b = {"2026-06-18": {"openrouter": 0.5, "claude-sdk": 1.0}}
    parts = [project_a, project_b]
    # all backends → daily totals, sorted by date
    assert lf.backend_cost_series(parts, "all") == [
        {"bucket_start": "2026-06-17", "cost": 5.0},
        {"bucket_start": "2026-06-18", "cost": 3.5},
    ]
    # single backend → only that backend's cost (missing day-entry → 0)
    assert lf.backend_cost_series(parts, "claude-sdk") == [
        {"bucket_start": "2026-06-17", "cost": 4.0},
        {"bucket_start": "2026-06-18", "cost": 1.0},
    ]
    assert lf.backend_cost_series([], "openrouter") == []


def test_aggregate_by_session():
    rows = lf.aggregate_by_session(
        [_trace(1, session="a"), _trace(4, session="b"), _trace(2, session="a")]
    )
    assert rows[0]["session_id"] == "b"
    assert rows[0]["cost"] == 4.0
    assert rows[1]["session_id"] == "a"
    assert rows[1]["cost"] == 3.0


def test_most_expensive_trace_and_session():
    traces = [_trace(1, session="a"), _trace(9, "implement", session="b")]
    assert lf.most_expensive_trace(traces)["cost"] == 9.0
    assert lf.most_expensive_session(traces)["session_id"] == "b"


def test_cost_trend_buckets_sum_to_total():
    traces = [_trace(1.0, ago_h=1), _trace(2.0, ago_h=5), _trace(3.0, ago_h=20)]
    trend = lf.cost_trend(traces, hours=24, buckets=24)
    assert len(trend) == 24
    assert round(sum(b["cost"] for b in trend), 6) == 6.0


def test_empty_inputs():
    assert lf.total_cost([]) == 0.0
    assert lf.aggregate_by_name([]) == []
    assert lf.most_expensive_trace([]) is None
    assert lf.most_expensive_session([]) is None
