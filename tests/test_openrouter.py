"""Unit tests for OpenRouterClient (no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import httpx

from robotsix_cost_monitor.openrouter import OpenRouterClient

# ---------------------------------------------------------------------------
# fetch_key_usage
# ---------------------------------------------------------------------------


async def test_fetch_key_usage_returns_usage():
    """Normal response: extract usage from data.usage."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={"data": {"usage": 3.14}})

    result = await client.fetch_key_usage()
    assert result == 3.14
    client._get.assert_called_once_with("/key")


async def test_fetch_key_usage_missing_data_key():
    """When 'data' key is absent, return 0.0."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={})

    result = await client.fetch_key_usage()
    assert result == 0.0


async def test_fetch_key_usage_missing_usage_field():
    """When 'usage' field is absent from data, return 0.0."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={"data": {}})

    result = await client.fetch_key_usage()
    assert result == 0.0


async def test_fetch_key_usage_data_is_none():
    """When data is None/null, return 0.0."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={})

    result = await client.fetch_key_usage()
    assert result == 0.0


async def test_fetch_key_usage_usage_is_none():
    """When usage is null, return 0.0 (float conversion of None → 0.0)."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={"data": {"usage": None}})

    result = await client.fetch_key_usage()
    assert result == 0.0


async def test_fetch_key_usage_http_error():
    """HTTP errors propagate as exceptions."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "unauthorized", request=Mock(), response=Mock(status_code=401)
        )
    )

    try:
        await client.fetch_key_usage()
        raise AssertionError("should have raised")
    except httpx.HTTPStatusError:
        pass


# ---------------------------------------------------------------------------
# fetch_credits
# ---------------------------------------------------------------------------


async def test_fetch_credits_returns_balance():
    """Normal response: extract total_credits, total_usage, remaining."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(
        return_value={"data": {"total_credits": 100.0, "total_usage": 42.5}}
    )

    result = await client.fetch_credits()
    assert result == {
        "total_credits": 100.0,
        "total_usage": 42.5,
        "remaining": 57.5,
    }


async def test_fetch_credits_missing_data_key():
    """When 'data' key is absent, return all zeros."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={})

    result = await client.fetch_credits()
    assert result == {
        "total_credits": 0.0,
        "total_usage": 0.0,
        "remaining": 0.0,
    }


async def test_fetch_credits_partial_data():
    """When some fields are missing, they default to 0.0."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(return_value={"data": {"total_credits": 50.0}})

    result = await client.fetch_credits()
    assert result == {
        "total_credits": 50.0,
        "total_usage": 0.0,
        "remaining": 50.0,
    }


async def test_fetch_credits_none_values():
    """When fields are null, they default to 0.0."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(
        return_value={"data": {"total_credits": None, "total_usage": None}}
    )

    result = await client.fetch_credits()
    assert result == {
        "total_credits": 0.0,
        "total_usage": 0.0,
        "remaining": 0.0,
    }


async def test_fetch_credits_http_error():
    """HTTP errors propagate as exceptions."""
    client = OpenRouterClient("sk-test")
    client._get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "unauthorized", request=Mock(), response=Mock(status_code=401)
        )
    )

    try:
        await client.fetch_credits()
        raise AssertionError("should have raised")
    except httpx.HTTPStatusError:
        pass
