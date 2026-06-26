"""Unit tests for the pure cost aggregations (no network)."""

from __future__ import annotations

import pytest
from helpers import trace

from robotsix_cost_monitor.aggregations import (
    aggregate_by_name,
    aggregate_by_name_backend,
    aggregate_by_name_split,
    aggregate_by_session,
    backend_cost_series,
    backend_for_model,
    cost_trend,
    merge_model_costs,
    most_expensive_session,
    most_expensive_trace,
)


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


def test_aggregate_by_name_periodic_session_uses_stage() -> None:
    """Unnamed traces from periodic-agent runs (stage-timestamp-hash)
    should group under the stage name, not a per-run "(unnamed) …" bucket."""
    rows = aggregate_by_name(
        [
            {
                "name": "",
                "sessionId": "robotsix-llmio · trace_review-20260619T200540Z-d2857b65",
                "totalCost": 1.0,
            },
            {
                "name": "",
                "sessionId": "robotsix-cost-monitor · trace_review-20260619T200542Z-2ba9839d",
                "totalCost": 2.0,
            },
            {
                "name": "implement",
                "sessionId": "robotsix-mill · 20260619T200540Z-some-slug",
                "totalCost": 0.5,
            },
        ]
    )
    by = {r["name"]: r for r in rows}
    # Both periodic trace_review runs group under "trace_review"
    assert by["trace_review"]["cost"] == 3.0
    assert by["trace_review"]["count"] == 2
    # Named trace (implement) still uses its name
    assert by["implement"]["cost"] == 0.5
    assert by["implement"]["count"] == 1


def test_aggregate_by_name_ticket_session_keeps_fallback() -> None:
    """Ticket sessions (timestamp-slug, no stage prefix) keep the
    "(unnamed) <session>" fallback."""
    rows = aggregate_by_name(
        [
            {
                "name": "",
                "sessionId": "robotsix-mill · 20260619T200540Z-some-slug",
                "totalCost": 1.5,
            },
        ]
    )
    assert rows[0]["name"] == "(unnamed) robotsix-mill · 20260619T200540Z-some-slug"
    assert rows[0]["cost"] == 1.5


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
    assert aggregate_by_name([]) == []
    assert most_expensive_trace([]) is None
    assert most_expensive_session([]) is None


# ---------------------------------------------------------------------------
# aggregate_by_name_backend
# ---------------------------------------------------------------------------


def test_aggregate_by_name_backend_sorted_desc() -> None:
    rows = [
        {"name": "review", "backend": "claude-sdk", "cost": 1.0, "count": 3},
        {"name": "implement", "backend": "claude-sdk", "cost": 5.0, "count": 2},
    ]
    result = aggregate_by_name_backend(rows, "claude-sdk")
    assert result[0] == {"name": "implement", "cost": 5.0, "count": 2}
    assert result[1] == {"name": "review", "cost": 1.0, "count": 3}


def test_aggregate_by_name_backend_filters_by_backend() -> None:
    """Rows whose backend does not match are silently dropped."""
    rows = [
        {"name": "implement", "backend": "openrouter", "cost": 10.0, "count": 1},
        {"name": "implement", "backend": "claude-sdk", "cost": 3.0, "count": 2},
        {"name": "review", "backend": "claude-sdk", "cost": 2.0, "count": 1},
    ]
    result = aggregate_by_name_backend(rows, "claude-sdk")
    assert len(result) == 2
    assert result[0] == {"name": "implement", "cost": 3.0, "count": 2}
    assert result[1] == {"name": "review", "cost": 2.0, "count": 1}


def test_aggregate_by_name_backend_merges_same_stage_across_projects() -> None:
    """Multiple rows for the same stage (from different projects) are summed."""
    rows = [
        {"name": "implement", "backend": "claude-sdk", "cost": 1.5, "count": 2},
        {"name": "implement", "backend": "claude-sdk", "cost": 2.5, "count": 3},
    ]
    result = aggregate_by_name_backend(rows, "claude-sdk")
    assert len(result) == 1
    assert result[0] == {"name": "implement", "cost": 4.0, "count": 5}


def test_aggregate_by_name_backend_rounds_to_6_decimals() -> None:
    rows = [
        {
            "name": "implement",
            "backend": "claude-sdk",
            "cost": 1.0 / 3.0,
            "count": 1,
        },
    ]
    result = aggregate_by_name_backend(rows, "claude-sdk")
    # 1/3 ≈ 0.3333333333… should be rounded to 0.333333
    assert result[0]["cost"] == round(1.0 / 3.0, 6)


def test_aggregate_by_name_backend_empty_rows() -> None:
    assert aggregate_by_name_backend([], "claude-sdk") == []


def test_aggregate_by_name_backend_no_match() -> None:
    """When no rows match the requested backend, return empty."""
    rows = [
        {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 1},
    ]
    assert aggregate_by_name_backend(rows, "claude-sdk") == []


def test_aggregate_by_name_backend_handles_null_cost() -> None:
    rows = [
        {"name": "review", "backend": "claude-sdk", "cost": None, "count": 1},
    ]
    result = aggregate_by_name_backend(rows, "claude-sdk")
    assert result[0]["cost"] == 0.0
    assert result[0]["count"] == 1


