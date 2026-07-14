"""Unit tests for LangfuseClient (no network).

Covers __init__, fetch_traces_window and fetch_trace_detail delegation,
metrics query construction, and the derived aggregation methods.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import respx

from robotsix_cost_monitor.clients.langfuse import LangfuseClient
from robotsix_cost_monitor.clients.models import LangfuseMetricsRow, LangfuseTrace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(**overrides: Any) -> LangfuseClient:
    kwargs: dict[str, Any] = {
        "public_key": "pk-test",
        "secret_key": "sk-test",
        "base_url": "http://localhost/",
    }
    kwargs.update(overrides)
    return LangfuseClient(**kwargs)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_composes_async_langfuse_read_client() -> None:
    """Verify the composed async client's public API reflects the credentials."""
    c = _client(public_key="pk-a", secret_key="sk-a")
    # auth_header() must produce the correct Basic credential for the
    # supplied public_key / secret_key pair.
    assert c._lf.auth_header() == "Basic cGstYTpzay1h"


def test_init_strips_trailing_slash_from_base_url() -> None:
    """base_url trailing slashes are stripped; url() joins cleanly."""
    c = LangfuseClient(
        public_key="pk", secret_key="sk", base_url="http://example.com/api//"
    )
    assert c._lf.base_url == "http://example.com/api"
    # url() must not produce a double-slash segment.
    assert c._lf.url("/public/traces") == "http://example.com/api/public/traces"


def test_init_uses_default_timeout() -> None:
    c = _client()
    assert c._timeout == 30.0


def test_init_custom_timeout() -> None:
    c = _client(timeout=10.0)
    assert c._timeout == 10.0


# ---------------------------------------------------------------------------
# fetch_traces_window
# ---------------------------------------------------------------------------


async def test_fetch_traces_window_delegates_to_async_client() -> None:
    """fetch_traces_window delegates to _LangfuseRESTClient.fetch_traces_window
    and collects the async iterator into a list of LangfuseTrace models.
    """
    c = _client()
    raw_traces = [{"id": "t1"}, {"id": "t2"}]

    async def _mock_fetch(hours: float):
        for t in raw_traces:
            yield t

    with patch.object(c._lf, "fetch_traces_window", side_effect=_mock_fetch):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == 2
    assert all(isinstance(t, LangfuseTrace) for t in result)
    assert result[0].id == "t1"
    assert result[1].id == "t2"


async def test_fetch_traces_window_empty() -> None:
    """Returns empty list when the async iterator yields nothing."""
    c = _client()

    async def _mock_fetch(hours: float):
        if False:
            yield  # never yields

    with patch.object(c._lf, "fetch_traces_window", side_effect=_mock_fetch):
        result = await c.fetch_traces_window(hours=24)
    assert result == []


async def test_fetch_traces_window_passes_hours() -> None:
    """Verifies hours is forwarded to the composed client."""
    c = _client()
    mock = Mock()

    async def _mock_fetch(hours: float):
        mock(hours)
        if False:
            yield

    with patch.object(c._lf, "fetch_traces_window", side_effect=_mock_fetch):
        await c.fetch_traces_window(hours=12.5)
    mock.assert_called_once_with(12.5)


# ---------------------------------------------------------------------------
# fetch_trace_detail
# ---------------------------------------------------------------------------


async def test_fetch_trace_detail_delegates() -> None:
    """fetch_trace_detail delegates to _LangfuseRESTClient.fetch_trace_detail
    and returns a LangfuseTrace model.
    """
    c = _client()
    detail = {"id": "tr-99", "name": "implement", "observations": []}
    mock = AsyncMock(return_value=detail)
    with patch.object(c._lf, "fetch_trace_detail", mock):
        result = await c.fetch_trace_detail("tr-99")
    assert isinstance(result, LangfuseTrace)
    assert result.id == "tr-99"
    assert result.name == "implement"
    mock.assert_called_once_with("tr-99")


# ---------------------------------------------------------------------------
# _metrics — query construction
# ---------------------------------------------------------------------------


async def test_metrics_basic_query(respx_mock: respx.MockRouter) -> None:
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": [{"sum_totalCost": 1.5}]}
    )
    result = await c._metrics(
        24,
        metrics=[{"measure": "totalCost", "aggregation": "sum"}],
    )
    assert len(result) == 1
    assert isinstance(result[0], LangfuseMetricsRow)
    assert result[0].sum_total_cost == 1.5
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["view"] == "observations"
    assert query["metrics"] == [{"measure": "totalCost", "aggregation": "sum"}]
    assert query["dimensions"] == [{"field": "providedModelName"}]
    assert "fromTimestamp" in query
    assert "toTimestamp" in query


