"""Unit tests for LangfuseClient (no network).

Covers __init__, _get error paths, pagination, metrics query construction,
and the derived aggregation methods.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import HTTPStatusError, Request, Response

from robotsix_cost_monitor.langfuse import (
    _MAX_PAGES,
    _PAGE_LIMIT,
    LangfuseClient,
)

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


def _response(status: int = 200, json_data: object = None) -> Response:
    """Return an httpx Response for use as a mock return value."""
    req = Request("GET", "http://localhost/")
    resp = Response(status, json=json_data, request=req)
    return resp


def _error_response(status: int) -> Response:
    """Return an error response that raises HTTPStatusError on raise_for_status."""
    req = Request("GET", "http://localhost/")
    return Response(status, json={"error": "boom"}, request=req)


def _async_client_mock(get_response: object = None) -> AsyncMock:
    """Create an AsyncMock that works with ``async with httpx.AsyncClient(...)``.

    Sets ``__aenter__`` to return self so the context variable is the mock,
    not a coroutine.  The ``get`` method returns *get_response* by default;
    callers can override with ``side_effect`` afterwards.
    """
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_composes_langfuse_read_client() -> None:
    c = _client(public_key="pk-a", secret_key="sk-a")
    assert c._lf._public_key == "pk-a"  # type: ignore[attr-defined]
    assert c._lf._secret_key == "sk-a"  # type: ignore[attr-defined]


def test_init_strips_trailing_slash_from_base_url() -> None:
    c = LangfuseClient(
        public_key="pk", secret_key="sk", base_url="http://example.com/api//"
    )
    assert c._lf.base_url == "http://example.com/api"  # type: ignore[attr-defined]


def test_init_uses_default_timeout() -> None:
    c = _client()
    assert c._timeout == 30.0  # type: ignore[attr-defined]


def test_init_custom_timeout() -> None:
    c = _client(timeout=10.0)
    assert c._timeout == 10.0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _get — success
# ---------------------------------------------------------------------------


async def test_get_returns_json() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": [{"id": "tr-1"}]}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c._get("/api/public/traces", {"limit": 1})
    assert result == {"data": [{"id": "tr-1"}]}


async def test_get_passes_auth_and_params() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c._get("/api/public/traces", {"page": 2})
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args.kwargs
    assert call_kwargs["headers"] == {"Authorization": "Basic cGstdGVzdDpzay10ZXN0"}
    assert call_kwargs["params"] == {"page": 2}


# ---------------------------------------------------------------------------
# _get — error paths
# ---------------------------------------------------------------------------


async def test_get_raises_on_http_4xx() -> None:
    c = _client()
    mock_client = _async_client_mock(_error_response(400))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(HTTPStatusError):
            await c._get("/api/public/traces", {})


async def test_get_raises_on_http_5xx() -> None:
    c = _client()
    mock_client = _async_client_mock(_error_response(503))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(HTTPStatusError):
            await c._get("/api/public/traces", {})


async def test_get_raises_on_malformed_json() -> None:
    c = _client()
    req = Request("GET", "http://localhost/")
    bad_response = Response(200, content=b"not json", request=req)
    mock_client = _async_client_mock(bad_response)
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(JSONDecodeError):
            await c._get("/api/public/traces", {})


# ---------------------------------------------------------------------------
# fetch_traces_window — pagination
# ---------------------------------------------------------------------------


async def test_fetch_traces_single_page() -> None:
    c = _client()
    batch = [{"id": "t1"}, {"id": "t2"}]
    mock_client = _async_client_mock(
        _response(200, {"data": batch, "meta": {"totalPages": 1}})
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == 2
    assert result == batch


async def test_fetch_traces_multi_page() -> None:
    c = _client()
    page1 = [{"id": f"t{i}"} for i in range(_PAGE_LIMIT)]
    page2 = [{"id": f"t{i}"} for i in range(_PAGE_LIMIT, 2 * _PAGE_LIMIT)]

    mock_client = _async_client_mock()
    mock_client.get = AsyncMock(
        side_effect=[
            _response(200, {"data": page1, "meta": {"totalPages": 2}}),
            _response(200, {"data": page2, "meta": {"totalPages": 2}}),
        ]
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == 2 * _PAGE_LIMIT
    assert mock_client.get.call_count == 2


async def test_fetch_traces_total_pages_none_continues_until_empty() -> None:
    """When meta.totalPages is None, pagination continues until empty batch."""
    c = _client()
    batch1 = [{"id": f"t{i}"} for i in range(_PAGE_LIMIT)]
    empty: list[dict[str, Any]] = []

    mock_client = _async_client_mock()
    mock_client.get = AsyncMock(
        side_effect=[
            _response(200, {"data": batch1, "meta": {}}),  # no totalPages
            _response(200, {"data": empty, "meta": {}}),
        ]
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == _PAGE_LIMIT
    assert mock_client.get.call_count == 2


async def test_fetch_traces_stops_at_partial_page() -> None:
    """When a page has fewer than _PAGE_LIMIT items, stop (no more data)."""
    c = _client()
    partial_batch = [{"id": "t1"}]  # < _PAGE_LIMIT

    mock_client = _async_client_mock(
        _response(200, {"data": partial_batch, "meta": {}})
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == 1
    assert mock_client.get.call_count == 1


async def test_fetch_traces_stops_before_page_cap() -> None:
    """Stops when page >= totalPages even if batches are full."""
    c = _client()
    full_batch = [{"id": f"t{i}"} for i in range(_PAGE_LIMIT)]

    mock_client = _async_client_mock()
    mock_client.get = AsyncMock(
        side_effect=[
            _response(200, {"data": full_batch, "meta": {"totalPages": 2}}),
            _response(200, {"data": full_batch, "meta": {"totalPages": 2}}),
        ]
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == 2 * _PAGE_LIMIT
    assert mock_client.get.call_count == 2


async def test_fetch_traces_empty_response() -> None:
    c = _client()
    mock_client = _async_client_mock(
        _response(200, {"data": [], "meta": {"totalPages": 0}})
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert result == []


async def test_fetch_traces_respects_page_cap() -> None:
    """If the API never returns totalPages and always returns full pages,
    we stop at _MAX_PAGES to avoid runaway pagination."""
    c = _client()
    full_batch = [{"id": f"t{i}"} for i in range(_PAGE_LIMIT)]

    side_effect = [
        _response(200, {"data": full_batch, "meta": {}}) for _ in range(_MAX_PAGES + 5)
    ]
    mock_client = _async_client_mock()
    mock_client.get = AsyncMock(side_effect=side_effect)
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_traces_window(hours=24)
    assert len(result) == _MAX_PAGES * _PAGE_LIMIT
    assert mock_client.get.call_count == _MAX_PAGES


# ---------------------------------------------------------------------------
# fetch_trace_detail
# ---------------------------------------------------------------------------


async def test_fetch_trace_detail() -> None:
    c = _client()
    detail = {"id": "tr-99", "name": "implement", "observations": []}
    mock_client = _async_client_mock(_response(200, detail))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_trace_detail("tr-99")
    assert result == detail
    mock_client.get.assert_called_once()
    url = mock_client.get.call_args.args[0]
    assert "/api/public/traces/tr-99" in url


# ---------------------------------------------------------------------------
# _metrics — query construction
# ---------------------------------------------------------------------------


async def test_metrics_basic_query() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": [{"sum_totalCost": 1.5}]}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c._metrics(
            24,
            metrics=[{"measure": "totalCost", "aggregation": "sum"}],
        )
    assert result == [{"sum_totalCost": 1.5}]
    call_kwargs = mock_client.get.call_args.kwargs
    assert "query" in call_kwargs["params"]
    query = json.loads(call_kwargs["params"]["query"])
    assert query["view"] == "observations"
    assert query["metrics"] == [{"measure": "totalCost", "aggregation": "sum"}]
    assert query["dimensions"] == [{"field": "providedModelName"}]
    assert "fromTimestamp" in query
    assert "toTimestamp" in query


async def test_metrics_with_time_dimension() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c._metrics(
            48,
            metrics=[{"measure": "totalCost", "aggregation": "sum"}],
            time_dimension={"granularity": "hour"},
        )
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_metrics_without_time_dimension() -> None:
    """When time_dimension is None, it should NOT be in the query."""
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c._metrics(
            12,
            metrics=[{"measure": "count", "aggregation": "count"}],
        )
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert "timeDimension" not in query


async def test_metrics_multiple_metrics() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
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
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert len(query["metrics"]) == 5


async def test_metrics_empty_data_returns_empty_list() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {}))  # no 'data' key
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c._metrics(
            24,
            metrics=[{"measure": "totalCost", "aggregation": "sum"}],
        )
    assert result == []


# ---------------------------------------------------------------------------
# fetch_model_usage_window
# ---------------------------------------------------------------------------


async def test_model_usage_basic_aggregation() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
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


async def test_model_usage_merges_same_model_across_rows() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 3.0
    assert result[0]["input_tokens"] == 150
    assert result[0]["observations"] == 5


async def test_model_usage_skips_missing_model_name() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["model"] == "opus"


async def test_model_usage_handles_missing_fields() -> None:
    """Rows with missing metric fields default to 0."""
    c = _client()
    rows = [
        {"providedModelName": "opus"},  # no metric fields
    ]
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0
    assert result[0]["input_tokens"] == 0
    assert result[0]["output_tokens"] == 0
    assert result[0]["total_tokens"] == 0
    assert result[0]["observations"] == 0


async def test_model_usage_handles_null_metrics() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_model_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0


# ---------------------------------------------------------------------------
# fetch_cost_by_backend
# ---------------------------------------------------------------------------


async def test_cost_by_backend_groups_by_backend() -> None:
    c = _client()
    rows = [
        {"providedModelName": "openai/gpt-4", "sum_totalCost": 3.0},
        {"providedModelName": "anthropic/claude-3", "sum_totalCost": 2.0},
        {"providedModelName": "opus", "sum_totalCost": 1.0},
    ]
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"openrouter": 5.0, "claude-sdk": 1.0}


async def test_cost_by_backend_skips_nameless_observations() -> None:
    c = _client()
    rows = [
        {"providedModelName": "opus", "sum_totalCost": 1.0},
        {"providedModelName": None, "sum_totalCost": 99.0},
    ]
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"claude-sdk": 1.0}


async def test_cost_by_backend_empty() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_cost_by_backend(hours=24)
    assert result == {}


async def test_cost_by_backend_handles_null_cost() -> None:
    c = _client()
    rows = [
        {"providedModelName": "opus", "sum_totalCost": None},
    ]
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_cost_by_backend(hours=24)
    assert result == {"claude-sdk": 0.0}


# ---------------------------------------------------------------------------
# fetch_backend_cost_window — granularity selection
# ---------------------------------------------------------------------------


async def test_backend_cost_window_minute_granularity() -> None:
    """hours <= 1 → 'minute' granularity."""
    c = _client()
    mock_client = _async_client_mock(
        _response(
            200,
            {
                "data": [
                    {
                        "providedModelName": "opus",
                        "time_dimension": "2026-01-01T12:00:00Z",
                        "sum_totalCost": 1.0,
                    }
                ]
            },
        )
    )
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c.fetch_backend_cost_window(hours=1)
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["timeDimension"] == {"granularity": "minute"}


async def test_backend_cost_window_hour_granularity() -> None:
    """1 < hours <= 72 → 'hour' granularity."""
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c.fetch_backend_cost_window(hours=24)
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_backend_cost_window_hour_granularity_boundary() -> None:
    """hours=72 → 'hour' granularity (<= 72)."""
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c.fetch_backend_cost_window(hours=72)
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["timeDimension"] == {"granularity": "hour"}


async def test_backend_cost_window_day_granularity() -> None:
    """hours > 72 → 'day' granularity."""
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c.fetch_backend_cost_window(hours=168)
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["timeDimension"] == {"granularity": "day"}


# ---------------------------------------------------------------------------
# fetch_backend_cost_window — data folding
# ---------------------------------------------------------------------------


async def test_backend_cost_window_folds_by_bucket() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_backend_cost_window(hours=24)
    assert set(result.keys()) == {"2026-01-01T12:00:00Z", "2026-01-01T13:00:00Z"}
    bucket_12 = result["2026-01-01T12:00:00Z"]
    assert bucket_12 == {"claude-sdk": 2.5}
    bucket_13 = result["2026-01-01T13:00:00Z"]
    assert bucket_13 == {"openrouter": 3.0}


async def test_backend_cost_window_skips_nameless() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_backend_cost_window(hours=24)
    assert result == {"2026-01-01T12:00:00Z": {"claude-sdk": 1.0}}


async def test_backend_cost_window_empty() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_backend_cost_window(hours=24)
    assert result == {}


# ---------------------------------------------------------------------------
# fetch_agent_usage_window
# ---------------------------------------------------------------------------


async def test_agent_usage_basic_aggregation() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
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


async def test_agent_usage_merges_same_stage_backend() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["name"] == "implement"
    assert result[0]["backend"] == "claude-sdk"
    assert result[0]["cost"] == 3.0
    assert result[0]["count"] == 5


async def test_agent_usage_splits_stage_across_backends() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 2
    backends = {(r["name"], r["backend"]): r["cost"] for r in result}
    assert backends[("implement", "openrouter")] == 3.0
    assert backends[("implement", "claude-sdk")] == 2.0


async def test_agent_usage_skips_missing_model_name() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["backend"] == "claude-sdk"
    assert result[0]["cost"] == 1.0


async def test_agent_usage_skips_missing_trace_name() -> None:
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
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["name"] == "review"


async def test_agent_usage_handles_missing_metric_fields() -> None:
    """Rows with missing metric fields default to 0."""
    c = _client()
    rows = [
        {"traceName": "audit", "providedModelName": "haiku"},
    ]
    mock_client = _async_client_mock(_response(200, {"data": rows}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert len(result) == 1
    assert result[0]["cost"] == 0.0
    assert result[0]["count"] == 0


async def test_agent_usage_empty() -> None:
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await c.fetch_agent_usage_window(hours=24)
    assert result == []


async def test_agent_uses_custom_dimensions() -> None:
    """Verify fetch_agent_usage_window asks for traceName + providedModelName."""
    c = _client()
    mock_client = _async_client_mock(_response(200, {"data": []}))
    with patch(
        "robotsix_cost_monitor.langfuse.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await c.fetch_agent_usage_window(hours=24)
    call_kwargs = mock_client.get.call_args.kwargs
    query = json.loads(call_kwargs["params"]["query"])
    assert query["dimensions"] == [
        {"field": "traceName"},
        {"field": "providedModelName"},
    ]
    assert query["metrics"] == [
        {"measure": "totalCost", "aggregation": "sum"},
        {"measure": "count", "aggregation": "count"},
    ]
    assert "timeDimension" not in query
