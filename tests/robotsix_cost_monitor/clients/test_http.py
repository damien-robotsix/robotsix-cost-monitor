"""Tests for the RetryClient (typed httpx wrapper with jittered backoff)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from robotsix_cost_monitor.clients._http import MAX_RETRIES, RetryClient
from robotsix_cost_monitor.exceptions import (
    ExternalAuthError,
    ExternalServiceError,
)


def _mock_response(status_code: int, text: str = "") -> httpx.Response:
    """Build a minimal httpx.Response for testing."""
    resp = httpx.Response(status_code=status_code)
    # Inject a text attribute (not writable on Response directly — patch _content).
    if text:
        resp._content = text.encode()  # noqa: SLF001
    return resp


class TestRetryClientSuccess:
    async def test_returns_response_on_2xx(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_ok = _mock_response(200, "ok")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_ok
            result = await client.get("http://example.com")
        assert result.status_code == 200
        mock_get.assert_awaited_once()

    async def test_returns_response_on_first_try(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_ok = _mock_response(200)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_ok
            result = await client.get("http://example.com")
        assert result.status_code == 200
        mock_get.assert_awaited_once()


class TestRetryClientTerminalErrors:
    async def test_401_raises_auth_error(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_401 = _mock_response(401, "unauthorized")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_401
            with pytest.raises(ExternalAuthError, match="401"):
                await client.get("http://example.com")
        mock_get.assert_awaited_once()

    async def test_403_raises_auth_error(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_403 = _mock_response(403, "forbidden")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_403
            with pytest.raises(ExternalAuthError, match="403"):
                await client.get("http://example.com")
        mock_get.assert_awaited_once()

    async def test_404_raises_service_error(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_404 = _mock_response(404, "not found")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_404
            with pytest.raises(ExternalServiceError, match="404"):
                await client.get("http://example.com")
        mock_get.assert_awaited_once()

    async def test_422_raises_service_error(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_422 = _mock_response(422, "unprocessable")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_422
            with pytest.raises(ExternalServiceError, match="422"):
                await client.get("http://example.com")
        mock_get.assert_awaited_once()


class TestRetryClientRetries:
    async def test_retries_503_then_succeeds(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_503 = _mock_response(503)
        resp_200 = _mock_response(200)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [resp_503, resp_200]
            result = await client.get("http://example.com")
        assert result.status_code == 200
        assert mock_get.await_count == 2

    async def test_retries_network_error_then_succeeds(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_200 = _mock_response(200)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                httpx.ConnectError("no route"),
                resp_200,
            ]
            result = await client.get("http://example.com")
        assert result.status_code == 200
        assert mock_get.await_count == 2

    async def test_exhausts_retries_on_503(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_503 = _mock_response(503, "unavailable")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_503
            with pytest.raises(ExternalServiceError, match="503"):
                await client.get("http://example.com")
        assert mock_get.await_count == 4  # MAX_RETRIES + 1

    async def test_exhausts_retries_on_network_errors(self) -> None:
        client = RetryClient(timeout=1.0)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(ExternalServiceError, match="TimeoutException"):
                await client.get("http://example.com")
        assert mock_get.await_count == 4  # MAX_RETRIES + 1

    async def test_respects_retry_after_header(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_429 = _mock_response(429)
        resp_429.headers["Retry-After"] = "0.05"
        resp_200 = _mock_response(200)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [resp_429, resp_200]
            result = await client.get("http://example.com")
        assert result.status_code == 200
        assert mock_get.await_count == 2


class TestAttemptGet:
    """Edge-case coverage for ``_attempt_get`` helper."""

    async def test_returns_resp_none_on_success(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_200 = _mock_response(200, "ok")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_200
            resp, exc = await client._attempt_get("http://x", {}, 0)
        assert resp is not None
        assert resp.status_code == 200
        assert exc is None

    async def test_returns_resp_none_on_retryable_status(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_503 = _mock_response(503, "unavailable")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_503
            resp, exc = await client._attempt_get("http://x", {}, 0)
        assert resp is not None
        assert resp.status_code == 503
        assert exc is None

    async def test_returns_none_exc_on_network_error(self) -> None:
        client = RetryClient(timeout=1.0)
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("no route")
            resp, exc = await client._attempt_get("http://x", {}, 0)
        assert resp is None
        assert isinstance(exc, httpx.ConnectError)

    async def test_raises_auth_error_on_401(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_401 = _mock_response(401, "unauthorized")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_401
            with pytest.raises(ExternalAuthError, match="401"):
                await client._attempt_get("http://x", {}, 0)

    async def test_returns_resp_none_on_429_retryable(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_429 = _mock_response(429, "rate limited")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_429
            resp, exc = await client._attempt_get("http://x", {}, 0)
        assert resp is not None
        assert resp.status_code == 429
        assert exc is None

    async def test_raises_service_error_on_404(self) -> None:
        client = RetryClient(timeout=1.0)
        resp_404 = _mock_response(404, "not found")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = resp_404
            with pytest.raises(ExternalServiceError, match="404"):
                await client._attempt_get("http://x", {}, 0)


class TestRaiseOnExhaustion:
    """Edge-case coverage for ``_raise_on_exhaustion`` helper."""

    def test_with_response(self) -> None:
        client = RetryClient(timeout=1.0)
        resp = _mock_response(503, "unavailable")
        with pytest.raises(ExternalServiceError, match="503"):
            client._raise_on_exhaustion(resp, "http://x")

    def test_with_exception(self) -> None:
        client = RetryClient(timeout=1.0)
        exc = httpx.TimeoutException("timed out")
        with pytest.raises(ExternalServiceError, match="TimeoutException"):
            client._raise_on_exhaustion(exc, "http://x")

    def test_with_none(self) -> None:
        client = RetryClient(timeout=1.0)
        with pytest.raises(
            ExternalServiceError,
            match=f"GET http://x failed after {MAX_RETRIES} retries",
        ):
            client._raise_on_exhaustion(None, "http://x")
