"""Tests for robotsix-http RetryClient used in cost-monitor.

Verifies that the shared ``RetryClient`` raises typed exceptions compatible
with cost-monitor's existing catch-blocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from robotsix_http import (
    ExternalAuthError,
    ExternalRateLimitError,
    ExternalServiceError,
    RetryClient,
    RetryConfig,
)


def _mock_response(status_code: int, text: str = "") -> httpx.Response:
    """Build a minimal httpx.Response for testing."""
    resp = httpx.Response(status_code=status_code)
    if text:
        resp._content = text.encode()  # noqa: SLF001
    # robotsix-http RetryClient calls response.raise_for_status() which
    # requires _request to be set on the response.
    resp._request = MagicMock()  # noqa: SLF001
    return resp


def _mock_client() -> MagicMock:
    """Return a MagicMock that can be passed as ``httpx.AsyncClient``."""
    return MagicMock(spec=httpx.AsyncClient)


class TestRetryClientSuccess:
    async def test_returns_response_on_2xx(self) -> None:
        http_client = _mock_client()
        http_client.request = AsyncMock(return_value=_mock_response(200, "ok"))
        client = RetryClient(http_client)
        result = await client.get("http://example.com")
        assert result.status_code == 200
        http_client.request.assert_awaited_once()

    async def test_returns_response_on_first_try(self) -> None:
        http_client = _mock_client()
        http_client.request = AsyncMock(return_value=_mock_response(200))
        client = RetryClient(http_client)
        result = await client.get("http://example.com")
        assert result.status_code == 200
        http_client.request.assert_awaited_once()


class TestRetryClientTerminalErrors:
    async def test_401_raises_auth_error(self) -> None:
        http_client = _mock_client()
        resp_401 = _mock_response(401, "unauthorized")
        http_client.request = AsyncMock(return_value=resp_401)
        client = RetryClient(http_client)
        with pytest.raises(ExternalAuthError, match="401"):
            await client.get("http://example.com")
        http_client.request.assert_awaited_once()

    async def test_403_raises_auth_error(self) -> None:
        http_client = _mock_client()
        resp_403 = _mock_response(403, "forbidden")
        http_client.request = AsyncMock(return_value=resp_403)
        client = RetryClient(http_client)
        with pytest.raises(ExternalAuthError, match="403"):
            await client.get("http://example.com")
        http_client.request.assert_awaited_once()

    async def test_404_raises_http_status_error(self) -> None:
        http_client = _mock_client()
        resp_404 = _mock_response(404, "not found")
        http_client.request = AsyncMock(return_value=resp_404)
        client = RetryClient(http_client)
        with pytest.raises(httpx.HTTPStatusError, match="404"):
            await client.get("http://example.com")
        http_client.request.assert_awaited_once()

    async def test_422_raises_http_status_error(self) -> None:
        http_client = _mock_client()
        resp_422 = _mock_response(422, "unprocessable")
        http_client.request = AsyncMock(return_value=resp_422)
        client = RetryClient(http_client)
        with pytest.raises(httpx.HTTPStatusError, match="422"):
            await client.get("http://example.com")
        http_client.request.assert_awaited_once()


class TestRetryClientRetries:
    async def test_retries_503_then_succeeds(self) -> None:
        http_client = _mock_client()
        resp_503 = _mock_response(503)
        resp_200 = _mock_response(200)
        http_client.request = AsyncMock(side_effect=[resp_503, resp_200])
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=3, jitter_factor=0.0)
        )
        result = await client.get("http://example.com")
        assert result.status_code == 200
        assert http_client.request.await_count == 2

    async def test_retries_network_error_then_succeeds(self) -> None:
        http_client = _mock_client()
        resp_200 = _mock_response(200)
        http_client.request = AsyncMock(
            side_effect=[httpx.ConnectError("no route"), resp_200]
        )
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=3, jitter_factor=0.0)
        )
        result = await client.get("http://example.com")
        assert result.status_code == 200
        assert http_client.request.await_count == 2

    async def test_exhausts_retries_on_503(self) -> None:
        http_client = _mock_client()
        resp_503 = _mock_response(503, "unavailable")
        http_client.request = AsyncMock(return_value=resp_503)
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=3, jitter_factor=0.0)
        )
        with pytest.raises(ExternalServiceError, match="503"):
            await client.get("http://example.com")
        assert http_client.request.await_count == 4  # max_retries + 1

    async def test_exhausts_retries_on_network_errors(self) -> None:
        http_client = _mock_client()
        http_client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=3, jitter_factor=0.0)
        )
        with pytest.raises(httpx.TimeoutException, match="timed out"):
            await client.get("http://example.com")
        assert http_client.request.await_count == 4  # max_retries + 1

    async def test_respects_retry_after_header(self) -> None:
        http_client = _mock_client()
        resp_429 = _mock_response(429)
        resp_429.headers["Retry-After"] = "0.05"
        resp_200 = _mock_response(200)
        http_client.request = AsyncMock(side_effect=[resp_429, resp_200])
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=3, jitter_factor=0.0)
        )
        result = await client.get("http://example.com")
        assert result.status_code == 200
        assert http_client.request.await_count == 2


class TestRetryClientRateLimitExhaustion:
    async def test_429_retries_then_exhausts(self) -> None:
        http_client = _mock_client()
        resp_429 = _mock_response(429, "rate limited")
        http_client.request = AsyncMock(return_value=resp_429)
        client = RetryClient(
            http_client, config=RetryConfig(max_retries=2, jitter_factor=0.0)
        )
        with pytest.raises(ExternalRateLimitError, match="429"):
            await client.get("http://example.com")
        assert http_client.request.await_count == 3  # max_retries + 1