# ---------------------------------------------------------------------------
# aggregate_by_name_split
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rows,expected",
    [
        (
            [
                {
                    "name": "implement",
                    "backend": "openrouter",
                    "cost": 10.0,
                    "count": 5,
                },
                {
                    "name": "implement",
                    "backend": "claude-sdk",
                    "cost": 40.0,
                    "count": 20,
                },
            ],
            {
                "name": "implement",
                "openrouter_cost": 10.0,
                "subscription_cost": 40.0,
                "total_cost": 50.0,
                "openrouter_count": 5,
                "subscription_count": 20,
            },
        ),
        (
            [
                {
                    "name": "refine",
                    "backend": "claude-sdk",
                    "cost": 51.15,
                    "count": 183,
                },
            ],
            {
                "name": "refine",
                "openrouter_cost": 0.0,
                "subscription_cost": 51.15,
                "total_cost": 51.15,
                "openrouter_count": 0,
                "subscription_count": 183,
            },
        ),
        (
            [
                {
                    "name": "spec_review",
                    "backend": "openrouter",
                    "cost": 0.0002,
                    "count": 1,
                },
            ],
            {
                "name": "spec_review",
                "openrouter_cost": 0.0002,
                "subscription_cost": 0.0,
                "total_cost": 0.0002,
                "openrouter_count": 1,
                "subscription_count": 0,
            },
        ),
    ],
    ids=["both_pools", "subscription_only", "openrouter_only"],
)
def test_aggregate_by_name_split(rows, expected) -> None:
    """Single-stage split: correct per-pool costs and counts for each backend mix."""
    result = aggregate_by_name_split(rows)
    assert len(result) == 1
    r = result[0]
    assert r["name"] == expected["name"]
    assert r["openrouter_cost"] == expected["openrouter_cost"]
    assert r["subscription_cost"] == expected["subscription_cost"]
    assert r["total_cost"] == expected["total_cost"]
    assert r["openrouter_count"] == expected["openrouter_count"]
    assert r["subscription_count"] == expected["subscription_count"]


def test_aggregate_by_name_split_merges_across_projects() -> None:
    """Multiple rows for the same stage (from different projects) are summed within each pool."""
    rows = [
        {"name": "implement", "backend": "openrouter", "cost": 1.5, "count": 2},
        {"name": "implement", "backend": "openrouter", "cost": 2.5, "count": 3},
        {"name": "implement", "backend": "claude-sdk", "cost": 0.5, "count": 1},
    ]
    result = aggregate_by_name_split(rows)
    assert len(result) == 1
    r = result[0]
    assert r["name"] == "implement"
    assert r["openrouter_cost"] == 4.0  # 1.5 + 2.5
    assert r["subscription_cost"] == 0.5
    assert r["openrouter_count"] == 5  # 2 + 3
    assert r["subscription_count"] == 1


def test_aggregate_by_name_split_sort_order() -> None:
    """Primary sort by openrouter_cost desc, tie-break total_cost desc.

    A high-subscription/low-marginal stage (refine-like) ranks BELOW a
    high-marginal stage, confirming the ranking is by marginal cash.
    """
    rows = [
        # refine: heavy Claude-SDK, trivial OpenRouter
        {"name": "refine", "backend": "claude-sdk", "cost": 51.15, "count": 183},
        {"name": "refine", "backend": "openrouter", "cost": 0.0002, "count": 1},
        # implement: moderate both pools
        {"name": "implement", "backend": "openrouter", "cost": 5.0, "count": 10},
        {"name": "implement", "backend": "claude-sdk", "cost": 12.0, "count": 20},
        # review: only moderate openrouter
        {"name": "review", "backend": "openrouter", "cost": 3.0, "count": 5},
    ]
    result = aggregate_by_name_split(rows)
    assert len(result) == 3
    # implement has highest openrouter_cost (5.0) → first
    assert result[0]["name"] == "implement"
    assert result[0]["openrouter_cost"] == 5.0
    # review has second-highest openrouter_cost (3.0) → second
    assert result[1]["name"] == "review"
    assert result[1]["openrouter_cost"] == 3.0
    # refine has lowest openrouter_cost (0.0002) despite highest total_cost → last
    assert result[2]["name"] == "refine"
    assert result[2]["openrouter_cost"] == 0.0002
    assert result[2]["total_cost"] == 51.1502


def test_aggregate_by_name_split_rounding() -> None:
    """Costs are rounded to 6 decimals."""
    rows = [
        {
            "name": "implement",
            "backend": "openrouter",
            "cost": 1.0 / 3.0,
            "count": 1,
        },
        {
            "name": "implement",
            "backend": "claude-sdk",
            "cost": 1.0 / 7.0,
            "count": 1,
        },
    ]
    result = aggregate_by_name_split(rows)
    r = result[0]
    assert r["openrouter_cost"] == round(1.0 / 3.0, 6)
    assert r["subscription_cost"] == round(1.0 / 7.0, 6)
    assert r["total_cost"] == round(1.0 / 3.0 + 1.0 / 7.0, 6)


def test_aggregate_by_name_split_empty_rows() -> None:
    assert aggregate_by_name_split([]) == []


def test_aggregate_by_name_split_handles_null_cost() -> None:
    rows = [
        {"name": "review", "backend": "openrouter", "cost": None, "count": 1},
        {"name": "review", "backend": "claude-sdk", "cost": None, "count": 2},
    ]
    result = aggregate_by_name_split(rows)
    r = result[0]
    assert r["openrouter_cost"] == 0.0
    assert r["subscription_cost"] == 0.0
    assert r["total_cost"] == 0.0
    assert r["openrouter_count"] == 1
    assert r["subscription_count"] == 2
