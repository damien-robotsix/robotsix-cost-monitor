"""Typed httpx client wrapper with retry/backoff for cost-monitor."""

from __future__ import annotations

import asyncio
import random
from typing import Any, NoReturn

import httpx
import structlog

from ..exceptions import (
    ExternalAuthError,
    ExternalRateLimitError,
    ExternalServiceError,
)

RETRYABLE_STATUSES = {429, 500, 502, 503, 504, 408}
MAX_RETRIES = 3
BASE_DELAY = 1.0

logger = structlog.get_logger(__name__)


class RetryClient:
    """An ``httpx.AsyncClient`` wrapper with jittered exponential backoff.

    Retries on:
    - 429 (rate limit), 500, 502, 503, 504 (server errors), 408 (timeout)
    - httpx network-level errors (ConnectError, TimeoutException, etc.)
    - Respects ``Retry-After`` headers on 429/503

    Never retries: 401, 403, 404, 422, or any 2xx.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def _should_retry(
        self, resp: httpx.Response | None, exc: Exception | None
    ) -> bool:
        if exc is not None:
            return isinstance(
                exc,
                (
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    httpx.RemoteProtocolError,
                    httpx.ReadError,
                ),
            )
        if resp is None:
            return False
        return resp.status_code in RETRYABLE_STATUSES

    async def _get_retry_delay(
        self, attempt: int, resp: httpx.Response | None
    ) -> float:
        """Jittered exponential backoff respecting Retry-After."""
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    return max(0.0, float(str(retry_after)))
                except ValueError, TypeError:
                    pass
        delay = BASE_DELAY * (2**attempt)
        jitter = random.uniform(0.8, 1.0)  # noqa: S311 — jitter, not crypto
        return float(delay * jitter)

    async def _attempt_get(
        self, url: str, kwargs: dict[str, Any], attempt: int
    ) -> tuple[httpx.Response | None, Exception | None]:
        """Make a single GET attempt.

        Returns ``(resp, None)`` on retryable outcomes (success or retryable
        HTTP error) and ``(None, exc)`` on retryable network errors.

        Raises immediately on terminal HTTP errors (auth, rate-limit,
        non-retryable status).
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, **kwargs)
                if resp.is_success:
                    return (resp, None)
                if await self._should_retry(resp, None):
                    return (resp, None)
                # Terminal HTTP error — classify
                if resp.status_code in (401, 403):
                    raise ExternalAuthError(
                        f"{resp.status_code} on {url}: {resp.text[:200]}"
                    )
                if resp.status_code == 429:
                    raise ExternalRateLimitError(f"429 on {url}: {resp.text[:200]}")
                raise ExternalServiceError(
                    f"{resp.status_code} on {url}: {resp.text[:200]}",
                    status_code=502,
                )
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as exc:
            return (None, exc)

    def _raise_on_exhaustion(
        self,
        last_resp_or_exc: httpx.Response | Exception | None,
        url: str,
    ) -> NoReturn:
        """Raise the appropriate error after all retries are exhausted."""
        if isinstance(last_resp_or_exc, httpx.Response):
            raise ExternalServiceError(
                f"{last_resp_or_exc.status_code} on {url} after {MAX_RETRIES} retries: "
                f"{last_resp_or_exc.text[:200]}",
                status_code=502,
            )
        if isinstance(last_resp_or_exc, Exception):
            raise ExternalServiceError(
                f"{type(last_resp_or_exc).__name__} after {MAX_RETRIES} retries: "
                f"{last_resp_or_exc}"
            ) from last_resp_or_exc
        raise ExternalServiceError(f"GET {url} failed after {MAX_RETRIES} retries")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET with retry/backoff. Raises typed exceptions on terminal errors."""
        last_resp_or_exc: httpx.Response | Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            resp, exc = await self._attempt_get(url, kwargs, attempt)
            if resp is not None and resp.is_success:
                return resp
            last_resp_or_exc = resp if resp is not None else exc
            if attempt == MAX_RETRIES:
                break
            delay = await self._get_retry_delay(attempt, resp)
            if exc is not None:
                logger.debug(
                    "retry attempt %d/%d for %s after %.1fs (%s)",
                    attempt + 1,
                    MAX_RETRIES,
                    url,
                    delay,
                    type(exc).__name__,
                )
            else:
                logger.debug(
                    "retry attempt %d/%d for %s after %.1fs",
                    attempt + 1,
                    MAX_RETRIES,
                    url,
                    delay,
                )
            await asyncio.sleep(delay)
        self._raise_on_exhaustion(last_resp_or_exc, url)