async def test_metrics_honors_explicit_view_and_empty_dimensions(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c._metrics(
        24,
        metrics=[{"measure": "count", "aggregation": "count"}],
        view="traces",
        dimensions=[],
    )
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["view"] == "traces"
    assert query["dimensions"] == []  # explicit [] is honored, not defaulted


async def test_fetch_trace_count_window_uses_traces_count_metric(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": [{"count_count": 5266}]}
    )
    count = await c.fetch_trace_count_window(168)
    assert count == 5266
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["view"] == "traces"
    assert query["metrics"] == [{"measure": "count", "aggregation": "count"}]
    assert query["dimensions"] == []


async def test_fetch_trace_count_window_empty_data_is_zero(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    assert await c.fetch_trace_count_window(24) == 0


async def test_metrics_with_time_dimension(respx_mock: respx.MockRouter) -> None:
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c._metrics(
        48,
        metrics=[{"measure": "totalCost", "aggregation": "sum"}],
        time_dimension={"granularity": "hour"},
    )
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_metrics_without_time_dimension(respx_mock: respx.MockRouter) -> None:
    """When time_dimension is None, it should NOT be in the query."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c._metrics(
        12,
        metrics=[{"measure": "count", "aggregation": "count"}],
    )
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert "timeDimension" not in query


async def test_metrics_multiple_metrics(respx_mock: respx.MockRouter) -> None:
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c._metrics(
        24,
        metrics=[
            {"measure": "totalCost", "aggregation": "sum"},
            {"measure": "inputTokens", "aggregation": "sum"},
            {"measure": "outputTokens", "aggregation": "sum"},
            {"measure": "totalTokens", "aggregation": "sum"},
            {"measure": "count", "aggregation": "count"},
        ],
    )
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert len(query["metrics"]) == 5


async def test_metrics_empty_data_returns_empty_list(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={}
    )  # no 'data' key
    result = await c._metrics(
        24,
        metrics=[{"measure": "totalCost", "aggregation": "sum"}],
    )
    assert result == []


# ---------------------------------------------------------------------------
# fetch_model_usage_window
# ---------------------------------------------------------------------------


async def test_model_usage_basic_aggregation(respx_mock: respx.MockRouter) -> None:
    c = _client()
    rows = [
        {
            "providedModelName": "opus",
            "sum_totalCost": 2.5,
            "sum_inputTokens": 100,
            "sum_outputTokens": 50,
            "sum_totalTokens": 150,
            "count_count": 3,
        },
        {
            "providedModelName": "haiku",
            "sum_totalCost": 0.5,
            "sum_inputTokens": 20,
            "sum_outputTokens": 10,
            "sum_totalTokens": 30,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 2
    # opus should be first (higher cost)
    assert result[0]["model"] == "opus"
    assert result[0]["cost"] == 2.5
    assert result[0]["input_tokens"] == 100
    assert result[0]["observations"] == 3
    assert result[0]["backend"] == "claude-sdk"

    assert result[1]["model"] == "haiku"
    assert result[1]["cost"] == 0.5


async def test_model_usage_merges_same_model_across_rows(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {
            "providedModelName": "opus",
            "sum_totalCost": 1.0,
            "sum_inputTokens": 50,
            "sum_outputTokens": 25,
            "sum_totalTokens": 75,
            "count_count": 2,
        },
        {
            "providedModelName": "opus",
            "sum_totalCost": 2.0,
            "sum_inputTokens": 100,
            "sum_outputTokens": 50,
            "sum_totalTokens": 150,
            "count_count": 3,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 3.0
    assert result[0]["input_tokens"] == 150
    assert result[0]["observations"] == 5


async def test_model_usage_skips_missing_model_name(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {
            "providedModelName": None,
            "sum_totalCost": 5.0,
            "sum_inputTokens": 10,
            "sum_outputTokens": 10,
            "sum_totalTokens": 20,
            "count_count": 1,
        },
        {
            "providedModelName": "opus",
            "sum_totalCost": 1.0,
            "sum_inputTokens": 10,
            "sum_outputTokens": 10,
            "sum_totalTokens": 20,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["model"] == "opus"


async def test_model_usage_handles_missing_fields(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows with missing metric fields default to 0."""
    c = _client()
    rows = [
        {"providedModelName": "opus"},  # no metric fields
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0
    assert result[0]["input_tokens"] == 0
    assert result[0]["output_tokens"] == 0
    assert result[0]["total_tokens"] == 0
    assert result[0]["observations"] == 0


async def test_model_usage_handles_null_metrics(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows with None metric values default to 0."""
    c = _client()
    rows = [
        {
            "providedModelName": "opus",
            "sum_totalCost": None,
            "sum_inputTokens": None,
            "sum_outputTokens": None,
            "sum_totalTokens": None,
            "count_count": None,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0


# ---------------------------------------------------------------------------
# fetch_cost_by_backend
# ---------------------------------------------------------------------------


async def test_cost_by_backend_groups_by_backend(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {"providedModelName": "openai/gpt-4", "sum_totalCost": 3.0},
        {"providedModelName": "anthropic/claude-3", "sum_totalCost": 2.0},
        {"providedModelName": "opus", "sum_totalCost": 1.0},
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"openrouter": 5.0, "claude-sdk": 1.0}


async def test_cost_by_backend_skips_nameless_observations(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {"providedModelName": "opus", "sum_totalCost": 1.0},
        {"providedModelName": None, "sum_totalCost": 99.0},
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"claude-sdk": 1.0}


async def test_cost_by_backend_empty(respx_mock: respx.MockRouter) -> None:
    c = _client()
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    result = await c.fetch_cost_by_backend(hours=24)
    assert result == {}


async def test_cost_by_backend_handles_null_cost(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {"providedModelName": "opus", "sum_totalCost": None},
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"claude-sdk": 0.0}


# ---------------------------------------------------------------------------
# fetch_backend_cost_window — granularity selection
# ---------------------------------------------------------------------------


async def test_backend_cost_window_minute_granularity(
    respx_mock: respx.MockRouter,
) -> None:
    """Hours <= 1 → 'minute' granularity."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200,
        json={
            "data": [
                {
                    "providedModelName": "opus",
                    "time_dimension": "2026-01-01T12:00:00Z",
                    "sum_totalCost": 1.0,
                }
            ]
        },
    )
    await c.fetch_backend_cost_window(hours=1)
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["timeDimension"] == {"granularity": "minute"}


async def test_backend_cost_window_hour_granularity(
    respx_mock: respx.MockRouter,
) -> None:
    """1 < hours <= 72 → 'hour' granularity."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c.fetch_backend_cost_window(hours=24)
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_backend_cost_window_hour_granularity_boundary(
    respx_mock: respx.MockRouter,
) -> None:
    """hours=72 → 'hour' granularity (<= 72)."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c.fetch_backend_cost_window(hours=72)
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_backend_cost_window_day_granularity(
    respx_mock: respx.MockRouter,
) -> None:
    """Hours > 72 → 'day' granularity."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c.fetch_backend_cost_window(hours=168)
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["timeDimension"] == {"granularity": "day"}


# ---------------------------------------------------------------------------
# fetch_backend_cost_window — data folding
# ---------------------------------------------------------------------------


async def test_backend_cost_window_folds_by_bucket(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {
            "providedModelName": "opus",
            "time_dimension": "2026-01-01T12:00:00Z",
            "sum_totalCost": 2.0,
        },
        {
            "providedModelName": "haiku",
            "time_dimension": "2026-01-01T12:00:00Z",
            "sum_totalCost": 0.5,
        },
        {
            "providedModelName": "openai/gpt-4",
            "time_dimension": "2026-01-01T13:00:00Z",
            "sum_totalCost": 3.0,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_backend_cost_window(hours=24)
    assert set(result.keys()) == {"2026-01-01T12:00:00Z", "2026-01-01T13:00:00Z"}
    bucket_12 = result["2026-01-01T12:00:00Z"]
    assert bucket_12 == {"claude-sdk": 2.5}
    bucket_13 = result["2026-01-01T13:00:00Z"]
    assert bucket_13 == {"openrouter": 3.0}


async def test_backend_cost_window_skips_nameless(
    respx_mock: respx.MockRouter,
) -> None:
    c = _client()
    rows = [
        {
            "providedModelName": "opus",
            "time_dimension": "2026-01-01T12:00:00Z",
            "sum_totalCost": 1.0,
        },
        {
            "providedModelName": None,
            "time_dimension": "2026-01-01T12:00:00Z",
            "sum_totalCost": 999.0,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_backend_cost_window(hours=24)
    assert result == {"2026-01-01T12:00:00Z": {"claude-sdk": 1.0}}


async def test_backend_cost_window_empty(respx_mock: respx.MockRouter) -> None:
    c = _client()
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    result = await c.fetch_backend_cost_window(hours=24)
    assert result == {}


# ---------------------------------------------------------------------------
# fetch_agent_usage_window
# ---------------------------------------------------------------------------


async def test_agent_usage_basic_aggregation(respx_mock: respx.MockRouter) -> None:
    """A single (stage, backend) pair aggregates cost and count, sorted desc."""
    c = _client()
    rows = [
        {
            "traceName": "implement",
            "providedModelName": "opus",
            "sum_totalCost": 2.5,
            "count_count": 3,
        },
        {
            "traceName": "review",
            "providedModelName": "haiku",
            "sum_totalCost": 0.5,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 2
    # implement (opus) is first — higher cost
    assert result[0] == {
        "name": "implement",
        "backend": "claude-sdk",
        "cost": 2.5,
        "count": 3,
    }
    assert result[1] == {
        "name": "review",
        "backend": "claude-sdk",
        "cost": 0.5,
        "count": 1,
    }


async def test_agent_usage_merges_same_stage_backend(
    respx_mock: respx.MockRouter,
) -> None:
    """Multiple rows for the same (stage, backend) are summed."""
    c = _client()
    rows = [
        {
            "traceName": "implement",
            "providedModelName": "opus",
            "sum_totalCost": 1.0,
            "count_count": 2,
        },
        {
            "traceName": "implement",
            "providedModelName": "opus",
            "sum_totalCost": 2.0,
            "count_count": 3,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["name"] == "implement"
    assert result[0]["backend"] == "claude-sdk"
    assert result[0]["cost"] == 3.0
    assert result[0]["count"] == 5


async def test_agent_usage_splits_stage_across_backends(
    respx_mock: respx.MockRouter,
) -> None:
    """One stage using models from two backends yields TWO rows."""
    c = _client()
    rows = [
        {
            "traceName": "implement",
            "providedModelName": "deepseek/deepseek-v4",
            "sum_totalCost": 3.0,
            "count_count": 1,
        },
        {
            "traceName": "implement",
            "providedModelName": "opus",
            "sum_totalCost": 2.0,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 2
    backends = {(r["name"], r["backend"]): r["cost"] for r in result}
    assert backends[("implement", "openrouter")] == 3.0
    assert backends[("implement", "claude-sdk")] == 2.0


async def test_agent_usage_skips_missing_model_name(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows with no model are skipped (they carry no cost)."""
    c = _client()
    rows = [
        {
            "traceName": "implement",
            "providedModelName": None,
            "sum_totalCost": 5.0,
            "count_count": 1,
        },
        {
            "traceName": "implement",
            "providedModelName": "opus",
            "sum_totalCost": 1.0,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["backend"] == "claude-sdk"
    assert result[0]["cost"] == 1.0


async def test_agent_usage_skips_missing_trace_name(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows with no trace name are skipped."""
    c = _client()
    rows = [
        {
            "traceName": None,
            "providedModelName": "opus",
            "sum_totalCost": 9.0,
            "count_count": 1,
        },
        {
            "traceName": "review",
            "providedModelName": "haiku",
            "sum_totalCost": 0.5,
            "count_count": 1,
        },
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["name"] == "review"


async def test_agent_usage_handles_missing_metric_fields(
    respx_mock: respx.MockRouter,
) -> None:
    """Rows with missing metric fields default to 0."""
    c = _client()
    rows = [
        {"traceName": "audit", "providedModelName": "haiku"},
    ]
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": rows}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0
    assert result[0]["count"] == 0


async def test_agent_usage_empty(respx_mock: respx.MockRouter) -> None:
    c = _client()
    respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    result = await c.fetch_agent_usage_window(hours=24)
    assert result == []


async def test_agent_uses_custom_dimensions(respx_mock: respx.MockRouter) -> None:
    """Verify fetch_agent_usage_window asks for traceName + providedModelName."""
    c = _client()
    route = respx_mock.get("http://localhost/api/public/metrics").respond(
        200, json={"data": []}
    )
    await c.fetch_agent_usage_window(hours=24)
    assert route.called
    query = json.loads(route.calls[0].request.url.params["query"])
    assert query["dimensions"] == [
        {"field": "traceName"},
        {"field": "providedModelName"},
    ]
    assert query["metrics"] == [
        {"measure": "totalCost", "aggregation": "sum"},
        {"measure": "count", "aggregation": "count"},
    ]
    assert "timeDimension" not in query
