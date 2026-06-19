"""Unit tests for the pure cost aggregations (no network)."""

from __future__ import annotations

from helpers import trace

from robotsix_cost_monitor.aggregations import (
    aggregate_by_name,
    aggregate_by_session,
    backend_cost_series,
    backend_for_model,
    cost_trend,
    merge_model_costs,
    most_expensive_session,
    most_expensive_trace,
    total_cost,
)


def test_total_cost() -> None:
    assert total_cost([trace(1.5), trace(2.25)]) == 3.75


def test_total_cost_tolerates_field_variants() -> None:
    assert total_cost([{"calculatedTotalCost": 2.0}, {"cost": 1.0}]) == 3.0


def test_aggregate_by_name_sorted_desc() -> None:
    rows = aggregate_by_name(
        [trace(1, "review"), trace(3, "implement"), trace(2, "implement")]
    )
    assert rows[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert rows[1] == {"name": "review", "cost": 1.0, "count": 1}


def test_merge_model_costs_sums_by_model_sorted_desc() -> None:
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
    rows = merge_model_costs([project_a, project_b])
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
    assert merge_model_costs([]) == []


def test_aggregate_by_name_unnamed_falls_back_to_session() -> None:
    rows = aggregate_by_name(
        [
            {"name": "", "sessionId": "robotsix-mill · ticket-1", "totalCost": 2.0},
            {"name": None, "totalCost": 1.0},  # no name, no session
            {"name": "implement", "totalCost": 0.5},
        ]
    )
    by = {r["name"]: r for r in rows}
    assert by["(unnamed) robotsix-mill · ticket-1"]["cost"] == 2.0
    assert by["(unnamed)"]["cost"] == 1.0
    assert by["implement"]["cost"] == 0.5


def test_backend_for_model() -> None:
    assert backend_for_model("deepseek/deepseek-v4-pro-20260423") == "openrouter"
    assert backend_for_model("anthropic/claude-x") == "openrouter"
    assert backend_for_model("opus") == "claude-sdk"
    assert backend_for_model("haiku") == "claude-sdk"


def test_backend_cost_series_merges_filters_and_sorts() -> None:
    project_a = {
        "2026-06-17": {"openrouter": 1.0, "claude-sdk": 4.0},
        "2026-06-18": {"openrouter": 2.0},
    }
    project_b = {"2026-06-18": {"openrouter": 0.5, "claude-sdk": 1.0}}
    parts = [project_a, project_b]
    # all backends → daily totals, sorted by date
    assert backend_cost_series(parts, "all") == [
        {"bucket_start": "2026-06-17", "cost": 5.0},
        {"bucket_start": "2026-06-18", "cost": 3.5},
    ]
    # single backend → only that backend's cost (missing day-entry → 0)
    assert backend_cost_series(parts, "claude-sdk") == [
        {"bucket_start": "2026-06-17", "cost": 4.0},
        {"bucket_start": "2026-06-18", "cost": 1.0},
    ]
    assert backend_cost_series([], "openrouter") == []


def test_aggregate_by_session() -> None:
    rows = aggregate_by_session(
        [trace(1, session="a"), trace(4, session="b"), trace(2, session="a")]
    )
    assert rows[0]["session_id"] == "b"
    assert rows[0]["cost"] == 4.0
    assert rows[1]["session_id"] == "a"
    assert rows[1]["cost"] == 3.0


def test_most_expensive_trace_and_session() -> None:
    traces = [trace(1, session="a"), trace(9, "implement", session="b")]
    most_exp_trace = most_expensive_trace(traces)
    assert most_exp_trace is not None
    assert most_exp_trace["cost"] == 9.0
    most_exp_session = most_expensive_session(traces)
    assert most_exp_session is not None
    assert most_exp_session["session_id"] == "b"


def test_cost_trend_buckets_sum_to_total() -> None:
    traces = [trace(1.0, ago_h=1), trace(2.0, ago_h=5), trace(3.0, ago_h=20)]
    trend = cost_trend(traces, hours=24, buckets=24)
    assert len(trend) == 24
    assert round(sum(b["cost"] for b in trend), 6) == 6.0


def test_empty_inputs() -> None:
    assert total_cost([]) == 0.0
    assert aggregate_by_name([]) == []
    assert most_expensive_trace([]) is None
    assert most_expensive_session([]) is None
